# Team Robots Legends — Sistema de 5 Armas para XRP Iron Acres

> Improvements to the FIRST XRP robot with secret weapons, improvements for game simulations and tests, in the tests and simulations the player in control has the pressure of a child not of a Computer to make it fair, Internal clock adapted to Iron Acress Game.

MicroPython + XRPLib exclusivamente. Sin `time.sleep()` de control, sin macros
de un solo botón, sin internet. Todo lazo cerrado sobre sensores
(encoders de fábrica, IMU a 208 Hz, rango, botón de board).

La partida se juega con **gamepad físico** (Logitech/Xbox) conectado a la
estación de conducción; el XRP recibe ejes y botones por **Bluetooth vía
protocolo XPP a 50 Hz** (`XRPLib.gamepad`, módulo oficial). El robot entero
corre en la placa; el mando solo pide, las armas deciden.

## Archivos

| Archivo | Arma | Rol |
|---|---|---|
| `piloto_gamepad.py` | Consola | Lazo 50 Hz: lee gamepad, elige modo, prioriza al piloto |
| `arma1_gyro_lock.py` | Gyro-Lock PID | Rumbo clavado, anti-trompos, 50 Hz |
| `arma2_torque_boost.py` | Anti-atasco | Boost de torque por rueda ante resistencia |
| `arma3_curvas.py` | Curvas cúbicas | Precisión quirúrgica en el mando, punta 100% |
| `arma4_traccion.py` | Traction & Brake | Rampa anti-derrape + frenado activo con `brake()` |
| `arma5_endgame.py` | Auto-Endgame | Reloj de 150 s + odometría X,Y,θ + retorno asistido |
| `main_partida.py` | Main de placa | Cablea todo y arranca (pegar en XRPCode) |
| `simulador_xrp.py` | Robot virtual | Partida de 150 s con mando virtual en PC/Pydroid |
| `_estres.py` | Batería de estrés | 30 partidas aleatorias con criterios P1-P4 |
| `_masiva.py` | Campaña masiva | Miles de partidas KID multiproceso (campo Iron Acres + puntos) |
| `_juegos.py` | Juegos | CONDUCIR / SUMO / SUMO2 / FUTBOL / FUTBOL2 con el código real de placa + métricas F1-F5 de fidelidad del mando |
| `_verifica.py` | Banco de pruebas | 12 pruebas de la matemática de las armas |

## Controles del mando (partida real)

| Control | Función (continua, no macro) |
|---|---|
| `Y1` | Avance/retroceso (pasa por curva del Arma 3) |
| `X1` | Giro: mientras se mueve, aparece modo GIRO |
| `X1` pequeño sostenido | RECORTE ASISTIDO: panea el rumbo bloqueado sin soltar avance (detección de empuje real por EMA ~0.25 s; el temblor de manos NO panea) |
| Palancas sueltas | El Arma 4 clava el robot + Arma 1 sostiene rumbo |
| `START` (flanco) | Arma reloj y casa del Arma 5 |
| `BACK` (flanco) | Activa/desactiva la asistencia de retorno del endgame |
| `BUMPER_L` (mantener) | Modo precisión (curva más quirúrgica) |

Prioridad SIEMPRE: palancas del piloto > asistencia. Las palancas sueltas en
los últimos 12 s disparan el retorno vivo a casa (A5), y tocar cualquier
palanca contramanda al instante.

## Cadena de mandos (cómo se conectan)

Solo UN módulo escribe en los motores cuando todo está encendido: el Arma 4.

```
gamepad (XPP 50 Hz)
        │
        ▼
piloto_gamepad._run()  ── lee Y1/X1 → curvas A3 → transición de modo
        │  RECTO: gyro.set_base(v, v)  PARADO: base 0  GIRO: mando directo
        ▼
arma1 gyro_lock._tick()  ── corrección diferencial PID (50 Hz)
        │  gyro_lock.attach(gancho)
        ▼
gancho: l, r = torque_boost.feed(l, r)     (Arma 2)
        arma4.set_command(l, r)            (Arma 4)
        ▼
arma4._run():  rampa anti-patinate → pulso inverso → motor.brake()  (50 Hz)
arma5 arma5._run():  reloj + odometría + endgame (50 Hz; en retorno escribe
                     set_target/set_base en el gyro_lock: nunca toca motores)
```

