#!/usr/bin/env python3
"""ROBOT COACH — Team Robots Legends (FUSAMO).

100% OFFLINE assistant for the developers. NO API, NO token, NO network,
NO config file. It runs anywhere Python 3 runs (laptop, school PC, even the
robot's laptop between matches) and it never runs during a match.

Why it exists: the on-board brain (Weapon 6) already thinks at 50 Hz during
the match. The Coach is the BETWEEN-MATCHES teammate: it audits constants,
explains every weapon in kid-friendly words, drills calibration routines,
summarizes battery logs and keeps the team memory of lessons learned.

Commands:
  python3 coach.py audit                    # safe-range sweep of every weapon + wiring check
  python3 coach.py explain weapon1          # kid-friendly deep dive of one weapon
  python3 coach.py calibrate weapon1        # step-by-step on-track tuning drill
  python3 coach.py report [log.txt]         # summarize a battery/cycle log
  python3 coach.py checklist                # pre-match checklist (print and tick)
  python3 coach.py remember "lesson"        # save a lesson to coach_memory.md
  python3 coach.py memory                   # read the team memory
  python3 coach.py plan                     # what to improve next, ordered by impact

Iron rules baked into every answer:
  1. Everything runs ON the board. No internet, no API during a match.
  2. No time.sleep() in the control loop (ticks_ms + uasyncio only).
  3. No one-button macros: continuous sensor-reactive assistance only.
  4. Weapon 4 is the ONLY writer to DRIVETRAIN.set_effort.
"""

import glob
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(ROOT, "coach_memory.md")

# ---------------------------------------------------------------- knowledge

