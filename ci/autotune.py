#!/usr/bin/env python3
"""
🤖 AUTOTUNE — autonomous self-improvement of the pilot/weapons.

The robot plays REAL simulated matches against itself (same files that run on
the board), tries tuning candidates for a few weapon constants, and keeps a
candidate ONLY if the measured score improves. `auto-improve.yml` packs the
result into a PR so humans can review — the robot proposes, the team decides.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, "ci")


def load_cfg():
    with open("ci/autotune.json") as fh:
        return json.load(fh)


def eval_once(env):
    """Run one scoring campaign; returns (points_avg, park_pct, strict_pct)."""
    full = {**os.environ, **env}
    out = subprocess.run([sys.executable, "mass_campaign.py"],
                         capture_output=True, text=True, env=full,
                         timeout=2400).stdout
    m = re.search(r"POINTS: avg=([0-9.]+)", out)
    if not m:
        return -1e9, 0.0, 0.0
    p = re.search(r"PARK in zone: ([0-9.]+)%", out)
    s = re.search(r"STRICT with no faults: ([0-9.]+)%", out)
    return float(m.group(1)), float(p.group(1)) if p else 0.0, float(s.group(1)) if s else 0.0


def read_const(path, name):
    txt = open(path).read()
    m = re.search(r"^%s\s*=\s*([-0-9.]+)" % name, txt, re.M)
    if not m:
        raise SystemExit("cannot find constant %s in %s" % (name, path))
    return m.group(1)


def write_const(path, name, value):
    txt = open(path).read()
    new = re.sub(r"^(%s\s*=\s*)[-0-9.]+" % name,
                 lambda mm: mm.group(1) + str(value), txt, count=1, flags=re.M)
    open(path, "w").write(new)


def keep_two_decimals(v):
    """Represent floats deterministically (0.85 -> '0.85')."""
    return str(round(float(v), 6))


def main():
    cfg = load_cfg()
    env = dict(cfg.get("eval", {}).get("env", {}))
    base_pts, base_park, base_strict = eval_once(env)
    print("BASELINE: points=%.2f park=%.1f%% strict=%.1f%%" %
          (base_pts, base_park, base_strict))

    summary = ["## 🤖 Autotune report (evidence, not vibes)", "",
               "| Constant | Tried | Points avg | Park %% | Verdict |",
               "|---|---|---|---|---|",
               "| (baseline) | — | %.2f | %.1f | — |" % (base_pts, base_park)]
    applied = []

    for tgt in cfg.get("targets", []):
        path = tgt["file"]
        name = tgt["const"]
        orig = read_const(path, name)
        best_val = orig
        best_pts, best_park = base_pts, base_park
        for cand in tgt.get("values", []):
            cand_s = keep_two_decimals(cand)
            if cand_s == orig:
                continue
            write_const(path, name, cand_s)
            try:
                pts, park, _strict = eval_once(env)
            except subprocess.TimeoutExpired:
                pts, park = -1e9, 0.0
            verdict = "REJECTED" if (pts <= best_pts or park < base_park - 1.0) else "BETTER"
            print("%s.%s = %s -> points=%.2f park=%.1f%% %s" %
                  (path, name, cand_s, pts, park, verdict))
            summary.append("| `%s:%s` | %s | %.2f | %.1f | %s |" %
                           (path, name, cand_s, pts, park, verdict))
            if pts > best_pts and park >= base_park - 1.0:
                best_val, best_pts, best_park = cand_s, pts, park
        write_const(path, name, orig)   # restore; re-apply winner below
        if best_val != orig:
            write_const(path, name, best_val)
            applied.append((path, name, orig, best_val, best_pts))
            summary.append("| ✅ **`%s:%s`** | %s → **%s** | **%.2f** | %.1f | APPLIED |" %
                           (path, name, orig, best_val, best_pts, best_park))

    print()
    print("== AUTOTUNE SUMMARY ==")
    print("\n".join(summary))
    if applied:
        report = "\n".join(summary) + \
            "\n\n**Robot-approved changes** (merge only if the FULL battery stays green):\n"
        for path, name, orig, best_val, pts in applied:
            report += "\n- `%s`: %s → **%s** (points %.2f vs %.2f baseline)" % (
                path + ":" + name, orig, best_val, pts, base_pts)
        with open("/tmp/autotune_report.md", "w") as fh:
            fh.write(report)
        open("/tmp/autotune_applied", "w").write("yes")
        print("RESULT: %d improvement(s) applied" % len(applied))
    else:
        with open("/tmp/autotune_report.md", "w") as fh:
            fh.write("## 🤖 Autotune report\n\nNo candidate beat the baseline. "
                     "The robot stays unchanged. 🧘\n")
        open("/tmp/autotune_applied", "w").write("no")
        print("RESULT: no improvements this round")

    subprocess.run([sys.executable, "-m", "py_compile"]
                   + [t["file"] for t in cfg.get("targets", [])], check=True)


if __name__ == "__main__":
    main()
