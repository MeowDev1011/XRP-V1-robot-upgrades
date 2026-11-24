# =========================================================
# ARMA 4: FRENADO ACTIVO Y CONTROL ANTI-DERRAPE
# (Traction & Brake Assist)
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# Dos sistemas por eje:
#  1) RAMPA ANTI-PATINAJE: el esfuerzo sube/baja con limite de
#     pendiente (unidades/seg). Al arrancar desde cero el
#     esfuerzo crece solo tan rapido como RAMPA_MAX permita
#     (mas suave aun justo en el arranque), y se congela si la
#     rueda gira mucho mas rapido que el modelo (derrape).
#  2) FRENADO ACTIVO: cuando la orden vuelve a cero con la
#     rueda girando, aplica un pulso INVERSO proporcional a la
#     velocidad medida (get_speed()) y, al caer la velocidad,
#     clava la rueda con motor.brake() (descubierto en el
#     fuente oficial: DualPWMMotor.brake energiza ambos
#     sentidos a la vez = posicion mantenida con motor vivo).
# ---------------------------------------------------------
# Este modulo es el DUENO de los motores cuando esta activo:
#   arma4.set_command(l, r)  <- el resto del sistema ordena aqui
#   arma4.start()            <- tarea 50 Hz que escribe los motores
# Cadena recomendada (ver README):
#   gyro_lock.attach(gancho)  con
#   gancho(l, r): l, r = torque_boost.feed(l, r); arma4.set_command(l, r)
# =========================================================
import uasyncio as asyncio
import time
from XRPLib.defaults import drivetrain, left_motor, right_motor

# ------------------------------------------------------------
# CALIBRACION EN PISTA
# ------------------------------------------------------------
RAMPA_MAX       = 3.0    # esfuerzo por segundo (0 -> 0.5 en ~170 ms)
DT_MS           = 20
RPM_FRENO_MIN   = 3.0    # bajo este rpm se considera detenido -> brake()
PULSO_K         = 0.012  # fuerza del pulso inverso por rpm de giro
PULSO_MAX       = 0.45   # techo del pulso inverso
RPM_ARRANQUE    = 5.0    # rpm por debajo de las cuales se rampa extra suave
KS              = 0.12   # modelo de fabrica (igual que el Arma 2)
KV              = 0.02
PATINAJE_MARGEN = 10.0   # rpm por encima de lo esperado = sospecha de derrape

LIBRE    = 0
FRENANDO = 1
CLAVADO  = 2
_NOMBRES_ESTADO = ("LIBRE", "FRENANDO", "CLAVADO")


class _Eje:
    """Maquina de estados de un eje: LIBRE / FRENANDO / CLAVADO."""

    def __init__(self, motor):
        self.motor = motor
        self.e = 0.0
        self.estado = CLAVADO

    def step(self, cmd):
        real = self.motor.get_speed()

        if abs(cmd) > 1e-6:
            self.estado = LIBRE
            paso = RAMPA_MAX * (DT_MS / 1000.0)
            if abs(real) < RPM_ARRANQUE:
                paso *= 0.5            # arranque desde parado: EXTRA suave
            diff = cmd - self.e
            esperado = (abs(cmd) - KS) / KV
            subiendo = abs(self.e) < abs(cmd)
            if subiendo and abs(real) > esperado + PATINAJE_MARGEN:
                pass                   # guardia de derrape: congelar rampa
            elif abs(diff) <= paso:
                self.e = cmd
            else:
                self.e += paso if diff > 0 else -paso
            return self.e

        if abs(real) > RPM_FRENO_MIN:
            self.estado = FRENANDO
            sgn = 1.0 if real > 0 else -1.0
            self.e = -sgn * min(PULSO_MAX, PULSO_K * abs(real))
            return self.e

        self.estado = CLAVADO
        self.e = 0.0
        self.motor.brake()
        return 0.0


class TractionBrake:
    def __init__(self):
        self.enabled = False
        self._izq = _Eje(left_motor)
        self._der = _Eje(right_motor)
        self._cmd_l = 0.0
        self._cmd_r = 0.0
        self._task = None

    # ---------------- estado observable para telemetria ----------------
    @property
    def estado_izq(self):
        return _NOMBRES_ESTADO[self._izq.estado]

    @property
    def estado_der(self):
        return _NOMBRES_ESTADO[self._der.estado]

    @property
    def clavado(self):
        return self._izq.estado == CLAVADO and self._der.estado == CLAVADO

    # ---------------- ordenes ----------------
    def set_command(self, left, right):
        self._cmd_l = left
        self._cmd_r = right

    def stop_inmediato(self):
        self.set_command(0.0, 0.0)

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False
        self.set_command(0.0, 0.0)
        drivetrain.set_effort(0.0, 0.0)

    def paso(self):
        """Un ciclo de control. La tarea _run() lo llama a 50 Hz;
        tambien sirve para el robot virtual (paso manual)."""
        if not self.enabled:
            return
        l = self._izq.step(self._cmd_l)
        r = self._der.step(self._cmd_r)
        drivetrain.set_effort(l, r)

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self

    async def _run(self):
        next_tick = time.ticks_ms()
        while True:
            next_tick = time.ticks_add(next_tick, DT_MS)
            self.paso()
            delay = time.ticks_diff(next_tick, time.ticks_ms())
            if delay <= 0:
                delay = 1
                next_tick = time.ticks_add(time.ticks_ms(), DT_MS)
            await asyncio.sleep_ms(delay)


traction_brake = TractionBrake()
