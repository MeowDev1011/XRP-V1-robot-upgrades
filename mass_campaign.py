# =========================================================
# IRON ACRES MASS CAMPAIGN - Team Robots Legends (FUSAMO)
# ---------------------------------------------------------
# Thousands of simultaneous matches (multiprocess, 5 cores)
# with the REAL board code (pilot + 5 weapons) played by a
# KID PILOT: an advanced kid, a good gamer, but without the
# motor precision of an adult. The kid plays ONLY with the
# virtual physical gamepad: the assist (Weapons 1-5) does the rest.
#
# FIELD (official): 272 x 137 cm (107 x 54 inch MAT).
#   - Alliance start zone on a short wall.
#   - City Center with alliance goals (red/blue) in the middle.
#   - Product hoppers and the barn.
# SCORING (parametric model): EDIT once the official
# "Read the Manual" is obtained (experiential.bot).
#   PTS_PRODUCTO: product delivered into the alliance goal.
#   PTS_PARK:     robot IN the start zone at the end (park).
#   PTS_DRAG: product still carried at the buzzer (0 = noise).
#
# SIMULATED GAME PRESSURE:
#   - Wall/opponent crashes (0-3): spin of 15-40 degrees.
#     A crash of more than 25 degrees KNOCKS OUT the carried product.
#   - Physical wheel stalls (0-2) of 2-5 s.
#   - Battery 82-100%, IMU drift + noise, crowded center.
#
# KID PILOT (editable parameters below):
#   TREMOR_SIGMA    stick tremor while holding them
#   DECISION_MS     human decision cadence (~5 Hz)
#   REACTION_MS     perception-action delay (+/- jitter)
#   KP_KID          heading-error degrees -> stick 1.0
#   AIM_DEADZONE stops correcting inside this angle
#   RUIDO_VISTA_*   the eye measures distances/angles with error
#   V_KID           kid cruise speed
#   STOP_CM         closes in "any way it can" up to this distance
#
# USAGE:
#   python3 mass_campaign.py            -> 1200 matches, 4 processes
#   MASS_N=3000 python3 mass_campaign.py
#   MASS_PILOT=KID|GOOD|REGULAR|ADULT python3 mass_campaign.py
# =========================================================
import os
import math
import random
import multiprocessing

import simulator_xrp as SIM

# ---------------- CAMPAIGN CONFIGURATION ----------------
N_MATCHES = int(os.environ.get("MASS_N", "1200"))
WORKERS = int(os.environ.get("MASS_W", "4"))
PILOT = os.environ.get("MASS_PILOT", "KID")
VARIANT = os.environ.get("MASS_VARIANT", "ASSIST")   # ASIST | NO_ASSIST

# ---------------- PILOT PROFILE (gamepad precision) ----------------
PILOTS = ("KID", "GOOD", "REGULAR", "ADULT")
PROFILES = {
    # tremor, decisions (ms), reaction (ms), aiming precision (KP/dead-
    # band/eye noise) and cruise: an advanced kid and good gamer, but
    # without the motor precision of an adult.
    "KID":     dict(TREMOR_SIGMA=0.050, DECISION_MS=200.0, REACTION_MS=180.0,
                    KP_KID=70.0, AIM_DEADZONE=8.0, EYE_NOISE_CM=4.0,
                    EYE_NOISE_DEG=4.0, V_KID=0.70,
                    STOP_CM=10.0, BRAKE_AT_CM=30.0),
    "GOOD":   dict(TREMOR_SIGMA=0.030, DECISION_MS=150.0, REACTION_MS=140.0,
                    KP_KID=55.0, AIM_DEADZONE=6.0, EYE_NOISE_CM=3.0,
                    EYE_NOISE_DEG=3.0, V_KID=0.72,
                    STOP_CM=10.0, BRAKE_AT_CM=28.0),
    "REGULAR": dict(TREMOR_SIGMA=0.085, DECISION_MS=280.0, REACTION_MS=260.0,
                    KP_KID=90.0, AIM_DEADZONE=12.0, EYE_NOISE_CM=6.0,
                    EYE_NOISE_DEG=6.0, V_KID=0.62,
                    STOP_CM=12.0, BRAKE_AT_CM=34.0),
    "ADULT":  dict(TREMOR_SIGMA=0.012, DECISION_MS=90.0, REACTION_MS=80.0,
                    KP_KID=28.0, AIM_DEADZONE=3.0, EYE_NOISE_CM=1.5,
                    EYE_NOISE_DEG=1.5, V_KID=0.55,
                    STOP_CM=10.0, BRAKE_AT_CM=25.0),
}
if PILOT not in PROFILES:
    PILOT = "KID"
