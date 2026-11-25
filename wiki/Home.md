# 🤖 Team Robots Legends — Wiki Home

> 🔬 **Official handbook** of the master software for the **XRP** robot
> (Experiential Robotics Platform) competing in **⚔️ Iron Acres** of
> **BootCamp Aventura Transforma** (FUSAMO).

🇬🇧 This wiki is in English, like all the code in the repository.

---

## 🚀 Quick start (3 steps)

1. 🛠️ Open the official editor **[XRPCode](https://xrpcode.wpi.edu)** (Chrome/Edge/Opera) and connect the robot by USB.
2. 📥 Upload the 7 files listed in [Uploading Files](Uploading-Files) (5 weapons + pilot + main).
3. 🎮 Run `import main_match` in the Python tab, connect the gamepad… **and play!** Details in [Controls](Controls).

---

## 📚 All pages

| Page | What you will find |
|---|---|
| 🤖 [What Is This Robot](What-Is-This-Robot) | The XRP hardware, its sensors and our team |
| 📥 [Uploading Files](Uploading-Files) | Every way to send code to the robot: XRPCode, mpremote, Thonny, Copa Robótica |
| 🎮 [Controls](Controls) | Gamepad map, pilot modes and priority rules |
| ⚔️ [The 5 Weapons](The-5-Weapons) | Each assist system, its constants and purpose |
| 🧪 [Testing and Simulation](Testing-and-Simulation) | verify · stress · mass_campaign · games + the 24/7 CI battery |
| 🚑 [Troubleshooting](Troubleshooting) | Symptoms, causes and fixes for the most common failures |
| 🎛️ [Calibration](Calibration) | On-track drills to tune every weapon |
| 🤝 [Collaborating](Collaborating) | Branches, PRs, the autonomous improvement workflow, do's & don'ts |
| 🧠 [AI Copilot](AI-Copilot) | The generic copilot (three config fields): analyze results, review PRs, plan, improve — you only paste your token |
| 🌐 [Documentation Website](Documentation-Website) | The `docs/` HTML site and the 3D sandbox (DRIVE / SUMO / SOCCER) |

---

## 🧭 Golden rules of this project

- ⛔ **NEVER `time.sleep()`** — only non-blocking `time.ticks_ms()` timers and `uasyncio` coroutines.
- ⛔ **NEVER one-button macros** — assistance must be continuous and sensor-reactive.
- ✅ **Pilot sticks are always the boss** — weapons assist around them, never override them.
- ✅ **Only ONE module touches the motors**: `weapon4_traction.py` at the end of the chain.
- 🧪 Fix evidence, not feelings: tests stay untouched, the pilot/weapons get edited.

## 🏆 Current scoreboard (CI, 24/7 battery)

| Metric | Value | Threshold |
|---|---|---|
| STRICT park rate (KID) | 94.7 % | ≥ 60 % 🟢 |
| Points avg (KID, n300) | 56.2 | ≥ 50 🟢 |
| SUMO losses (n100) | 0.0 % | 0 % 🔒 |
| SOCCER 1v1 goals/match | 0.61 | ≥ 0.2 🟢 |
| SOCCER2 2v2 goals/match | 4.42 | ≥ 3.0 🟢 |
| F1–F4 cleanliness | 5/5 modes | 5/5 🟢 |

---

🤝 Broken something? Read [Troubleshooting](Troubleshooting) · Want to help? Read [Collaborating](Collaborating).
