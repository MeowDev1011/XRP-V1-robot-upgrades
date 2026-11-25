# 🚑 Troubleshooting

> 🩺 Symptoms → probable cause → fix. Check the CI run first: if a metric is red, the
> simulator already reproduced it.

---

## 🔌 Connection / upload

| Symptom | Cause | Fix |
|---|---|---|
| XRPCode "Connect" finds nothing | Browser without WebSerial | Use **Chrome / Edge / Opera** (desktop); mobile browsers cannot connect via USB 📵 |
| `ImportError: no module named 'weapon3_curves'` | File missing on the board | Re-upload all 7 files ([Uploading Files](Uploading-Files)) |
| `mpremote` says port busy | REPL or Thonny still open | Close the other tool / press Ctrl+C, retry |
| Random freezes on the board | Someone added `time.sleep()` or a `while True` without yield | Search the diff for `sleep(` — **forbidden**; use `ticks_ms()` deadlines or `uasyncio` |
| Motor stutter every ~1 s | Blocking code in the 50 Hz loop | Keep loop bodies tiny; no prints in the hot loop on the board |

## 🎮 Driving behavior

| Symptom | Probable cause | Fix |
|---|---|---|
| 🌀 Robot spins after a crash and keeps spinning | P1 exceeded: collision dropped the target yaw | Verify IMU flat-mounted; re-run `imu.calibrate(1.0)` at boot; if needed lower `KD` in weapon 1 |
| 🎯 Drifts to one side going straight | Motor bias |
  Weapon 1 `KI` will absorb it; raise `KI` slightly or trim with the small-X | 
| 🐢 Wheels hum but no movement on carpet | Real stall — torque boost at ceiling | Check gearbox/battery < 7.4 V; raise `STALL_RATIO` sensitivity or `BOOST_MAX` |
| 🛝 Robot slides 5–10 cm after stop | Weapon 4 brake pulse too weak | Raise `PULSE_MAX` / check `RPM_STOP_MIN` on the sim |
| 🔄 Over-rotates when releasing the turn | SETTLE window missed | Raise `SETTLE_RATE` (deg/s threshold) or lengthen `SETTLE_MAX_MS` in pilot |
| 🏃 Kid pushes forward, robot pan-rotates | Stick X noise under deadzone | Check `TRIM_THRESHOLD` wiring order; ensure curve deadband `DEADBAND=0.04` not edited |

## ⏱️ Clock / endgame

| Symptom | Probable cause | Fix |
|---|---|---|
| ENDGAME alert at the wrong time | START not pressed (clock never armed) or double-pressed | One clean START edge `home_here()`; check `endgame.start_match()` in logs |
| Return goes to the wrong corner | Home point captured at the wrong place | `home_here()` is recorded when the clock arms — place the robot in the zone first |
| Return collides | Obstacle stop off or too small `OBSTACLE_CM` | Test ultrasonic; raise `OBSTACLE_CM` |

## 🧪 CI is red! What now?

1. 🧾 Open the failing `check` line in `ci/battery.sh` — it names the metric and threshold.
2. 🔍 Download the log artifacts from the Actions run (they are kept 90 days).
3. 🧮 Reproduce locally with the same env (`MASS_N`, `GAMES_N`, …).
4. 🛠️ Edit **ONLY** pilot/weapons — never the harness, never the F-metrics, never thresholds
   (thresholds change only as a team decision on a PR).
5. ✅ Re-run `bash ci/battery.sh` locally until green, then PR (see [Collaborating](Collaborating)).
