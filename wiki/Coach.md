# 🎽 Robot Coach (100% offline)

> 🎽 A teammate that never gets tired and NEVER needs a network: the **Robot Coach**
> (`coach.py`). There is **no AI API anymore** — no token, no config file, no internet,
> no dependencies. Pure Python 3 stdlib. It **audit**s 🔍 the constants, **explains** 🎈
> every weapon in kid-friendly words, **drills** 🎯 calibration routines, **reports** 📊
> battery logs and keeps the **team memory** 🧠 of lessons learned. It *proposes*,
> **humans** and the battery decide.

---

## 🧠 Who thinks during the match? (IMPORTANT)

**The ROBOT thinks alone.** On the board lives **Weapon 6 — [the brain](The-5-Weapons)**:
it re-tunes the weapons 50 times per second with **zero internet and zero API**. The
Coach is the **between-matches teammate**: it runs on YOUR computer when a developer
launches it deliberately. **Nothing AI-ish runs on the board during a match** — the
venue has no internet, and the board must never wait on a network.

---

## 🚀 Usage (no setup at all)

```bash
python3 coach.py audit                    # 🔍 safe-range sweep of all 6 weapons + wiring + iron rules
python3 coach.py explain weapon1          # 🎈 kid-friendly deep dive of one weapon
python3 coach.py calibrate weapon1        # 🎯 step-by-step on-track tuning drill
python3 coach.py report cycle-3.txt       # 📊 summarize a battery/marathon cycle log
python3 coach.py checklist                # ✅ pre-match checklist (print and tick)
python3 coach.py remember "lesson"        # 🧠 team memory -> coach_memory.md
python3 coach.py memory                   # 📖 read the lessons the team saved
python3 coach.py plan                     # 🗺️ what to improve next, ordered by score impact
```

---

## 🔍 What `audit` checks (the iron rules, automatically)

| Check | Rule |
|---|---|
| Every weapon constant inside its **safe range** | e.g. `KP` in 0.055..0.075, `V_RETURN` in 0.75..0.95 |
| **Weapon 4 is the ONLY** `set_effort` writer | other weapons may only use it behind their standalone-fallback hook guard |
| **No blocking `sleep()`** | `ticks_ms` + `uasyncio` only (`sleep_ms` is fine) |
| **Chain wiring** | every weapon imported by `main_match.py` |

`audit` exits with code 0 (ALL CLEAN) or 1 (issues found), so CI scripts can use it too.

---

## 🧠 Team memory

Lessons live in `coach_memory.md` (created on first `remember`). Read them before every
competition: `python3 coach.py memory`.

---

## 🙅 Guardrails

- The Coach **never edits files autonomously** and never touches the test harnesses or F-metrics.
- It **never runs during a match** and never runs in the cloud workflows.
- No API key exists anywhere in this repo → **nothing to leak**.
