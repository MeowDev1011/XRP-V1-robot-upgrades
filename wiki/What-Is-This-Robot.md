# 🤖 What Is This Robot?

> 📸 The **XRP** (Experiential Robotics Platform) is a small competition robot built by
> **SparkFun · Worcester Polytechnic Institute (WPI) · DEKA · FIRST**. It is the official
> platform of the **FIRST** robotics progression for entry classes and of programs such as
> **BootCamp Aventura Transforma**.

---

## 🧠 The brain: Raspberry Pi Pico W

- ⚙️ Microcontroller **RP2040** dual-core running **MicroPython**.
- 📡 The **W** variant adds Wi-Fi — but our rules say **no Internet during a match**. On-board only!
- 🔌 The user code lives at the board root (`.py` files), started from XRPCode or the REPL.

## 👀 The senses (sensors we use)

| Sensor | What we use it for | Used by |
|---|---|---|
| 🌀 **IMU** (`XRPLib.imu`) | Yaw angle for the heading lock; calibration `imu.calibrate(1.0)` at boot | Weapon 1 · 5 |
| 🔄 **Wheel encoders** (`get_left_encoder_position` / `get_right_encoder_position`) | Real wheel speed, stall detection, odometry X/Y/θ | Weapon 2 · 4 · 5 |
| 📏 **Ultrasonic** (`DistanceSensor`) | Obstacle stop during the endgame return | Weapon 5 |
| 🎮 **Gamepad** (50 Hz packet loop) | The pilot's real console — the ONLY source of intent | `pilot_gamepad.py` |
| 💡 On-board **LED** | Endgame alert (blinks 4 Hz) and mode feedback | `main_match.py` |

## 💪 The muscles

- Two DC geared motors on the **left/right drivetrain** (`DRIVETRAIN.set_effort`) — the target of
  the whole assist chain.
- One or two **servos** (game pieces / attachments — not used by the 5 weapons).

---

## 👥 Who is Team Robots Legends?

🇸🇻 We are **Team Robots Legends**, from **FUSAMO**, competing in the **⚔️ Iron Acres** game of
**BootCamp Aventura Transforma**. Our pilot is a young, very good gamer 👦🎮 with great instincts —
and without the motor precision of an adult. That is exactly why this software exists:

> 💡 **The mission**: let the kid play with a real video-game console while the robot quietly
> fixes drift, stalls, skids and the match clock — assistance for a
> *good gamer*, not automation that ignores the pilot.

## 🏟️ The competition: Iron Acres

- ⏱️ Matches last **exactly 2 minutes 30 seconds (150,000 ms)**.
- 🧺 Points come from delivering/parking game objects, with the **park bonus at the home zone**.
- 🏁 The last **12 seconds** are the endgame — return home time (see [The 5 Weapons](The-5-Weapons)).

Next ➡️ [Uploading Files](Uploading-Files) to install the software, or [The 5 Weapons](The-5-Weapons)
to understand the magic.
