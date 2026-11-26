# =========================================================
# INDIVIDUAL AND TEAM GAMES - Team Robots Legends (FUSAMO)
# ---------------------------------------------------------
# Multi-mode battery with the REAL board code
# (pilot_gamepad + 5 weapons) played by the KID PILOT
# from mass_campaign.py (tremor, ~200 ms decisions, ~180 ms reaction,
# eye with noise). Modes:
#
#   DRIVE   : 4-door circuit in loop (60 s), individual.
#   SUMO    : 1 vs 1 push duel in a r=76 cm ring (45 s).
#   SUMO2   : TEAMS 2 vs 2: us + scripted ally vs 2 rivals;
#             winning = eject both of them from the ring.
#   SOCCER  : physical ball 1 vs 1; score in the goal (120 s).
#   SOCCER2 : TEAMS 2 vs 2: ball + ally and 2 dynamic rivals;
#             our goal at the top (City Center), rival goal near
#             our wall; whoever scores more wins.
#
# STICK PRECISION: the pilot profile is chosen with
# GAMES_PILOT=KID|GOOD|REGULAR|ADULT (same table as mass_campaign).
#
# STICK FIDELITY (detect movements contrary to or involuntary
# versus what the pilot wanted; ONLY our bot):
#   F1 contrary    : SUSTAINED forward intent (Y1>0.3 for
#                    >=15 ticks) while the robot goes backward for
#                    most of that stretch (v <-2.5 cm/s). Must never happen.
#   F2 slide       : distance covered after releasing sticks at
#                    high speed (Weapon 4 must nail it; >8 cm is a fault).
#   F3 involuntary : kid with sticks released >1 s while the robot
#                    moved >3 cm in total.
#   F4 pan         : kid WITHOUT touching X1 >1 s while the heading changed >3
#                    degrees (outside crash windows).
#   F5 latency     : ms from Y1>=0.5 until wheels >8 cm/s.
#
# NOTE: team/rival collisions with our robot use the same
# model as 1v1 (reciprocal push + encoder slide on us); the
# RECEIVED push does not count as a stick fault.
#
# USAGE:  python3 games.py                     (5 modes x 400)
#         GAMES_MODE=SUMO2 GAMES_N=300 python3 games.py
#         GAMES_PILOT=REGULAR GAMES_N=200 python3 games.py
# =========================================================
import os

if "GAMES_PILOT" in os.environ:
    os.environ["MASS_PILOT"] = os.environ["GAMES_PILOT"]

import math
import random
import multiprocessing

import simulator_xrp as SIM
from mass_campaign import (KidPilot, wrap180, _reload, PILOT,
                     TREMOR_SIGMA, DECISION_MS, REACTION_MS,
                     KP_KID, AIM_DEADZONE, EYE_NOISE_CM,
                     EYE_NOISE_DEG, V_KID, STOP_CM, BRAKE_AT_CM)

N_MATCHES = int(os.environ.get("GAMES_N", "400"))
WORKERS = int(os.environ.get("GAMES_W", "4"))
MODE = os.environ.get("GAMES_MODE", "ALL")

MODE_T = {"DRIVE": 60000.0, "SUMO": 45000.0, "SUMO2": 45000.0,
          "SOCCER": 120000.0, "SOCCER2": 120000.0}
UMBRAL_AV_KID = 0.30          # Y1 above this: intent to drive forward
F1_RACHA_MIN = 15             # ticks (0.3 s) of sustained intent
F1_V_CONTRARIO = -2.5         # cm/s: going backward with forward ordered
F2_CM_MAX = 8.0               # tolerated slide after releasing
F3_CM_MAX = 3.0               # tolerated drift while still
F4_GRADOS = 3.0               # tolerated pan without X1
F5_V_STALL = 8.0              # cm/s that counts as a response

CIRCUIT = ((35.0, 35.0), (60.0, 70.0), (5.0, 105.0), (-35.0, 55.0))
DOOR_RADIUS = 20.0               # door passing radius
RING_R = 76.0               # sumo
BODY_R = 10.0               # body radius (cm)
BALL_R = 4.0
GOAL_XY = (-5.0, 121.0)        # our attacking goal (City Center)
RIVAL_GOAL_XY = (5.0, 10.0)    # goal we defend (close to our wall)
GOAL_R = 18.0                  # the ball enters the goal
KICK_R = 14.0                # robot-ball contact
BALL_APPROACH = 2.0            # the kid aims almost AT the ball: continuous dribble
GOAL2_XY = (-5.0, 127.0)       # in SOCCER2: our attacking goal (opposite wall)
SUMO_EXT = float(os.environ.get("GAMES_EXT", "56.0"))
                             # wp extension "through the rival": with
                             # E>=14 the kid does NOT enter the braking band
                             # (BRAKE_AT_CM from the wp) and charges at full

GOAL2_R = 15.0                 # mouth of both wall goals (SOCCER2)
Y_MAX2 = 132.0                # back wall in SOCCER2 (137 cm field)
BALL_FRICTION = 0.98        # per tick (20 ms): ~1.0 s of real rolling

_MODE_ORDER = {"DRIVE": 0, "SUMO": 1, "SUMO2": 2, "SOCCER": 3, "SOCCER2": 4}


