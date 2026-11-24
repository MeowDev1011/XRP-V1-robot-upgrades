# =========================================================
# MANDO FISICO (GAMEPAD): TELEOPERACION + 5 ARMAS EN VIVO
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# La partida se juega con un GAMEPAD fisico (Logitech/Xbox)
# conectado a la computadora de operacion. Esa computadora
# envia ejes y botones al XRP por Bluetooth (protocolo XPP
# de XRPLib) a 50 Hz. En la placa: XRPLib.gamepad.
#   from XRPLib.gamepad import Gamepad
#   pad = Gamepad.get_default_gamepad()
#   pad.get_value(pad.Y1), pad.is_button_pressed(pad.START)
#
# ESTE MODULO NO ES UNA MACRO: es un lazo continuo de 50 Hz
# (uasyncio + ticks_ms, CERO sleep bloqueante) que en cada
# ciclo:
#   1. Lee los ejes Y1 (avance) y X1 (giro) del mando.
#   2. Aplica las CURVAS del Arma 3 a las palancas.
#   3. Elige modo de conduccion con transiciones limpias:
#        RECTO  = palanca de giro suelta -> Gyro-Lock PID
#                 (Arma 1) sostiene el rumbo capturado.
#        GIRO   = el piloto gira; el Arma 1 se retira.
#        PARADO = palancas sueltas -> frenado activo del
#                 Arma 4 (CLAVADO) + anti-trompo en parado.
#        RETORNO= endgame (A5) conduce a casa SOLO si el
#                 piloto suelta las palancas.
#   4. Todo esfuerzo sale por la cadena: Arma 2 (anti-atasco)
#      -> Arma 4 (rampa anti-derrape, DUEÑO de los motores).
#   Botones: START = armar reloj/odometria (A5). BACK = activa
#   o desactiva la asistencia de retorno del endgame.
#   Las palancas SIEMPRE contramandan: el piloto manda.
# =========================================================
import uasyncio as asyncio
import time
from XRPLib.defaults import imu
from XRPLib.gamepad import Gamepad
from arma1_gyro_lock import gyro_lock
from arma2_torque_boost import torque_boost
import arma3_curvas as curvas
from arma4_traccion import traction_brake
from arma5_endgame import arma5

# ------------------------------------------------------------
# CALIBRACION EN PISTA
# ------------------------------------------------------------
DT_MS       = 20     # periodo del lazo (50 Hz)
GIRO_MIN    = 0.08   # palanca de giro sobre esta curva = PILOTO gira
AV_MIN      = 0.02   # umbral de avance asistido
SLEW_PREC   = 1.8    # rampa de palanca en modo precision (BUMPER_L)
TRIM_UMBRAL = 0.12   # palanca cruda FILTRADA sobre esto: recorte de rumbo
TRIM_SAT    = 0.25   # palanca aqui o mas = recorte a maxima velocidad
                     # (0.25 es la palanca cruda que produce GIRO_MIN: sin
                     #  zona muerta entre el recorte y el giro del piloto)
TRIM_GRADOS_S = 60.0 # recorte maximo (grados/s)
TRIM_TAU    = 0.25   # filtro EMA de la palanca (s): anula el temblor del
                     # piloto kid (media cero) y deja pasar el empuje real
ASENTAR_MAX_MS = 600  # al salir de GIRO: tope de la fase de asentamiento
                     # (frenado activo del Arma 4 mientras muere el momento
                     # de diferencial; capturar el rumbo antes seria bloquear
                     # un objetivo que el momento todavia va a tirar 5-18
                     # grados)
ASENTAR_TASA = 45.0  # grados/s de velocidad de viraje por debajo de la cual
                     # el momento ya murio y se puede capturar el rumbo

PARADO, RECTO, GIRO, RETORNO = 0, 1, 2, 3
_NOMBRES = ("PARADO", "RECTO", "GIRO", "RETORNO")


def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


