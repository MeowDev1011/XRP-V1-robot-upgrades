#!/usr/bin/env python3
"""
🧠 AI COPILOT — Team Robots Legends (FUSAMO)

A teammate with a lot of context about this repo: analyzes match results,
reviews changes, plans the next improvement and (with a human reviewing)
edits the robot code. NOTE: this runs on the LAPTOP or in GitHub Actions —
NEVER on the robot during a match (rule #1: the board has no internet).
It is also ONLY RUN MANUALLY (never on a schedule) so it never burns API credit.

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
  python3 ai_copilot.py explain weapon5_endgame.py   # kid-friendly deep dive
  python3 ai_copilot.py calibrate weapon1            # on-track tuning checklist
  python3 ai_copilot.py audit              # constants sanity sweep (OFFLINE)
  python3 ai_copilot.py remember "lesson"  # team memory (OFFLINE)
  python3 ai_copilot.py plan               # next-steps roadmap
  python3 ai_copilot.py chat               # interactive session
Optional: --save FILE.md writes the answer to a file.

🧠 MEMORY: `remember` appends a lesson to ai_memory.md; every AI task
   reads that memory first, so the copilot learns from past track sessions.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_LOCAL = os.path.join(ROOT, "ai_config.local.json")
CONFIG_DEFAULT = os.path.join(ROOT, "ai_config.json")
MEMORY_FILE = os.path.join(ROOT, "ai_memory.md")
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
        "model": cfg.get("model", ""),
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


# ---------------- persistent team memory (local file, no API) ----------------
def memory_context(limit=2000):
    try:
        with open(MEMORY_FILE, encoding="utf-8") as fh:
            text = fh.read(limit)
        return "### TEAM MEMORY (ai_memory.md, lessons learned)\n" + text + "\n"
    except OSError:
        return ""


def remember_note(text):
    text = (text or "").strip()
    if not text:
        return "Usage: python3 ai_copilot.py remember \"what you learned\""
    stamp = time.strftime("%Y-%m-%d %H:%M")
    exists = os.path.exists(MEMORY_FILE)
    with open(MEMORY_FILE, "a", encoding="utf-8") as fh:
        if not exists:
            fh.write("# 🧠 Team Robots Legends — Copilot memory\n\n")
        fh.write("- **%s** — %s\n" % (stamp, text))
    return "✅ saved to ai_memory.md (the copilot will carry it into every task)"


# ---------------- offline constants audit ----------------
CONST_RE = re.compile(r"^([A-Z][A-Z_0-9]+)\s*=\s*([-+]?[0-9][0-9.eE+-]*)\s*(#.*)?$")


def parse_constants(path):
    out = []
    for lineno, line in enumerate(read_truncated(path, 20000).splitlines(), 1):
        match = CONST_RE.match(line.strip())
        if match:
            out.append((lineno, match.group(1), match.group(2)))
    return out


def resolve_target(name):
    name = (name or "").strip()
    if not name:
        return None
    for candidate in CONTEXT_FILES + ("main_match.py", "verify.py"):
        if candidate == name or candidate.startswith(name):
            return candidate
    if name.endswith(".py"):
        return name
    return None


def run_audit():
    print("🔍 CONSTANTS AUDIT — offline sweep of every tuning constant\n")
    total = 0
    report = []
    for path in CONTEXT_FILES[1:]:
        if not os.path.exists(os.path.join(ROOT, path)):
            continue
        consts = parse_constants(path)
        if not consts:
            continue
        report.append("%s (%d constants)" % (path, len(consts)))
        for lineno, key, value in consts:
            total += 1
            flags = ""
            try:
                number = float(value)
                if number == 0.0:
                    flags = "  ⚠️ zero (disabled?)"
                elif abs(number) > 1000.0 and "MS" not in key and "N" != key:
                    flags = "  ⚠️ unusually large"
            except ValueError:
                flags = "  ⚠️ not numeric"
            report.append("  L%-4d %-16s = %-8s%s" % (lineno, key, value, flags))
        report.append("")
    table = "\n".join(report)
    print(table)
    print("TOTAL: %d constants across %d files. Check the ⚠️ flags before a match,"
          % (total, sum(1 for p in CONTEXT_FILES[1:]
                        if os.path.exists(os.path.join(ROOT, p))))
          )
    print("and keep ci/autotune.json ranges in sync with what the track likes.")
    return table


# ---------------- tasks ----------------
TASKS = {}


def task(fn):
    TASKS[fn.__name__] = fn
    return fn


@task
def ask(question, cfg, token):
    """Free question with repo context + memory."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": memory_context() +
         "\nREPO CONTEXT:\n" + repo_context() +
         "\n\nQUESTION: " + (question or "(empty)")},
    ]
    return chat(messages, cfg, token)


