# 🌐 Documentation Website & 3D Sandbox

> 🎨 Inside the repository there is a small website in `docs/` — pure HTML + CSS + a
> little JavaScript. **No build step, works offline**, open it in any browser.

---

## 📂 What lives in `docs/`

| File | What it is |
|---|---|
| `index.html` | 🏠 Main documentation site: animated hero, weapon cards, match rules, install guides, test tables, troubleshooting |
| `sandbox.html` | 🎮 The **Three.js 3D sandbox v3** — 5 games (SUMO / SUMO2 / SOCCER / SOCCER2 / DRIVE), cinematic tone mapping, pooled particles, canvas-generated field textures, XRP-style robot, sound, minimap, boost, records, 3 cameras |
| `style.css` | 🎨 Shared theme: aurora background, glass cards, scroll animations |

## 🎯 100% SVG icons — zero emojis

Every icon on the website (nav, headings, buttons, HUD, touch pad, footer) is a
hand-made **stroke SVG symbol** defined once in a hidden sprite
(`<symbol id="i-...">` + `<use href="#i-...">`). No emoji characters anywhere —
they render identically on every device and colorize with `currentColor`.

## 🎮 The 3D sandbox (DRIVE · SUMO · SUMO2 · SOCCER · SOCCER2)

Open `docs/sandbox.html` (or serve the folder: `python3 -m http.server -d docs 8000` →
http://localhost:8000/sandbox.html).

Games included (same spirit as `games.py`, minus Iron Acres which needs the full field model):

- 🛡️ **SUMO** — 45 s, push the red rival out of the dohyo before it pushes you.
- ⚽ **SOCCER** — 120 s, grab and kick the ball into the green goal defended by a little keeper.
- 🚗 **DRIVE** — 60 s, cross the **doors** in order as they light up; count full laps.

Controls: **W A S D / arrows** drive · **SHIFT** boost · **SPACE** brake · **R** restart ·
**C** camera · **M** mute · **drag** to orbit the camera · **wheel** to zoom ·
on phones, use the on-screen touch pad.

### What makes v3 smooth (the stutter fix)

- **Pooled particles**: one single `THREE.Points` with a fixed 500-particle ring buffer.
  `burst()` only writes into the buffers — **zero geometry/material allocation per frame**,
  so the garbage collector never hitches the render loop (v2 created a new Box + material
  for every spark, which caused the stutter).
- **Cinematic renderer**: ACES filmic tone mapping, sRGB output, pixel-ratio capped at 1.75,
  soft 1024² shadow map with bias — better look, less GPU load than v2's 2048².
- **Canvas-generated textures**: mowed grass with white field markings, clay dohyo with
  shikiri-sen, asphalt with dashed lane — generated at load in ~4 KB of code, no assets.
- **XRP-style robot**: 2 big drive wheels + front caster, green "Pi" board with chip, red
  battery, ultrasonic sensor bar with two eyes, LED visor, blinking mast LED — and
  **lean physics**: the chassis rolls into curves.
- **Smoothed camera**: the follow camera lerps position and FOV, so driving feels analog
  instead of rigid.

> 🧠 The sandbox robot has the same proportions and "kid physics" (acceleration curve +
> active brake) as the real chain — useful to teach new members the pilot feel without hardware.

## 🖼️ Why no emojis-as-3D?

The Three.js scenes are intentionally simple so the whole folder stays readable by students:
`makeRobot()` in `sandbox.html` builds the realistic XRP-style robot in ~60 lines. 🎓 Reuse it
for class demos!

---

**Enable GitHub Pages to see it online:** repository *Settings → Pages → Source: `main` /
folder: `/docs`*. Until then, open the files locally.