PROFILE = PROFILES[PILOT]
(TREMOR_SIGMA, DECISION_MS, REACTION_MS, KP_KID, AIM_DEADZONE,
 EYE_NOISE_CM, EYE_NOISE_DEG, V_KID, STOP_CM, BRAKE_AT_CM) = (
    PROFILE["TREMOR_SIGMA"], PROFILE["DECISION_MS"], PROFILE["REACTION_MS"],
    PROFILE["KP_KID"], PROFILE["AIM_DEADZONE"], PROFILE["EYE_NOISE_CM"],
    PROFILE["EYE_NOISE_DEG"], PROFILE["V_KID"], PROFILE["STOP_CM"],
    PROFILE["BRAKE_AT_CM"])

# ---------------- FIELD & SCORING (EDIT WITH THE MANUAL) ----------------
FIELD_L_CM = 272.0        # length (Y axis: from our wall to the back)
FIELD_W_CM = 68.0         # fenced half-width (±) for wall crashes
PICKUP_XY = (30.0, 90.0)   # product pickup point (hopper/barn)
GOAL_XY = (-5.0, 121.0)    # alliance goal (City Center)
PTS_PRODUCTO = 10         # per product in the goal
PTS_PARK = 10             # for finishing In the start Zone (park)
PTS_DRAG = 0          # product carried but not delivered at the end

RACE_START_MS = 2000.0
RELEASE_MS = 138000.0   # the kid releases the sticks and leaves the endgame assisted
PICKUP_MIN_CM = 18.0
CRASH_DROPS_DEG = 25.0    # spin degrees that knock the product out
P1_THRESHOLD = 3.0
P2_THRESHOLD = 12.0

_MODULOS = ("weapon3_curves", "weapon2_torque_boost", "weapon4_traction",
            "weapon5_endgame", "weapon1_gyro_lock", "pilot_gamepad")


def _reload():
    import importlib
    import sys
    for nombre in _MODULOS:
        importlib.reload(sys.modules[nombre])
    return sys.modules


RX_JIT_MAX = 80.0          # pilot reaction spread (ms)


def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


class KidPilot:
    """Virtual human: decides every DECISION_MS, reacts late,
    trembles and looks with noise. Only touches the gamepad."""

    def __init__(self, pad, RNG, GP, endgame):
        self.pad = pad
        self.GP = GP
        self.RNG = RNG
        self.a5 = endgame
        self.jit = RNG.uniform(0.0, RX_JIT_MAX)
        self.decision_t = -1.0
        self.x1 = 0.0
        self.y1 = 0.0
        self.pending = None
        self.wp_x, self.wp_y = PICKUP_XY
        self.target = "PICKUP"
        self.possession = 0
        self.deliveries = 0
        self.pickups = 0
        self.re_aim = False
        self.prev_d = None
        self.dejando = False
        self.delivery_times = []

    def _mira(self, px, py, yaw):
        nx = px + self.RNG.gauss(0.0, EYE_NOISE_CM)
        ny = py + self.RNG.gauss(0.0, EYE_NOISE_CM)
        err = wrap180(math.degrees(math.atan2(self.wp_y - ny,
                                              self.wp_x - nx)) - yaw
                      + self.RNG.gauss(0.0, EYE_NOISE_DEG))
        return err

    def _decide(self, t, pose, yaw):
        px, py, _ = pose
        err = self._mira(px, py, yaw)
        dist = math.hypot(self.wp_x - px, self.wp_y - py) + \
            self.RNG.gauss(0.0, EYE_NOISE_CM)
        if self.y1 > 0.25 and self.prev_d is not None and \
                dist > self.prev_d + 2.0 and dist > STOP_CM + 3.0:
            err += 35.0 if err >= 0 else -35.0
        self.prev_d = dist
        self.re_aim = False
        if abs(err) > AIM_DEADZONE:
            x1n = max(-1.0, min(1.0, err / KP_KID))
            y1n = 0.12
        else:
            x1n = 0.0
            if dist <= STOP_CM:
                y1n = 0.0
            elif dist < BRAKE_AT_CM:
                y1n = V_KID * (0.35 + 0.65 * dist / BRAKE_AT_CM)
            else:
                y1n = V_KID
        self.pending = (t + REACTION_MS + abs(self.RNG.gauss(0.0, self.jit)),
                     x1n, y1n)

    def step(self, t, pose, yaw):
        if self.pending is not None and t >= self.pending[0]:
            _, self.x1, self.y1 = self.pending
            self.pending = None
        if t >= self.decision_t:
            self.decision_t = t + DECISION_MS + abs(self.RNG.gauss(0.0, self.jit))
            self._decide(t, pose, yaw)
        else:
            if self.x1 != 0.0:
                self.x1 += self.RNG.gauss(0.0, TREMOR_SIGMA)
            else:
                self.x1 = self.RNG.gauss(0.0, TREMOR_SIGMA * 0.6)
            if abs(self.x1) < 0.02:
                self.x1 = 0.0
            if self.y1 != 0.0:
                self.y1 = max(0.0, self.y1 + self.RNG.gauss(0.0, TREMOR_SIGMA * 0.8))
        self.pad.axes[self.GP.X1] = max(-1.0, min(1.0, self.x1))
        self.pad.axes[self.GP.Y1] = max(-1.0, min(1.0, self.y1))


