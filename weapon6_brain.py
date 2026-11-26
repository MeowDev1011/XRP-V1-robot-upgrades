# =========================================================
# WEAPON 6: THE BRAIN — ON-BOARD ADAPTIVE INTELLIGENCE
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# The robot THINKS BY ITSELF, every 20 ms tick, WITHOUT
# internet, WITHOUT any API and WITHOUT a single sleep().
# It watches the pilot and the other weapons and re-tunes
# them LIVE, always inside safe clamps, so the robot
# corrects its own movements in real time:
#
#   GAIN  cruise drift detected  -> raises W1 KP (decays back)
#   DAMP  crash/spin spike seen  -> raises W1 KD for 2 s (kills P1 spins)
#   GRIP  repeated wheel stalls  -> raises W2 BOOST_MAX (decays back)
#   HOME  endgame return active  -> keeps the heading gain high
#
# It NEVER touches the motors (Weapon 4 is still the only
# writer) and NEVER overrides the pilot: it only tunes the
# assist AROUND the sticks. With the copilot on the laptop
# it forms the full loop: laptop brain plans off-line,
# this on-board brain adapts on-line during the match.
# ---------------------------------------------------------
# Usage:
#   from weapon6_brain import brain
#   brain.wire(gyro_lock, torque_boost, endgame, pilot_console)
#   brain.start()          # real board: 50 Hz uasyncio task
#   brain.step()           # simulators/tests: call every 20 ms tick
#   brain.snapshot()       # telemetry dict for the console/log
# =========================================================
import uasyncio as asyncio
import time

import weapon1_gyro_lock as W1
import weapon2_torque_boost as W2

# ------------------------------------------------------------
# TUNING CLAMPS (the brain may only move within these fences)
# ------------------------------------------------------------
DT_MS          = 20     # one thought every 20 ms (50 Hz)

KP_MIN         = 0.058  # never below the battery-proven base
KP_MAX         = 0.072  # never above +12% (autotune's sweet range)
KP_STEP        = 0.0004 # gain raise per tick while drift persists
KP_DECAY       = 0.0002 # decay per tick back to base
DRIFT_TRIG_DEG = 6.0    # EMA error above this = real cruise drift
DRIFT_OK_DEG   = 2.5    # EMA error below this = drift under control
EMA_ERR_A      = 0.02   # ~1 s moving window at 50 Hz

KD_SPIKE_DEG   = 10.0   # error jump = crash/spin signature
KD_HOLD_MS     = 2000   # extra damping time after a spike
KD_HIGH        = 0.0085 # damped derivative gain
KD_DECAY       = 0.0002

BOOST_HARD_MAX = 0.45   # never above +0.10 over W2's own max
BOOST_STEP     = 0.002
BOOST_DECAY    = 0.004
STALL_EMA_A    = 0.01
STALL_TRIG     = 0.05   # stalls in >5% of recent ticks = gripping terrain

HOME_KP_FLOOR  = 0.066  # the return home deserves precision
THOUGHT_MS     = 2500   # at most one "thought" line every 2.5 s


