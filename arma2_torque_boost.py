# =========================================================
# WEAPON 2: SMART TORQUE BOOST (ANTI-STALL)
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# Closed loop per WHEEL: commanded effort vs. real rpm.
# get_speed() is sampled every 20 ms by XRPLib itself
# (encoded_motor.py: _UPDATE_PERIOD_MS timer), so the
# measurement is free and always fresh.
# Friction model of the official source: kS=0.12, kV=0.02.
#   expected rpm = (effort - kS) / kV
# If the wheel turns much less than expected during
# TICKS_CONFIRMAR, it is a real stall: the boost climbs
# in THAT wheel only and releases as soon as it flows again.
# ---------------------------------------------------------
# Two modes:
#   1) Composite (recommended): gyro_lock.attach(arma2.feed)
#      and the last chain link calls torque_boost.aplicar().
#   2) Standalone: set_command(l, r) + enable() + start().
# =========================================================
import uasyncio as asyncio
import time
from XRPLib.defaults import drivetrain, board, left_motor, right_motor

# ------------------------------------------------------------
# ON-TRACK CALIBRATION
# ------------------------------------------------------------
KS             = 0.12   # factory: effort to "break the static"
KV             = 0.02   # factory: effort per rpm
COMP_BATERIA   = True   # multiply by board.voltage_scale (stable torque)
STALL_CMD_MIN  = 0.25   # do not watch for stalls below this effort
RPM_MIN_FALLO  = 8.0    # minimum expected speed to speak of a stall
RATIO_ATASCO   = 0.4    # stall if turning < 40% of expected
TICKS_CONFIRMAR = 8     # 8 x 20 ms = 160 ms confirming stall (anti-noise)
BOOST_MAX      = 0.35   # maximum extra effort per wheel
BOOST_PASO     = 0.012  # ~0.6 effort/second climb: strong but sensitive
BOOST_FUGA     = 0.05   # release per cycle once fluid again
DT_MS          = 20


class _Rueda:
    """State of one wheel: current boost + stall cycle counter."""

    def __init__(self, motor):
        self.motor = motor
        self.boost = 0.0
        self.ticks = 0

    def step(self, cmd):
        e = abs(cmd)
        if e < STALL_CMD_MIN:
            self.boost = 0.0
            self.ticks = 0
            return cmd
        expected = (e - KS) / KV
        if expected < RPM_MIN_FALLO:
            return cmd
        real = self.motor.get_speed()
        if abs(real) < RATIO_ATASCO * expected:
            self.ticks += 1
            if self.ticks >= TICKS_CONFIRMAR:
                self.boost = min(BOOST_MAX, self.boost + BOOST_PASO)
        else:
            self.ticks = 0
            self.boost = max(0.0, self.boost - BOOST_FUGA)
        sgn = 1.0 if cmd >= 0 else -1.0
        return cmd + sgn * self.boost


class TorqueBoost:
    def __init__(self):
        self.enabled = False
        self._izq = _Rueda(left_motor)
        self._der = _Rueda(right_motor)
        self._cmd_l = 0.0
        self._cmd_r = 0.0
        self._task = None

    # ---------------- observable state for telemetry ----------------
    @property
    def boost_l(self):
        return self._izq.boost

    @property
    def boost_r(self):
        return self._der.boost

    @property
    def atasco_l(self):
        return self._izq.ticks >= TICKS_CONFIRMAR

    @property
    def atasco_r(self):
        return self._der.ticks >= TICKS_CONFIRMAR

    # ---------------- composite mode ----------------
    def feed(self, left, right):
        """Returns the efforts with boost applied. Does NOT write motors;
        the last chain link calls aplicar(). In standalone mode,
        _run() acts as the last link."""
        return self._izq.step(left), self._der.step(right)

    def aplicar(self, left, right):
        """Final link of any chain: writes the motors, with battery
        compensation when applicable."""
        if not self.enabled:
            self._izq.boost = 0.0
            self._der.boost = 0.0
        vs = board.voltage_scale if COMP_BATERIA else 1.0
        drivetrain.set_effort(max(-1.0, min(1.0, left * vs)),
                              max(-1.0, min(1.0, right * vs)))

    # ---------------- standalone mode ----------------
    def set_command(self, left, right):
        self._cmd_l = left
        self._cmd_r = right

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False
        self._cmd_l = 0.0
        self._cmd_r = 0.0
        self._izq.boost = 0.0
        self._der.boost = 0.0
        self._izq.ticks = 0
        self._der.ticks = 0
        drivetrain.set_effort(0.0, 0.0)

    def start(self):
        """Own 50 Hz task. ONLY if not composed with Weapon 1."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self

    async def _run(self):
        next_tick = time.ticks_ms()
        while True:
            next_tick = time.ticks_add(next_tick, DT_MS)
            l, r = self.feed(self._cmd_l, self._cmd_r)
            self.aplicar(l, r)
            delay = time.ticks_diff(next_tick, time.ticks_ms())
            if delay <= 0:
                delay = 1
                next_tick = time.ticks_add(time.ticks_ms(), DT_MS)
            await asyncio.sleep_ms(delay)


torque_boost = TorqueBoost()