def new_match(seed, MOD):
    RNG = random.Random(seed)

    A1 = MOD["weapon1_gyro_lock"]
    A2 = MOD["weapon2_torque_boost"]
    A4 = MOD["weapon4_traction"]
    A5 = MOD["weapon5_endgame"]
    MAIN = MOD["pilot_gamepad"]

    DRV = SIM.DRIVETRAIN
    GP = SIM.GamepadSim

    SIM.CLOCK.t = 0
    DRV.LEFT = SIM.WheelSim()
    DRV.RIGHT = SIM.WheelSim()
    DRV.yaw = 0.0
    DRV.source = "idle"
    SIM.BOARD.voltage_scale = RNG.uniform(0.82, 1.0)
    SIM.BIAS_IMU_CS = RNG.uniform(0.0, 0.2)
    pad = GP.nueva()

    gyro = A1.gyro_lock
    tb = A4.traction_brake
    endgame = A5.endgame
    console = MAIN.pilot_console

    def hook(l, r):
        l, r = A2.torque_boost.feed(l, r)
        tb.set_command(l, r)

    gyro.attach(hook)
    tb.enable()
    A2.torque_boost.enable()
    endgame.connect(gyro)
    endgame.set_return(VARIANT != "NO_ASSIST")
    A5.V_RETORNO = 0.85
    imu = SIM.IMU
    imu.reset_yaw()
    console.connect(pad)
    gyro.set_target_here()

    kid = KidPilot(pad, RNG, GP, endgame)

    crashes = [RNG.uniform(5000, 135000) for _ in range(RNG.randint(0, 3))]
    stalls = []
    for _ in range(RNG.randint(0, 2)):
        stalls.append((RNG.uniform(5000, 115000),
                        RNG.uniform(2000.0, 5000.0), RNG.choice(("L", "R"))))

    faults = []
    max_err = 0.0
    crash_regs = []
    p1_pending = []
    p1_rec = {}          # crash -> any time err <= THRESHOLD in the window
    trompos = 0.0
    inicio = False

    for k in range(7500):
        SIM.CLOCK.advance(20)
        t = SIM.CLOCK.ticks_ms()

        if not inicio:
            if 400 <= t < 420:
                pad.buttons[GP.START - 4] = 1
            else:
                pad.buttons[GP.START - 4] = 0
            if t >= 420:
                inicio = True

        if inicio:
            if t < RELEASE_MS:
                pose = endgame.pose()
                kid.step(t, pose, SIM.IMU.get_yaw())

            # pickup/delivery events (field ground truth)
            if t < RELEASE_MS:
                px, py, _ = endgame.pose()
                if kid.target == "PICKUP":
                    if math.hypot(px - kid.wp_x, py - kid.wp_y) < PICKUP_MIN_CM:
                        kid.possession = 1
                        kid.pickups += 1
                        kid.target = "SCORE"
                        kid.wp_x, kid.wp_y = GOAL_XY
                        kid.re_aim = True
                else:
                    if math.hypot(px - kid.wp_x, py - kid.wp_y) < PICKUP_MIN_CM:
                        kid.possession = 0
                        kid.deliveries += 1
                        kid.delivery_times.append(t)
                        kid.target = "PICKUP"
                        kid.wp_x, kid.wp_y = PICKUP_XY
                        kid.re_aim = True
            else:
                if VARIANT == "NO_ASSIST":
                    if not kid.dejando:
                        kid.dejando = True
                        kid.target = "HOME"
                        kid.wp_x, kid.wp_y = 0.0, 0.0
                        kid.re_aim = True
                    kid.step(t, endgame.pose(), SIM.IMU.get_yaw())
                    if t >= 149000:
                        pad.axes[GP.X1] = 0.0
                        pad.axes[GP.Y1] = 0.0
                else:
                    pad.axes[GP.X1] = 0.0
                    pad.axes[GP.Y1] = 0.0
        else:
            pad.axes[GP.X1] = 0.0
            pad.axes[GP.Y1] = 0.0

        for lo, dur, wheel in stalls:
            if lo <= t < lo + dur:
                DRV.LEFT.stalled = (wheel == "L")
                DRV.RIGHT.stalled = (wheel == "R")
            else:
                if wheel == "L" and t >= lo + dur:
                    DRV.LEFT.stalled = False
                if wheel == "R" and t >= lo + dur:
                    DRV.RIGHT.stalled = False
        for lo in crashes:
            if lo <= t < lo + 20:
                salto = RNG.uniform(15.0, 40.0) * RNG.choice((-1.0, 1.0))
                DRV.yaw += salto
                SIM.DRIVETRAIN.source = "active"
                crash_regs.append((lo, salto))
                p1_pending.append([lo, lo + 10000])
                trompos += abs(salto)
                if abs(salto) > CRASH_DROPS_DEG and kid.possession:
                    kid.possession = 0
                    kid.target = "PICKUP"
                    kid.wp_x, kid.wp_y = PICKUP_XY
                    kid.re_aim = True
        DRV.yaw += RNG.gauss(0.0, 0.05)

        console._cycle()
        gyro._tick()
        tb.step()
        endgame._odometry()
        endgame._endgame_logic()
        DRV.step(0.02)

        if "MASS_G1" in os.environ:
            en_win = any(lo - 500 <= t <= lo + 12000 for lo, _ in crash_regs)
            if en_win and k % 10 == 0:
                print("G1 t=%5.1f mode=%s err=%6.2f tgt=%7.1f yaw=%7.1f "
                      "base=(%.2f %.2f) en=%d X1raw=%+.3f ema=%+.3f Y1=%+.2f"
                      % (t / 1000.0, console.mode_name(), gyro.get_error(),
                         gyro.get_target(), SIM.IMU.get_yaw(),
                         gyro.base_l, gyro.base_r, gyro.enabled,
                         pad.axes[0], console._ema_x, pad.axes[1]))

        if "MASS_DEBUG" in os.environ and k % 100 == 0:
            pxx, pyy, _th = endgame.pose()
            _e = wrap180(math.degrees(math.atan2(kid.wp_y - pyy,
                                                 kid.wp_x - pxx)) -
                         SIM.IMU.get_yaw())
            print("t=%5.1f pose=(%6.1f,%6.1f) yaw=%6.1f mode=%s wp=(%.0f,%.0f) "
                  "obj=%s poss=%d x1=%+.2f y1=%+.2f err=%6.2f" %
                  (t / 1000.0, pxx, pyy, SIM.IMU.get_yaw(), console.mode_name(),
                   kid.wp_x, kid.wp_y, kid.target, kid.possession,
                   pad.axes[0], pad.axes[1], _e))

        if "MASS_G2" in os.environ and k % 25 == 0:
            en_win0 = any(lo - 500 <= t <= lo + 12000 for lo, _ in crash_regs)
            if en_win0:
                print("G2 t=%5.1f mode=%s err=%6.2f tgt=%7.1f yaw=%7.1f "
                      "base=(%.2f %.2f) en=%d X1r=%+.3f ema=%+.3f Y1=%+.2f"
                      % (t / 1000.0, console.mode_name(), gyro.get_error(),
                         gyro.get_target(), SIM.IMU.get_yaw(),
                         gyro.base_l, gyro.base_r, gyro.enabled,
                         pad.axes[0], console._ema_x, pad.axes[1]))

        if console._mode in (MAIN.STRAIGHT, MAIN.STOP) and gyro.enabled:
            in_crash_window = any(lo - 200 <= t <= lo + 6000 for lo, _ in crash_regs)
            if not in_crash_window:
                e = abs(gyro.get_error())
                if e > max_err:
                    max_err = e

        stall_active = any(lo - 200 <= t <= lo + dur + 2000 for lo, dur, _ in stalls)
        alive = []
        for lo, deadline in p1_pending:
            if t >= deadline:
                if abs(gyro.get_error()) <= P1_THRESHOLD:
                    p1_rec[lo] = True
            if t < deadline + 5000 or stall_active:
                alive.append((lo, deadline))
                continue
            if not p1_rec.get(lo):
                faults.append("P1: crash t=%.0f persistent error (>%.0f: %.1f)"
                              % (lo / 1000.0, P1_THRESHOLD, abs(gyro.get_error())))
        p1_pending = alive

    dist = endgame.home_distance()
    nailed = tb.nailed or (abs(DRV.LEFT.rpm) < 1.5 and abs(DRV.RIGHT.rpm) < 1.5)
    park = dist <= A5.HOME_TOL_CM and nailed
    if not park:
        faults.append("P3: final dist=%.1f" % dist)
    if max_err > P2_THRESHOLD:
        faults.append("P2: cruise %.1f" % max_err)

    puntos = (kid.deliveries * PTS_PRODUCTO +
              (PTS_PARK if park else 0) +
              kid.possession * PTS_DRAG)
    return {"seed": seed, "puntos": puntos, "deliveries": kid.deliveries,
            "pickups": kid.pickups, "park": park, "dist": dist,
            "max_err": max_err, "faults": faults, "trompos": trompos,
            "t_entrega": (kid.delivery_times[0] / 1000.0) if kid.delivery_times else -1.0}