Cableado exacto: `main_partida.py` (ver arriba). En bloques XRPCode basta
invocar `main_partida.main()` línea a línea.

## Resultados de la batería de estrés (30 partidas, mando virtual)

Eventos aleatorios por partida: choques ±15..40° (0-3), atascos físicos de
rueda 2-5 s (0-2), batería 82-100%, deriva IMU 0-0.2°/s, ruido gaussiano.

| Criterio | Resultado |
|---|---|
| P1 trompos recuperados < 3° | 30/30 |
| P2 crucero estable (< 12°) | 30/30 |
| P3 llegada a casa CLAVADO (≤ 10 cm) | 30/30 (fin típico 8.5-9.5 cm) |
| P4 cero excepciones | 30/30 |

Partida escriptada completa: llegada automática a casa antes de t≈148 s,
`EN ZONA` a ~8.5 cm, pulso de boost del Arma 2 visible en giros.

## Campaña masiva Iron Acres (piloto KID, miles de partidas)

`_masiva.py` juega el modelo del campo oficial (272 x 137 cm; City Center
gol de alianza, hoppers/granero de recogida) con un piloto KID: buen gamer
pero con temblor en palancas (σ=0.05), decisiones cada ~200 ms, reacción
~180 ms, ojo con ruido (±4 cm / ±4°). Presión del juego: choques de hasta
40° que TIRAN el producto cargado (>25°), atascos, batería 82-100%.

| Batería | Puntos | Entregas | Park en zona | Sin ningún fallo |
|---|---|---|---|---|
| 400 partidas KID con armas (código final) | **56.1** | 4.63 | 97.5% | **94.8%** |
| 200 KID SIN asistencia de retorno | 46.2 | 4.62 | **0.0%** (quedan a ~81 cm) | 0% |

Hallazgos aplicados editando archivos (e iterados con A/B):

1. **Recorte asistido (trim) en el piloto**: la palanca pequeña que la curva
   del Arma 3 deja bajo `GIRO_MIN` no se ignora: panea el rumbo bloqueado
   (el gyro sigue estabilizando). La fracción del recorte está recortada
   a [0,1] (con EMA por encima de `TRIM_SAT` llegaba a 1.98x = 119°/s de
   paneo y el objetivo escapaba del robot: picos P2 de 13-23°).
2. **`V_RETORNO=0.85` por defecto en el Arma 5** (0.45 llega tarde desde
   >60 cm). El park asistido pasa de 0% a 97% y vale ~10 puntos/partida:
   es el segundo medio de cómo se gana.
3. **`PUNTO_CLAVAR_CM=8` + `SEGURO_FINAL_MS=2000` (Arma 5)**: soltar el
   retorno al ras de la tolerancia (10 cm) dejaba al robot a 10.1-10.3 cm
   (park perdido por centímetros) o aún avanzando al silbatazo (no
   CLAVADO). Ahora apunta 2 cm más adentro y en los últimos 2 s fuerza
   orden cero si ya está en zona: el Arma 4 clava garantizado.
4. **Asentamiento post-GIRO (piloto)**: al soltar el giro el momento del
   diferencial sigue girando al robot ~5-18° (medido: encoders −30/+39 rpm
   al capturar). Capturar el rumbo AHÍ bloquea un objetivo que el momento
   va a tirar: el piloto frena activo (Arma 4) mientras muere el momento
   y captura cuando la tasa de viraje cae de 45°/s (tope 600 ms). Este
   fix subió las ESTRICTAS de 52.8% a **94.8%** (400 partidas A/B).
5. **Piso `MIN_EFFORT` solo en marcha (Arma 1)**: en HOLD la deriva de la
   IMU empujaba el error fuera de la banda muerta y el piso arrancaba
   pulsos de 1.53 rpm (nunca CLAVADO en el corte). Sin piso en solicitación
   de base cero, el esfuerzo natural bajo el rozamiento estático corrige
   sin sacudir al robot del sitio.
