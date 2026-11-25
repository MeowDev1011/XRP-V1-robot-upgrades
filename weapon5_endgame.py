# =========================================================
# WEAPON 5: CLOCK MANAGER & CLOSING ODOMETRY (AUTO-ENDGAME)
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# Match = exactly 150,000 ms (ticks_ms, no drift).
# Fusion odometry: encoder distance (drivetrain positions,
# in cm) + IMU heading (get_yaw, integrated at 208 Hz by the
# library itself). If the IMU drops, heading is backed up by
# the encoder difference (factory constants: wheels 6 cm,
# track 15.5 cm).
# Endgame: at the last ENDGAME_MS it raises the alert and, if
# RETURN mode is enabled, drives continuously toward the
# starting pose: NOT a macro, it recalculates heading and
# speed every cycle (live heading) and yields to front obstacles.
# ---------------------------------------------------------
# Usage from XRPCode blocks:
#   from weapon5_endgame import endgame
#   endgame.connect(gyro_lock)     # injects Weapon 1
#   endgame.start()                 # 50 Hz background task
#   endgame.start_match()       # robot ALREADY in the start zone
#   endgame.set_return(True)      # enables closing assist
#   endgame.seconds_left() / endgame.is_endgame() / endgame.pose()
# =========================================================
import uasyncio as asyncio
import time
import math
from XRPLib.defaults import drivetrain, imu, board, rangefinder

# ------------------------------------------------------------
# ON-TRACK CALIBRATION
# ------------------------------------------------------------
MATCH_MS        = 150000   # exactly 2:30
ENDGAME_MS        = 12000    # endgame duration: alert + return
DT_MS             = 20
V_RETORNO         = 0.85     # base return effort (calibrated: covers home
                             # at ~130 cm within the 12 s; 0.45 arrives late)
K_SOFT_ARRIVAL   = 0.04     # per remaining cm: lowers speed on approach
V_ARRIVAL_MIN     = 0.18     # speed floor so it does not die before arriving
HOME_TOL_CM     = 10.0     # "we are home" (confirm with manual: the real
                             # 'In Zone' is a band, not a 6 cm point)
PARK_LOCK_CM   = 8.0      # do not release the return right at tolerance:
                             # aim 2 cm DEEPER so the final slide leaves the
                             # robot inside the zone with margin
FINAL_SAFE_MS  = 2000     # in the last 2 s: if already inside the zone and
                             # still ordering motion, zero command -> Weapon 4
                             # nails the robot no matter what the odometry says
PIVOT_DEG     = 45.0     # if home is farther than this angle: pivot first
OBSTACLE_CM = 12.0     # minimum front obstacle during the return
TRACK_CM          = 15.5     # factory track (fallback without IMU)
LED_HZ            = 4        # LED blink rate during the endgame


def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


class EndGameManager:
    def __init__(self):
        self._t0 = None
        self._x = 0.0
        self._y = 0.0
        self._th = 0.0
        self._dic = [0.0, 0.0]
        self.has_imu = 0
        self._home_x = 0.0
        self._home_y = 0.0
        self.return_on = False
        self._alerted = False
        self._at_home = False
        self._gyro = None
        self._task = None

    # ---------------- configuration ----------------
    def connect(self, gyro_lock):
        """Injects Weapon 1, which executes the assisted return."""
        self._gyro = gyro_lock

    def start_match(self):
        """Starts the clock and takes the CURRENT pose as home.
        Place the robot in the start zone BEFORE calling."""
        self._t0 = time.ticks_ms()
        self.has_imu = 1 if imu.is_connected() else 0
        self._dic = [drivetrain.get_left_encoder_position(),
                     drivetrain.get_right_encoder_position()]
        self._x = 0.0
        self._y = 0.0
        self._th = 0.0
        self._home_x = 0.0
        self._home_y = 0.0
        self._alerted = False
        self._at_home = False

    def home_here(self):
        """Recaptures the current pose as home (e.g. after repositioning)."""
        self._home_x = self._x
        self._home_y = self._y

    def set_return(self, on):
        self.return_on = on

    # ---------------- queries (all O(1)) ----------------
    def ms_elapsed(self):
        if self._t0 is None:
            return 0
        return max(0, time.ticks_diff(time.ticks_ms(), self._t0))

    def elapsed_s(self):
        return self.ms_elapsed() / 1000

    def ms_left(self):
        return max(0, MATCH_MS - self.ms_elapsed())

    def seconds_left(self):
        return self.ms_left() / 1000

    def is_endgame(self):
        return self.ms_left() <= ENDGAME_MS

    def pose(self):
        return (self._x, self._y, math.degrees(self._th))

    def home_distance(self):
        return math.sqrt((self._home_x - self._x) ** 2 +
                         (self._home_y - self._y) ** 2)

    # ---------------- 50 Hz task ----------------
    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self

    async def _run(self):
        next_tick = time.ticks_ms()
        while True:
            next_tick = time.ticks_add(next_tick, DT_MS)
            self._odometry()
            if self._t0 is not None:
                self._endgame_logic()
            delay = time.ticks_diff(next_tick, time.ticks_ms())
            if delay <= 0:
                delay = 1
                next_tick = time.ticks_add(time.ticks_ms(), DT_MS)
            await asyncio.sleep_ms(delay)

    def _odometry(self):
        dl = drivetrain.get_left_encoder_position() - self._dic[0]
        dr = drivetrain.get_right_encoder_position() - self._dic[1]
        self._dic[0] += dl
        self._dic[1] += dr
        d = (dl + dr) / 2.0
        if self.has_imu:
            self._th = math.radians(imu.get_yaw())
        elif abs(d) > 1e-9:
            self._th += (dr - dl) / TRACK_CM
        self._x += d * math.cos(self._th)
        self._y += d * math.sin(self._th)

    def _endgame_logic(self):
        if not self.is_endgame():
            return
        if not self._alerted:
            self._alerted = True
            try:
                board.led_blink(LED_HZ)
            except Exception:
                pass
        if not (self.return_on and self._gyro is not None and self._gyro.enabled):
            return
        dist = self.home_distance()
        in_zone = dist <= HOME_TOL_CM
        if in_zone and self.ms_left() <= FINAL_SAFE_MS:
            # closing safety: guarantees the NAILING even if the minimum
            # effort floor keeps nudging the robot at the buzzer
            self._gyro.set_base(0.0, 0.0)
            self._at_home = True
            return
        if dist <= PARK_LOCK_CM:
            if not self._at_home:
                self._at_home = True
                self._gyro.set_base(0.0, 0.0)
            return
        # LIVE heading: the target is recalculated every cycle
        beta = math.atan2(self._home_y - self._y, self._home_x - self._x)
        heading_err = _wrap180(math.degrees(beta - self._th))
        self._gyro.set_target(math.degrees(beta))
        if abs(heading_err) > PIVOT_DEG:
            # face home first (pivot in place: no distance is lost)
            self._gyro.set_base(0.0, 0.0)
            return
        v = V_RETORNO
        v_arrival = K_SOFT_ARRIVAL * dist
        if v_arrival < v:
            v = max(V_ARRIVAL_MIN, v_arrival)
        try:
            if rangefinder.distance() < OBSTACLE_CM:
                v = 0.0
        except Exception:
            pass
        self._gyro.set_base(v, v)


endgame = EndGameManager()
