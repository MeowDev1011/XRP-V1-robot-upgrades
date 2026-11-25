# 🧪 Testing and Simulation

> 🧠 We cannot break the robot 800 times on a real field — so we break it 800 times
> in the simulator, and only measure **pilot/weapons** behavior. Tests and the
> **F-fidelity metrics are NEVER edited to make results look good.**

---

## 🧰 The harnesses

| Script | What it does | Typical run |
|---|---|---|
| 🧮 `verify.py` | 12 mathematical unit checks (PID gates, curves, ramps, odometry, endgame) | seconds |
| 💣 `stress.py` | 30 Iron Acres matches with scripted crashes & stalls → P-metrics | ~1 min |
| 🏟️ `mass_campaign.py` | Up to 300+ Iron Acres matches with pilot profiles `KID / GOOD / REGULAR / ADULT`, multiprocess | minutes |
| 🕹️ `games.py` | 🚗 DRIVE · 🤼 SUMO · 🤼 SUMO2 (2v2) · ⚽ SOCCER · ⚽ SOCCER2 (2v2) with F1–F5 stick-fidelity metrics | minutes |
| 🔋 `ci/battery.sh` | Runs everything above and fails if any of **13 thresholds** drops | full CI |

## 🖥️ The simulator

`simulator_xrp.py` injects **stubs of `XRPLib`, `uasyncio`, `time` and `micropython`** so the exact
same files that run on the board run in the laptop. Physics constants:

| Constant | Meaning |
|---|---|
| `KW=44` rpm per effort | Motor gain |
| `TAU=0.14` s | Motor time constant |
| `KS=0.12` | Static friction slope |
| `TRACK_CM=15.5` | Wheel track for odometry |
| IMU bias | `BIAS_IMU_CS × 0.05 °/s` slow drift, yaw **unbounded** (like real life) |

Events are scripted per seed: collisions (±15–40° yaw jumps), wheel stalls, battery sag.

## 🎯 Quality metrics

### P-metrics (Iron Acres performance)
- **P1** — spin right after a crash > 3° must recover (the kid's reality: he *will* crash).
- **P2** — cruise heading error must stay under 12°.
- **P3** — the final park must nail inside the zone (rpm < 1.5, < 10 cm from home).

### F-metrics (stick fidelity — UNTOUCHABLE 🙅)
- **F1** — opposite movement with respect to the commanded direction (0 tolerated).
- **F2** — slide > 8 cm against a brake command (0 tolerated).
- **F3** — involuntary drift > 3 cm at stick release.
- **F4** — involuntary pan > 3°/s.
- **F5** — command→reaction latency.

## 🚀 Run them yourself

```bash
python3 verify.py                                  # 12/12 must pass
python3 stress.py                                  # RESULT: 30/30 matches approved
MASS_PILOT=KID MASS_N=100 python3 mass_campaign.py
MASS_PILOT=ADULT MASS_VARIANT=NO_ASSIST python3 mass_campaign.py   # proves the weapons add value
GAMES_MODE=ALL GAMES_N=100 GAMES_PILOT=KID python3 games.py
bash ci/battery.sh                                 # the 13-threshold gate — ALL OK or exit 1
```

Environment knobs exist for every run: `MASS_N`, `MASS_W`, `MASS_PILOT`, `MASS_VARIANT`,
`GAMES_MODE`, `GAMES_N`, `GAMES_PILOT` — see the header of each script.

## 🤖 The 24/7 battery on GitHub Actions

- 🔁 Workflow **`battery-24-7.yml`** runs the full battery **every 3 hours** and on every push to `main`.
- 🧾 `ci/battery.sh` writes `/tmp/summary.md` (visible in the Actions run) and exits `1` on any miss → red ❌.
- 🤖 Workflow **`daily-improve.yml`** tries *tuning candidates* for the weapons (see
  [Collaborating](Collaborating)) and opens a PR only when simulations prove an improvement.

> 🧭 Rule of thumb: **edit only `pilot_gamepad.py` and `weaponN_*.py`** when a metric fails.