class Brain:
    """Passive tuner: observes and re-tunes, never drives."""

    def __init__(self):
        self.gyro = None
        self.torque = None
        self.endgame = None
        self.console = None
        self._kp_base = W1.KP
        self._kd_base = W1.KD
        self._boost_base = W2.BOOST_MAX
        self._kp = W1.KP
        self._kd = W1.KD
        self._boost = W2.BOOST_MAX
        self._ema_err = 0.0
        self._ema_stall = 0.0
        self._kd_until = 0
        self._prev_err = 0.0
        self._last_thought = 0
        self._task = None
        self.thoughts = 0

    # ---------------- wiring ----------------
    def wire(self, gyro, torque, endgame=None, console=None):
        self.gyro = gyro
        self.torque = torque
        self.endgame = endgame
        self.console = console
        self.reset()

    def reset(self):
        """Restore the battery-proven constants and clear memory."""
        W1.KP = self._kp = self._kp_base
        W1.KD = self._kd = self._kd_base
        W2.BOOST_MAX = self._boost = self._boost_base
        self._ema_err = 0.0
        self._ema_stall = 0.0
        self._kd_until = 0
        self._prev_err = 0.0
        self._last_thought = 0

    # ---------------- one thought (50 Hz) ----------------
    def step(self):
        now = time.ticks_ms()
        gyro = self.gyro
        if gyro is None:
            return
        moving = (gyro.base_l != 0.0 or gyro.base_r != 0.0)
        err = abs(gyro.last_error) if gyro.enabled else 0.0

        # ---- GAIN: fight sustained drift, relax when clean ----
        self._ema_err += (err - self._ema_err) * EMA_ERR_A
        if moving and self._ema_err > DRIFT_TRIG_DEG:
            self._kp = min(KP_MAX, self._kp + KP_STEP)
        elif self._ema_err < DRIFT_OK_DEG or not gyro.enabled:
            self._kp = max(self._kp_base, self._kp - KP_DECAY)
            if self._kp - self._kp_base < 1e-9:
                self._kp = self._kp_base

        # ---- HOME: the last 12 s deserve the sharpest heading ----
        in_return = False
        if self.endgame is not None:
            try:
                in_return = (bool(getattr(self.endgame, "return_on", False))
                             and self.endgame.is_endgame())
            except Exception:  # noqa: BLE001 - endgame may be absent in sims
                in_return = False
        if in_return and self._kp < HOME_KP_FLOOR:
            self._kp = HOME_KP_FLOOR

        # ---- DAMP: a sudden error jump is a crash -> extra damping ----
        spike = abs(err - self._prev_err)
        self._prev_err = err
        if spike > KD_SPIKE_DEG:
            self._kd_until = now + KD_HOLD_MS
        if now < self._kd_until or in_return:
            self._kd = KD_HIGH
        else:
            self._kd = max(self._kd_base, self._kd - KD_DECAY)
            if self._kd - self._kd_base < 1e-9:
                self._kd = self._kd_base

        # ---- GRIP: repeated stalls mean slippery/heavy ground ----
        if self.torque is not None:
            stalling = bool(self.torque.stall_l or self.torque.stall_r)
            self._ema_stall += ((1.0 if stalling else 0.0)
                                - self._ema_stall) * STALL_EMA_A
            if stalling and self._ema_stall > STALL_TRIG:
                self._boost = min(BOOST_HARD_MAX, self._boost + BOOST_STEP)
            elif self._boost > self._boost_base:
                self._boost = max(self._boost_base, self._boost - BOOST_DECAY)
                if self._boost - self._boost_base < 1e-9:
                    self._boost = self._boost_base

        # ---- apply the tuning (constants of W1 / W2) ----
        W1.KP = self._kp
        W1.KD = self._kd
        W2.BOOST_MAX = self._boost

        # ---- say the thought out loud (only while ACTIVELY adapting,
        #      max one line / 2.5 s) ----
        busy = (self._kp > self._kp_base + 1e-9
                or self._kd > self._kd_base + 1e-9
                or self._boost > self._boost_base + 1e-9
                or in_return)
        if busy and time.ticks_diff(now, self._last_thought) > THOUGHT_MS:
            self._last_thought = now
            self.thoughts += 1
            print("🧠 BRAIN t=%5.1f KP=%.4f KD=%.4f BOOST=%.2f err=%.1f "
                  "drift=%.1f stall=%.2f%s"
                  % (now / 1000.0, self._kp, self._kd, self._boost,
                     err, self._ema_err, self._ema_stall,
                     " [RETURN]" if in_return else ""))

    # ---------------- telemetry ----------------
    def snapshot(self):
        return {"kp": W1.KP, "kp_base": self._kp_base, "kd": W1.KD,
                "boost_max": W2.BOOST_MAX, "drift_ema": self._ema_err,
                "stall_ema": self._ema_stall, "thoughts": self.thoughts}

    # ---------------- real-board 50 Hz task ----------------
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


brain = Brain()
