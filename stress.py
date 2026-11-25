# =========================================================
# STRESS BATTERY - Team Robots Legends (FUSAMO)
# 30 random matches. The pilot plays WITH THE STICKS
# (virtual gamepad + pilot_gamepad: the same code that runs
# on the board) while the plant attacks the robot:
#   - crashes of up to 40 degrees of spin (0 to 3 per match)
#   - physical wheel stalls of 2-5 s (0 to 2, either wheel)
#   - battery between 82% and 100%
#   - IMU drift up to 0.2 deg/s + gaussian noise
# CRITERIA (per match):
#   P1: every crash spin stays < 3 degrees (measured 10 s
#       after the crash, with the Gyro-Lock active)
#   P2: stable heading in cruise (max err < 12 degrees, not
#       counting crash windows nor the pilot's turn)
#   P3: ENDGAME returns home and stays NAILED (<= 6 cm)
#   P4: not a single exception in any match
# USAGE: python3 stress.py
# =========================================================
import sys
import importlib
import os

import simulator_xrp as SIM          # injects plant + stubs, no match run

_MODULOS = ("weapon3_curves", "weapon2_torque_boost", "weapon4_traction",
            "weapon5_endgame", "weapon1_gyro_lock", "pilot_gamepad")


def reload_modules():
    for nombre in _MODULOS:
        importlib.reload(sys.modules[nombre])
    return sys.modules