WEAPONS = {
    "weapon1": dict(
        file="weapon1_gyro_lock.py",
        name="Gyro-Lock PID (heading keeper)",
        kid="It is the robot's 'straight-line superpower'. The IMU is like a "
            "compass in the robot's head. 20 times per second it compares the "
            "heading you WANT with the heading you HAVE, and nudges the motors "
            "so the nose does not drift. Crash into something? It kills the "
            "post-crash spin (fault P1).",
        tun="KP decides how hard it corrects: too low = wobbly/slow to react, "
            "too high = nervous buzzing. KI fixes small constant drift; KD "
            "damps the correction so it does not overshoot.",
        drill=["Put the robot on a long straight line (tape on the floor).",
               "Full forward for 3 m. Watch the tape: does the nose wander?",
               "Wander > 5 cm -> raise KP by 0.004. Nose buzzing -> lower KP by 0.004.",
               "Repeat until 5 straight runs in a row stay inside 3 cm.",
               "Then crash it gently into a wall: it must recover in < 1 s without spinning."],
        safe={"KP": (0.055, 0.075), "KI": (0.030, 0.090), "KD": (0.002, 0.010),
              "MIN_EFFORT": (0.08, 0.20), "DT_MS": (15, 30)},
    ),
    "weapon2": dict(
        file="weapon2_torque_boost.py",
        name="Torque Boost (anti-stall)",
        kid="When the robot pushes something heavy (or a rival!) the wheels "
            "slow down but the driver still holds full stick. This weapon "
            "detects that 'I ask a lot but the wheels say little' moment and "
            "injects extra effort so the robot does not get stuck.",
        tun="STALL_RATIO is how much wheel slowdown counts as a stall. "
            "BOOST_MAX is the extra punch ceiling: too high and the battery "
            "sags / the robot gets wild.",
        drill=["Find a wall. Push against it with full forward.",
               "WITHOUT boost the wheels stall and rpm drops near zero.",
               "With the weapon ON the robot should keep creeping (not freeze).",
               "If motors whine hot after 5 s -> lower BOOST_MAX by 0.05."],
        safe={"STALL_RATIO": (0.30, 0.55), "BOOST_MAX": (0.25, 0.45)},
    ),
    "weapon3": dict(
        file="weapon3_curves.py",
        name="Cubic curves + slew (driver feel)",
        kid="A kid's thumb is not a surgeon. This weapon reshapes the stick "
            "signal: small stick moves = small robot moves (precision zone), "
            "and fast stick moves get a short ramp (slew) so the robot does "
            "not jerk. It is the difference between a wild kart and a smooth "
            "racing kart.",
        tun="MIX blends 'precision curve' with 'sport curve'. Slew rate is the "
            "ramp speed (units per second).",
        drill=["Slalom: 4 gates 40 cm apart. Full track with curves only.",
               "Clipping gates -> raise MIX by 0.05 (more precision).",
               "Robot feels laggy/sleepy -> lower MIX by 0.05.",
               "Jerk on direction change -> lower SLEW by 0.5."],
        safe={"MIX": (0.25, 0.45), "MIX_PRECISION": (0.08, 0.20),
              "SLEW_DEFAULT": (2.0, 4.5)},
    ),
    "weapon4": dict(
        file="weapon4_traction.py",
        name="Traction & Active Brake (the ONLY motor writer)",
        kid="This is the robot's hands: the ONLY code allowed to touch "
            "DRIVETRAIN.set_effort. Everyone else sends requests; this weapon "
            "decides the final numbers. It also brakes actively when you drop "
            "the stick to zero (no ice-skating slides) and pulses effort to "
            "un-stick a nailed wheel.",
        tun="RAMP_MAX limits sudden effort jumps; PULSE_K/PULSE_MAX drive the "
            "anti-nailed pulse. Do not raise PULSE_MAX too much or the robot "
            "twitches.",
        drill=["Full speed, then release sticks: the robot must stop in its "
               "own length (no sliding past a tape mark).",
               "Slide > 15 cm -> increase braking pulse slightly.",
               "Robot twitching at standstill -> RPM_STOP_MIN a bit higher."],
        safe={"RAMP_MAX": (2.0, 4.0), "PULSE_K": (0.008, 0.020),
              "PULSE_MAX": (0.30, 0.60), "RPM_STOP_MIN": (2.0, 5.0)},
    ),
    "weapon5": dict(
        file="weapon5_endgame.py",
        name="Endgame clock + return home",
        kid="The referee clock. The match lasts 150,000 ms (2 min 30 s). At "
            "12,000 ms left the robot can AUTOMATICALLY drive home: it "
            "replays its odometer bread crumbs (X, Y, heading) back to the "
            "start tile and parks inside 8 cm. The pilot can always override "
            "with the sticks.",
        tun="V_RETURN is the home speed (slower = more precise). "
            "PARK_LOCK_CM is how close counts as parked.",
        drill=["Run a full match with RETURN allowed.",
               "If it bumps obstacles on the way home -> keep OBSTACLE_CM and "
               "check the odometry scale, do NOT just slow down more.",
               "Parked but outside the zone -> check HOME_TOL_CM and drift "
               "(Weapon 1 keeps the heading during return)."],
        safe={"MATCH_MS": (150000, 150000), "ENDGAME_MS": (10000, 15000),
              "V_RETURN": (0.75, 0.95), "PARK_LOCK_CM": (6.0, 12.0),
              "HOME_TOL_CM": (8.0, 15.0)},
    ),
    "weapon6": dict(
        file="weapon6_brain.py",
        name="On-board brain (GAIN/DAMP/GRIP/HOME)",
        kid="The robot's own little brain. 50 times per second it watches "
            "spins, stalls and drift and re-tunes KP/KD/BOOST by itself, "
            "always inside safe clamps. NO internet, NO API, NO sleep: it "
            "runs on the board during the match. GAIN reacts to crashes, "
            "DAMP kills wobble, GRIP fights slippery ground, HOME sharpens "
            "the endgame return.",
        tun="You rarely tune it by hand: its whole job is tuning others. Check "
            "its clamps stay inside the weapons' safe ranges.",
        drill=["Play 3 matches with the brain telemetry visible.",
               "It should log re-tunes only after real events (crash/stall), "
               "not constantly. Constant re-tuning = clamps too loose."],
        safe={"KP_MIN": (0.055, 0.060), "KP_MAX": (0.070, 0.075),
              "BOOST_HARD_MAX": (0.40, 0.50)},
    ),
}

