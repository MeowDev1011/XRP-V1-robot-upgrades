# 🧠 AI Copilot (Groq)

> 🤝 A teammate that never gets tired: an AI copilot with the full context of this
> repository. It **analyze** 📊 the match results, **review** 🔍 your changes before a PR,
> **plan** 🗺️ the next features and **improve** 💡 the weapons — it *proposes*, **humans**
> and the battery decide. It runs on the laptop or in GitHub Actions — **never on the
> robot during a match** (iron rule #1: the board has no internet).

---

## 🔑 Setup (60 seconds)

The file **`ai_config.json`** already ships configured for **Groq** ✅:

```json
{
  "base_url": "https://api.groq.com/openai/v1",
  "api_path": "/chat/completions",
  "model": "llama-3.3-70b-versatile"
}
```

You only **add your token** (never commit it!):

```bash
echo "gsk_your_groq_token_here" > ai_token.txt
```

…or as an environment variable: `export GROQ_TOKEN=gsk_...` — / the same as a
**GitHub secret** named `GROQ_TOKEN` for the cloud workflow
(*Settings → Secrets and variables → Actions*).

- 🔒 `ai_token.txt` is in `.gitignore` — verify with `git status` that it never shows up.

## 🛠️ Commands (all of them)

| Command | What it does |
|---|---|
| `python3 ai_copilot.py ask "…" ` | 💬 Any question with full repo context |
| `python3 ai_copilot.py analyze` | 📊 Reads the last battery and says 1) why each metric moved, 2) the top-3 fixes with concrete constants |
| `python3 ai_copilot.py review` | 🔍 Strict review of your current `git diff` (or last commit): 4 iron rules, pilot priority, constants sanity → APPROVE or FIX FIRST |
| `python3 ai_copilot.py improve weapon3_curves.py` | 💡 One-level-higher proposal for a weapon: plan + FULL file (never auto-applied) |
| `python3 ai_copilot.py plan` | 🗺️ Roadmap of new functions/ drills ordered by score impact |
| `python3 ai_copilot.py chat` | 💭 Interactive session with the iron rules preloaded |

Extras: append `--save answer.md` to any command to save the answer.
No heavy dependencies — Python 3 stdlib only (`urllib`).

## ☁️ In the cloud (workflow `ai-copilot.yml`)

*Actions → AI Copilot → Run workflow* → pick the task (analyze / plan / review / ask /
improve), optionally type the question or the target file. The run:

1. 🧪 Prepares fresh context (verify + stress + mini Iron Acres campaign),
2. 🧠 Calls the copilot with your `GROQ_TOKEN` secret,
3. 📦 Saves the answer as an artifact (**90 days**) **and opens an Issue** so the whole
   team can discuss it.

## 🧭 Team flow with the copilot

```
battery red ❌ → ai_copilot.py analyze           → change the proposed constants
PR ready   🔀 → ai_copilot.py review             → fix FIRST list zero
new idea  💡 → ai_copilot.py improve weaponN     → human reading + simulator → PR
```

> ⚠️ The copilot NEVER edits files by itself in this flow. Every code change goes through
> [Collaborating](Collaborating): a human PR + green `ci/battery.sh`. AI is a teammate
> with opinions, not a driver.
