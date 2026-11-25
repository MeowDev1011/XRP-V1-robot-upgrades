# 🎮 Controls — the real gamepad pilot

> 🕹️ **The physical console is the boss.** The pilot loop runs at **50 Hz** (every 20 ms) and
> always respects the sticks — the weapons just wrap smarter behavior around the pilot's intent.

---

## 🗺️ Stick map

| Input | Action | Assist involved |
|---|---|---|
| 🕹️ **Left stick Y** (`axes[1]`) | Forward / backward drive | Weapon 3 cubic curve → Weapon 2 boost |
| 🕹️ **Left stick X** (`axes[0]`) | Turning | Weapon 3 curve → Weapon 1 locks the turn rate |
| 🕹️ **Left stick released** | Robot must stand still | Weapon 4 nails it + Weapon 1 holds heading |
| 🔘 **START** (edge) | Start / restart the 150 s match clock | Weapon 5 |
| 🔘 **Select/(double-click START)** | Toggle assisted home-return ON/OFF | Weapon 5 |

## 🧭 Pilot modes (internal, 50 Hz)

| Mode | When it activates | What the assists do |
|---|---|---|
| 🅿️ **STOP** | Sticks released | Weapon 4 brake pulse; Weapon 1 holds yaw for the future |
| ⬆️ **STRAIGHT** | Only Y (beyond `FWD_MIN`) | Weapon 1 locks heading; small X becomes **trim** of the locked angle |
| 🔄 **TURN** | X beyond `TURN_MIN` | Weapon 1 turns at a controlled rate; on release, **SETTLE** kills residual momentum |
| 🏠 **RETURN** | Endgame toggle ON | Weapon 5 drives home; pilot can always override |

**Priority is always: 🎮 sticks > 🏠 return > 🅿️ helpers.** No assist ever fights an active stick.

## 🧒 The pilot profile: KID

Our pilot is a **young good gamer** — fast reflexes, not adult thumb precision. The console
handles it with:

- 🌊 **Tremor filter** (EMA) and a dead zone — micro stick noise never reaches the motors.
- ✂️ **No reverse** in soccer-type games: a kid pressing down by accident shouldn't score an own goal.
- 🧲 **Trim re-aiming**: when the kid pushes Y+small-X, the locked heading slides a bit — gentle
  "nudge steering" instead of fighting the drive.
- 🧯 **Active braking on turn release**: the robot stops *with* him, no over-rotate.

The pilot profiles used by the simulators: `KID` (default) · `GOOD` · `REGULAR` · `ADULT`
(see [Testing and Simulation](Testing-and-Simulation)).

## 🔁 What the pilot sees on the LED

| LED state | Meaning |
|---|---|
| 💚 Solid | Match armed, waiting for START |
| 🟡 Slow blink | Normal play |
| 🔴 Fast blink (4 Hz) | **125 s reached** — return home now! |
| 🟢 Locked solid at end | Parked in zone (weapon 5) |