def new_match(seed, MOD):
    import random
    RNG = random.Random(seed)

    A1 = MOD["weapon1_gyro_lock"]
    A2 = MOD["weapon2_torque_boost"]
    A4 = MOD["weapon4_traction"]
    A5 = MOD["weapon5_endgame"]
    MAIN = MOD["pilot_gamepad"]

    DRV = SIM.DRIVETRAIN
    GP = SIM.GamepadSim

    # -------- plant at zero + random conditions --------
    SIM.CLOCK.t = 0
    DRV.LEFT = SIM.WheelSim()
    DRV.RIGHT = SIM.WheelSim()
    DRV.yaw = 0.0
    DRV.source = "idle"
    SIM.BOARD.voltage_scale = RNG.uniform(0.82, 1.0)
    bias = RNG.uniform(0.0, 0.2)
    SIM.BIAS_IMU_CS = bias
    pad = GP.nueva()

    # -------- full chain, same as main_match.py --------
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
    endgame.set_return(True)
    A5.V_RETURN = 0.85
    imu = SIM.IMU
    imu.reset_yaw()
    console.connect(pad)
    gyro.set_target_here()

    # -------- pilot script (random per seed) --------
    turn_t = RNG.uniform(25000.0, 50000.0)
    turn_delta = RNG.choice((-180.0, 180.0, 90.0, -90.0))
    vel = RNG.uniform(0.38, 0.55)
    target_dist = RNG.uniform(60.0, 110.0)
    crashes = [RNG.uniform(5000, 120000) for _ in range(RNG.randint(0, 3))]
    crashes = [t for t in crashes if not (turn_t - 1500 <= t <= turn_t + 6500)]
    stalls = []
    for _ in range(RNG.randint(0, 2)):
        t0 = RNG.uniform(5000, 115000)
        stalls.append((t0, RNG.uniform(2000.0, 5000.0), RNG.choice(("L", "R"))))

    # -------- metrics --------
    faults = []
    max_err = 0.0
    crash_regs = []
    p1_pending = []
    turn_started = False
    turn_done = False    # the pilot releases the stick forever after the turn
    target_heading = 0.0

    # -------- match (150 s in 20 ms steps) --------
    for k in range(7500):
        SIM.CLOCK.advance(20)
        t = SIM.CLOCK.ticks_ms()

        # ---------- pilot with the sticks ----------
        pad.buttons[GP.START - 4] = 1 if 400 <= t < 420 else 0

        if not turn_started:
            if t >= turn_t:
                turn_started = True
                target_heading = SIM.IMU.get_yaw() + turn_delta
                pad.axes[GP.Y1] = 0.0
                pad.axes[GP.X1] = 1.0 if turn_delta > 0 else -1.0
            elif t >= 2000:
                # drives toward its target distance and releases on arrival
                if endgame.home_distance() < target_dist:
                    pad.axes[GP.Y1] = vel
                elif pad.axes[GP.Y1] > 0.0:
                    pad.axes[GP.Y1] = 0.0
        elif not turn_done:
            # the pilot turns with stick X1 guided by the IMU
            err_giro = (target_heading - SIM.IMU.get_yaw() + 180.0) % 360.0 - 180.0
            if abs(err_giro) > 4.0 and pad.axes[GP.X1] == 0.0:
                pad.axes[GP.X1] = 1.0 if err_giro > 0 else -1.0
            elif abs(err_giro) <= 4.0 and pad.axes[GP.X1] != 0.0:
                pad.axes[GP.X1] = 0.0
                turn_done = True

        # ---------- physical events ----------
        for lo, dur, wheel in stalls:
            if lo <= t < lo + dur:
                DRV.LEFT.stalled = (wheel == "L")
                DRV.RIGHT.stalled = (wheel == "R")
            elif getattr(DRV.LEFT, "stalled", False) and wheel == "L" and t >= lo + dur:
                DRV.LEFT.stalled = False
            elif getattr(DRV.RIGHT, "stalled", False) and wheel == "R" and t >= lo + dur:
                DRV.RIGHT.stalled = False
        for lo in crashes:
            if lo <= t < lo + 20:
                salto = RNG.uniform(15.0, 40.0) * RNG.choice((-1.0, 1.0))
                DRV.yaw += salto
                crash_regs.append((lo, salto))
                p1_pending.append([lo, lo + 10000])
        DRV.yaw += RNG.gauss(0.0, 0.05)

        if "STRESS_DEBUG" in os.environ and t >= 136000 and k % 25 == 0:
            A3M = MOD["weapon3_curves"]
            print("DBG t=%.1f mode=%s endgame=%s return_on=%s gyro_en=%s "
                  "dist=%.1f base=(%.2f %.2f) tgt=%.1f yaw=%.1f V=%.2f "
                  "Y1=%.2f X1=%.2f suav_v=%.2f suav_g=%.2f cmd=(%.2f %.2f) e=(%.2f %.2f)"
                  % (t / 1000.0, console.mode_name(), endgame.is_endgame(),
                     endgame.return_on, gyro.enabled, endgame.home_distance(),
                     gyro.base_l, gyro.base_r, gyro.get_target(),
                     SIM.IMU.get_yaw(), A5.V_RETURN,
                     pad.axes[1], pad.axes[0],
                     A3M.slew_fwd.v, A3M.slew_turn.v,
                     tb._cmd_l, tb._cmd_r,
                     tb._left.e, tb._right.e))

        # ---------- weapons (same order as on the board) ----------
        console._cycle()
        gyro._tick()
        tb.step()
        endgame._odometry()
        endgame._endgame_logic()
        DRV.step(0.02)

        # ---------- P2 metrics ----------
        if console._mode in (MAIN.STRAIGHT, MAIN.STOP) and gyro.enabled:
            in_crash_window = any(lo - 200 <= t <= lo + 6000 for lo, _ in crash_regs)
            if not in_crash_window:
                e = abs(gyro.get_error())
                if e > max_err:
                    max_err = e

        # ---------- P1 metrics ----------
        stall_active = any(lo - 200 <= t <= lo + dur + 2000 for lo, dur, _ in stalls)
        if "STRESS_DEBUG" in os.environ:
            for lo, _d in crash_regs:
                if lo <= t <= lo + 12000 and k % 25 == 0:
                    print("P1DBG t=%.1f mode=%s err=%.2f base=(%.2f %.2f) "
                          "tgt=%.1f yaw=%.1f atascos_vig=%s en_giro_win=%s"
                          % (t / 1000.0, console.mode_name(), gyro.get_error(),
                             gyro.base_l, gyro.base_r, gyro.get_target(),
                             SIM.IMU.get_yaw(), stall_active,
                             turn_t - 1500 <= t <= turn_t + 6500))
        alive = []
        for lo, deadline in p1_pending:
            if t < deadline or stall_active:
                alive.append((lo, deadline))
                continue
            if console._mode in (MAIN.STRAIGHT, MAIN.STOP) and gyro.enabled:
                e = abs(gyro.get_error())
                if e > 3.0:
                    faults.append("P1: crash t=%.1f residual err %.1f" % (lo / 1000.0, e))
            elif t < deadline + 5000:
                alive.append((lo, deadline))
        p1_pending = alive

    # ---------------- closing ----------------
    dist = endgame.home_distance()
    nailed = tb.nailed or (abs(DRV.LEFT.rpm) < 1.5 and abs(DRV.RIGHT.rpm) < 1.5)
    in_zone = dist <= A5.HOME_TOL_CM and nailed
    if not in_zone:
        faults.append("P3: final dist=%.1f nailed=%s (axes %s/%s, cmd %.2f/%.2f, "
                      "rpm %.2f/%.2f, at_home=%s)"
                      % (dist, nailed, tb.state_left, tb.state_right,
                         tb._cmd_l, tb._cmd_r,
                         DRV.LEFT.rpm, DRV.RIGHT.rpm, endgame._at_home))
    if max_err > 12.0:
        faults.append("P2: max cruise err %.1f" % max_err)

    return {"seed": seed, "in_zone": in_zone, "dist": dist,
            "max_err": max_err, "faults": faults,
            "bateria": SIM.BOARD.voltage_scale, "bias": bias,
            "crashes": len(crash_regs), "stalls": len(stalls)}


def stress(n=30):
    print("== STRESS BATTERY: %d random matches (virtual physical sticks) ==" % n)
    bads = []
    for i in range(n):
        MOD = reload_modules()
        r = new_match(1000 + i * 17, MOD)
        mark = "OK  " if (r["in_zone"] and not r["faults"]) else "BAD"
        print("match %2d | %s | end=%5.1f cm | max err=%5.2f | bat=%.2f | "
              "bias=%.2f | crashes=%d stalls=%d%s"
              % (i, mark, r["dist"], r["max_err"], r["bateria"], r["bias"],
                 r["crashes"], r["stalls"],
                 (" | " + "; ".join(r["faults"])) if r["faults"] else ""))
        if mark == "BAD":
            bads.append(r)
    print()
    print("RESULT: %d/%d matches approved" % (n - len(bads), n))
    if bads:
        print("Failure detail:")
        for r in bads:
            for f in r["faults"]:
                print("  - match %d: %s" % (r["seed"], f))
    return bads


if __name__ == "__main__":
    stress(30)
