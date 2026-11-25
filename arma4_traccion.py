# =========================================================
# WEAPON 4: ACTIVE BRAKING & ANTI-SLIP CONTROL
# (Traction & Brake Assist)
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# Two systems per axis:
#  1) ANTI-SLIP RAMP: effort rises/falls with a slope limit
#     (units/second). Starting from zero, effort grows only
#     as fast as RAMPA_MAX allows (even softer right at the
#     start) and freezes if the wheel spins much faster than
#     the model expects (slip).
#  2) ACTIVE BRAKING: when the order returns to zero with the
#     wheel still spinning, applies an inverse PULSE
#     proportional to the measured speed (get_speed()) and,
#     once the speed drops, nails the wheel with motor.brake()
#     (discovered in the official source: DualPWMMotor.brake
#     energizes both directions at once = held position with
#     a live motor).
# ---------------------------------------------------------
# This module OWNS the motors when active:
#   arma4.set_command(l, r)  <- the rest of the system commands here
#   arma4.start()            <- 50 Hz task that writes the motors
# Recommended chain (see README):
#   gyro_lock.attach(hook)  with
#   hook(l, r): l, r = torque_boost.feed(l, r); arma4.set_command(l, r)
# =========================================================
import uasyncio as asyncio
import time
from XRPLib.defaults import drivetrain, left_motor, right_motor

# ------------------------------------------------------------
# ON-TRACK CALIBRATION
# ------------------------------------------------------------
RAMPA_MAX       = 3.0    # effort per second (0 -> 0.5 in ~170 ms)
DT_MS           = 20
RPM_FRENO_MIN   = 3.0    # below this rpm we are "stopped" -> brake()
PULSO_K         = 0.012  # strength of the inverse pulse per rpm of spin
PULSO_MAX       = 0.45   # ceiling of the inverse pulse
RPM_ARRANQUE    = 5.0    # rpm below which the extra-soft ramp applies
KS              = 0.12   # factory model (same as Weapon 2)
KV              = 0.02
PATINAJE_MARGEN = 10.0   # rpm above expected = slip suspicion

LIBRE    = 0
FRENANDO = 1
CLAVADO  = 2
_NOMBRES_ESTADO = ("LIBRE", "FRENANDO", "CLAVADO")


class _Eje:
    """State machine of one axis: LIBRE / FRENANDO / CLAVADO."""

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
                paso *= 0.5            # start from rest: EXTRA soft
            diff = cmd - self.e
            esperado = (abs(cmd) - KS) / KV
            subiendo = abs(self.e) < abs(cmd)
            if subiendo and abs(real) > esperado + PATINAJE_MARGEN:
                pass                   # slip guard: freeze the ramp
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

    # ---------------- observable state for telemetry ----------------
    @property
    def estado_izq(self):
        return _NOMBRES_ESTADO[self._izq.estado]

    @property
    def estado_der(self):
        return _NOMBRES_ESTADO[self._der.estado]

    @property
    def clavado(self):
        return self._izq.estado == CLAVADO and self._der.estado == CLAVADO

    # ---------------- orders ----------------
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
        """One control cycle. The _run() task calls it at 50 Hz;
        it also works for the virtual robot (manual step)."""
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