6. La métrica justa del piloto kid es persistencia: P1 solo falla si el
   error sigue >3° todo deadline+5 s (el flicker del niño no es culpa del
   Arma 1; los holds reales quedan a ≤2°).

Puntuación modelada (paramétrica; EDITAR al descargar "Read the Manual" de
experiential.bot/ironacres): `PTS_PRODUCTO=10`, `PTS_PARK=10`,
`PTS_ARRASTRE=0`. Primera entrega del kid a t≈50 s (con V_KID=0.70 y
puntería KP 70°: antes 70 s y 3.3 entregas por partida).

## Juegos individuales y en equipo: CONDUCIR, SUMO, SUMO2, FUTBOL, FUTBOL2

`_juegos.py` juega tres modos con el MISMO código de placa (piloto + 5 armas)
y el MISMO piloto kid de la campaña masiva, para cazar **movimientos
contrarios o involuntarios de lo que quiso el piloto** (F1-F5):

- F1: ordena avanzar sostenido y el robot retrocede (jamás debe pasar).
- F2: al soltar palancas en velocidad el robot desliza >8 cm (freno A4).
- F3: kid quieto >1 s y el robot se mueve >3 cm.
- F4: kid SIN tocar X1 >1 s y el rumbo cambia >3° (fuera de ventanas de choque).
- F5: latencia palanca → ruedas (ms).

Batería final de **100 partidas por modo, piloto KID** (el perfil de los
pilotos reales: avanzados en videojuegos, sin precisión de adulto).
F-métricas limpias en TODOS los modos:

| Modo | Rendimiento | F1 | F2 | F3 | F4 | F5 lat. |
|---|---|---|---|---|---|---|
| CONDUCIR (100) | 2.84 puertas, máx 3 | 0 | 0 | 0 | 0 | 144 ms |
| SUMO (100) | **73.0% / 0.0% / 27.0%** | 0 | 0 | 0 | 0 | 31 ms |
| SUMO2 (100) | **63.0% / 0.0% / 37.0%** | 0 | 0 | 0 | 0 | 32 ms |
| FUTBOL (100) | **0.55 goles/partida** (55% con gol; era 0.00) | 0 | 0 | 0 | 0 | 123 ms |
| FUTBOL2 (100) | 4.79 goles, **51% / 35%**, encajadas 3.71 | 0 | 0 | 0 | 0 | 38 ms |

Referencia A/B con piloto ADULTO (40/modo, estrés): 0 en F1-F2, F3 2/40 y
F4 4/40 SOLO en fútbol/futbol2 (efecto límite >3°/1.1 s del propio empuje
del perfil adulto, se auto-recupera). ADULTO FUTBOL2: **77.5% ganadas /
15% perdidas** — con operador fino el equipo gana a talento.

Hallazgos del fichero (instrumento, no robot): el kid de fútbol apunta casi
A LA PELOTA (`APROX_PELOTA=2.0`) para dribble continuo; el punto "detrás"
clásico lo dejaba fuera del radio de patada (trabado). Roles del kid
1v1 reescritos (rodeo + carrerilla a través del arco) subieron el marcador
de 0.00 a **0.55** goles/partida. El empuje del rival en SUMO no cuenta
como F1/F2 (un choque que nos corre las ruedas es gameplay, no un defecto
del mando).

## Constantes calibradas (por batería, no a ojo)

0. **Piloto (nuevo):** `TRIM_UMBRAL=0.12`, `TRIM_SAT=0.25`,
   `TRIM_GRADOS_S=60`, `TRIM_TAU=0.25` (anti-tremor EMA), `GIRO_MIN=0.08`,
   `ASENTAR_MAX_MS=600` / `ASENTAR_TASA=45` (asentamiento post-giro).
1. **A1:** `KP=0.064` (fábrica) → `KD=0.0055` → **`KI=0.06`, `MAX_I=0.3`**
   (bajar el integral elimina la caza sostenida de ±4° tras choques; probado
   A/B en 30 partidas vs variante KP×1.5). `DEADBAND=1.5` con integral
   conservado: quieto sólido, sin mareo.
