# =========================================================
# ARMA 5: GESTOR DE RELOJ Y ODOMETRIA DE CIERRE (AUTO-ENDGAME)
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# Partida = 150,000 ms exactos (ticks_ms, sin deriva).
# Odometria por fusion: distancia de encoders (posiciones del
# drivetrain, en cm) + rumbo de la IMU (get_yaw, integrada a
# 208 Hz por la propia libreria). Si la IMU cae, el rumbo se
# respalda con la diferencia de encoders (constantes de
# fabrica: ruedas 6 cm, track 15.5 cm).
# Endgame: a los ultimos ULTIMOS_MS activa alerta y, si se
# habilita el MODO RETORNO, conduce continuamente hacia la
# pose de inicio: NO es una macro, recalcula rumbo y velocidad
# cada ciclo (rumbo vivo) y cede ante obstaculos de frente.
# ---------------------------------------------------------
# Uso desde bloques XRPCode:
#   from arma5_endgame import arma5
#   arma5.conectar(gyro_lock)     # inyecta el Arma 1
#   arma5.start()                 # tarea 50 Hz en background
#   arma5.iniciar_partida()       # robot YA en zona de inicio
#   arma5.modo_retorno(True)      # activa asistencia de cierre
#   arma5.restante_s() / arma5.is_endgame() / arma5.pose()
# =========================================================
import uasyncio as asyncio
import time
import math
from XRPLib.defaults import drivetrain, imu, board, rangefinder

# ------------------------------------------------------------
# CALIBRACION EN PISTA
# ------------------------------------------------------------
PARTIDA_MS        = 150000   # 2:30 exactos
ULTIMOS_MS        = 12000    # duracion del finalgame: aviso y retorno
DT_MS             = 20
V_RETORNO         = 0.85     # esfuerzo base del retorno (calibrado: cubre
                             # casa a ~130 cm en los 12 s; 0.45 llega tarde)
K_LLEGADA_SUAVE   = 0.04     # por cm restante: reduce velocidad al acercarse
V_MIN_LLEGADA     = 0.18     # piso de velocidad para no morir antes de llegar
TOLERANCIA_CM     = 10.0     # "ya estamos en casa" (confirmar con manual:
                             # 'En Zona' real es una franja, no un punto de 6 cm)
PUNTO_CLAVAR_CM   = 8.0      # no soltar el retorno al ras de la tolerancia:
                             # apuntar 2 cm MAS ADENTRO para que el deslizamiento
                             # final deje al robot dentro de zona con margen
SEGURO_FINAL_MS  = 2000     # en los ultimos 2 s: si ya esta dentro de zona y
                             # todavia ordena avance, orden cero -> el Arma 4
                             # clave al robot pase lo que pase con la odometria
PIVOTE_GRADOS     = 45.0     # si casa queda a mas de este angulo: pivonar primero
DIST_SEGURIDAD_CM = 12.0     # obstaculo minimo de frente durante el retorno
TRACK_CM          = 15.5     # track de fabrica (respaldo sin IMU)
LED_HZ            = 4        # parpadeo del LED durante el endgame


def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