FILE_TO_KEY = {v["file"].replace(".py", ""): k for k, v in WEAPONS.items()}
FILE_TO_KEY.update({v["file"]: k for k, v in WEAPONS.items()})

IRON_RULES = (
    "Iron rules: (1) everything runs ON the board, no internet/API in a match; "
    "(2) no time.sleep() in the control loop; (3) no one-button macros, only "
    "continuous sensor-reactive assist; (4) Weapon 4 is the only set_effort writer."
)

# ------------------------------------------------------------------ helpers

def read_constants(path):
    """Parse `NAME = value` module-level constants (ints/floats only)."""
    consts = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#", 1)[0]          # strip comments
                m = re.match(r"^([A-Z][A-Z0-9_]{1,})\s*=\s*(-?\d+\.\d+|-?\d+)\s*$", line)
                if m:
                    try:
                        consts[m.group(1)] = float(m.group(2))
                    except ValueError:
                        pass
    except OSError:
        pass
    return consts


def resolve_target(name):
    if not name:
        return None
    key = name.lower().replace(".py", "").replace("_", "").replace("-", "")
    if key in WEAPONS:
        return key
    for k in WEAPONS:
        if k in key:
            return k
    fk = FILE_TO_KEY.get(name)
    return fk


def find_latest_log():
    cands = sorted(
        glob.glob(os.path.join(ROOT, "*cycle*.txt"))
        + glob.glob("/tmp/logs/cycle-*.txt")
        + glob.glob(os.path.join(ROOT, "battery*.log"))
        + glob.glob("/tmp/battery*.log"),
        key=os.path.getmtime,
    )
    return cands[-1] if cands else None


def grab(text, pattern):
    m = re.search(pattern, text)
    return m.group(1) if m else None

# ------------------------------------------------------------------ commands

def cmd_audit(_args):
    print("== COACH AUDIT (offline) ==")
    issues = 0
    for key in sorted(WEAPONS):
        spec = WEAPONS[key]
        consts = read_constants(os.path.join(ROOT, spec["file"]))
        if not consts:
            print("  [?] %s: no numeric constants found (file missing?)" % spec["file"])
            issues += 1
            continue
        for name, (lo, hi) in sorted(spec["safe"].items()):
            val = consts.get(name)
            if val is None:
                print("  [!] %s: %s not found (expected range %s..%s)"
                      % (spec["file"], name, lo, hi))
                issues += 1
            elif not (lo <= val <= hi):
                print("  [!] %s: %s = %g OUT OF SAFE RANGE %g..%g"
                      % (spec["file"], name, val, lo, hi))
                issues += 1
    main_src = ""
    try:
        main_src = open(os.path.join(ROOT, "main_match.py"), "r", encoding="utf-8").read()
    except OSError:
        print("  [!] main_match.py missing")
        issues += 1
    chained = "weapon4" in main_src and "attach" in main_src
    # iron-rule sweep (comments stripped; uasyncio sleep_ms is allowed)
    for py in sorted(glob.glob(os.path.join(ROOT, "weapon*.py"))) + \
              [os.path.join(ROOT, "pilot_gamepad.py"), os.path.join(ROOT, "main_match.py")]:
        try:
            raw = open(py, "r", encoding="utf-8").read()
        except OSError:
            continue
        code = "\n".join(ln.split("#", 1)[0] for ln in raw.splitlines())
        base = os.path.basename(py)
        if base not in ("weapon4_traction.py",) and "set_effort(" in code:
            if chained:
                # standalone fallback only; in the chain Weapon 4 is the writer
                if not re.search(r"_post is not None|standalone", raw):
                    print("  [!] IRON RULE 4: %s writes set_effort with no hook guard." % base)
                    issues += 1
            else:
                print("  [!] IRON RULE 4: %s writes set_effort and the chain is NOT wired." % base)
                issues += 1
        if re.search(r"(?<![_\w])sleep\s*\(", code):
            print("  [!] IRON RULE 2: %s calls blocking sleep() (use ticks_ms/uasyncio)." % base)
            issues += 1
    # wiring: every weapon imported?
    for key in sorted(WEAPONS):
        mod = WEAPONS[key]["file"].replace(".py", "")
        if mod and mod not in main_src:
            print("  [!] WIRING: %s is not imported by main_match.py" % mod)
            issues += 1
    if issues == 0:
        print("  ALL CLEAN: every constant inside its safe range and the chain is wired.")
    else:
        print("  %d issue(s) found. Fix them before the next match." % issues)
    print("  " + IRON_RULES)
    return 1 if issues else 0