2. **A2:** `RATIO_ATASCO`, `BOOST_MAX`. En robot libre el boost no debe subir nunca.
3. **A3:** `MIX=0.35` (0.12 en modo precisión BUMPER_L); no depende del motor.
4. **A4:** `RAMPA_MAX=3.0`/s, `PULSO_K=0.012` según lo "duro" que frene.
5. **A5:** `V_RETORNO=0.85` (viabilidad del regreso; 0.45 llega tarde),
   `TOLERANCIA_CM=10` (candidato a ajuste con el manual),
   `PUNTO_CLAVAR_CM=8` + `SEGURO_FINAL_MS=2000` (park garantizado),
   `PIVOTE_GRADOS=45` (pivona hacia casa si mira lejos, ahorra distancia).

## Limitaciones conocidas (medidas, no ocultas)

- **FUTBOL 1v1: ~45% de partidas sin gol** (el kid anota 0.55 goles/partida;
  era 0.00). El resto mueren con la pelota en banda/esquina: el modelo de
  piloto niño NO puede retroceder ni afinar ángulos finos; el salvavidas
  es el rodeo de 3 roles ya implementado. En el robot REAL con piloto
  humano la perspectiva es mejor (recibirá el trim asistido y la curva
  del Arma 3).
- **F4 paneo residual con perfil ADULTO** (estrés, no kid): 4/40 en
  FUTBOL 1v1 — efecto límite >3°/1.1 s del propio empuje filtrado,
  se auto-recupera. Los perfiles de competencia (KID) salen limpios.
- **F5 latencia no medible con ADULTO en Iron Acres** (crucero 7.6 cm/s
  bajo el umbral de medición 8.0): interacción de métrica, no fallo.
- La odometría usa el track de fábrica (15.5 cm) y deriva con derrapes
  reales: mantén la zona de arranque gustosa con `START` cerca del
  momento del park.

## Lecciones de la simulación

- **La casa debe estar a ≤ ~130 cm al entrar al endgame**: a 0.85 de esfuerzo
  el robot cubre ~39 cm/s de punta; con pivote, rampa y frenada quedan
  ~130 cm jugables. A 150 cm ya es límite; más lejos, imposible.
- **El park sin Arma 5 no existe** (800 partidas KID: 0% en zona, quedan
  a ~79 cm de media manejando el niño al final). La asistencia de cierre
  es el segundo medio de puntos del juego.
- Si una rueda queda atascada, el Gyro-Lock corrige asimétrico; con atasco
  activo la recuperación de trompos es parcial (física, no software).
- El integral del Arma 1 con delays de rampa es la fuente nº1 de trompos
  oscilatorios: mantén `MAX_I` pequeño.

## Verificación

```
python3 _verifica.py     # 12/12 pruebas matemáticas
python3 _estres.py       # 30/30 partidas de estrés
python3 simulador_xrp.py # partida completa con mando virtual
MASIVA_N=400 python3 _masiva.py   # campaña masiva Iron Acres KID
MASIVA_PILOTO=ADULTO MASIVA_N=100 python3 _masiva.py
MASIVA_VAR=SIN_ASIST MASIVA_N=200 python3 _masiva.py   # valor de las armas
JUEGOS_MODO=TODOS JUEGOS_N=100 JUEGOS_PILOTO=KID python3 _juegos.py
JUEGOS_MODO=SUMO JUEGOS_N=300 JUEGOS_PILOTO=KID python3 _juegos.py
JUEGOS_MODO=TODOS JUEGOS_N=40 JUEGOS_PILOTO=ADULTO python3 _juegos.py  # referencia
```

## Reglas del proyecto respetadas

- Cero `time.sleep()` en control; todo lazo usa `ticks_ms` + `uasyncio`.
- Sin macros de botón: los botones solo habilitan/deshabilitan asistencia
  continua o marcan eventos (reloj); ninguna rutina fija por botón.
- El único bloqueo del sistema es `imu.calibrate(1.0)` de la propia XRPLib,
  una sola vez al encender, robot quieto.
- Módulos autocontenidos e invocables línea a línea desde XRPCode.
