#!/usr/bin/env bash
# =========================================================
# 24/7 BATTERY - Team Robots Legends (FUSAMO)
# Runs the ENTIRE robot test package and fails (exit 1) if
# any metric drops below its threshold. Thresholds come from
# the measured results recorded in the README.
# Usage: bash ci/battery.sh
# Summary: /tmp/summary.md (GitHub Actions shows it in the run)
# =========================================================
set -uo pipefail
cd "$(dirname "$0")/.."

S=/tmp/summary.md
L="${BATTERY_LOGS:-/tmp}"
: > "$S"
FAIL=0

# ---------------- 1. math unit tests ----------------
if python3 verify.py 2>/dev/null | tee "$L/verify.log" | grep -q "ALL TESTS PASS"; then
  echo "| tests | tests | 12/12 | 12/12 | OK |" >> "$S"
else
  echo "| tests | tests | FAIL | 12/12 | FAIL |" >> "$S"; FAIL=1
fi

# ---------------- 2. stress ----------------
N_OK=$(python3 stress.py 2>/dev/null | tee "$L/stress.log" \
       | grep -oE "RESULT: [0-9]+" | grep -oE "[0-9]+")
check() {  # check "Name" "measured" "threshold_gte" "metric"
  local ok
  ok=$(python3 -c "print('OK' if float('${2:-nan}') >= float('${3:-nan}') else 'FAIL')" 2>/dev/null) || ok=FAIL
  echo "| $1 | $4 | ${2:-?} | ${3} | ${ok} |" >> "$S"
  if [ "$ok" != "OK" ]; then FAIL=1; fi
}
check "stress (30 matches)" "${N_OK:-0}" "30" "Matches approved"

# ---------------- helpers for campaign logs ----------------
grab() {  # first line of log containing $1, first datum ending in %
  grep -m1 "$1" "$2" | awk '{ for (i=1;i<=NF;i++) if ($i ~ /%$/) { sub(/%/,"",$i); print $i; exit } }'
}
pointsAvg() { # points avg from the mass_campaign summary
  grep -m1 "^POINTS" "$1" | sed -n "s/.*avg=\([0-9.]*\).*/\1/p"
}
goalsAvg() {  # goals avg of one games mode (the FIRST "avg", scored in our favor)
  grep -m1 "^$1 " "$2" | awk '{ for (i=1;i<=NF;i++) if ($i == "avg") { print $(i+1); exit } }'
}

# ---------------- 3. Iron Acres (mass campaigns) ----------------
MASS_N=300 MASS_W=2 MASS_PILOT=KID python3 mass_campaign.py 2>/dev/null \
  | tee "$L/mass_kid.log" > /dev/null
check "IronAcres KID (n300)" "$(grab "PARK in zone" "$L/mass_kid.log")" "90.0" "Park in zone %"
check "IronAcres KID (n300)" "$(grab "STRICT"   "$L/mass_kid.log")" "60.0" "STRICT %"
P1=$(grep -oE "P1\(spin post-crash\): [0-9]+" "$L/mass_kid.log" | grep -oE "[0-9]+$")
check "IronAcres KID (n300)" "${P1:-0}" "0" "P1 spins post-collision"
FLT_K=$(pointsAvg "$L/mass_kid.log")
check "IronAcres KID (n300)" "${FLT_K:-0}" "50.0" "Points avg"

MASS_N=100 MASS_W=2 MASS_PILOT=ADULT python3 mass_campaign.py 2>/dev/null \
  | tee "$L/mass_adult.log" > /dev/null
check "IronAcres ADULT (n100)" "$(pointsAvg "$L/mass_adult.log")" "35.0" "Points avg"

MASS_N=100 MASS_W=2 MASS_VARIANT=NO_ASSIST python3 mass_campaign.py 2>/dev/null \
  | tee "$L/mass_no_assist.log" > /dev/null
# SIN_ASIST must be WORSE than with weapons (otherwise the weapons add nothing)
CONTRIB=$(python3 -c "print(round(${FLT_K:-0} - $(pointsAvg "$L/mass_no_assist.log"), 1))")
check "Weapons vs NO_ASSIST" "$CONTRIB" "2.0" "Weapon contribution (pts)"

# ---------------- 4. games (5 modes, KID and ADULT) ----------------
GAMES_MODE=ALL GAMES_N=100 GAMES_PILOT=KID python3 games.py 2>/dev/null \
  | tee "$L/games_kid.log" > /dev/null
F_CLEAN=$(grep -c "F1)=0" "$L/games_kid.log")
check "Games KID (n100 x5)" "$F_CLEAN" "5" "Modes with F1-F4 clean"
# SUMO must NEVER be LOST (worst case: draw)
S_SUMO_L=$(grep -m1 "SUMO won" "$L/games_kid.log" | sed -n "s/.*lost \([0-9.]*\)%.*/\1/p")
check "Games KID SUMO (n100)" "${S_SUMO_L:-99}" "0.0" "Losses %"
check "SOCCER 1v1  (n100)" "$(goalsAvg "SOCCER"  "$L/games_kid.log")" "0.2" "Goals/match"
check "SOCCER2 2v2 (n100)" "$(goalsAvg "SOCCER2" "$L/games_kid.log")" "3.0" "Goals/match"

GAMES_MODE=ALL GAMES_N=40 GAMES_PILOT=ADULT python3 games.py 2>/dev/null \
  | tee "$L/games_adult.log" > /dev/null
# ADULT = stress: only require a clear win rate in SOCCER2
WIN=$(grep "SOCCER2 goals" "$L/games_adult.log" | sed -n "s/.*we-win \([0-9.]*\)%.*/\1/p")
check "SOCCER2 ADULT (n40)" "${WIN:-0}" "50.0" "Win %"

echo >> "$S"
if [ "$FAIL" = "1" ]; then
  echo "## FAILURES PRESENT: review artifacts and EDIT pilot/weapons (never the tests or metrics)" >> "$S"
  echo "== BATTERY: FAILURES PRESENT =="
  cat "$S"
  exit 1
fi
echo "## No failures: robot at 100" >> "$S"
echo "== BATTERY: ALL OK =="
cat "$S"