def cmd_explain(args):
    key = resolve_target(args[0] if args else "")
    if not key:
        keys = ", ".join(sorted(WEAPONS))
        print("Which one? %s   (e.g. python3 coach.py explain weapon1)" % keys)
        return 2
    spec = WEAPONS[key]
    print("== %s ==" % spec["name"])
    print("File: %s" % spec["file"])
    print("\n[KID VERSION]\n%s" % spec["kid"])
    print("\n[HOW TO TUNE]\n%s" % spec["tun"])
    consts = read_constants(os.path.join(ROOT, spec["file"]))
    if consts:
        print("\n[LIVE CONSTANTS]")
        for name in sorted(spec["safe"]):
            lo, hi = spec["safe"][name]
            val = consts.get(name)
            mark = "ok" if (val is not None and lo <= val <= hi) else "CHECK!"
            shown = "?" if val is None else "%g" % val
            print("  %-14s = %-8s safe %g..%g  %s" % (name, shown, lo, hi, mark))
    return 0


def cmd_calibrate(args):
    key = resolve_target(args[0] if args else "")
    if not key:
        print("Usage: python3 coach.py calibrate weapon1  (weapon1..weapon6)")
        return 2
    spec = WEAPONS[key]
    print("== CALIBRATION DRILL: %s ==" % spec["name"])
    for i, step in enumerate(spec["drill"], 1):
        print("  %d. %s" % (i, step))
    print("\nRemember: change ONE constant at a time, run the battery after "
          "each change, and keep the value inside the safe range "
          "(python3 coach.py audit).")
    return 0


def cmd_report(args):
    path = args[0] if args else find_latest_log()
    if not path or not os.path.exists(path):
        print("No battery log found. Pass one: python3 coach.py report cycle-3.txt")
        return 2
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    print("== COACH REPORT: %s ==" % os.path.basename(path))
    pts = grab(text, r"^POINTS: avg=([\d.]+)")
    park = grab(text, r"PARK in zone: (\d+(?:\.\d+)?)%")
    strict = grab(text, r"STRICT with no faults: (\d+(?:\.\d+)?)%")
    p1 = grab(text, r"P1\(spin post-crash\): (\d+)")
    result = grab(text, r"RESULT: (\d+)")
    sumo = grab(text, r"SUMO won .*lost (\d+(?:\.\d+)?)%")
    soccer = grab(text, r"SOCCER2 goals .*we-win (\d+(?:\.\d+)?)%")
    print("  points avg      : %s" % (pts or "?"))
    print("  park in zone    : %s %%" % (park or "?"))
    print("  strict no faults: %s %%" % (strict or "?"))
    print("  P1 spin events  : %s" % (p1 or "?"))
    print("  SUMO lost%%      : %s" % (sumo or "?"))
    print("  SOCCER2 we-win%%: %s" % (soccer or "?"))
    print("  battery verdict : %s" % ("PASS (%s checks)" % result if result else "?"))
    tips = []
    if pts and float(pts) < 55.0:
        tips.append("points below 55: run `python3 coach.py calibrate weapon3` "
                    "(driver feel is usually worth the most points).")
    if park is not None and float(park) < 95.0:
        tips.append("park < 95%: check Weapon 5 odometry scale and V_RETURN.")
    if strict is not None and float(strict) < 94.0:
        tips.append("strict faults: audit Weapon 1 KP and the post-crash DAMP.")
    if p1 and int(p1) > 0:
        tips.append("P1 > 0: post-crash spins still happen -> raise KD damping "
                    "(Weapon 1 / brain DAMP), never touch the test harness.")
    if sumo and float(sumo) > 0.0:
        tips.append("SUMO lost some bouts: try BOOST_MAX up 0.05 (inside safe range).")
    if soccer and float(soccer) < 60.0:
        tips.append("SOCCER2 we-win < 60%: review kid profile speed in games.py "
                    "tactics, not the harness.")
    if tips:
        print("\n  TOP FIXES:")
        for t in tips:
            print("   - %s" % t)
    else:
        print("\n  Nothing alarming. Keep the chain running!")
    return 0


