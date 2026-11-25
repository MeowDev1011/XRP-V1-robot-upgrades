#!/usr/bin/env python3
"""
🧠 AI COPILOT — Team Robots Legends (FUSAMO)

A teammate with a lot of context about this repo: analyzes match results,
reviews changes, plans the next improvement and (with a human reviewing)
edits the robot code. NOTE: this runs on the LAPTOP or in GitHub Actions —
NEVER on the robot during a match (rule #1: the board has no internet).

🔌 CONFIG — GENERIC (any OpenAI-compatible provider, platform-agnostic):
  • Open ai_config.json (or copy it to ai_config.local.json) and fill
    the THREE fields:  base_url  /  api_path  /  api_token  (+ model).
  • That is all: token lives in YOUR config file, never committed.
    (ai_config.local.json is gitignored so your token cannot leak.)

🛠 COMMANDS:
  python3 ai_copilot.py ask "how do I raise park accuracy?"
  python3 ai_copilot.py analyze            # reads the last battery summary
  python3 ai_copilot.py review             # reviews `git diff` before a PR
  python3 ai_copilot.py improve weapon1_gyro_lock.py
  python3 ai_copilot.py plan               # next-steps roadmap
  python3 ai_copilot.py chat               # interactive session
Optional: --save FILE.md writes the answer to a file.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_LOCAL = os.path.join(ROOT, "ai_config.local.json")
CONFIG_DEFAULT = os.path.join(ROOT, "ai_config.json")
CONTEXT_FILES = ("README.md", "pilot_gamepad.py", "weapon1_gyro_lock.py",
                 "weapon2_torque_boost.py", "weapon3_curves.py",
                 "weapon4_traction.py", "weapon5_endgame.py")
MAX_CONTEXT_CHARS = 16000

SYSTEM_PROMPT = (
    "You are the AI COPILOT of Team Robots Legends (FUSAMO), a kid-driven robotics "
    "team competing in XRP Iron Acres (150,000 ms matches).\n"
    "Iron rules of this repo, memorize them:\n"
    "1. Code runs ON the robot: MicroPython + XRPLib only, no internet during matches.\n"
    "2. NO time.sleep() and no blocking waits: ticks_ms() deadlines or uasyncio only.\n"
    "3. NO one-button macros: assistance must be continuous and sensor-reactive.\n"
    "4. Pilot sticks are ALWAYS the boss; weapons only assist around them.\n"
    "5. Only weapon4_traction writes to the motors (end of the chain).\n"
    "When you propose code, keep names/structure consistent with the existing files, "
    "explain WHY with the measured metrics (P1/P2/P3, F1-F5, points, park %), and "
    "remind the team to re-run the battery and calibrate on the real track."
)


# ---------------- config (ONE file, THREE fields) ----------------
def load_config():
    """Prefer ai_config.local.json (gitignored), fallback to ai_config.json."""
    path = CONFIG_LOCAL if os.path.exists(CONFIG_LOCAL) else CONFIG_DEFAULT
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_config(cfg):
    missing = [k for k in ("base_url", "api_path", "api_token", "model")
               if not str(cfg.get(k) or "").strip()]
    if missing:
        print("🔑 ai config incomplete. Open ai_config.json "
              "(or ai_config.local.json) and fill:",
              ", ".join(missing))
        return False
    return True


# ---------------- transport (stdlib only) ----------------
def chat(messages, cfg, token, temperature=None, max_tokens=None):
    url = cfg["base_url"].rstrip("/") + cfg["api_path"]
    payload = {
        "model": cfg.get("model", "llama-3.3-70b-versatile"),
        "messages": messages,
        "temperature": cfg.get("temperature", 0.4) if temperature is None else temperature,
        "max_tokens": cfg.get("max_tokens", 1800) if max_tokens is None else max_tokens,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SystemExit("API error %s: %s\n(check api_token / base_url / api_path "
                         "in your ai_config)"
                         % (exc.code, exc.read().decode("utf-8", "ignore")[:300]))
    except urllib.error.URLError as exc:
        raise SystemExit("Cannot reach %s (%s). Coming back when you have internet."
                         % (url, exc.reason))
    return data["choices"][0]["message"]["content"]


# ---------------- context builders ----------------
def read_truncated(path, limit):
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            return fh.read(limit)
    except OSError:
        return "(missing: %s)" % path


def repo_context(extra=(), limit=MAX_CONTEXT_CHARS):
    parts = []
    for name in tuple(extra) + CONTEXT_FILES:
        if not os.path.exists(os.path.join(ROOT, name)):
            continue
        parts.append("### FILE: %s\n%s" % (name, read_truncated(name, 4000)))
    text = "\n\n".join(parts)
    return text[:limit]


def git_out(*args):
    try:
        return subprocess.run(("git",) + args, cwd=ROOT, capture_output=True,
                              text=True, timeout=30).stdout
    except Exception as exc:  # noqa: BLE001
        return "(git failed: %s)" % exc


def battery_context():
    paths = ["/tmp/summary.md", os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"),
                                             "summary.md")]
    for p in paths:
        if p and os.path.exists(p):
            return "### LAST BATTERY SUMMARY\n" + open(p, encoding="utf-8").read(4000)
    recent = git_out("log", "--oneline", "-5").strip()
    return ("### NO BATTERY LOG FOUND\nRun `bash ci/battery.sh` first; meanwhile, "
            "the last commits were:\n%s" % (recent or "(none)"))


# ---------------- tasks ----------------
TASKS = {}


def task(fn):
    TASKS[fn.__name__] = fn
    return fn


@task
def ask(question, cfg, token):
    """Free question with repo context."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "REPO CONTEXT:\n" + repo_context() +
         "\n\nQUESTION: " + question},
    ]
    return chat(messages, cfg, token)