@task
def analyze(_unused, cfg, token):
    """Diagnose the last battery / match results and propose fixes."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": memory_context() +
         "\nRESULTS:\n" + battery_context() +
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
        {"role": "user", "content": memory_context() +
         "\nDIFF STAT:\n" + stat + "\nDIFF:\n" + diff[:14000] +
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
        {"role": "user", "content": memory_context() +
         "\nTARGET FILE: %s\n%s\n\nLAST RESULTS:\n%s\n\n"
         "TASK: take this file one level higher. Produce: (1) the plan in bullets, "
         "(2) the FULL updated MicroPython file in one code block, honoring the iron "
         "rules. It will be reviewed and simulated by humans — do not break the API "
         "used by pilot/main (module names, singleton names, method names)."
         % (target, current, battery_context()[:3000])},
    ]
    return chat(messages, cfg, token, max_tokens=2400)


@task
def explain(target, cfg, token):
    """Kid-friendly deep explanation of one file."""
    target = target or "weapon1_gyro_lock.py"
    resolved = resolve_target(target) or target
    current = read_truncated(resolved, 12000)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "FILE: %s\n%s\n\n"
         "TASK: explain this file to a smart kid pilot who is new to code: "
         "what each part does in plain words, one worked example of the math, "
         "which constants the team can safely tune (and what happens if they go "
         "too far), and 3 quick facts for the judge interview table."
         % (resolved, current)},
    ]
    return chat(messages, cfg, token)


@task
def calibrate(target, cfg, token):
    """On-track tuning checklist for one weapon (default: gyro lock)."""
    resolved = resolve_target(target) or "weapon1_gyro_lock.py"
    current = read_truncated(resolved, 12000)
    consts = parse_constants(resolved)
    table = "\n".join("L%-4d %-16s = %-8s" % (n, k, v) for n, k, v in consts)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": memory_context() +
         "\nFILE: %s\nCONSTANTS:\n%s\n\nSOURCE:\n%s\n\n"
         "TASK: produce a step-by-step calibration drill for THIS file on the real "
         "track: order of tests, what to observe, which single constant to touch at "
         "each step, safe start values, stop conditions (symptoms of too high / too "
         "low), and the battery command to re-run after each step."
         % (resolved, table, current)},
    ]
    return chat(messages, cfg, token, temperature=0.3)


@task
def plan(_unused, cfg, token):
    """Roadmap: next features/calibrations worth building."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": memory_context() +
         "\nRESULTS:\n" + battery_context()[:4000] +
         "\n\nREPO SUMMARY:\n" + repo_context(limit=8000) +
         "\n\nTASK: build the next-steps roadmap: new assist functions (legal, "
         "continuous, sensor-driven), tests to add, calibration drills. Order by "
         "impact on the Iron Acres score."},
    ]
    return chat(messages, cfg, token, temperature=0.6)


HELP = """
🧠 AI Copilot — usage:

  python3 ai_copilot.py ask "question…"
  python3 ai_copilot.py analyze
  python3 ai_copilot.py review
  python3 ai_copilot.py improve weapon3_curves.py
  python3 ai_copilot.py explain weapon5_endgame.py
  python3 ai_copilot.py calibrate weapon1
  python3 ai_copilot.py audit             ← OFFLINE, no token needed
  python3 ai_copilot.py remember "lesson" ← OFFLINE, no token needed
  python3 ai_copilot.py plan
  python3 ai_copilot.py chat

Optional: --save FILE.md (writes the answer).
Config: ai_config.json (or ai_config.local.json) — fill base_url, api_path, api_token.
Memory: ai_memory.md (auto-created by `remember`, read before every AI task).
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

    if cmd == "remember":
        print(remember_note(" ".join(args[1:])))
        return 0
    if cmd == "audit":
        run_audit()
        return 0
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
