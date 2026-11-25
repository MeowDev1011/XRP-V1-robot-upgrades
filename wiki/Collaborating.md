# 🤝 Collaborating

> 💛 This project is built by a school robotics team: kids, mentors and the robot itself.
> These rules keep the repo healthy for everyone.

---

## 🌿 Branches & PRs

- 🛡️ `main` is protected-ish: changes land by **PR**, or direct push by the maintainers after a green battery.
- 🌳 Feature branches: `feature/<weapon>-<idea>`, fixes: `fix/<what>`.
- ✅ A PR is only reviewable when **`bash ci/battery.sh` is green locally** (or CI finishes green).
- ✍️ PR titles in English: `weapon2: raise BOOST_MAX after 1v1 demos`.

## 🚦 What you may and may NOT edit

| Allowed freely ✅ | Only by team decision ⚠️ | NEVER ❌ |
|---|---|---|
| `pilot_gamepad.py` | constants shared by several weapons | test harnesses (`verify/stress/mass_campaign/games`) |
| `weaponN_*.py` behavior | thresholds in `ci/battery.sh` | the **F1–F5 fidelity metrics** definitions |
| comments/docstrings | simulator physics constants | `time.sleep()`, one-button macros, blocking waits |

## 🔁 The 24/7 autonomous improvement (for developers 👀)

Two GitHub Actions workflows keep the robot evolving while we sleep:

- 🧪 **`battery-24-7.yml`** — every 3 hours + every push: the full battery. A red run ❌ is
  the team's to-do list (see the run summary table).
- 🤖 **`auto-improve.yml`** — runs `ci/autotune.py`:
  1. Takes a **baseline** score from a fast campaign (small `MASS_N`).
  2. Tries **tuning candidates** listed in `ci/autotune.json` (one constant at a time — e.g.
     weapon 1 `KP`, weapon 5 `V_RETURN`).
  3. Keeps a candidate only if the score improves; reverts otherwise.
  4. If at least one candidate survived, it **commits the tuned constants on a branch and opens
     a PR** with the measured evidence. Humans merge — the robot proposes, the team decides. 🤝

> 📊 The developers can watch both workflows in the **Actions** tab — that is the "test wall"
> of the team: red = work to do, green = robot healthy.

## 🧭 PR review checklist

- [ ] No `time.sleep(` added anywhere 🔍
- [ ] No exact-button macros or fixed routines
- [ ] Pilot stick priority preserved
- [ ] `ci/battery.sh` green (13/13)
- [ ] Tests and F-metrics untouched
- [ ] New constants documented in [The 5 Weapons](The-5-Weapons) (or [Calibration](Calibration))

## 🐛 Reporting issues

Open a GitHub issue with: **what happened**, **which battery metric**, **the seed / run link**
and, if real field, a short video. Add the `🤖 robot` label if it only reproduces on the
physical board.