@task
def analyze(_unused, cfg, token):
    """Diagnose the last battery / match results and propose fixes."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "RESULTS:\n" + battery_context() +
         "\n\nREPO:\n" + repo_context(extra=("ci/battery.sh",), limit=8000) +
         "\n\nTASK: diagnose which weapon/pilot behavior explains each metric, "
         "rank the 3 highest-impact fixes, and give concrete constant changes "
         "(file, constant, current → proposed, expected effect)."},
    ]
    return chat(messages, cfg, token)


@task
def review(_unused, cfg, token):
    """Review the current uncommitted diff like a strict coach."""
    diff = git_out("diff")
    stat = git_out("diff", "--stat")
    if not diff.strip():
        diff = git_out("diff", "HEAD~1")
        stat = git_out("diff", "--stat", "HEAD~1")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "DIFF STAT:\n" + stat + "\nDIFF:\n" + diff[:14000] +
         "\n\nTASK: review this change: correctness, the 4 iron rules, "
         "pilot-priority violations, constants sanity. Verdict: APPROVE or FIX FIRST "
         "with the exact list."},
    ]
    return chat(messages, cfg, token)


@task
def improve(target, cfg, token):
    """Propose a concrete upgrade for one file (never applied automatically)."""
    target = target or "weapon1_gyro_lock.py"
    current = read_truncated(target, 12000)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "TARGET FILE: %s\n%s\n\nLAST RESULTS:\n%s\n\n"
         "TASK: take this file one level higher. Produce: (1) the plan in bullets, "
         "(2) the FULL updated MicroPython file in one code block, honoring the iron "
         "rules. It will be reviewed and simulated by humans — do not break the API "
         "used by pilot/main (module names, singleton names, method names)."
         % (target, current, battery_context()[:3000])},
    ]
    return chat(messages, cfg, token, max_tokens=2400)


@task
def plan(_unused, cfg, token):
    """Roadmap: next features/calibrations worth building."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "RESULTS:\n" + battery_context()[:4000] +
         "\n\nREPO SUMMARY:\n" + repo_context(limit=8000) +
         "\n\nTASK: build the next-steps roadmap: new assist functions (legal, "
         "continuous, sensor-driven), tests to add, calibration drills. Order by "
         "impact on the Iron Acres score."},
    ]
    return chat(messages, cfg, token, temperature=0.6)


HELP = """🧠 AI Copilot — usage:

  python3 ai_copilot.py ask "question…"
  python3 ai_copilot.py analyze
  python3 ai_copilot.py review
  python3 ai_copilot.py improve weapon3_curves.py
  python3 ai_copilot.py plan
  python3 ai_copilot.py chat

Optional: --save FILE.md (writes the answer).
Config: ai_config.json (or ai_config.local.json) — fill base_url, api_path, api_token.
"""


def interactive(cfg, token):
    print("💬 Copilot chat — write your message ('exit' to quit). Iron rules are loaded.")
    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    while True:
        try:
            line = input("\n🧑‍🚀 you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye 👋")
            return ""
        if line.lower() in ("exit", "quit"):
            return ""
        if not line:
            continue
        history.append({"role": "user", "content": line})
        reply = chat(history, cfg, token)
        history.append({"role": "assistant", "content": reply})
        print("\n🤖 copilot>\n" + reply)


def main(argv):
    cfg = load_config()
    args = [a for a in argv if a != "--save"]
    save = argv.index("--save") + 1 < len(argv) if "--save" in argv else None
    if save:
        args = [a for a in args if a != argv[save]]

    cmd = args[0] if args else "help"
    if cmd == "help" or cmd not in TASKS and cmd != "chat":
        print(HELP)
        return 0
    if not check_config(cfg):
        return 2
    token = str(cfg["api_token"]).strip()

    if cmd == "chat":
        out = interactive(cfg, token)
    else:
        out = TASKS[cmd](args[1] if len(args) > 1 else None, cfg, token)
        print(out)
    if save:
        with open(argv[save], "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
        print("\n💾 saved to %s" % argv[save])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
