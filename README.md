<div align="center">

# 🤖 XRP Master Software — Team Robots Legends ⚔️

### 🏆 5 Secret Weapons for the **XRP Iron Acres** competition (150-second matches)

**FUSAMO · BootCamp Aventura Transforma**

![CI](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/actions/workflows/battery-24-7.yml/badge.svg)
![MicroPython](https://img.shields.io/badge/MicroPython-XRPLib-blue)
![Platform](https://img.shields.io/badge/Platform-XRP%20(Pico%20W)-purple)
![License](https://img.shields.io/badge/License-MIT-green)
![Tests](https://img.shields.io/badge/Battery-13%2F13%20thresholds%20OK-brightgreen)

*Everything runs on the robot's board. No bridges, no internet, no APIs, no `time.sleep()`. The gamepad only asks — the weapons decide.* 🧠⚡

</div>

---

## 🌐 Language / Idioma

**🇬🇧 English** (this file) · [🇪🇸 Español](README.es.md)

> 🚀 **New!** 📖 [GitHub Wiki](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki) — step-by-step guides with emojis.
> 🌐 **New!** 🎨 [Documentation website + 3D games sandbox](docs/index.html) — DRIVE / SUMO / SOCCER, play in the browser.

---

## 📚 Table of Contents

0. [🌐 Documentation website + 3D sandbox](#-documentation-website--3d-sandbox)
1. [⚡ What is this?](#-what-is-this)
2. [⚔️ The 5 Secret Weapons](#%EF%B8%8F-the-5-secret-weapons)
3. [🎮 How the match is played](#-how-the-match-is-played)
4. [🔗 Control chain](#-control-chain)
5. [🔌 Installation on the robot (3 ways)](#-installation-on-the-robot-3-ways)
   - [Method 1 — XRPCode (official web editor)](#method-1--xrpcode-official-web-editor--recommended)
   - [Method 2 — USB serial (mpremote / Thonny)](#method-2--usb-serial-mpremote--thonny)
   - [Method 3 — Copa Robótica (class platform)](#method-3--copa-robótica-class-platform)
6. [🕹️ Gamepad controls](#%EF%B8%8F-gamepad-controls)
7. [🧪 Running the tests locally](#-running-the-tests-locally)
8. [🤖 24/7 battery in GitHub Actions](#-247-battery-in-github-actions)
9. [📊 Measured results](#-measured-results)
10. [🛠️ Calibration guide](#%EF%B8%8F-calibration-guide)
11. [📚 Lessons from 800+ simulated matches](#-lessons-from-800-simulated-matches)
12. [❓ FAQ](#-faq)
13. [📜 License & credits](#-license--credits)
14. [📖 Wiki](#-wiki)

---

## 🌐 Documentation website + 3D sandbox

Beyond this README, the project ships with two extra layers of docs:

- **🌍 [docs/index.html](docs/index.html)** — a self-contained website (HTML + CSS + JS, no build step, works offline) with animated hero, cards for every weapon, full game rules and a **Three.js 3D sandbox** where you can play the three simulation games in the browser: 🚗 **DRIVE** (individual driving circuit), 🤼 **SUMO** (1v1 and 2v2 push-out) and ⚽ **SOCCER** (1v1 and 2v2). 🏟️ Iron Acres is documented but not sandboxed (it needs the full field model).
- **📖 [GitHub Wiki](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki)** — many pages with emojis: what this robot is, installation, how to upload files, controls, the 5 weapons, testing & simulation, troubleshooting, calibration, collaboration guide.

## ⚡ What is this?

This repository contains the **master software** for our XRP robot in the **XRP Iron Acres** competition: a field where you deliver products, park in the home zone, and the match lasts **exactly 150,000 ms** (2:30 minutes).

**Hard rules we obey (no exceptions):**

| Rule | How we honor it |
|---|---|
| 🚫 No internet, no bridges, no external APIs | 100% of the code runs on the XRP board (RP2040 / Pico W) |
| 🚫 No `time.sleep()` / blocking pauses | Everything is `time.ticks_ms()` + `uasyncio` + continuous sensor reading |
| 🚫 No one-button fixed macros | Every assist is a **continuous, real-time closed loop**; buttons only toggle assists |
| 🎯 Easy to integrate with XRPCode blocks | Self-contained modules, importable line-by-line |

The match is driven with a **physical gamepad** (Xbox/Logitech) connected to the driving station; the XRP receives axes and buttons over **Bluetooth via the official XPP protocol at 50 Hz** (`XRPLib.gamepad`). The pilot is a kid who is great at video games but does not have adult-level motor precision — all 5 weapons exist to inflate the kid's precision without ever fighting the pilot's intent.

---

## ⚔️ The 5 Secret Weapons

### 🔒 Weapon 1 — Gyro-Lock PID (Heading Autocorrect / Anti-Spin)
A real-time PID using `imu.get_yaw()` that **locks the heading** whenever the robot should go straight or was not ordered to turn.
- Stops spins, drifts, and collision deflection **immediately**.
- Anti-windup (`MAX_I`), deadband (1.5°) with integral kept, output limit 0.5.
- Bonus logic: the minimum-effort floor applies only **while moving** (never in hold — the floor used to cause 1.53 rpm pulses that broke the *nailed* park check).

### 💪 Weapon 2 — Smart Torque Boost (Anti-Stall)
Compares **desired wheel speed vs. real encoder speed**.
- Extra power **per wheel** when it detects resistance/friction/heavy load at low speed.
- Boost is released the moment the wheel recovers fluidity.

### 🎛️ Weapon 3 — Cubic Response Curves (Surgical Handling)
Transforms stick inputs with a smooth **cubic curve**: `y = MIX·v + (1−MIX)·v³`.
- Millimeter-precision micro-movements in delicate maneuvers.
- **100% top speed** preserved on long pushes (`MIX=0.35`; precision mode `MIX=0.12` with `BUMPER_L`).
- Slew-rate limiting: firm on press (3.0), extra forgiving on release (12.0).

### 🛞 Weapon 4 — Traction & Brake Assist (Active Braking)
Owns the motors (single final writer):
- **Acceleration ramp** (`RAMP_MAX=3.0`/s) so wheels never slip from a standstill.
- **Controlled reverse pulse** (`PULSE_K=0.012`) read back via encoders when the command returns to zero — the robot is **nailed to its exact spot** with no inertia slide.

### ⏱️ Weapon 5 — Auto-Endgame (Clock + Home Odometry)
- Counts the exact **150,000 ms** of the match.
- Maintains **relative position X, Y, θ** via encoder + IMU fusion (dead-reckoning odometry).
- When **12 seconds remain** and sticks are released, a live assist returns the robot home (`V_RETORNO=0.85`).
- Final 2 seconds: guaranteed zero command once inside 8 cm → the **park is locked in**.

---

## 🎮 How the match is played

```
   ┌──────────────┐  Bluetooth XPP @ 50 Hz  ┌────────────────────────┐
   │ PHYSICAL     │ ───────────────────────▶│  XRP board (MicroPython)│
   │ GAMEPAD      │                         │                        │
   │ (kid pilot)  │ ◀───────────────────────│  100% on-board logic:  │
   └──────────────┘   rumble/status          │  pilot → curves → A2   │
                                             │  → A4 (owns motors)    │
                                             │  with A1 gyro-lock     │
                                             │  hooked inside, A5     │
                                             │  managing the clock    │
                                             └────────────────────────┘
```

- **Pilot authority is always supreme**: touching any stick instantly overrides every assist.
- Releasing the sticks in the last 12 s arms the **live return home**; touching a stick cancels it that instant.
- The board needs **zero operator software during the match** — the gamepad talks to the driving station, the station talks to the XRP.

For the exact button map see [🕹️ Gamepad controls](#%EF%B8%8F-gamepad-controls).

---

## 🔗 Control chain

Only **one** module ever writes to the motors; the chain flows strictly in one direction so assists can never fight each other.

```
pilot_gamepad.py (50 Hz loop; modes STOP / STRAIGHT / TURN / SETTLE / RETURN)
        │
        ▼
weapon3_curves.py  (cubic response + slew)      ← Weapon 3
        │
        ▼
weapon2_torque_boost.py  (anti-stall boost)      ← Weapon 2
        │
        ▼
weapon4_traction.py  (ramp + active brake)       ← Weapon 4  ⟵ ONLY writer to motors
        └── weapon1_gyro_lock.py (PID hooked inside)   ← Weapon 1
        │
        ▼
   DRIVETRAIN.set_effort(l, r)

weapon5_endgame.py (clock + odometry + live return)   ← Weapon 5 (20 Hz task)
```

---

## 🔌 Installation on the robot (3 ways)

> **Goal in all methods:** copy the software to the **root of the XRP's filesystem**
> (`main_match.py` + the 5 weapons + `pilot_gamepad.py`), then run
> `main_match.py` once before the match starts.

**The 8 files to load:**

```
main_match.py          ← entry point (run this one)
pilot_gamepad.py        ← gamepad driver
weapon1_gyro_lock.py        weapon2_torque_boost.py
weapon3_curves.py           weapon4_traction.py
weapon5_endgame.py         curvas.py (if your copy references it)
```

### Method 1 — XRPCode (official web editor) 🥇 *recommended*

[XRPCode](https://xrpcode.wpi.edu) is the **official** platform (Experiential Robotics / WPI / SparkFun / FIRST) to program the XRP: a **web editor** that works in Chrome, Edge or Opera, connects to the robot over **USB serial** (WebSerial), and supports **both Blockly and Python**.

1. **Open [xrpcode.wpi.edu](https://xrpcode.wpi.edu)** in Chrome, Edge or Opera.
2. **Connect the XRP by USB** and switch the robot to **XRP mode** (firmware ≥ 1.0.2 ships this; older units need the WebSerial firmware update from the same site).
3. Click **Connect / Serial** in the editor toolbar and **select the robot's port** in the browser dialog.
4. Create a new **Python** project.
5. **Copy the 8 files to the robot**: use the **Filesystem panel** (left sidebar) to upload them to the robot's root filesystem. If your editor version has no upload button, create each file with **New File**, paste its contents, and **Save** — same result.
6. **Start**: open `main_match.py` and press **Run (▶)**. The board then tracks the gamepad for the whole match — you may close the editor afterward without stopping the program.
7. First boot: the XRPLib IMU **calibrates once** with the robot still (`imu.calibrate(1.0)` — the only intentional pause in the system, done by the official library, not by us).

> 💡 **Blockly integration**: each weapon is a plain MicroPython module with a clean API (`set_base()`, `feed()`, `attach()`, `enable()`…), so you can also invoke them from Python blocks in Blockly (`import weapon1_gyro_lock`) and mix with your own custom blocks.

### Method 2 — USB serial (mpremote / Thonny)

Classic REPL workflow from a PC:

```bash
# Install the MicroPython device tool
pip install mpremote

# Copy every file to the robot's root (XRP plugged in by USB)
mpremote cp main_match.py :/
mpremote cp pilot_gamepad.py :/
mpremote cp weapon1_gyro_lock.py :/
mpremote cp weapon2_torque_boost.py :/
mpremote cp weapon3_curves.py :/
mpremote cp weapon4_traction.py :/
mpremote cp weapon5_endgame.py :/

# Open the REPL and start the match software
mpremote
# >>> import main_match
```

Alternative: **Thonny** (`Tools → Options → Interpreter → MicroPython (generic)`), then right-click each file → *Upload to /*.

> ⚠️ The XRP's MicroPython build must include XRPLib (every XRP unit ships it). If `import XRPLib` fails in the REPL, reflash the official XRP firmware first from [experientialrobotics.org](https://experientialrobotics.org).

### Method 3 — Copa Robótica (class platform)

[**Copa Robótica**](https://programacion.coparobotica.com) is the class/camp platform our BootCamp (**Aventura Transforma / FUSAMO**) uses: an online learning environment (virtual classroom) where coaches share lesson content and **code-accessible pages via a class link with an access/edition code** — you don't log in with a personal account, you enter through the **class link your coach gave you**.

How to use it with this project:

1. Ask your coach for the **class link with its edition code** (BootCamp Aventura Transforma uses these for the XRP module).
2. Open that link in Chrome/Edge — it loads the lesson's editor/emulator for your group.
3. **Paste this project's files** in that editor as plain Python text (`main_match.py` and each weapon, exactly as-is).
4. Connect the robot the same way XRPCode does (USB serial + WebSerial in the browser): connect, select the port, upload/run the files.
5. **Simulator-only mode** (no robot present): clone this repo on a PC (or Pydroid on Android) and run `python3 simulator_xrp.py` to play full 150 s matches with a virtual gamepad against the same code that goes on the board.

> ℹ️ If your Copa Robótica link says "no valid edition code", ask your coach to re-share the **class edition link** — the edition code is what unlocks the editable code area; the plain student view is read-only.

---

## 🕹️ Gamepad controls

| Control | Function (continuous, never a macro) |
|---|---|
| `Y1` (left stick) | Forward/backward (passes through Weapon 3 curve) |
| `X1` (right stick) | Turn: while moving, enters TURN mode |
| `X1` small sustained | **ASSISTED TRIM**: pans the locked heading without releasing forward (real-push detection via ~0.25 s EMA — hand tremor does **not** pan) |
| Sticks released | Weapon 4 nails the robot + Weapon 1 holds heading |
| `START` (edge) | Arms the clock & defines home for Weapon 5 |
| `BACK` (edge) | Toggles the endgame return assist on/off |
| `BUMPER_L` (hold) | Precision mode (more surgical curve, `MIX=0.12`) |

**Priority is always: pilot sticks > assistance.** Releasing the sticks in the last 12 s triggers the live return home (A5), and touching any stick instantly countermands it.

---

## 🧪 Running the tests locally

All tests run on a **PC simulator** (`simulator_xrp.py`) — a physical plant with stubs for XRPLib/uasyncio, a virtual clock, a virtual gamepad and the pilot model. Nothing touches the real robot.

```bash
python3 verify.py     # 12/12 math unit tests of the weapons
python3 stress.py       # 30/30 stress matches (random chaos)
python3 simulator_xrp.py # one full 150 s match with a virtual gamepad

# Mass campaigns (Iron Acres scoring, multiprocess)
MASS_N=400 python3 mass_campaign.py
MASS_PILOT=ADULT MASS_N=100 python3 mass_campaign.py
MASS_VARIANT=NO_ASSIST MASS_N=200 python3 mass_campaign.py   # value of the weapons

# Individual & team games
GAMES_MODE=ALL GAMES_N=100 GAMES_PILOT=KID python3 games.py
GAMES_MODE=SUMO GAMES_N=300 GAMES_PILOT=KID python3 games.py
GAMES_MODE=ALL GAMES_N=40 GAMES_PILOT=ADULT python3 games.py  # reference
```

Useful env flags for debugging:

| Variable | Purpose |
|---|---|
| `MASS_PILOT` | Pilot profile: `KID` (default) / `GOOD` / `REGULAR` / `ADULT` |
| `MASS_VARIANT` | `ASSIST` (full assist, default) or `NO_ASSIST` (no weapons) |
| `MASS_N` / `GAMES_N` | Number of matches per run |
| `MASS_DEBUG` / `STRESS_DEBUG` / `GAMES_DEBUG` / `GAMES_TRACE` | Verbose traces for hunting failures |

---

## 🤖 24/7 battery in GitHub Actions

`.github/workflows/battery-24-7.yml` runs the **entire battery continuously**:

- ⏰ **Every 3 hours** (`cron 0 */3 * * *`) — around the clock
- 🚀 On every **push to `main`**
- 🔘 On demand (**Run workflow** button, `workflow_dispatch`)
- 📦 Logs of every battery are uploaded as artifacts (**90-day retention**)

The **daily enhancement workflow** (`daily-improve.yml`) adds one more guard: it replays the battery, and **if a threshold regresses it automatically opens a GitHub Issue** titled with the failing metric — the team gets told the same day without watching CI. Improvement **proposals** are attached to that same issue; but no automated edit ever lands on the robot code without a human reviewing the cause first.

Quality thresholds enforced (`ci/battery.sh`) — the run turns **red** if ANY falls:

| Battery | Metric | Threshold |
|---|---|---|
| `verifica` | math tests | 12/12 |
| `stress` (30 matches) | matches approved | 30/30 |
| Iron Acres KID (n300) | Park in zone | ≥ 90% |
| Iron Acres KID (n300) | STRICT matches (zero faults) | ≥ 60% |
| Iron Acres KID (n300) | P1 spins post-collision | = 0 |
| Iron Acres KID (n300) | Points avg | ≥ 50 |
| Iron Acres ADULT (n100) | Points avg | ≥ 35 |
| Weapons vs NO-ASSIST | Contribution | ≥ 2 pts |
| Games KID (n100 × 5) | Modes with F1–F4 clean | 5/5 |
| SUMO KID (n100) | Losses | 0% |
| SOCCER 1v1 (n100) | Goals/match | ≥ 0.2 |
| SOCCER2 2v2 (n100) | Goals/match | ≥ 3.0 |
| SOCCER2 ADULT (n40) | Win % | ≥ 50% |

> 🛡️ **When a metric regresses, we edit `pilot_gamepad.py` / `arma*.py` — NEVER the test harnesses or their fidelity metrics (F-metrics).** CI is an alarm, not an auto-editor.

---

## 📊 Measured results

**Iron Acres — mass campaign, KID pilot (the real kids' profile), 400 matches**

| Metric | Result |
|---|---|
| Points avg | **≈ 58 / 60 possible** |
| Park in zone + nailed | 90%+ |
| STRICT matches (zero faults P1–P3) | **94.8%** (was 52.8% before the post-turn set-up fix) |
| P1 spins post-collision | 0 (kid flicker is not a fault; real holds settle to ≤2°) |

**Individual & team games — 100 matches per mode, KID pilot**

| Mode | Performance | F1 | F2 | F3 | F4 | F5 lat. |
|---|---|---|---|---|---|---|
| DRIVE (100) | 2.84 doors, max 3 | 0 | 0 | 0 | 0 | 144 ms |
| SUMO 1v1 (100) | **73% won / 0% lost / 27% draw** | 0 | 0 | 0 | 0 | 31 ms |
| SUMO 2v2 (100) | **63% won / 0% lost / 37%** | 0 | 0 | 0 | 0 | 32 ms |
| SOCCER 1v1 (100) | **0.55 goals/match** (55% of matches with a goal) | 0 | 0 | 0 | 0 | 123 ms |
| SOCCER2 2v2 (100) | 4.79 goals, **51% won / 35% lost** | 0 | 0 | 0 | 0 | 38 ms |

**ADULT reference (40/mode, stress):** 0 in F1–F2, F3 2/40, F4 4/40 only in soccer (limit effect of the adult profile's own push, self-recovers). ADULT SOCCER2: **77.5% won / 15% lost**.

Fidelity metrics (proving the kid cannot trigger involuntary robot moves): **F1** robot goes backward when commanded forward (never happens), **F2** slides >8 cm after releasing sticks at speed, **F3** >3 cm drift while the kid is still >1 s, **F4** >3° heading change without X1 >1 s, **F5** stick→wheels latency. All clean in all modes with the KID profile.

---

## 🛠️ Calibration guide

All constants live at the top of each module, tuned by battery (never by eye):

| Module | Constant(s) | What to tune on the real track |
|---|---|---|
| `pilot_gamepad.py` | `TRIM_THRESHOLD=0.12`, `TRIM_SAT=0.25`, `TRIM_DEG_S=60`, `TRIM_TAU=0.25`, `TURN_MIN=0.08`, `SETTLE_MAX_MS=600`, `SETTLE_RATE=45` | Kid tremor filter / post-turn settle window |
| `weapon1_gyro_lock.py` | `KP=0.064`, **`KI=0.06`, `MAX_I=0.3`**, `KD=0.0055`, `DEADBAND=1.5`, `OUT_LIMIT=0.5` | Start from factory KP → add KD → finally KI. Lower `KI` if the oscillation after crashes won't die; keep `MAX_I` small (the integral is the #1 source of oscillatory spins) |
| `weapon2_torque_boost.py` | `STALL_RATIO`, `BOOST_MAX` | On a free robot the boost must **never** trigger |
| `weapon3_curves.py` | `MIX=0.35` (0.12 precision), `SLEW_DEFAULT=3.0`, `SLEW_RELEASE=12.0` | Higher `MIX` = rawer stick; lower `SLEW` = softer starts |
| `weapon4_traction.py` | `RAMP_MAX=3.0`, `PULSE_K=0.012` | Increase `PULSE_K` if the robot still slides after braking |
| `weapon5_endgame.py` | `V_RETORNO=0.85`, `TOLERANCIA_CM=10`, `PARK_LOCK_CM=8`, `FINAL_SAFE_MS=2000`, `PIVOT_DEG=45` | `TOLERANCIA_CM` per the official "Read the Manual"; `V_RETORNO` = how early the assist must fire |

📱 **Calibration order on the real robot:** Weapon 1 first (park the robot, push it with a hand, it must not spin) → Weapon 4 (release sticks at speed → no slide) → Weapon 3 (curves by feel) → Weapon 2 (push the robot into a wall → boost) → Weapon 5 (full mock match).

---

## 📚 Lessons from 800+ simulated matches

- 🏠 **The home zone must be ≤ ~130 cm away when the endgame begins** — at 0.85 effort the robot covers ~39 cm/s top; with pivot, ramp and braking that leaves ~130 cm playable. Farther = physically impossible.
- 🅿️ **Park without Weapon 5 does not exist**: over 800 KID matches with assistance off, 0% parked (the kid ends at ~79 cm from the zone on average). Endgame assist is the second scoring method of the game.
- 🌀 If a wheel stalls, Gyro-Lock corrects asymmetrically, so spin recovery with an active stall is partial (physics, not software).
- ♨️ Weapon 1's integral + the ramp delay is the #1 source of oscillatory spins — keep `MAX_I` small.
- 🎚️ The `MIN_EFFORT` floor must apply only while the pilot asks to move; in hold it caused 1.53 rpm pulses that broke the "nailed" park check.
- ✍️ The kid pilot's fair metric is **persistence**: P1 only fails if the error stays >3° for the whole deadline + 5 s (kid flicker is not Weapon 1's fault; real holds stay ≤2°).

---

## ❓ FAQ

**Q: Why no `time.sleep()` anywhere?**
Because the match can't block: we read encoders and IMU continuously every 20–50 ms, and a blocking sleep would freeze the whole chain. Everything is scheduled with `ticks_ms` deadlines and `uasyncio` tasks.

**Q: Why does the pilot need a physical gamepad if the kid could also drive with Python?**
Because in the real match the robot must react instantly to a human operator — the gamepad simulates that operator (50 Hz streaming via the official XPP protocol). No operator code runs during the match; only the board.

**Q: Do the weapons fight each other?**
No. There's a strict single-writer rule: only `weapon4_traction.py` ever calls `DRIVETRAIN.set_effort()`. Everything else feeds it.

**Q: Can I use this with Blockly only (no Python)?**
You can import the modules from Python blocks, but the weapons themselves are Python files — they must be uploaded to the robot's filesystem either way.

**Q: Which XRP firmware do we need?**
Any official firmware ≥ 1.0.2 with XRPLib. Bluetooth gamepad support needs `XRPLib.gamepad` (present in current firmware images).

**Q: Is the simulator identical to the real robot?**
No — it's a fidelity plant (encoder inertia, IMU drift, programmed stalls, crash jolts) used to hunt bugs before they reach the metal. Real-track calibration is still mandatory, in the 🛠️ order above.

---

## 📖 Wiki

The [GitHub Wiki](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki) is the living handbook of the team (in English, with emojis and lots of markdown):

| Page | What you will find |
|---|---|
| 🏠 [Home](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki) | Overview + all page links |
| 🤖 [What is this robot?](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki/What-Is-This-Robot) | XRP hardware, sensors, who is Team Robots Legends |
| 📥 [Upload files](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki/Uploading-Files) | XRPCode / mpremote / Thonny / Copa Robótica, step by step |
| 🎮 [Controls](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki/Controls) | Gamepad map and pilot modes |
| ⚔️ [The 5 weapons](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki/The-5-Weapons) | Each system, constants and how to tune it |
| 🧪 [Testing & simulation](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki/Testing-and-Simulation) | verify / stress / mass_campaign / games explained |
| 🚑 [Troubleshooting](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki/Troubleshooting) | Common failures and fixes |
| 🤝 [Collaborating](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki/Collaborating) | Branches, PRs, the 24/7 workflows, how to contribute |
| 🎛️ [Calibration](https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki/Calibration) | On-track calibration drills for every weapon |

---

## 📜 License & credits

[MIT](LICENSE) — **Team Robots Legends**, FUSAMO (BootCamp Aventura Transforma).

Standing on the shoulders of giants:
- 🤖 [XRP — Experiential Robotics Platform](https://experientialrobotics.org) (WPI · SparkFun · DEKA · FIRST)
- 🧰 [XRPLib docs](https://docs.experientialrobotics.org) — official robot library
- 💻 [XRPCode](https://xrpcode.wpi.edu) — official web editor
- 🏫 [Copa Robótica](https://programacion.coparobotica.com) — BootCamp class platform

<div align="center">

⚔️ *Built brick by brick: one weapon at a time, calibrated, tested at scale, then shipped.* ⚔️

</div>
