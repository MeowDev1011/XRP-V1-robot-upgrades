#!/usr/bin/env bash
# =========================================================
# BATERIA 24/7 - Team Robots Legends (FUSAMO)
# Corre TODO el paquete de pruebas del robot y falla ( exit 1 )
# si alguna metrica cae por debajo de su umbral. Los umbrales
# salen de los resultados medidos que quedaron en el README.
# Uso: bash ci/bateria.sh
# Resumen: /tmp/summary.md (GitHub Actions lo muestra en el run)
# =========================================================
set -uo pipefail
cd "$(dirname "$0")/.."

S=/tmp/summary.md
L="${BATERIA_LOGS:-/tmp}"
: > "$S"
MALA=0

print -r -- "# Bateria 24/7 — Team Robots Legends" >> "$S" 2>/dev/null || echo "# Bateria 24/7 — Team Robots Legends" >> "$S"
echo "Corrida: $(date -u "+%Y-%m-%d %H:%M UTC")" >> "$S"
echo >> "$S"
echo "| Bateria | Metrica | Medido | Umbral | Estado |" >> "$S"
echo "|---|---|---|---|---|" >> "$S"

# ---------------- 1. pruebas matematicas ----------------
if python3 _verifica.py 2>/dev/null | tee "$L/verifica.log" | grep -q "TODAS LAS PRUEBAS PASAN"; then
  echo "| verifica | pruebas | 12/12 | 12/12 | OK |" >> "$S"
else
  echo "| verifica | pruebas | FALLO | 12/12 | FALLO |" >> "$S"; MALA=1
fi

# ---------------- 2. estres ----------------
N_OK=$(python3 _estres.py 2>/dev/null | tee "$L/estres.log" \
       | grep -oE "RESULTADO: [0-9]+" | grep -oE "[0-9]+")
check() {  # check "Nombre" "medido" "umbral_mayor_o_igual" "metrica"
  local ok
  ok=$(python3 -c "print('OK' if float('${2:-nan}') >= float('${3:-nan}') else 'FALLO')" 2>/dev/null) || ok=FALLO
  echo "| $1 | $4 | ${2:-?} | ${3} | ${ok} |" >> "$S"
  if [ "$ok" != "OK" ]; then MALA=1; fi
}
check "estres (30 partidas)" "${N_OK:-0}" "30" "Partidas aprobadas"

# ---------------- helpers para los logs de campana ----------------
lee() {  # primera linea del log que contiene $1, primer dato con % (sin signo)
  grep -m1 "$1" "$2" | awk '{ for (i=1;i<=NF;i++) if ($i ~ /%$/) { sub(/%/,"",$i); print $i; exit } }'
}
puntos() { # puntos media del resumen de _masiva
  grep -m1 "^PUNTOS" "$1" | sed -n "s/.*media=\([0-9.]*\).*/\1/p"
}
goles() {  # goles media de un modo de _juegos (la PRIMERA "media", a favor)
  grep -m1 "^$1 " "$2" | awk '{ for (i=1;i<=NF;i++) if ($i == "media") { print $(i+1); exit } }'
}

# ---------------- 3. Iron Acres (campanas masivas) ----------------
MASIVA_N=300 MASIVA_W=2 MASIVA_PILOTO=KID python3 _masiva.py 2>/dev/null \
  | tee "$L/masiva_kid.log" > /dev/null
check "IronAcres KID (n300)" "$(lee "PARK en zona" "$L/masiva_kid.log")" "90.0" "Park en zona %"
check "IronAcres KID (n300)" "$(lee "ESTRICTAS"   "$L/masiva_kid.log")" "60.0" "ESTRICTAS %"
P1=$(grep -oE "P1\(trompo post-choque\): [0-9]+" "$L/masiva_kid.log" | grep -oE "[0-9]+$")
check "IronAcres KID (n300)" "${P1:-0}" "0" "P1 trompos post-choque"
FLT_K=$(puntos "$L/masiva_kid.log")
check "IronAcres KID (n300)" "${FLT_K:-0}" "50.0" "Puntos media"

MASIVA_N=100 MASIVA_W=2 MASIVA_PILOTO=ADULTO python3 _masiva.py 2>/dev/null \
  | tee "$L/masiva_adulto.log" > /dev/null
check "IronAcres ADULTO (n100)" "$(puntos "$L/masiva_adulto.log")" "35.0" "Puntos media"

MASIVA_N=100 MASIVA_W=2 MASIVA_VAR=SIN_ASIST python3 _masiva.py 2>/dev/null \
  | tee "$L/masiva_sin_asist.log" > /dev/null
# SIN_ASIST debe quedar PEOR que con armas (si no, las armas no aportan)
CONTRIB=$(python3 -c "print(round(${FLT_K:-0} - $(puntos "$L/masiva_sin_asist.log"), 1))")
check "Armas vs SIN_ASIST" "$CONTRIB" "2.0" "Contribucion de las armas (pts)"

# ---------------- 4. juegos (5 modos, KID y ADULTO) ----------------
JUEGOS_MODO=TODOS JUEGOS_N=100 JUEGOS_PILOTO=KID python3 _juegos.py 2>/dev/null \
  | tee "$L/juegos_kid.log" > /dev/null
F_LIMP=$(grep -c "F1)=0" "$L/juegos_kid.log")
check "Juegos KID (n100 x5)" "$F_LIMP" "5" "Modos con F1-F4 limpios"
# SUMO no debe PERDER NUNCA (empate al peor)
PERD_SUMO=$(grep -m1 "SUMO ganadas" "$L/juegos_kid.log" | sed -n "s/.*perdidas \([0-9.]*\)%.*/\1/p")
check "Juegos KID SUMO (n100)" "${PERD_SUMO:-99}" "0.0" "Perdidas %"
check "FUTBOL 1v1  (n100)" "$(goles "FUTBOL"  "$L/juegos_kid.log")" "0.2" "Goles/partida"
check "FUTBOL2 2v2 (n100)" "$(goles "FUTBOL2" "$L/juegos_kid.log")" "3.0" "Goles/partida"

JUEGOS_MODO=TODOS JUEGOS_N=40 JUEGOS_PILOTO=ADULTO python3 _juegos.py 2>/dev/null \
  | tee "$L/juegos_adulto.log" > /dev/null
# ADULTO = estres: solo que el equipo gane claramente en FUTBOL2
GA=$(grep "FUTBOL2 goles" "$L/juegos_adulto.log" | sed -n "s/.*ganamos \([0-9.]*\)%.*/\1/p")
check "FUTBOL2 ADULTO (n40)" "${GA:-0}" "50.0" "Ganamos %"

echo >> "$S"
if [ "$MALA" = "1" ]; then
  echo "## HAY FALLAS: revisar artefactos y EDITAR piloto/armas (nunca las pruebas ni las metricas)" >> "$S"
  echo "== BATERIA: HAY FALLAS =="
  cat "$S"
  exit 1
fi
echo "## Sin fallas: robot al 100" >> "$S"
echo "== BATERIA: TODO OK =="
cat "$S"