class Arma5:
    def __init__(self):
        self._t0 = None
        self._x = 0.0
        self._y = 0.0
        self._th = 0.0
        self._dic = [0.0, 0.0]
        self.con_imu = 0
        self._home_x = 0.0
        self._home_y = 0.0
        self.retorno_on = False
        self._alerta_dada = False
        self._en_casa = False
        self._gyro = None
        self._task = None

    # ---------------- configuracion ----------------
    def conectar(self, gyro_lock):
        """Inyecta el Arma 1, que ejecuta el retorno asistido."""
        self._gyro = gyro_lock

    def iniciar_partida(self):
        """Arranca el reloj y toma la pose ACTUAL como casa.
        Colocar el robot en la zona de inicio ANTES de llamar."""
        self._t0 = time.ticks_ms()
        self.con_imu = 1 if imu.is_connected() else 0
        self._dic = [drivetrain.get_left_encoder_position(),
                     drivetrain.get_right_encoder_position()]
        self._x = 0.0
        self._y = 0.0
        self._th = 0.0
        self._home_x = 0.0
        self._home_y = 0.0
        self._alerta_dada = False
        self._en_casa = False

    def hogar_aqui(self):
        """Recaptura la pose actual como casa (p. ej. tras recolocarlo)."""
        self._home_x = self._x
        self._home_y = self._y

    def modo_retorno(self, on):
        self.retorno_on = on

    # ---------------- consultas (todo O(1)) ----------------
    def ms_transcurridos(self):
        if self._t0 is None:
            return 0
        return max(0, time.ticks_diff(time.ticks_ms(), self._t0))

    def transcurrido_s(self):
        return self.ms_transcurridos() / 1000

    def ms_restantes(self):
        return max(0, PARTIDA_MS - self.ms_transcurridos())

    def restante_s(self):
        return self.ms_restantes() / 1000

    def is_endgame(self):
        return self.ms_restantes() <= ULTIMOS_MS

    def pose(self):
        return (self._x, self._y, math.degrees(self._th))

    def distancia_al_hogar(self):
        return math.sqrt((self._home_x - self._x) ** 2 +
                         (self._home_y - self._y) ** 2)

    # ---------------- tarea 50 Hz ----------------
    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self

    async def _run(self):
        next_tick = time.ticks_ms()
        while True:
            next_tick = time.ticks_add(next_tick, DT_MS)
            self._odometria()
            if self._t0 is not None:
                self._logica_endgame()
            delay = time.ticks_diff(next_tick, time.ticks_ms())
            if delay <= 0:
                delay = 1
                next_tick = time.ticks_add(time.ticks_ms(), DT_MS)
            await asyncio.sleep_ms(delay)

    def _odometria(self):
        dl = drivetrain.get_left_encoder_position() - self._dic[0]
        dr = drivetrain.get_right_encoder_position() - self._dic[1]
        self._dic[0] += dl
        self._dic[1] += dr
        d = (dl + dr) / 2.0
        if self.con_imu:
            self._th = math.radians(imu.get_yaw())
        elif abs(d) > 1e-9:
            self._th += (dr - dl) / TRACK_CM
        self._x += d * math.cos(self._th)
        self._y += d * math.sin(self._th)

    def _logica_endgame(self):
        if not self.is_endgame():
            return
        if not self._alerta_dada:
            self._alerta_dada = True
            try:
                board.led_blink(LED_HZ)
            except Exception:
                pass
        if not (self.retorno_on and self._gyro is not None and self._gyro.enabled):
            return
        dist = self.distancia_al_hogar()
        en_zona = dist <= TOLERANCIA_CM
        if en_zona and self.ms_restantes() <= SEGURO_FINAL_MS:
            # seguro de cierre: garantiza el CLAVADO aunque el crep del avance
            # minimo del avance siga moviendo al robot al silbatazo
            self._gyro.set_base(0.0, 0.0)
            self._en_casa = True
            return
        if dist <= PUNTO_CLAVAR_CM:
            if not self._en_casa:
                self._en_casa = True
                self._gyro.set_base(0.0, 0.0)
            return
        # rumbo VIVO: el objetivo se recalcula cada ciclo
        beta = math.atan2(self._home_y - self._y, self._home_x - self._x)
        err_rumbo = _wrap180(math.degrees(beta - self._th))
        self._gyro.set_target(math.degrees(beta))
        if abs(err_rumbo) > PIVOTE_GRADOS:
            # mirar primero a casa (pivote en el sitio: no se pierde distancia)
            self._gyro.set_base(0.0, 0.0)
            return
        v = V_RETORNO
        v_llegada = K_LLEGADA_SUAVE * dist
        if v_llegada < v:
            v = max(V_MIN_LLEGADA, v_llegada)
        try:
            if rangefinder.distance() < DIST_SEGURIDAD_CM:
                v = 0.0
        except Exception:
            pass
        self._gyro.set_base(v, v)


arma5 = Arma5()
