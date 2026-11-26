# ⚔️ The 5 Secret Weapons

> 🧩 Five independent MicroPython modules. One builds at a time, one calibrates at a time,
> one declines any macro. **They assist the pilot continuously — they never replace him.**

---

## 🎯 Weapon 1 — Gyro-Lock PID (`weapon1_gyro_lock.py`)

**Job**: keep the nose pointing exactly where it should, kill spins and collision drift.

- 🧮 Real-time PID over `imu.get_yaw()` error, iterated every 20 ms.
- 🔒 `engage_straight(v)` locks the current heading; `hold_pose()` locks even at zero base.
- 🚧 **MIN_EFFORT floor applies only while a stick commands a base** — at true hold the motors
  rest (protects the battery and the field rules).
- ⚙️ Calibration: `KP=0.064` (speed of the fix) · `KI=0.06` (steady bias) · `KD=0.0055`
  (brake of the fix) · `I_ZONE=4.0` ° (anti-windup zone) · `MIN_EFFORT=0.14`.
- 🧪 Sanity test: `verify.py` checks saturation, integral gating, angle wrap, crash recovery.

## 💪 Weapon 2 — Torque Boost (`weapon2_torque_boost.py`)

**Job**: feel wheel stalls from the encoders and add torque, then release it.

- 📉 Compares commanded effort vs real wheel acceleration (encoder deltas).
- 🔥 Slow fire ramp `BOOST_STEP`, leak `BOOST_LEAK`, ceiling `BOOST_MAX=0.35`.
- 🧲 Stall declared after `STALL_TICKS=8` (160 ms) under `STALL_RATIO=0.4` of expected speed.
- 🔋 `BATTERY_COMP` scales the boost when the battery sags (measured on board).
- ⚙️ Calibration: raise `BOOST_MAX` only if motors do not overheat in demoes.

## 🕹️ Weapon 3 — Cubic Curves (`weapon3_curves.py`)

**Job**: turn raw sticks into surgical millimetre moves without losing top speed.

- 📐 `curve(x) = x³·MIX + x·(1−MIX)`-style response — fine control zone near zero, full 100 %
  at the extremes.
- 🎚️ `MIX=0.35` for running, `MIX_PRECISION=0.12` when close to targets.
- 🛝 `SlewRamp` (`slew_fwd`, `slew_turn`) smooths command steps at `SLEW_DEFAULT=3.0`/s.
- ⚙️ Calibration: if the kid says "heavy/hard" lower `MIX_PRECISION`; if it overshoots, raise it.

## 🛞 Weapon 4 — Traction & Brake (`weapon4_traction.py`)

**Job**: no wheel slip at launch; no inertia slide at stop. **The ONLY module writing to the motors.**

- 🚀 Launch ramp `RAMP_MAX=3.0` effort/s + antiskid pulse `PULSE_K=0.012` when slip is detected.
- 🧲 On command → 0: controlled inverse pulse then `motor.brake()` — the robot **nails** its spot.
- 🧊 States per axis: `FREE → BRAKING → NAILED` (visible in logs).
- ⚙️ Calibration: `RPM_STOP_MIN=3.0` decides when "stopped is stopped"; if it still creeps,
  raise the brake pulse.

## ⏱️ Weapon 5 — Auto-Endgame (`weapon5_endgame.py`)

**Job**: be the only clock of the match and take the robot home for the park bonus.

- 🧮 Counts exactly **150,000 ms** (no drift, non-blocking).
- 📡 Fuses encoders + IMU into **X, Y, θ odometry**; home is set with `home_here()` at START.
- 🔴 At **t = 138,000 ms** (12 s left): LED alert + assisted return at `V_RETURN=0.85`.
- 🧲 `PARK_LOCK_CM=8.0` — distance at which it declares "parked" and `FINAL_SAFE_MS=2000` keeps the
  last 2 s safe-locked.
- 🚧 Ultrasonic `OBSTACLE_CM=12` protects the return against robots/field pieces.
- ⚙️ Calibration: `HOME_TOL_CM=10.0` (what the scorekeeper calls "in the zone").

---

## 🧠 Weapon 6 — The Brain (on-board adaptive intelligence)

The robot **thinks by itself**, every 20 ms tick, with **zero internet and zero API**
(the venue has none — that is iron rule #1). `weapon6_brain.py` watches the pilot and
the other weapons and re-tunes them LIVE, always inside safe clamps:

| Thought | Trigger | Action |
|---|---|---|
| 🎯 **GAIN** | sustained cruise drift (EMA error > 6°) | raises W1 `KP` (0.064 → up to 0.072), decays back |
| 🛑 **DAMP** | crash/spin spike (error jump > 10°) | extra W1 `KD` (0.0055 → 0.0085) for 2 s — kills P1 spins |
| 💪 **GRIP** | repeated wheel stalls (>5% of ticks) | raises W2 `BOOST_MAX` (0.35 → up to 0.45), decays back |
| 🏠 **HOME** | endgame return active (last 12 s) | keeps `KP ≥ 0.066` + damping for the sharpest arrival |

- It NEVER touches the motors (Weapon 4 stays the only writer) and NEVER overrides the
  pilot: it only tunes the assist **around the sticks**.
- Every adaptation decays back to the battery-proven base constants.
- `brain.snapshot()` gives live telemetry (kp/kd/boost/drift/stall) for the console.
- Between matches the offline [Robot Coach](Coach) audits and drills the team:
  **Coach plans off-line ↔ on-board brain adapts on-line.**

---

## 🔗 How the chain is wired

```
gamepad 50 Hz → pilot_console (mode decision)
                    → weapon3_curves (shape + slew)
                        → weapon2_torque_boost (feed + boost)
                            → weapon1_gyro_lock (differential PID)
                                → weapon4_traction  ⟶ DRIVETRAIN.set_effort (ONLY writer)
weapon5_endgame  ⟶ side loop: clock + odometry + (optionally) return commands
weapon6_brain    ⟶ side loop: watches everything, re-tunes KP/KD/BOOST live
```

Every weapon has its own `verify.py` unit checks and stress scenarios — see
[Testing and Simulation](Testing-and-Simulation) and [Calibration](Calibration).
