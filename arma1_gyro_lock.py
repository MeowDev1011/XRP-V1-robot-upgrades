# =========================================================
# WEAPON 1: HEADING AUTOCORRECTOR & ANTI-SPIN (Gyro-Lock PID)
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# Closed-loop heading at 50 Hz against imu.get_yaw().
# Constants anchored to the XRPLib factory heading PID
# (differential_drive.py: kp=0.064, ki=0.12, kd=0.0055,
#  integral_zone=4, max_integral=3).
# ---------------------------------------------------------
# Usage from XRPCode blocks:
#   from arma1_gyro_lock import gyro_lock
#   gyro_lock.start()                 # once at boot
#   gyro_lock.engage_straight(0.5)    # straight with locked heading
#   gyro_lock.hold_pose()             # anti-spin while stopped
#   gyro_lock.disable()               # release control (free turn)
#   gyro_lock.set_target(ang)         # re-lock an absolute heading
# ---------------------------------------------------------
# Weapons chain (composition): gyro_lock.attach(fn) makes the
# final efforts pass through `fn(l, r)` before the motors.
# =========================================================
import uasyncio as asyncio
import time
from XRPLib.defaults import drivetrain, imu

# ------------------------------------------------------------
# ON-TRACK CALIBRATION  (one parameter at a time, in this order)
# ------------------------------------------------------------
KP        = 0.064   # [step 1] effort per degree of error. Oscillates -> lower 30-40%.
KI        = 0.06    # [step 3] constant drift. Only once KP/KD are stable.
KD        = 0.0055  # [step 2] damps spins and crashes. Raise if it bounces.
I_ZONE    = 4.0     # degrees: the integral only accumulates inside this band
MAX_I     = 0.3     # integral cap (factory uses 3, but with the ramp+motor
                    # delay that causes sustained hunting of +-4 degrees:
                    # battery-proven that MAX_I <= 0.3 kills the oscillation)
OUT_LIMIT = 0.5     # ceiling of the correction effort
DEADBAND  = 1.5     # deadband in degrees: avoids tremor with the robot still
MIN_EFFORT = 0.14   # factory: minimum effort for the wheel to turn
SIGN      = 1.0     # -1.0 if correcting pushes the robot FURTHER off
DT_MS     = 20      # loop period (50 Hz). The IMU integrates at 208 Hz.


def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


class PID:
    """Mirror of the XRPLib PID (integral zone + integral cap),
    with derivative on measurement to avoid the derivative spike
    when the setpoint changes."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.i = 0.0
        self.prev = None
        self.p = 0.0
        self.d = 0.0

    def update(self, error, dt):
        self.p = KP * error
        if abs(error) <= I_ZONE:
            self.i += error * dt
            self.i = max(-MAX_I, min(MAX_I, self.i))
        else:
            self.i = 0.0
        d = 0.0
        if self.prev is not None and dt > 0:
            d = -KD * (error - self.prev) / dt
        self.prev = error
        self.d = d
        return max(-OUT_LIMIT, min(OUT_LIMIT, self.p + KI * self.i + d))


class GyroLock:
    """Continuous heading lock. While active it OWNS the motors:
    never call drivetrain.straight()/turn()/set_speed() at the same time."""

    def __init__(self):
        self.pid = PID()
        self.enabled = False
        self.target = 0.0
        self.base_l = 0.0
        self.base_r = 0.0
        self.last_error = 0.0
        self.last_out = 0.0
        self._post = None
        self._task = None

    # ---------------- composition with other weapons ----------------
    def attach(self, fn):
        """fn(left, right) receives the corrected final efforts and
        applies them (for example, Weapon 2). Without a hook it writes directly."""
        self._post = fn

    # ---------------- API for XRPCode blocks ----------------
    def set_target_here(self):
        self.target = imu.get_yaw()
        self.pid.reset()
        return self.target

    def set_target(self, ang):
        self.target = _wrap180(ang)
        self.pid.reset()
        return self.target

    def get_target(self):
        return self.target

    def get_error(self):
        return self.last_error

    def set_base(self, left, right):
        self.base_l = left
        self.base_r = right

    def enable(self):
        if not self.enabled:
            self.pid.reset()
            self.enabled = True

    def disable(self):
        self.enabled = False
        self.base_l = 0.0
        self.base_r = 0.0
        self.pid.reset()
        if self._post is None:
            drivetrain.set_effort(0.0, 0.0)
        # With a hook (weapons chain) it does NOT write: the owner of the
        # motors (Weapon 4) decides the stop with its active braking.

    def hold_pose(self):
        """Anti-spin while stopped: locks the current heading without moving."""
        self.set_target_here()
        self.set_base(0.0, 0.0)
        self.enable()

    def engage_straight(self, speed):
        """Straight drive with the heading locked at the current angle."""
        self.set_target_here()
        self.set_base(speed, speed)
        self.enable()

    def start(self):
        """Runs forever in the background at 50 Hz. Idempotent."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self

    # ---------------- non-blocking loop ----------------
    async def _run(self):
        next_tick = time.ticks_ms()
        while True:
            next_tick = time.ticks_add(next_tick, DT_MS)
            self._tick()
            delay = time.ticks_diff(next_tick, time.ticks_ms())
            if delay <= 0:
                delay = 1
                next_tick = time.ticks_add(time.ticks_ms(), DT_MS)
            await asyncio.sleep_ms(delay)

    def _tick(self):
        if not self.enabled:
            self.last_error = 0.0
            self.last_out = 0.0
            return
        err = _wrap180(self.target - imu.get_yaw())
        if abs(err) < DEADBAND and self.base_l == 0.0 and self.base_r == 0.0:
            # in hold and inside the band: ZERO effort, no integral reset
            # (keeps the anti-drift trim for when it comes out)
            u = 0.0
            self.pid.prev = err
        else:
            u = self.pid.update(err, DT_MS / 1000.0)
        self.last_error = err
        self.last_out = u
        l = self.base_l - SIGN * u
        r = self.base_r + SIGN * u
        # With a motion base (pilot asking to march) we floor at the factory
        # threshold so gentle orders DO move the robot. In HOLD (base 0,
        # anti-spin while stopped / home arrival) there is NO floor: the
        # natural effort under static friction corrects tiny drifts without
        # starting pulses that shake the robot off its spot.
        if (self.base_l != 0.0 or self.base_r != 0.0):
            if 0.0 < abs(l) < MIN_EFFORT:
                l = MIN_EFFORT if l > 0 else -MIN_EFFORT
            if 0.0 < abs(r) < MIN_EFFORT:
                r = MIN_EFFORT if r > 0 else -MIN_EFFORT
        if self._post is not None:
            self._post(l, r)
        else:
            drivetrain.set_effort(l, r)


gyro_lock = GyroLock()