class Mando:
    """Consola del piloto: gamepad -> curvas -> armas -> motores."""

    def __init__(self):
        self.pad = None
        self._modo = PARADO
        self._task = None
        self._btn_prev = {}
        self._ema_x = 0.0
        self._asentar_hasta = 0
        self._yaw_prev = None
        self.n_partidas = 0

    # ---------------- configuracion ----------------
    def conectar(self, pad):
        self.pad = pad
        return self

    def nombre_modo(self):
        return _NOMBRES[self._modo]

    # ---------------- botones (con deteccion de flanco) ----------------
    def _borde(self, btn):
        act = bool(self.pad.is_button_pressed(btn))
        prev = self._btn_prev.get(btn, False)
        self._btn_prev[btn] = act
        return act and not prev

    # ---------------- mezcla arcade (convencion oficial XRPLib) ----------------
    @staticmethod
    def _arcade(v, g):
        """left = v - g, right = v + g, escalado para no recortar.
        Con marcha atras el giro se invierte (steer toward stick)."""
        if v == 0.0 and g == 0.0:
            return 0.0, 0.0
        if v < 0.0:
            g = -g
        s = max(abs(v), abs(g)) / (abs(v) + abs(g))
        return (v - g) * s, (v + g) * s

    # ---------------- UN ciclo de control (50 Hz) ----------------
    def _paso(self):
        if self.pad is None:
            return

        # botones de eventos
        if self._borde(self.pad.START):
            imu.reset_yaw()
            gyro_lock.set_target_here()
            arma5.iniciar_partida()
            self.n_partidas += 1
        if self._borde(self.pad.BACK):
            arma5.modo_retorno(not arma5.retorno_on)

        # curvas del Arma 3 sobre las palancas
        mix = curvas.MIX_PRECIS if self.pad.is_button_pressed(self.pad.BUMPER_L) else curvas.MIX
        slew = SLEW_PREC if self.pad.is_button_pressed(self.pad.BUMPER_L) else curvas.SLEW_DEF
        curvas.suav_avance.slew = slew
        curvas.suav_giro.slew = slew
        dt = DT_MS / 1000.0
        x_raw = self.pad.get_value(self.pad.X1)
        self._ema_x += (x_raw - self._ema_x) * (dt / TRIM_TAU)
        v = curvas.suav_avance.update(
            curvas.forma(self.pad.get_value(self.pad.Y1), mix), dt)
        g = curvas.suav_giro.update(
            curvas.forma(x_raw, mix), dt)

        # seleccion de modo (transiciones limpias, CON HISTERESIS:
        # salir de GIRO solo al bajar de la mitad del umbral evita el
        # aleteo GIRO/RECTO del temblor, que re-captura rumbo a cada
        # flanco y deja paneos residuales con la palanca ya quieta)
        if False:                      # TEST: histeresis desactivada
            en_giro = abs(g) > GIRO_MIN * 0.5
        else:
            en_giro = abs(g) > GIRO_MIN
        if en_giro:
            nuevo = GIRO
        elif abs(v) > AV_MIN:
            nuevo = RECTO
        elif arma5.is_endgame() and arma5.retorno_on:
            nuevo = RETORNO
        else:
            nuevo = PARADO
        if nuevo != self._modo:
            salio_giro = (self._modo == GIRO)
            self._modo = nuevo
            if nuevo in (RECTO, PARADO) and not salio_giro:
                # patron oficial: capturar el rumbo UNA vez al entrar
                gyro_lock.set_target_here()
                gyro_lock.enable()
            elif nuevo in (RECTO, PARADO) and salio_giro:
                # ASENTAMIENTO: el momento de diferencial de la curva sigue
                # girando al robot (encoders lo demuestran). NO capturar
                # todavía: orden cero -> Arma 4 frena activo y anula la
                # deriva; se captura cuando la tasa de viraje cae.
                self._asentar_hasta = time.ticks_add(time.ticks_ms(),
                                                     ASENTAR_MAX_MS)
                gyro_lock.disable()
            elif nuevo == GIRO:
                gyro_lock.disable()      # el piloto posee el giro
            elif nuevo == RETORNO:
                gyro_lock.enable()       # Arma 5 conduce (rumbo vivo)

        # tasa de viraje real (para soltar el asentamiento sin pausas fijas)
        ahora = time.ticks_ms()
        yaw = imu.get_yaw()
        if self._yaw_prev is None:
            self._yaw_prev = yaw
            tasa_viraje = 0.0
        else:
            tasa_viraje = abs(_wrap180(yaw - self._yaw_prev)) / (DT_MS / 1000.0)
            self._yaw_prev = yaw
        asentando = (time.ticks_diff(self._asentar_hasta, ahora) > 0 and
                     tasa_viraje > ASENTAR_TASA and self._modo != GIRO)

        # aplicacion por modo (SOLO Arma 4 escribe motores)
        if asentando:
            l, r = torque_boost.feed(0.0, 0.0)
            traction_brake.set_command(l, r)
        elif self._modo == GIRO:
            l, r = self._arcade(v, g)
            l, r = torque_boost.feed(l, r)
            traction_brake.set_command(l, r)
        elif self._modo == RECTO and not asentando:
            # fin del asentamiento: capturar el rumbo UNA vez (el momento ya
            # murio, el objetivo sera fiel al lugar donde el robot quedo)
            if not gyro_lock.enabled:
                gyro_lock.set_target_here()
                gyro_lock.enable()
            # AUTO-CORRECCION DEL PILOTO: el empuje pequeño y SOSTENIDO
            # (EMA ~0.25 s, el temblor de media cero no pasa) que la curva
            # deja bajo GIRO_MIN NO se ignora: panea el rumbo bloqueado de
            # forma asistida (el Arma 1 sigue estabilizando). Las palancas
            # grandes siguen siendo GIRO plano del piloto.
            ax = abs(self._ema_x)
            sigue_presionada = abs(x_raw) >= 0.5 * ax
            if TRIM_UMBRAL <= ax <= TRIM_SAT and sigue_presionada:
                fraccion = (ax - TRIM_UMBRAL) / (TRIM_SAT - TRIM_UMBRAL)
                fraccion = max(0.0, min(1.0, fraccion))
                recorte = TRIM_GRADOS_S * fraccion * dt
                gyro_lock.set_target(gyro_lock.get_target() +
                                     (recorte if self._ema_x > 0 else -recorte))
            gyro_lock.set_base(v, v)
        elif self._modo == PARADO:
            if not gyro_lock.enabled and not asentando:
                gyro_lock.set_target_here()
                gyro_lock.enable()
            gyro_lock.set_base(0.0, 0.0)
        elif self._modo == RETORNO:
            pass          # Arma 5 fija base y rumbo cada ciclo

    # ---------------- tarea 50 Hz no bloqueante ----------------
    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self

    async def _run(self):
        next_tick = time.ticks_ms()
        while True:
            next_tick = time.ticks_add(next_tick, DT_MS)
            self._paso()
            delay = time.ticks_diff(next_tick, time.ticks_ms())
            if delay <= 0:
                delay = 1
                next_tick = time.ticks_add(time.ticks_ms(), DT_MS)
            await asyncio.sleep_ms(delay)


piloto_mando = Mando()