def _mode_key(mode):
    return sum(ord(c) for c in mode)


class Body:
    def __init__(self, x, y, th):
        self.x = x
        self.y = y
        self.th = th
        self.vx = 0.0
        self.vy = 0.0
        self.knocked_out = False


def _collide(m1, c1, m2, c2):
    """Elastic 1D impulse + positional separation between two bodies."""
    dx = c2.x - c1.x
    dy = c2.y - c1.y
    d = math.hypot(dx, dy)
    if d >= 2 * BODY_R:
        return False
    nx, ny = dx / max(d, 1e-6), dy / max(d, 1e-6)
    vrel = (c1.vx - c2.vx) * nx + (c1.vy - c2.vy) * ny
    p = max(0.0, vrel) * (2.0 * m1 * m2 / (m1 + m2))
    c1.vx -= p * nx / m1
    c1.vy -= p * ny / m1
    c2.vx += p * nx / m2
    c2.vy += p * ny / m2
    sep = (2 * BODY_R - d) * 0.5
    c1.x -= nx * sep * (m2 / (m1 + m2))
    c1.y -= ny * sep * (m2 / (m1 + m2))
    c2.x += nx * sep * (m1 / (m1 + m2))
    c2.y += ny * sep * (m1 / (m1 + m2))
    return True


