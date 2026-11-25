#!/usr/bin/env bash
# =========================================================
# 24/7 BATTERY - Team Robots Legends (FUSAMO)
# Runs the ENTIRE robot test package and fails (exit 1) if
# any metric drops below its threshold. Thresholds come from
# the measured results recorded in the README.
# Usage: bash ci/bateria.sh
# Summary: /tmp/summary.md (GitHub Actions shows it in the run)
# =========================================================
set -uo pipefail
cd "$(dirname "$0")/.."

S=/tmp/summary.md
L="${BATERIA_LOGS:-/tmp}"
: > "$S"
FAIL=0

# ---------------- 1. math unit tests ----------------
if python3 _verifica.py 2>/dev/null | tee "$L/verifica.log" | grep -q "ALL TESTS PASS"; then
  echo "| verifica | tests | 12/12 | 12/12 | OK |" >> "$S"
else
  echo "| verifica | tests | FAIL | 12/12 | FAIL |" >> "$S"; FAIL=1
fi

# ---------------- 2. stress ----------------
N_OK=$(python3 _estres.py 2>/dev/null | tee "$L/estres.log" \
       | grep -oE "RESULT: [0-9]+" | grep -oE "[0-9]+")
check() {  # check "Name" "measured" "threshold_gte" "metric"
  local ok
  ok=$(python3 -c "print('OK' if float('${2:-nan}') >= float('${3:-nan}') else 'FAIL')" 2>/dev/null) || ok=FAIL
  echo "| $1 | $4 | ${2:-?} | ${3} | ${ok} |" >> "$S"
  if [ "$ok" != "OK" ]; then FAIL=1; fi
}
check "stress (30 matches)" "${N_OK:-0}" "30" "Matches approved"

# ---------------- helpers for campaign logs ----------------
lee() {  # first line of log containing $1, first datum ending in %
  grep -m1 "$1" "$2" | awk '{ for (i=1;i<=NF;i++) if ($i ~ /%$/) { sub(/%/,"",$i); print $i; exit } }'
}
puntos() { # points avg from the _masiva summary
  grep -m1 "^POINTS" "$1" | sed -n "s/.*avg=\([0-9.]*\).*/\1/p"
}
goles() {  # goals avg of one _juegos mode (the FIRST "avg", scored in our favor)
  grep -m1 "^$1 " "$2" | awk '{ for (i=1;i<=NF;i++) if ($i == "avg") { print $(i+1); exit } }'
}

# ---------------- 3. Iron Acres (mass campaigns) ----------------
MASIVA_N=300 MASIVA_W=2 MASIVA_PILOTO=KID python3 _masiva.py 2>/dev/null \
  | tee "$L/masiva_kid.log" > /dev/null
check "IronAcres KID (n300)" "$(lee "PARK in zone" "$L/masiva_kid.log")" "90.0" "Park in zone %"
check "IronAcres KID (n300)" "$(lee "STRICT"   "$L/masiva_kid.log")" "60.0" "STRICT %"
P1=$(grep -oE "P1\(spin post-crash\): [0-9]+" "$L/masiva_kid.log" | grep -oE "[0-9]+$")
check "IronAcres KID (n300)" "${P1:-0}" "0" "P1 spins post-collision"
FLT_K=$(puntos "$L/masiva_kid.log")
check "IronAcres KID (n300)" "${FLT_K:-0}" "50.0" "Points avg"

MASIVA_N=100 MASIVA_W=2 MASIVA_PILOTO=ADULTO python3 _masiva.py 2>/dev/null \
  | tee "$L/masiva_adulto.log" > /dev/null
check "IronAcres ADULTO (n100)" "$(puntos "$L/masiva_adulto.log")" "35.0" "Points avg"

MASIVA_N=100 MASIVA_W=2 MASIVA_VAR=SIN_ASIST python3 _masiva.py 2>/dev/null \
  | tee "$L/masiva_sin_asist.log" > /dev/null
# SIN_ASIST must be WORSE than with weapons (otherwise the weapons add nothing)
CONTRIB=$(python3 -c "print(round(${FLT_K:-0} - $(puntos "$L/masiva_sin_asist.log"), 1))")
check "Weapons vs SIN_ASIST" "$CONTRIB" "2.0" "Weapon contribution (pts)"

# ---------------- 4. games (5 modes, KID and ADULTO) ----------------
JUEGOS_MODO=TODOS JUEGOS_N=100 JUEGOS_PILOTO=KID python3 _juegos.py 2>/dev/null \
  | tee "$L/juegos_kid.log" > /dev/null
F_CLEAN=$(grep -c "F1)=0" "$L/juegos_kid.log")
check "Games KID (n100 x5)" "$F_CLEAN" "5" "Modes with F1-F4 clean"
# SUMO must NEVER be LOST (worst case: draw)
S_SUMO_L=$(grep -m1 "SUMO won" "$L/juegos_kid.log" | sed -n "s/.*lost \([0-9.]*\)%.*/\1/p")
check "Games KID SUMO (n100)" "${S_SUMO_L:-99}" "0.0" "Losses %"
check "FUTBOL 1v1  (n100)" "$(goles "FUTBOL"  "$L/juegos_kid.log")" "0.2" "Goals/match"
check "FUTBOL2 2v2 (n100)" "$(goles "FUTBOL2" "$L/juegos_kid.log")" "3.0" "Goals/match"

JUEGOS_MODO=TODOS JUEGOS_N=40 JUEGOS_PILOTO=ADULTO python3 _juegos.py 2>/dev/null \
  | tee "$L/juegos_adulto.log" > /dev/null
# ADULTO = stress: only require a clear win rate in FUTBOL2
WIN=$(grep "FUTBOL2 goals" "$L/juegos_adulto.log" | sed -n "s/.*we-win \([0-9.]*\)%.*/\1/p")
check "FUTBOL2 ADULTO (n40)" "${WIN:-0}" "50.0" "Win %"

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
