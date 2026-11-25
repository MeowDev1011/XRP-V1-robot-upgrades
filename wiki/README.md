# 📖 Wiki source pages (English, with emojis)

These are the pages of our **GitHub Wiki** handbook, kept in the repository so they are
versioned with the code.

## 🚚 How they reach https://github.com/MeowDev1011/XRP-V1-robot-upgrades/wiki

1. On GitHub open the repo and click the **Wiki** tab → **Create the first page** (one-time
   initialization; only a human with the browser can create the wiki repo — there is no REST API).
2. Then anyone can copy these files (or we push them by git):

   ```bash
   git clone https://github.com/MeowDev1011/XRP-V1-robot-upgrades.wiki.git
   cp wiki/Home.md wiki/*.md XRP-V1-robot-upgrades.wiki.git/
   cd XRP-V1-robot-upgrades.wiki.git && git add -A && git commit -m "📚 sync wiki" && git push
   ```

| Page | Content |
|---|---|
| `Home.md` | 🏠 Index + golden rules + scoreboard |
| `What-Is-This-Robot.md` | 🤖 XRP hardware, sensors, our team |
| `Uploading-Files.md` | 📥 XRPCode / mpremote / Thonny / Copa Robótica |
| `Controls.md` | 🎮 Gamepad map + pilot modes |
| `The-5-Weapons.md` | ⚔️ All five assist systems & constants |
| `Testing-and-Simulation.md` | 🧪 Harnesses, metrics, 24/7 CI battery |
| `Troubleshooting.md` | 🚑 Symptoms → cause → fix |
| `Calibration.md` | 🎛️ Track drills, weapon by weapon |
| `Collaborating.md` | 🤝 Branches, PRs, autonomous improvement |
| `AI-Copilot.md` | 🧠 Generic AI copilot: three fields (base_url / api_path / api_token) |
| `Documentation-Website.md` | 🌐 docs/ site + 3D sandbox |
