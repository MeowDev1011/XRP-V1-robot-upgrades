# 🌐 Documentation Website & 3D Sandbox

> 🎨 Inside the repository there is a small website in `docs/` — pure HTML + CSS + a
> little JavaScript. **No build step, works offline**, open it in any browser.

---

## 📂 What lives in `docs/`

| File | What it is |
|---|---|
| `index.html` | 🏠 Main documentation site: animated hero, weapon cards, match rules, install guides, test tables, troubleshooting, FAQ links |
| `sandbox.html` | 🧊 The **Three.js 3D sandbox** — play the three training games in the browser |
| `style.css` | 🎨 Shared theme: aurora background, glass cards, scroll animations |

## 🧊 The 3D sandbox (DRIVE · SUMO · SOCCER)

Open `docs/sandbox.html` (or serve the folder: `python3 -m http.server -d docs 8000` →
http://localhost:8000/sandbox.html).

Games included (same spirit as `games.py`, minus Iron Acres which needs the full field model):

- 🤼 **SUMO** — 45 s, push the red rival out of the dohyo before it pushes you.
- ⚽ **SOCCER** — 120 s, grab and kick the ball into the green goal defended by a little keeper.
- 🚗 **DRIVE** — 60 s, cross the **doors** in order as they light up; count full laps.

Controls: **W A S D / arrows** drive · **SPACE** brake · **R** restart · **drag** to orbit
the camera · **wheel** to zoom · on phones, use the on-screen touch pad.

> 🧠 The sandbox robot has the same proportions and "kid physics" (acceleration curve +
> active brake) as the real chain — useful to teach new members the pilot feel without hardware.

## 🖼️ Why no emojis-as-3D?

The Three.js scenes are intentionally simple so the whole folder stays readable by students:
`makeRobot()` in `sandbox.html` builds the chassis + 4 wheels + cabin in ~30 lines. 🎓 Reuse it
for class demos!
