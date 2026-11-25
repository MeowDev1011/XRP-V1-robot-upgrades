# =========================================================
# WEAPON 4: ACTIVE BRAKING & ANTI-SLIP CONTROL
# (Traction & Brake Assist)
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# Two systems per axis:
#  1) ANTI-SLIP RAMP: effort rises/falls with a slope limit
#     (units/second). Starting from zero, effort grows only
#     as fast as RAMP_MAX allows (even softer right at the
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
RAMP_MAX       = 3.0    # effort per second (0 -> 0.5 in ~170 ms)
DT_MS           = 20
RPM_STOP_MIN   = 3.0    # below this rpm we are "stopped" -> brake()
PULSE_K         = 0.012  # strength of the inverse pulse per rpm of spin
PULSE_MAX       = 0.45   # ceiling of the inverse pulse
RPM_LAUNCH    = 5.0    # rpm below which the extra-soft ramp applies
KS              = 0.12   # factory model (same as Weapon 2)
KV              = 0.02
SLIP_MARGIN = 10.0   # rpm above expected = slip suspicion

FREE    = 0
BRAKING = 1
NAILED  = 2
_STATE_NAMES = ("FREE", "BRAKING", "NAILED")


class _Axis:
    """State machine of one axis: FREE / BRAKING / NAILED."""

    def __init__(self, motor):
        self.motor = motor
        self.e = 0.0
        self.estado = NAILED

    def step(self, cmd):
        real = self.motor.get_speed()

        if abs(cmd) > 1e-6:
            self.estado = FREE
            step = RAMP_MAX * (DT_MS / 1000.0)
            if abs(real) < RPM_LAUNCH:
                step *= 0.5            # start from rest: EXTRA soft
            diff = cmd - self.e
            esperado = (abs(cmd) - KS) / KV
            subiendo = abs(self.e) < abs(cmd)
            if subiendo and abs(real) > esperado + SLIP_MARGIN:
                pass                   # slip guard: freeze the ramp
            elif abs(diff) <= step:
                self.e = cmd
            else:
                self.e += step if diff > 0 else -step
            return self.e

        if abs(real) > RPM_STOP_MIN:
            self.estado = BRAKING
            sgn = 1.0 if real > 0 else -1.0
            self.e = -sgn * min(PULSE_MAX, PULSE_K * abs(real))
            return self.e

        self.estado = NAILED
        self.e = 0.0
        self.motor.brake()
        return 0.0


class TractionBrake:
    def __init__(self):
        self.enabled = False
        self._left = _Axis(left_motor)
        self._right = _Axis(right_motor)
        self._cmd_l = 0.0
        self._cmd_r = 0.0
        self._task = None

    # ---------------- observable state for telemetry ----------------
    @property
    def state_left(self):
        return _STATE_NAMES[self._left.estado]

    @property
    def state_right(self):
        return _STATE_NAMES[self._right.estado]

    @property
    def nailed(self):
        return self._left.estado == NAILED and self._right.estado == NAILED

    # ---------------- orders ----------------
    def set_command(self, left, right):
        self._cmd_l = left
        self._cmd_r = right

    def emergency_stop(self):
        self.set_command(0.0, 0.0)

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False
        self.set_command(0.0, 0.0)
        drivetrain.set_effort(0.0, 0.0)

    def step(self):
        """One control cycle. The _run() task calls it at 50 Hz;
        it also works for the virtual robot (manual step)."""
        if not self.enabled:
            return
        l = self._left.step(self._cmd_l)
        r = self._right.step(self._cmd_r)
        drivetrain.set_effort(l, r)

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self

    async def _run(self):
        next_tick = time.ticks_ms()
        while True:
            next_tick = time.ticks_add(next_tick, DT_MS)
            self.step()
            delay = time.ticks_diff(next_tick, time.ticks_ms())
            if delay <= 0:
                delay = 1
                next_tick = time.ticks_add(time.ticks_ms(), DT_MS)
            await asyncio.sleep_ms(delay)


traction_brake = TractionBrake()