def match(mode, seed, MOD):
    RNG = random.Random(seed * 31 + _mode_key(mode))
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
    SIM.BOARD.voltage_scale = RNG.uniform(0.85, 1.0)
    SIM.BIAS_IMU_CS = RNG.uniform(0.0, 0.15)
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
    endgame.set_return(False)          # in games there is no endgame
    B6 = MOD.get("weapon6_brain")
    BRAIN = None
    if B6 is not None:
        BRAIN = B6.brain
        BRAIN.wire(gyro, A2.torque_boost, endgame, console)
    imu = SIM.IMU
    imu.reset_yaw()
    console.connect(pad)
    gyro.set_target_here()
    endgame.start_match()

    kid = KidPilot(pad, RNG, GP, endgame)
    T_PARTIDA = MODE_T[mode]
    TICKS = int(T_PARTIDA // 20)

    # ------- mode setup -------
    door = 0
    laps = 0
    result = ""
    goals_for = 0
    goals_against = 0
    kicks = 0
    rivals = []                       # (body, vmax, mass)
    ally = None
    contact_t = [-1e9]                 # last touch of any body
    if mode in ("SUMO", "SUMO2"):
        is_team = mode == "SUMO2"
        n_rivals = 2 if is_team else 1
        for _ in range(n_rivals):
            ang = RNG.uniform(0.0, 2.0 * math.pi)
            d = RNG.uniform(45.0, 60.0)
            rivals.append((Body(math.cos(ang) * d, math.sin(ang) * d,
                                   RNG.uniform(0, 6.3)),
                            RNG.uniform(30.0, 40.0) if is_team else
                            RNG.uniform(22.0, 34.0),
                            RNG.uniform(2.2, 2.8) if is_team else
                            RNG.uniform(1.0, 1.6)))
        if mode == "SUMO2":
            ang_c = math.atan2(rivals[0][0].y, rivals[0][0].x)
            aa = ang_c + math.pi + RNG.uniform(-0.6, 0.6)
            dd = RNG.uniform(28.0, 42.0)
            ally = (Body(math.cos(aa) * dd, math.sin(aa) * dd, 0.0),
                      RNG.uniform(24.0, 32.0), 1.2)
    elif mode in ("SOCCER", "SOCCER2"):
        ball = Body(RNG.uniform(-25.0, 25.0), RNG.uniform(40.0, 70.0), 0.0)
        if mode == "SOCCER2":
            for _ in range(2):
                rivals.append((Body(RNG.uniform(-35.0, 35.0),
                                       RNG.uniform(88.0, 112.0), 0.0),
                                RNG.uniform(23.0, 29.0), 1.0))
            ally = (Body(RNG.uniform(-25.0, 25.0),
                             RNG.uniform(24.0, 38.0), 0.0),
                      RNG.uniform(26.0, 32.0), 1.2)

    crashes = [RNG.uniform(4000, T_PARTIDA * 0.25)
               for _ in range(RNG.randint(0, 2))]
    riv_info = [dict(hasta=0.0, wx=0.0, wy=0.0, pateo=0.0)
                for _ in rivals]
    aliado_cd = [0.0]
    dbg = dict(rk=0, ak_def=0, ak_atq=0, kk=0, ball_low=0, ball_high=0)
    stalls = []
    for _ in range(RNG.randint(0, 1)):
        stalls.append((RNG.uniform(5000, T_PARTIDA * 0.8),
                        RNG.uniform(1500.0, 3000.0), RNG.choice(("L", "R"))))

    # ------- scripted-body helpers -------
    def _chase(c, wx, wy, vmax):
        aa = math.atan2(wy - c.y, wx - c.x)
        c.vx += (math.cos(aa) * vmax - c.vx) * 0.25
        c.vy += (math.sin(aa) * vmax - c.vy) * 0.25

    def _integra(c):
        c.x += c.vx * 0.02
        c.y += c.vy * 0.02

    def _empuja_robot(c, masa, px, py):
        """Body-vs-OUR bot contact (same model as 1v1).
        Devuelve True si hubo contacto."""
        dx = px - c.x
        dy = py - c.y
        dist = math.hypot(dx, dy)
        if dist >= 2 * BODY_R:
            return False
        contact_t[0] = SIM.CLOCK.ticks_ms()
        nx, ny = dx / max(dist, 1e-6), dy / max(dist, 1e-6)
        v_rel = math.hypot(px - prev_pose[0], py - prev_pose[1]) / 0.02
        v_op = math.hypot(c.vx, c.vy)
        imp = max(0.0, v_rel * 1.0 - v_op * 0.6) * 0.02
        c.vx -= nx * imp / masa * 50.0
        c.vy -= ny * imp / masa * 50.0
        if imp > 0.25:
            DRV.yaw += RNG.uniform(-8.0, 8.0)
        if dist < 1.6 * BODY_R:
            sep = (1.6 * BODY_R - dist) * 0.5
            # they run our wheels; we project it as encoder slide
            # (external push), CAPPED per tick so a deep penetration
            # does not blow up the odometry
            desliz = min(sep * 0.25, 0.3)
            DRV.LEFT.pos_cm -= nx * desliz
            DRV.RIGHT.pos_cm -= nx * desliz
            # displacement scales with rival mass: "mass" models the
            # rival's push weight on the contact point
            c.x += nx * sep * 0.5 * masa
            c.y += ny * sep * 0.5 * masa
        return True

    # ------- fidelity -------
    f1_ticks = 0
    f1_streak = 0
    f1_opposite = 0
    f2_events = 0
    f2_worst = 0.0
    f3_events = 0
    f4_events = 0
    f5_ms = []
    y1_prev = 0.0
    braking = False
    brake_d = 0.0
    brake_t0 = 0.0
    quieto_t = -1.0
    quieto_dist = 0.0
    sin_x1_t = -1.0
    sin_x1_yaw0 = None
    lat_in_flight = None
    prev_pose = (0.0, 0.0, 0.0)

    for k in range(TICKS):
        SIM.CLOCK.advance(20)
        t = SIM.CLOCK.ticks_ms()

        # ---------- KID pilot ----------
        if k == 0:
            pad.buttons[GP.START - 4] = 1
        else:
            pad.buttons[GP.START - 4] = 0

        px, py, pth = endgame.pose()

        if mode == "DRIVE":
            gx, gy = CIRCUIT[door]
            kid.wp_x, kid.wp_y = gx, gy
        elif mode in ("SUMO", "SUMO2"):
            alive = [c for c, _v, _m in rivals if not c.knocked_out]
            if alive:
                cero = min(alive, key=lambda c: (c.x - px) ** 2 + (c.y - py) ** 2)
                drc = math.hypot(cero.x, cero.y)
                if drc > 1e-6:
                    # sustained push: wp BEYOND the rival toward the wall,
                    # so the kid never releases contact
                    kid.wp_x = cero.x + cero.x / drc * SUMO_EXT
                    kid.wp_y = cero.y + cero.y / drc * SUMO_EXT
                    if mode == "SUMO2":
                        # in teams the kid does not chase points outside the
                        # ring: with 2 rivals on him he would self-eject
                        dw = math.hypot(kid.wp_x, kid.wp_y)
                        if dw > RING_R - 12.0:
                            kid.wp_x *= (RING_R - 12.0) / dw
                            kid.wp_y *= (RING_R - 12.0) / dw
        elif mode == "SOCCER":
            # the kid CANNOT reverse and a tangential contact pins the
            # ball against the wall (trace: the ball died in the corner and
            # the kid orbited at 2 cm/s). Tactics in 3 roles:
            #   ALIGNED    -> dash THROUGH the goal (wp 35 cm past the goal:
            #                 he does not fall in his braking band before scoring)
            #   IN CONTACT misaligned -> lateral dodge 26 cm on HIS side,
            #                 moving away BEFORE re-entering (moving toward
            #                 home does not kick: he left the contact radius)
            #   CLEAR      -> entry point 24 cm BEHIND the ball, with a free
            #                 path (go around it and re-align)
            atk = GOAL_XY
            goal_ang = math.atan2(atk[1] - ball.y, atk[0] - ball.x)
            cg, sg = math.cos(goal_ang), math.sin(goal_ang)
            dxp = ball.x - px
            dyp = ball.y - py
            d_ball = math.hypot(dxp, dyp)
            alineado = dxp * cg + dyp * sg >= 8.0
            if alineado:
                kid.wp_x = ball.x + cg * 20.0
                kid.wp_y = ball.y + sg * 20.0
            elif d_ball < 20.0:
                lado_sin = (-sg, cg)
                lado = 1.0 if (dxp * lado_sin[0] + dyp * lado_sin[1]) >= 0 else -1.0
                kid.wp_x = px - sg * lado * 26.0
                kid.wp_y = py + cg * lado * 26.0
            else:
                kid.wp_x = ball.x - cg * 24.0
                kid.wp_y = ball.y - sg * 24.0
        elif mode == "SOCCER2":
            # here the kid is SUPPORT: it stays NEAR the ball (at +6
            # it does not reach KICK_R and does not touch it: with kid
            # aim its whacks break the expert ally's play, A/B proven)
            atk = GOAL2_XY
            goal_ang = math.atan2(atk[1] - ball.y, atk[0] - ball.x)
            kid.wp_x = ball.x + math.cos(goal_ang) * 6.0
            kid.wp_y = ball.y + math.sin(goal_ang) * 6.0
        kid.step(t, (px, py, pth), SIM.IMU.get_yaw())

        # mode events (field ground truth)
        if mode == "DRIVE" and t >= 1000:
            if math.hypot(px - kid.wp_x, py - kid.wp_y) < DOOR_RADIUS:
                door += 1
                if door % len(CIRCUIT) == 0:
                    laps += 1
                door %= len(CIRCUIT)

        elif mode in ("SUMO", "SUMO2"):
            for ri, (rc, vmax_r, masa_r) in enumerate(rivals):
                if rc.knocked_out:
                    continue
                if _empuja_robot(rc, masa_r, px, py):
                    continue        # in contact ONLY push (like 1v1)
                                # sumo: in 1v1 charges straight; in 2v2 posture between prey
                # and center, charges from close and self-cares near the edge
                if ally:
                    dkid = (px - rc.x) ** 2 + (py - rc.y) ** 2
                    dali = ((ally[0].x - rc.x) ** 2 +
                            (ally[0].y - rc.y) ** 2)
                    prey = (px, py) if dkid < dali else \
                        (ally[0].x, ally[0].y)
                    do = math.hypot(rc.x, rc.y)
                    dprey = math.hypot(prey[0] - rc.x, prey[1] - rc.y)
                    if do > RING_R - 12.0:
                        _chase(rc, 0.0, 0.0, vmax_r)
                    elif dprey < 42.0:
                        _chase(rc, prey[0], prey[1], vmax_r)
                    else:
                        _chase(rc, rc.x * 0.30 + prey[0] * 0.70,
                               rc.y * 0.30 + prey[1] * 0.70, vmax_r)
                else:
                    _chase(rc, px, py, vmax_r)
                if os.environ.get("GAMES_DEBUG"):
                    riv_info[ri]["lt"] = t
            if ally:
                alive = [c for c, _v, _m in rivals if not c.knocked_out]
                if alive:
                    obj = min(alive, key=lambda c: (c.x - ally[0].x) ** 2 +
                              (c.y - ally[0].y) ** 2)
                    do = math.hypot(obj.x, obj.y)
                    lim = RING_R - 12.0
                    if do > lim:
                        esc = lim / do
                        ox, oy = obj.x * esc, obj.y * esc
                    else:
                        ox, oy = obj.x, obj.y
                    _chase(ally[0], ox, oy, ally[1])
            if ally:
                for rc, _v, mr in rivals:
                    if not rc.knocked_out:
                        _collide(mr, rc, ally[1], ally[0])
            for i in range(len(rivals)):
                for j in range(i + 1, len(rivals)):
                    _collide(rivals[i][2], rivals[i][0],
                            rivals[j][2], rivals[j][0])
            for c, _v, _m in rivals:
                _integra(c)
            if ally:
                _integra(ally[0])
            riv_fuera = sum(1 for c, _v, _m in rivals
                            if c.knocked_out or math.hypot(c.x, c.y) > RING_R)
            for c, _v, _m in rivals:
                if math.hypot(c.x, c.y) > RING_R and not c.knocked_out:
                    c.knocked_out = True
                    c.vx = c.vy = 0.0
            if os.environ.get("GAMES_TRACE") and k % 25 == 0:
                print("  t=%.1f r=(%.1f,%.1f) rival0=(%.1f,%.1f) v=(%.1f,%.1f) "
                      "knocked_out=%s lt=%.1f f=%.1f mode=%s y1=%.2f" %
                      (t / 1000.0, px, py, rivals[0][0].x, rivals[0][0].y,
                       rivals[0][0].vx, rivals[0][0].vy,
                       rivals[0][0].knocked_out,
                       riv_info[0].get("lt", -9.0) / 1000.0,
                       math.hypot(px - rivals[0][0].x,
                                  py - rivals[0][0].y),
                       console.mode_name(), pad.axes[1]))
            nosotros_afuera = math.hypot(px, py) > RING_R
            if riv_fuera == len(rivals) and not nosotros_afuera:
                result = "WON"
                break
            if nosotros_afuera and riv_fuera < len(rivals):
                result = "LOST"
                break

        elif mode in ("SOCCER", "SOCCER2"):
            dx = px - ball.x
            dy = py - ball.y
            dist = math.hypot(dx, dy)
            if dist < KICK_R:
                nx, ny = -dx / max(dist, 1e-6), -dy / max(dist, 1e-6)
                vrx = (px - prev_pose[0]) / 0.02
                vry = (py - prev_pose[1]) / 0.02
                w = max(0.0, vrx * nx + vry * ny)
                obj_v = w * 1.15 + 2.0
                ball.vx += (nx * obj_v - ball.vx) * 0.5
                ball.vy += (ny * obj_v - ball.vy) * 0.5
                kicks += 1
                if os.environ.get("GAMES_DEBUG"):
                    dbg["kk"] += 1

            if mode == "SOCCER2":
                for ri, (rc, vmax_r, _m) in enumerate(rivals):
                    info = riv_info[ri]
                    if t >= info["hasta"]:
                        dr = math.hypot(RIVAL_GOAL_XY[0] - ball.x,
                                        RIVAL_GOAL_XY[1] - ball.y)
                        axn = (RIVAL_GOAL_XY[0] - ball.x) / max(dr, 1e-6)
                        ayn = (RIVAL_GOAL_XY[1] - ball.y) / max(dr, 1e-6)
                        # they surround the ball from opposite sides (no piling up)
                        lat = 7.0 if ri == 0 else -7.0
                        # rivals are kids too: they decide every 220-450 ms
                        # and see the ball with +-5 cm of noise
                        info["wx"] = (ball.x - axn * 10.0 - ayn * lat +
                                      RNG.uniform(-5.0, 5.0))
                        info["wy"] = (ball.y - ayn * 10.0 + axn * lat +
                                      RNG.uniform(-5.0, 5.0))
                        info["hasta"] = t + RNG.uniform(220.0, 450.0)
                    _chase(rc, info["wx"], info["wy"], vmax_r)
                    dbx = rc.x - ball.x
                    dby = rc.y - ball.y
                    if (math.hypot(dbx, dby) < KICK_R and
                            t >= info["pateo"] and
                            math.hypot(ball.vx, ball.vy) < 12.0):
                        dr2 = math.hypot(RIVAL_GOAL_XY[0] - ball.x,
                                         RIVAL_GOAL_XY[1] - ball.y)
                        axn = (RIVAL_GOAL_XY[0] - ball.x) / max(dr2, 1e-6)
                        ayn = (RIVAL_GOAL_XY[1] - ball.y) / max(dr2, 1e-6)
                        # real kid: DRIVES with shoves away from the goal,
                        # only SHOOTS inside 45 cm of the goal
                        v = math.hypot(rc.vx, rc.vy)
                        if dr2 < 30.0:
                            ru = RNG.uniform(-0.8, 0.8)
                            vf = min(max(v * 1.2 + 4.0, dr2 * 1.1), 20.0)
                        else:
                            ru = RNG.uniform(-0.35, 0.35)
                            vf = min(v * 1.15 + 2.0, 12.0)
                        cr, sr = math.cos(ru), math.sin(ru)
                        ball.vx = (axn * cr - ayn * sr) * vf
                        ball.vy = (axn * sr + ayn * cr) * vf
                        # 2v2 balance: rival cooldown (was 800) so the
                        # kid + ally can contest the ball
                        info["pateo"] = t + 1200.0
                        if os.environ.get("GAMES_DEBUG"):
                            dbg["rk"] += 1
                if ally:
                    # ally WITH THE WEAPONS (same software as ours): direct
                    # ball hunter, no decision delay; inside OUR goal box it
                    # defends the mouth (between ball and goal line) and
                    # clears, outside it drives or shoots.
                    dp_gol = math.hypot(ball.x - RIVAL_GOAL_XY[0],
                                        ball.y - RIVAL_GOAL_XY[1])
                    da = math.hypot(GOAL2_XY[0] - ball.x,
                                    GOAL2_XY[1] - ball.y)
                    en_caja = dp_gol < 40.0
                    v_pelota = math.hypot(ball.vx, ball.vy)
                    if en_caja:
                        if v_pelota > 12.0:
                            # shot in progress: it stands on the ball-goal LINE
                            gx = RIVAL_GOAL_XY[0] + (ball.x -
                                                    RIVAL_GOAL_XY[0]) / \
                                max(dp_gol, 1e-6) * 9.0
                            gy = RIVAL_GOAL_XY[1] + (ball.y -
                                                    RIVAL_GOAL_XY[1]) / \
                                max(dp_gol, 1e-6) * 9.0
                        else:
                            # slow ball in our box: comes OUT TO CONTEST IT
                            gx, gy = ball.x, ball.y
                        _chase(ally[0], gx, gy, ally[1] + 5.0)
                    else:
                        _chase(ally[0], ball.x, ball.y, ally[1] + 5.0)
                    dbx = ally[0].x - ball.x
                    dby = ally[0].y - ball.y
                    alcance = (KICK_R + 6.0) if en_caja else KICK_R
                    v_pel_ok = (True if en_caja else v_pelota < 12.0)
                    if (math.hypot(dbx, dby) < alcance and
                            t >= aliado_cd[0] and v_pel_ok):
                        cr, sr = 1.0, 0.0
                        if dp_gol < da:
                            # LONG clear toward the top of the field
                            # (never against the side wall)
                            axn = (GOAL2_XY[0] - ball.x) / \
                                max(da, 1e-6)
                            ayn = (GOAL2_XY[1] - ball.y) / \
                                max(da, 1e-6)
                            ru = RNG.uniform(-0.45, 0.45)
                            cr, sr = math.cos(ru), math.sin(ru)
                            vf = RNG.uniform(26.0, 34.0)
                            ball.vx = (axn * cr - ayn * sr) * vf
                            ball.vy = (axn * sr + ayn * cr) * vf
                            if os.environ.get("GAMES_DEBUG"):
                                dbg["ak_def"] += 1
                        else:
                            axn = (GOAL2_XY[0] - ball.x) / max(da, 1e-6)
                            ayn = (GOAL2_XY[1] - ball.y) / max(da, 1e-6)
                            v = math.hypot(ally[0].vx, ally[0].vy)
                            if da < 30.0:
                                ru = RNG.uniform(-0.7, 0.7)
                                vf = min(max(v * 1.2 + 4.0, da * 1.1), 24.0)
                            else:
                                ru = RNG.uniform(-0.25, 0.25)
                                vf = min(v * 1.15 + 2.0, 12.0)
                            cr, sr = math.cos(ru), math.sin(ru)
                            ball.vx = (axn * cr - ayn * sr) * vf
                            ball.vy = (axn * sr + ayn * cr) * vf
                            if os.environ.get("GAMES_DEBUG"):
                                dbg["ak_atq"] += 1
                        aliado_cd[0] = t + (250.0 if en_caja else 700.0)
                for c, _v, _m in rivals:
                    _empuja_robot(c, _m, px, py)
                for i in range(len(rivals)):
                    for j in range(i + 1, len(rivals)):
                        _collide(rivals[i][2], rivals[i][0],
                                rivals[j][2], rivals[j][0])
                if ally:
                    _empuja_robot(ally[0], ally[2], px, py)
                    for rc, _v, mr in rivals:
                        _collide(mr, rc, ally[2], ally[0])
                for c, _v, _m in rivals:
                    _integra(c)
                if ally:
                    _integra(ally[0])

            if os.environ.get("GAMES_DEBUG"):
                if ball.y < 68.5:
                    dbg["ball_low"] += 1
                else:
                    dbg["ball_high"] += 1
            ball.vx *= BALL_FRICTION
            ball.vy *= BALL_FRICTION
            ball.x += ball.vx * 0.02
            ball.y += ball.vy * 0.02
            if abs(ball.x) > 60.0:
                ball.vx *= -0.5
                ball.x = 60.0 * (1 if ball.x > 0 else -1)
            y_max = Y_MAX2 if mode == "SOCCER2" else 250.0
            if ball.y > y_max or ball.y < 5.0:
                ball.vy *= -0.5
                ball.y = min(y_max, max(5.0, ball.y))
            atq_xy, r_gol = (GOAL2_XY, GOAL2_R) if mode == "SOCCER2" \
                else (GOAL_XY, GOAL_R)
            if math.hypot(ball.x - atq_xy[0],
                          ball.y - atq_xy[1]) < r_gol:
                goals_for += 1
                ball.x, ball.y = RNG.uniform(-25, 25), RNG.uniform(40, 70)
                ball.vx = ball.vy = 0.0
            if (mode == "SOCCER2" and
                    math.hypot(ball.x - RIVAL_GOAL_XY[0],
                               ball.y - RIVAL_GOAL_XY[1]) < GOAL2_R):
                goals_against += 1
                if os.environ.get("GAMES_DEBUG"):
                    vb = math.hypot(ball.vx, ball.vy)
                    dbg["gol_v"] = dbg.get("gol_v", 0.0) + vb
                    dbg["gol_n"] = dbg.get("gol_n", 0) + 1
                ball.x, ball.y = RNG.uniform(-25, 25), RNG.uniform(40, 70)
                ball.vx = ball.vy = 0.0
            if os.environ.get("GAMES_TRACE") and k % 25 == 0:
                tail = ""
                for _i, (c, _v, _m) in enumerate(rivals):
                    tail += " r%d=(%.1f,%.1f)" % (_i, c.x, c.y)
                if ally:
                    tail += " AL=(%.1f,%.1f)" % (ally[0].x, ally[0].y)
                print("  t=%.1f robot=(%.1f,%.1f) th=%.0f ball=(%.1f,%.1f) "
                      "v_pel=(%.1f,%.1f) d=%.1f wp=(%.1f,%.1f) y1=%.2f "
                      "console=%s%s" %
                      (t / 1000.0, px, py, pth, ball.x, ball.y,
                       ball.vx, ball.vy, dist, kid.wp_x, kid.wp_y,
                       pad.axes[1], console.mode_name(), tail))

        # ---------- hostile physics ----------
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

        console._cycle()
        gyro._tick()
        if BRAIN is not None:
            BRAIN.step()
        tb.step()
        endgame._odometry()
        endgame._endgame_logic()
        DRV.step(0.02)

        # ---------- stick fidelity ----------
        p2 = endgame.pose()
        pth_rad = math.radians(pth)
        dprog = (p2[0] - prev_pose[0]) * math.cos(pth_rad) + \
                (p2[1] - prev_pose[1]) * math.sin(pth_rad)
        dist2 = math.hypot(p2[0] - prev_pose[0], p2[1] - prev_pose[1])
        v_cm_s = dprog / 0.02
        y1i = kid.y1
        x1i = kid.x1
        yaw_now = SIM.IMU.get_yaw()

        # the rival pushing us is NOT a stick defect
        pushed = (t - contact_t[0] < 1000) or \
            any(lo - 200 <= t <= lo + 1000 for lo in crashes)
        if not pushed and y1i > UMBRAL_AV_KID:
            f1_streak += 1
            if v_cm_s < F1_V_CONTRARIO:
                f1_opposite += 1
                if "GAMES_TRACE" in os.environ:
                    print("  tick t=%.2f modo_mando=%s y1=%.2f x1=%.2f "
                          "v=%.1f yaw=%.1f pth=%.1f dpos=(%.2f,%.2f)" %
                          (t / 1000.0, console.mode_name(), y1i, x1i,
                           v_cm_s, yaw_now, pth, prev_pose[0], prev_pose[1]))
        elif pushed:
            f1_streak = 0
            f1_opposite = 0
        else:
            if f1_streak >= F1_RACHA_MIN and f1_opposite * 2 > f1_streak:
                f1_ticks += f1_streak
                if "GAMES_TRACE" in os.environ:
                    print("F1 t=%.1f mode=%s streak=%d opposite=%d "
                          "modo_mando=%s yaw=%.1f" %
                          (t / 1000.0, mode, f1_streak, f1_opposite,
                           console.mode_name(), yaw_now))
            f1_streak = 0
            f1_opposite = 0

        if pushed:
            braking = False
        elif not braking:
            if y1_prev >= 0.4 and y1i < 0.02 and abs(v_cm_s) > 10.0:
                braking = True
                brake_d = 0.0
                brake_t0 = t
        elif y1i > 0.05:
            braking = False          # the kid commanded again: not a slide
        else:
            brake_d += dist2
            if abs(v_cm_s) < 1.0 or t - brake_t0 > 2000:
                if brake_d > F2_CM_MAX:
                    f2_events += 1
                    f2_worst = max(f2_worst, brake_d)
                    if "GAMES_TRACE" in os.environ:
                        print("F2 t=%.1f slide=%.1f dur=%.1fs stalls=%s "
                              "modo_mando=%s" %
                              (t / 1000.0, brake_d, (t - brake_t0) / 1000.0,
                               [(a, b) for a, b, _ in stalls],
                               console.mode_name()))
                braking = False

        if lat_in_flight is None and y1i >= 0.5:
            lat_in_flight = t
        if lat_in_flight is not None and v_cm_s >= F5_V_STALL:
            f5_ms.append(t - lat_in_flight)
            lat_in_flight = None
        elif lat_in_flight is not None and y1i < 0.5:
            lat_in_flight = None

        if y1i <= 0.02 and x1i <= 0.02 and abs(pad.axes[0]) < 0.05:
            if quieto_t < 0:
                quieto_t = t
                quieto_dist = 0.0
            quieto_dist += dist2
            if t - quieto_t > 1000 and quieto_dist > F3_CM_MAX:
                f3_events += 1
                quieto_t = t
                quieto_dist = 0.0
        else:
            quieto_t = -1.0
            quieto_dist = 0.0

        if abs(x1i) < 0.05:
            in_crash_window = any(lo - 500 <= t <= lo + 6000
                                    for lo in crashes)
            if sin_x1_t < 0:
                sin_x1_t = t
                sin_x1_yaw0 = yaw_now
            elif (not in_crash_window and t - sin_x1_t > 1000 and
                    abs(wrap180(yaw_now - sin_x1_yaw0)) > F4_GRADOS):
                f4_events += 1
                if "GAMES_TRACE" in os.environ:
                    print("F4 t=%.1f d_yaw=%.2f dur=%.1fs modo_mando=%s "
                          "ema=%+.3f y1=%.2f x1=%.3f tgt=%.1f "
                          "enabled=%s yaw=%.1f" %
                          (t / 1000.0, wrap180(yaw_now - sin_x1_yaw0),
                           (t - sin_x1_t) / 1000.0, console.mode_name(),
                           console._ema_x, y1i, x1i,
                           gyro.target, gyro.enabled, yaw_now))
                sin_x1_t = -1.0
                sin_x1_yaw0 = None
            elif os.environ.get("GAMES_DEBUG"):
                print("  F4row t=%.1f mode=%s x1=%+.4f y1=%.2f ema=%+.4f "
                      "yaw=%.2f tgt=%.2f lerr=%.2f L=(%.1f,%.3f) "
                      "R=(%.1f,%.3f)" %
                      (t / 1000.0, console.mode_name(), x1i, y1i,
                       console._ema_x, yaw_now, gyro.target,
                       gyro.last_error, DRV.LEFT.rpm, DRV.LEFT.effort,
                       DRV.RIGHT.rpm, DRV.RIGHT.effort))
        else:
            sin_x1_t = -1.0
            sin_x1_yaw0 = None

        y1_prev = y1i
        prev_pose = p2

        if result or endgame.ms_elapsed() >= T_PARTIDA:
            break

    if f1_streak >= F1_RACHA_MIN and f1_opposite * 2 > f1_streak:
        f1_ticks += f1_streak
        if "GAMES_TRACE" in os.environ:
            print("F1 FINAL streak=%d opposite=%d (%s)" %
                  (f1_streak, f1_opposite, result))

    if os.environ.get("GAMES_DEBUG"):
        gn = dbg.get("gol_n", 0)
        print("DBG %s kicks rk=%d ak_def=%d ak_atq=%d kk=%d "
              "ball_low=%d ball_high=%d goals_for=%d goals_against=%d "
              "gol_v_avg=%.1f" %
              (mode, dbg["rk"], dbg["ak_def"], dbg["ak_atq"], dbg["kk"],
               dbg["ball_low"], dbg["ball_high"], goals_for, goals_against,
               (dbg.get("gol_v", 0.0) / gn) if gn else -1))

    if mode in ("SUMO", "SUMO2") and not result:
        riv_fuera = sum(1 for c, _v, _m in rivals
                        if c.knocked_out or math.hypot(c.x, c.y) > RING_R)
        if mode == "SUMO":
            result = "DRAW"
        else:
            result = "WON" if riv_fuera == len(rivals) else \
                "DRAW outs=%d" % riv_fuera
    if mode == "DRIVE":
        result = "doors=%d" % door
    elif mode in ("SOCCER", "SOCCER2"):
        if mode == "SOCCER":
            result = "goals=%d" % goals_for
        else:
            result = ("WON" if goals_for > goals_against else
                         "LOST" if goals_for < goals_against else "DRAW") + \
                " %d-%d" % (goals_for, goals_against)

    f5_avg = sum(f5_ms) / len(f5_ms) if f5_ms else -1.0
    return {"seed": seed, "mode": mode, "result": result,
            "goals": goals_for if mode in ("SOCCER", "SOCCER2") else -1,
            "conceded": goals_against if mode == "SOCCER2" else -1,
            "kicks": kicks if mode in ("SOCCER", "SOCCER2") else -1,
            "doors": door if mode == "DRIVE" else -1,
            "laps": laps if mode == "DRIVE" else -1,
            "won": ("WON" in result) if mode in ("SUMO", "SUMO2",
                                                         "SOCCER2") else False,
            "f1": f1_ticks, "f2": f2_events, "f2_cm": f2_worst,
            "f3": f3_events, "f4": f4_events, "f5": f5_avg}


def evaluate(mode, n):
    base = 900000 + _mode_key(mode) % 5000
    with multiprocessing.Pool(WORKERS) as pool:
        res = pool.map(_mode_worker, [(mode, base + i) for i in range(n)],
                       chunksize=8)
    m = [r for r in res if r["mode"] == mode]
    if not m:
        return
    f1 = sum(1 for r in m if r["f1"] > 25)
    f2 = sum(1 for r in m if r["f2"] > 0)
    f3 = sum(1 for r in m if r["f3"] > 0)
    f4 = sum(1 for r in m if r["f4"] > 0)
    f5_ok = [r["f5"] for r in m if r["f5"] > 0]
    f5_avg = sum(f5_ok) / len(f5_ok) if f5_ok else -1
    print("\n== MODE %s : %d matches %s ==" % (mode, len(m), PILOT))
    if mode in ("SUMO", "SUMO2"):
        g = sum(1 for r in m if r["won"])
        p = sum(1 for r in m if r["result"].startswith("LOST"))
        print("%s won %.1f%% / lost %.1f%% / draws %.1f%%" %
              (mode, 100.0 * g / len(m), 100.0 * p / len(m),
               100.0 * (len(m) - g - p) / len(m)))
    elif mode in ("SOCCER", "SOCCER2"):
        gs = [r["goals"] for r in m]
        ks = [r["kicks"] for r in m]
        g = sum(1 for r in m if r["won"])
        p = sum(1 for r in m if r["result"].startswith("LOST"))
        extra = "  conceded avg %.2f" % \
            (sum(r["conceded"] for r in m) / len(m)) if mode == "SOCCER2" else ""
        print("%s goals: avg %.2f [0:%d 1:%d 2:%d 3+:%d] kicks/p %.1f | "
              "we-win %.1f%% / we-lose %.1f%%%s" %
              (mode, sum(gs) / len(gs), gs.count(0), gs.count(1),
               gs.count(2), sum(1 for x in gs if x >= 3),
               sum(ks) / len(ks), 100.0 * g / len(m),
               100.0 * p / len(m), extra))
    else:
        ps = [r["doors"] for r in m]
        vs = [r["laps"] for r in m]
        print("DRIVE doors: avg %.2f  min %d  max %d | "
              "full laps: avg %.2f  max %d" %
              (sum(ps) / len(ps), min(ps), max(ps),
               sum(vs) / len(vs), max(vs)))
    print("FIDELITY: opposites(F1)=%d  slide(F2)=%d  involuntary(F3)=%d  "
          "pan(F4)=%d | avg latency=%.0f ms" % (f1, f2, f3, f4, f5_avg))
    foul = [r for r in m if r["f1"] > 25 or r["f2"] or r["f3"] or r["f4"]]
    if foul:
        print("  matches with fault: %d/%d" % (len(foul), len(m)))
        for r in foul[:5]:
            print("  seed %d: f1=%d f2=%d(%.1fcm) f3=%d f4=%d  %s" %
                  (r["seed"], r["f1"], r["f2"], r["f2_cm"],
                   r["f3"], r["f4"], r["result"]))
    return m


def _mode_worker(arg):
    mode, seed = arg
    MOD = _reload()
    return match(mode, seed, MOD)


def games_campaign():
    if MODE == "ALL":
        modos = ("DRIVE", "SUMO", "SUMO2", "SOCCER", "SOCCER2")
    else:
        modos = (MODE,)
    print("== CAMPAIGN INDIVIDUAL AND TEAM GAMES == pilot=%s "
          "n=%d/%s processes=%d" % (PILOT, N_MATCHES, MODE, WORKERS))
    for mode in modos:
        evaluate(mode, N_MATCHES)


if __name__ == "__main__":
    games_campaign()
