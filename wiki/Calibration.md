# 🎛️ Calibration Guide (on the real track)

> 🧪 The simulator gives the *shape*; the real track gives the *truth*. Calibrate **one
> weapon at a time**, in this order, on the same carpet and battery level when possible.

---

## 0️⃣ Before any tuning

- 🔋 Charge the battery (kneecap at **7.4 V+**; weak battery fakes "weak weapons").
- 🧹 Flat IMU mount, robot on the **actual competition surface**.
- 📝 Bring a notebook: every change we commit must have its measured `before → after`.

## 1️⃣ Weapon 1 — Gyro-Lock

1. Place the robot straight, press START. Push Y and **release**: it must stop pointing 0°.
2. Give it a *shoulder hit* across the nose: it must recover in < 1 s without overshoot.
3. Tune: oscillates → lower `KP`· raise `KD` · slow/lazy to correct → raise `KP` · steady small
   angle error → confirm `KI` acts (only within `I_ZONE`).
4. Target: P2-style error < 3° during cruise on carpet.

## 2️⃣ Weapon 2 — Torque Boost

1. Place a light weight / hand resistance on top; half stick Y.
2. Feel the boost cut in (motors "grab") and release when freed.
3. Tune: `STALL_RATIO` down = more sensitive · `BOOST_STEP` up = faster grab ·
   never need `BOOST_MAX > 0.4` in Iron Acres.

## 3️⃣ Weapon 3 — Curves

1. Kid drives a slalom of two cones at walking speed: if it feels twitchy, raise `MIX_PRECISION`.
2. Long straight sprints must feel identical to stock (100 % at full stick).
3. Check the **trim nudge**: hold Y and small-X — heading should pan smoothly, not step.

## 4️⃣ Weapon 4 — Traction & Brake

1. Full-speed stop test from the far wall: measure slide distance on the floor tape — target < 8 cm.
2. Launch test on glossy tiles (worst case): no chirp/squeal on startup.
3. Tune: slide > 8 cm → raise `PULSE_MAX` · startup slip → lower `RAMP_MAX`.

## 5️⃣ Weapon 5 — Auto-Endgame

1. `home_here()` on the start pad, drive away ~2 m, wait for the LED alarm.
2. It must cross the zone edge, slow, and stop **inside**, brake-nailed.
3. Tune: arrives late → raise `V_RETURN` (0.85 default) · overshoots → raise `K_SOFT_ARRIVAL`.
4. Verify with the official field marks that `HOME_TOL_CM=10` matches the scorer's eye.

## 6️⃣ Whole-match rehearsal

- 🎮 Full 150 s run with the kid pilot on the gamepad, weapons ON.
- 🎥 Film it; compare against the CI table (STRICT %, points avg).
- 🔁 One change per rehearsal day — otherwise we cannot attribute improvements.

---

> 🗺️ Also rehearse the OTHER games at least before each event:
> 🤼 SUMO push-outs, ⚽ SOCCER roles — the browser [sandbox](Documentation-Website)
> is a fun way to teach game rules to new members.
