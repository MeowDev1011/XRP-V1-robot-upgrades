# 📥 Uploading Files to the Robot

> 🎯 Goal: get these **7 files** onto the robot's filesystem root:
> `weapon1_gyro_lock.py` · `weapon2_torque_boost.py` · `weapon3_curves.py` ·
> `weapon4_traction.py` · `weapon5_endgame.py` · `pilot_gamepad.py` · `main_match.py`

---

## 🥇 Method 1 — XRPCode (official web editor) ⭐ recommended

1. 🌐 Open **[xrpcode.wpi.edu](https://xrpcode.wpi.edu)** in **Chrome, Edge or Opera** (WebSerial only works there).
2. 🔌 Plug the XRP to the computer with **USB** and press **Connect** (top right). Pick the board when asked.
3. 🗂️ Open the **Filesystem** panel and press **+ / New file**, one file at a time:
   - Name it exactly like the repo file (`weapon1_gyro_lock.py`, …).
   - Paste the file content and **save** (Ctrl+S).
   - The sensor/servo test blocks of XRPCode keep working — our code is designed to coexist with them.
4. ▶️ Open the **Python** tab and run:

```python
import main_match
```

5. 🎮 Connect the gamepad, press **START** on the console and the match clock begins.

> 💡 **Tip**: after uploading, use the Filesystem panel list to confirm all 7 files are there —
> a missing file shows up as `ImportError` in the REPL (see [Troubleshooting](Troubleshooting)).

## 🥈 Method 2 — USB serial with `mpremote`

On any OS with Python 3.9+ installed:

```bash
# install the official device tool
pip install mpremote

# copy files (XRP plugged by USB) — run this from the repo folder
mpremote fs cp weapon1_gyro_lock.py weapon2_torque_boost.py \
  weapon3_curves.py weapon4_traction.py weapon5_endgame.py \
  pilot_gamepad.py main_match.py :

# open the REPL and start
mpremote
>>> import main_match
```

Notes:
- 📁 The trailing `:` in `fs cp ... :` means *robot root*.
- 🔁 If the board is mid-program, press **Ctrl+C** twice or reset the board first.

## 🥉 Method 2b — Thonny (friendliest for kids)

1. Install [Thonny](https://thonny.org) → Tools → **Options → Interpreter → MicroPython (RP2040)**.
2. Plug the board; the files panel opens automatically.
3. Right-click each local file → **Upload to /**.

## 🏫 Method 3 — Copa Robótica classroom platform

Our class platform: **[programacion.coparobotica.com](https://programacion.coparobotica.com)** 🇪🇸

1. Log in and join the **class link + code** the coach shared.
2. Open the robot editor — it uses the **same USB connect flow** as XRPCode.
3. Create/paste the 7 files with the same names and run `import main_match`.

---

## 🧷 File-by-file cheat sheet

| File | One-line role |
|---|---|
| `main_match.py` | 🧵 Starts IMU calibration and runs the forever loop |
| `pilot_gamepad.py` | 🎮 50 Hz console: reads gamepad → decides mode |
| `weapon1_gyro_lock.py` | 🎯 Heading lock PID |
| `weapon2_torque_boost.py` | 💪 Stall detection + torque boost |
| `weapon3_curves.py` | 🕹️ Cubic stick curves |
| `weapon4_traction.py` | 🛞 Launch ramp + active brake pulse (ONLY writer to motors) |
| `weapon5_endgame.py` | ⏱️ Match clock, odometry, home return |

Troubles? ➡️ [Troubleshooting](Troubleshooting) · Ready to drive? ➡️ [Controls](Controls)
