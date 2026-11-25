# 🧠 AI Copilot (generic)

> 🤝 A teammate that never gets tired: an AI copilot with the full context of this
> repository. It **analyze** 📊 the match results, **review** 🔍 your changes before a PR,
> **plan** 🗺️ the next features and **improve** 💡 the weapons — it *proposes*, **humans**
> and the battery decide. It runs on YOUR computer (laptop/PC), **never on the robot
> during a match** (iron rule #1: the board has no internet) and **not in the cloud
> workflows** either — zero API spend by default.

---

## 🔑 Setup (60 seconds, THREE fields — GENERIC, provider-agnostic)

Open **`ai_config.json`** (or copy it to `ai_config.local.json`, which is gitignored and
safer while pushing) and fill the three fields with the values of the API provider of
your choice (any OpenAI-compatible one works):

```json
{
  "base_url":  "<your provider base URL>",
  "api_path":  "<your provider API path>",
  "api_token": "<your token>",
  "model":     "<your model>"
}
```

- 🚫 No GitHub secrets, no `.env`, no keyring — just that file, on your computer.
- 🔒 `ai_config.local.json` is in `.gitignore`; if you fill `ai_config.json` directly,
  just make sure you never commit/push your token (`git status` / `git diff` first).

## 🛠️ Commands (all of them)

| Command | What it does |
|---|---|
| `python3 ai_copilot.py ask "…"` | 💬 Any question with full repo context |
| `python3 ai_copilot.py analyze` | 📊 Reads the last battery and says 1) why each metric moved, 2) the top-3 fixes with concrete constants |
| `python3 ai_copilot.py review` | 🔍 Strict review of your current `git diff` (or last commit): 4 iron rules, pilot priority, constants sanity → APPROVE or FIX FIRST |
| `python3 ai_copilot.py improve weapon3_curves.py` | 💡 One-level-higher proposal for a weapon: plan + FULL file (never auto-applied) |
| `python3 ai_copilot.py explain weapon5_endgame.py` | 🎓 Kid-friendly deep dive into one file: plain words, worked math example, tunable constants, 3 judge-table facts |
| `python3 ai_copilot.py calibrate weapon1` | 🎯 On-track calibration drill for one weapon: test order, what to watch, one constant per step, symptoms of too high / too low |
| `python3 ai_copilot.py audit` | 🔍 OFFLINE sweep of all tuning constants across every file with ⚠️ flags — no token, no internet needed |
| `python3 ai_copilot.py remember "lesson"` | 🧠 OFFLINE: saves a lesson to `ai_memory.md`; every AI task reads that memory first |
| `python3 ai_copilot.py plan` | 🗺️ Roadmap of new functions / drills ordered by score impact |
| `python3 ai_copilot.py chat` | 💭 Interactive session with the iron rules preloaded |

Extras: append `--save answer.md` to any command to save the answer.
No heavy dependencies — Python 3 stdlib only (`urllib`).

## 🧭 Team flow with the copilot

```
battery red  ❌ → ai_copilot.py analyze           → change the proposed constants
PR ready   🔀 → ai_copilot.py review             → fix FIRST list zero
new idea  💡 → ai_copilot.py improve weaponN     → human reading + simulator → PR
lesson    🧠 → ai_copilot.py remember "..."       → the copilot never forgets it
```

> ⚠️ The copilot NEVER edits files by itself. Every code change goes through
> [Collaborating](Collaborating): a human PR + green `ci/battery.sh`. AI is a teammate
> with opinions, not a driver.