def _worker(seed):
    MOD = _reload()
    return new_match(seed, MOD)


def campaign():
    base_seed = 777000
    print("== IRON ACRES MASS CAMPAIGN == pilot=%s n=%d processes=%d variant=%s" %
          (PILOT, N_MATCHES, WORKERS, VARIANT))
    with multiprocessing.Pool(WORKERS) as pool:
        res = pool.map(_worker, [base_seed + i for i in range(N_MATCHES)],
                       chunksize=8)

    n = len(res)
    parks = [r for r in res if r["park"]]
    clean = [r for r in res if not r["faults"]]
    deliveries = [r["deliveries"] for r in res]
    puntos = [r["puntos"] for r in res]
    dists = [r["dist"] for r in res]
    errs = [r["max_err"] for r in res]
    f1 = sum(1 for r in res if any(f.startswith("P1") for f in r["faults"]))
    f2 = sum(1 for r in res if any(f.startswith("P2") for f in r["faults"]))
    f3 = sum(1 for r in res if any(f.startswith("P3") for f in r["faults"]))

    def media(v):
        return sum(v) / len(v) if v else 0.0

    def pct(v):
        return 100.0 * len(v) / n

    hist = {}
    for e in deliveries:
        hist[e] = hist.get(e, 0) + 1

    print("\n-- RESULTS (%d matches, pilot %s) --" % (n, PILOT))
    print("POINTS: avg=%.1f  min=%d  max=%d" %
          (media(puntos), min(puntos), max(puntos)))
    print("PRODUCTS delivered: avg=%.2f  [0:%d | 1:%d | 2:%d | 3:%d | 4+:%d]"
          % (media(deliveries),
             hist.get(0, 0), hist.get(1, 0), hist.get(2, 0), hist.get(3, 0),
             sum(v for k, v in hist.items() if k >= 4)))
    print("PARK in zone: %.1f%%  (avg final dist=%.1f cm)" % (pct(parks), media(dists)))
    desglose = media(deliveries) * PTS_PRODUCTO + pct(parks) / 100.0 * PTS_PARK
    print("Theoretical breakdown: %.2f products*%d + park %d*%.2f = %.1f points" %
          (media(deliveries), PTS_PRODUCTO, PTS_PARK, pct(parks) / 100.0, desglose))
    print("STRICT with no faults: %.1f%%" % pct(clean))
    print("Faults  P1(spin post-crash): %d  P2(cruise): %d  P3(park): %d"
          % (f1, f2, f3))
    with_delivery = [r["t_entrega"] for r in res if r["t_entrega"] > 0]
    print("first delivery: avg t = %.1f s (of 138 useful s)" %
          (media(with_delivery) if with_delivery else -1.0))

    avg_park_dist = media([r["dist"] for r in parks]) if parks else -1
    print("Closing: final dist when parked: %.1f cm | avg cruise err=%.2f | "
          "avg accumulated spin=%.1f" % (avg_park_dist, media(errs),
                                           media([r["trompos"] for r in res])))
    worst = sorted(res, key=lambda r: r["puntos"])[:3]
    print("Worst matches:")
    for r in worst:
        print("  seed=%d points=%d deliveries=%d park=%s dist=%.1f | %s"
              % (r["seed"], r["puntos"], r["deliveries"], r["park"],
                 r["dist"], "; ".join(r["faults"]) if r["faults"] else "-"))
    return res


if __name__ == "__main__":
    campaign()