def cmd_checklist(_args):
    items = [
        "Battery charged and strapped (voltage above nominal, no sag under push test).",
        "Wheels tight, no hair/string on axles, caster spins free.",
        "Robot on the CORRECT side of the field facing the CORRECT way.",
        "Home position marked: endgame return lands exactly here.",
        "IMU calibrated (robot still on the ground when powering on).",
        "Gamepad paired, sticks centered (no drift), pilot profile = KID.",
        "Weapon 6 brain telemetry visible so the team can watch re-tunes.",
        "Match clock ready: 150,000 ms; endgame return at 12,000 ms left.",
        "Iron rules check: python3 coach.py audit -> ALL CLEAN.",
        "Plan B agreed: if assist misbehaves, pilot drives sticks-only (assist only AROUND the sticks).",
    ]
    print("== PRE-MATCH CHECKLIST (print me) ==")
    for i, it in enumerate(items, 1):
        print("  [ ] %2d. %s" % (i, it))
    print("\n  " + IRON_RULES)
    return 0


def cmd_remember(args):
    if not args:
        print('Usage: python3 coach.py remember "always park facing the crowd side"')
        return 2
    note = " ".join(args).strip()
    with open(MEMORY_FILE, "a", encoding="utf-8") as fh:
        fh.write("- %s _(%s)_\n" % (note, datetime.now().strftime("%Y-%m-%d %H:%M")))
    print("Saved to %s. The whole team can read it with: python3 coach.py memory" % os.path.basename(MEMORY_FILE))
    return 0


def cmd_memory(_args):
    if not os.path.exists(MEMORY_FILE):
        print("Team memory is empty. Add lessons: python3 coach.py remember \"...\"")
        return 0
    print("== TEAM MEMORY (%s) ==" % os.path.basename(MEMORY_FILE))
    with open(MEMORY_FILE, "r", encoding="utf-8") as fh:
        sys.stdout.write(fh.read())
    return 0


def cmd_plan(_args):
    print("== COACH PLAN (ordered by score impact) ==")
    plan = [
        ("1", "Run `python3 coach.py audit` -> fix every CHECK! before touching anything else."),
        ("2", "Bundle the autotune proposal from issue #13 (KP 0.068, MIX 0.4, V_RETURN 0.8) "
              "if the team approves it: battery says +2.8 points."),
        ("3", "Calibrate Weapon 3 driver feel with the real pilot (biggest points-per-minute)."),
        ("4", "Rehearse the endgame: 5 full matches, park >= 95% required."),
        ("5", "Keep the 24/7 marathon alive; review its cycle logs after each school day."),
    ]
    for num, line in plan:
        print("  %s. %s" % (num, line))
    return 0


COMMANDS = {
    "audit": cmd_audit,
    "explain": cmd_explain,
    "calibrate": cmd_calibrate,
    "report": cmd_report,
    "checklist": cmd_checklist,
    "remember": cmd_remember,
    "memory": cmd_memory,
    "plan": cmd_plan,
}


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[0].lower()
    fn = COMMANDS.get(cmd)
    if not fn:
        print("Unknown command '%s'. Try: %s" % (cmd, ", ".join(sorted(COMMANDS))))
        return 2
    return fn(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
