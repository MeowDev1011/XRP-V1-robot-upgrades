# =========================================================
# IRON ACRES MASS CAMPAIGN - Team Robots Legends (FUSAMO)
# ---------------------------------------------------------
# Thousands of simultaneous matches (multiprocess, 5 cores)
# with the REAL board code (pilot + 5 weapons) played by a
# KID PILOT: an advanced kid, a good gamer, but without the
# motor precision of an adult. The kid plays ONLY with the
# virtual physical gamepad: the assist (Weapons 1-5) does the rest.
#
# FIELD (official): 272 x 137 cm (107 x 54 inch MAT).
#   - Alliance start zone on a short wall.
#   - City Center with alliance goals (red/blue) in the middle.
#   - Product hoppers and the barn.
# SCORING (parametric model): EDIT once the official
# "Read the Manual" is obtained (experiential.bot).
#   PTS_PRODUCTO: product delivered into the alliance goal.
#   PTS_PARK:     robot IN the start zone at the end (park).
#   PTS_ARRASTRE: product still carried at the buzzer (0 = noise).
#
# SIMULATED GAME PRESSURE:
#   - Wall/opponent crashes (0-3): spin of 15-40 degrees.
#     A crash of more than 25 degrees KNOCKS OUT the carried product.
#   - Physical wheel stalls (0-2) of 2-5 s.
#   - Battery 82-100%, IMU drift + noise, crowded center.
#
# KID PILOT (editable parameters below):
#   TREMOR_SIGMA    stick tremor while holding them
#   DECISION_MS     human decision cadence (~5 Hz)
#   REACCION_MS     perception-action delay (+/- jitter)
#   KP_KID          heading-error degrees -> stick 1.0
#   MUERTE_PUNTERIA stops correcting inside this angle
#   RUIDO_VISTA_*   the eye measures distances/angles with error
#   V_KID           kid cruise speed
#   STOP_CM         closes in "any way it can" up to this distance
#
# USAGE:
#   python3 _masiva.py            -> 1200 matches, 4 processes
#   MASIVA_N=3000 python3 _masiva.py
#   MASIVA_PILOTO=KID|BUENO|REGULAR|ADULTO python3 _masiva.py
# =========================================================
import os
import math
import random
import multiprocessing

import simulador_xrp as SIM

# ---------------- CAMPAIGN CONFIGURATION ----------------
N_PARTIDAS = int(os.environ.get("MASIVA_N", "1200"))
WORKERS = int(os.environ.get("MASIVA_W", "4"))
PILOTO = os.environ.get("MASIVA_PILOTO", "KID")
VARIANTE = os.environ.get("MASIVA_VAR", "ASIST")   # ASIST | SIN_ASIST

# ---------------- PILOT PROFILE (gamepad precision) ----------------
PILOTOS = ("KID", "BUENO", "REGULAR", "ADULTO")
PERFILES = {
    # tremor, decisions (ms), reaction (ms), aiming precision (KP/dead-
    # band/eye noise) and cruise: an advanced kid and good gamer, but
    # without the motor precision of an adult.
    "KID":     dict(TREMOR_SIGMA=0.050, DECISION_MS=200.0, REACCION_MS=180.0,
                    KP_KID=70.0, MUERTE_PUNTERIA=8.0, RUIDO_VISTA_CM=4.0,
                    RUIDO_VISTA_GRADOS=4.0, V_KID=0.70,
                    STOP_CM=10.0, FRENA_A_CM=30.0),
    "BUENO":   dict(TREMOR_SIGMA=0.030, DECISION_MS=150.0, REACCION_MS=140.0,
                    KP_KID=55.0, MUERTE_PUNTERIA=6.0, RUIDO_VISTA_CM=3.0,
                    RUIDO_VISTA_GRADOS=3.0, V_KID=0.72,
                    STOP_CM=10.0, FRENA_A_CM=28.0),
    "REGULAR": dict(TREMOR_SIGMA=0.085, DECISION_MS=280.0, REACCION_MS=260.0,
                    KP_KID=90.0, MUERTE_PUNTERIA=12.0, RUIDO_VISTA_CM=6.0,
                    RUIDO_VISTA_GRADOS=6.0, V_KID=0.62,
                    STOP_CM=12.0, FRENA_A_CM=34.0),
    "ADULTO":  dict(TREMOR_SIGMA=0.012, DECISION_MS=90.0, REACCION_MS=80.0,
                    KP_KID=28.0, MUERTE_PUNTERIA=3.0, RUIDO_VISTA_CM=1.5,
                    RUIDO_VISTA_GRADOS=1.5, V_KID=0.55,
                    STOP_CM=10.0, FRENA_A_CM=25.0),
}
if PILOTO not in PERFILES:
    PILOTO = "KID"
PERFIL = PERFILES[PILOTO]
(TREMOR_SIGMA, DECISION_MS, REACCION_MS, KP_KID, MUERTE_PUNTERIA,
 RUIDO_VISTA_CM, RUIDO_VISTA_GRADOS, V_KID, STOP_CM, FRENA_A_CM) = (
    PERFIL["TREMOR_SIGMA"], PERFIL["DECISION_MS"], PERFIL["REACCION_MS"],
    PERFIL["KP_KID"], PERFIL["MUERTE_PUNTERIA"], PERFIL["RUIDO_VISTA_CM"],
    PERFIL["RUIDO_VISTA_GRADOS"], PERFIL["V_KID"], PERFIL["STOP_CM"],
    PERFIL["FRENA_A_CM"])

# ---------------- FIELD & SCORING (EDIT WITH THE MANUAL) ----------------
CAMPO_L_CM = 272.0        # length (Y axis: from our wall to the back)
CAMPO_W_CM = 68.0         # fenced half-width (±) for wall crashes
CARGA_XY = (30.0, 90.0)   # product pickup point (hopper/barn)
GOL_XY = (-5.0, 121.0)    # alliance goal (City Center)
PTS_PRODUCTO = 10         # per product in the goal
PTS_PARK = 10             # for finishing In the start Zone (park)
PTS_ARRASTRE = 0          # product carried but not delivered at the end

T_INICIO_CARRERA = 2000.0
T_DEJA_JUGAR = 138000.0   # the kid releases the sticks and leaves the endgame assisted
MIN_RECOGIDA_CM = 18.0
CHOQUE_PIERDE_CARGA = 25.0    # spin degrees that knock the product out
UMBRAL_P1 = 3.0
UMBRAL_P2 = 12.0

_MODULOS = ("arma3_curvas", "arma2_torque_boost", "arma4_traccion",
            "arma5_endgame", "arma1_gyro_lock", "piloto_gamepad")


def _recargar():
    import importlib
    import sys
    for nombre in _MODULOS:
        importlib.reload(sys.modules[nombre])
    return sys.modules


RX_JIT_MAX = 80.0          # pilot reaction spread (ms)


def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


class PilotoKid:
    """Virtual human: decides every DECISION_MS, reacts late,
    trembles and looks with noise. Only touches the gamepad."""

    def __init__(self, pad, RNG, GP, arma5):
        self.pad = pad
        self.GP = GP
        self.RNG = RNG
        self.a5 = arma5
        self.jit = RNG.uniform(0.0, RX_JIT_MAX)
        self.decision_t = -1.0
        self.x1 = 0.0
        self.y1 = 0.0
        self.pend = None
        self.wp_x, self.wp_y = CARGA_XY
        self.objetivo = "CARGA"
        self.posesion = 0
        self.entregas = 0
        self.recogidas = 0
        self.re_aim = False
        self.prev_d = None
        self.dejando = False
        self.t_entregas = []

    def _mira(self, px, py, yaw):
        nx = px + self.RNG.gauss(0.0, RUIDO_VISTA_CM)
        ny = py + self.RNG.gauss(0.0, RUIDO_VISTA_CM)
        err = wrap180(math.degrees(math.atan2(self.wp_y - ny,
                                              self.wp_x - nx)) - yaw
                      + self.RNG.gauss(0.0, RUIDO_VISTA_GRADOS))
        return err

    def _decide(self, t, pose, yaw):
        px, py, _ = pose
        err = self._mira(px, py, yaw)
        dist = math.hypot(self.wp_x - px, self.wp_y - py) + \
            self.RNG.gauss(0.0, RUIDO_VISTA_CM)
        if self.y1 > 0.25 and self.prev_d is not None and \
                dist > self.prev_d + 2.0 and dist > STOP_CM + 3.0:
            err += 35.0 if err >= 0 else -35.0
        self.prev_d = dist
        self.re_aim = False
        if abs(err) > MUERTE_PUNTERIA:
            x1n = max(-1.0, min(1.0, err / KP_KID))
            y1n = 0.12
        else:
            x1n = 0.0
            if dist <= STOP_CM:
                y1n = 0.0
            elif dist < FRENA_A_CM:
                y1n = V_KID * (0.35 + 0.65 * dist / FRENA_A_CM)
            else:
                y1n = V_KID
        self.pend = (t + REACCION_MS + abs(self.RNG.gauss(0.0, self.jit)),
                     x1n, y1n)

    def paso(self, t, pose, yaw):
        if self.pend is not None and t >= self.pend[0]:
            _, self.x1, self.y1 = self.pend
            self.pend = None
        if t >= self.decision_t:
            self.decision_t = t + DECISION_MS + abs(self.RNG.gauss(0.0, self.jit))
            self._decide(t, pose, yaw)
        else:
            if self.x1 != 0.0:
                self.x1 += self.RNG.gauss(0.0, TREMOR_SIGMA)
            else:
                self.x1 = self.RNG.gauss(0.0, TREMOR_SIGMA * 0.6)
            if abs(self.x1) < 0.02:
                self.x1 = 0.0
            if self.y1 != 0.0:
                self.y1 = max(0.0, self.y1 + self.RNG.gauss(0.0, TREMOR_SIGMA * 0.8))
        self.pad.axes[self.GP.X1] = max(-1.0, min(1.0, self.x1))
        self.pad.axes[self.GP.Y1] = max(-1.0, min(1.0, self.y1))


def nueva_partida(seed, MOD):
    RNG = random.Random(seed)

    A1 = MOD["arma1_gyro_lock"]
    A2 = MOD["arma2_torque_boost"]
    A4 = MOD["arma4_traccion"]
    A5 = MOD["arma5_endgame"]
    MAIN = MOD["piloto_gamepad"]

    DRV = SIM.DRIVETRAIN
    GP = SIM.GamepadSim

    SIM.RELOJ.t = 0
    DRV.LEFT = SIM.RuedaSim()
    DRV.RIGHT = SIM.RuedaSim()
    DRV.yaw = 0.0
    DRV.fuente = "inactiva"
    SIM.BOARD.voltage_scale = RNG.uniform(0.82, 1.0)
    SIM.BIAS_IMU_CS = RNG.uniform(0.0, 0.2)
    pad = GP.nueva()

    gyro = A1.gyro_lock
    tb = A4.traction_brake
    arma5 = A5.arma5
    mando = MAIN.piloto_mando

    def gancho(l, r):
        l, r = A2.torque_boost.feed(l, r)
        tb.set_command(l, r)

    gyro.attach(gancho)
    tb.enable()
    A2.torque_boost.enable()
    arma5.conectar(gyro)
    arma5.modo_retorno(VARIANTE != "SIN_ASIST")
    A5.V_RETORNO = 0.85
    imu = SIM.IMU
    imu.reset_yaw()
    mando.conectar(pad)
    gyro.set_target_here()

    kid = PilotoKid(pad, RNG, GP, arma5)

    choques = [RNG.uniform(5000, 135000) for _ in range(RNG.randint(0, 3))]
    atascos = []
    for _ in range(RNG.randint(0, 2)):
        atascos.append((RNG.uniform(5000, 115000),
                        RNG.uniform(2000.0, 5000.0), RNG.choice(("L", "R"))))

    fallos = []
    max_err = 0.0
    choque_regs = []
    p1_pend = []
    p1_rec = {}          # crash -> any time err <= THRESHOLD in the window
    trompos = 0.0
    inicio = False

    for k in range(7500):
        SIM.RELOJ.avanzar(20)
        t = SIM.RELOJ.ticks_ms()

        if not inicio:
            if 400 <= t < 420:
                pad.botones[GP.START - 4] = 1
            else:
                pad.botones[GP.START - 4] = 0
            if t >= 420:
                inicio = True

        if inicio:
            if t < T_DEJA_JUGAR:
                pose = arma5.pose()
                kid.paso(t, pose, SIM.IMU.get_yaw())

            # pickup/delivery events (field ground truth)
            if t < T_DEJA_JUGAR:
                px, py, _ = arma5.pose()
                if kid.objetivo == "CARGA":
                    if math.hypot(px - kid.wp_x, py - kid.wp_y) < MIN_RECOGIDA_CM:
                        kid.posesion = 1
                        kid.recogidas += 1
                        kid.objetivo = "GOL"
                        kid.wp_x, kid.wp_y = GOL_XY
                        kid.re_aim = True
                else:
                    if math.hypot(px - kid.wp_x, py - kid.wp_y) < MIN_RECOGIDA_CM:
                        kid.posesion = 0
                        kid.entregas += 1
                        kid.t_entregas.append(t)
                        kid.objetivo = "CARGA"
                        kid.wp_x, kid.wp_y = CARGA_XY
                        kid.re_aim = True
            else:
                if VARIANTE == "SIN_ASIST":
                    if not kid.dejando:
                        kid.dejando = True
                        kid.objetivo = "CASA"
                        kid.wp_x, kid.wp_y = 0.0, 0.0
                        kid.re_aim = True
                    kid.paso(t, arma5.pose(), SIM.IMU.get_yaw())
                    if t >= 149000:
                        pad.axes[GP.X1] = 0.0
                        pad.axes[GP.Y1] = 0.0
                else:
                    pad.axes[GP.X1] = 0.0
                    pad.axes[GP.Y1] = 0.0
        else:
            pad.axes[GP.X1] = 0.0
            pad.axes[GP.Y1] = 0.0

        for lo, dur, rueda in atascos:
            if lo <= t < lo + dur:
                DRV.LEFT.atascada = (rueda == "L")
                DRV.RIGHT.atascada = (rueda == "R")
            else:
                if rueda == "L" and t >= lo + dur:
                    DRV.LEFT.atascada = False
                if rueda == "R" and t >= lo + dur:
                    DRV.RIGHT.atascada = False
        for lo in choques:
            if lo <= t < lo + 20:
                salto = RNG.uniform(15.0, 40.0) * RNG.choice((-1.0, 1.0))
                DRV.yaw += salto
                SIM.DRIVETRAIN.fuente = "activa"
                choque_regs.append((lo, salto))
                p1_pend.append([lo, lo + 10000])
                trompos += abs(salto)
                if abs(salto) > CHOQUE_PIERDE_CARGA and kid.posesion:
                    kid.posesion = 0
                    kid.objetivo = "CARGA"
                    kid.wp_x, kid.wp_y = CARGA_XY
                    kid.re_aim = True
        DRV.yaw += RNG.gauss(0.0, 0.05)

        mando._paso()
        gyro._tick()
        tb.paso()
        arma5._odometria()
        arma5._logica_endgame()
        DRV.paso(0.02)

        if "MASIVA_G1" in os.environ:
            en_win = any(lo - 500 <= t <= lo + 12000 for lo, _ in choque_regs)
            if en_win and k % 10 == 0:
                print("G1 t=%5.1f modo=%s err=%6.2f tgt=%7.1f yaw=%7.1f "
                      "base=(%.2f %.2f) en=%d X1raw=%+.3f ema=%+.3f Y1=%+.2f"
                      % (t / 1000.0, mando.nombre_modo(), gyro.get_error(),
                         gyro.get_target(), SIM.IMU.get_yaw(),
                         gyro.base_l, gyro.base_r, gyro.enabled,
                         pad.axes[0], mando._ema_x, pad.axes[1]))

        if "MASIVA_DEBUG" in os.environ and k % 100 == 0:
            pxx, pyy, _th = arma5.pose()
            _e = wrap180(math.degrees(math.atan2(kid.wp_y - pyy,
                                                 kid.wp_x - pxx)) -
                         SIM.IMU.get_yaw())
            print("t=%5.1f pose=(%6.1f,%6.1f) yaw=%6.1f modo=%s wp=(%.0f,%.0f) "
                  "obj=%s poss=%d x1=%+.2f y1=%+.2f err=%6.2f" %
                  (t / 1000.0, pxx, pyy, SIM.IMU.get_yaw(), mando.nombre_modo(),
                   kid.wp_x, kid.wp_y, kid.objetivo, kid.posesion,
                   pad.axes[0], pad.axes[1], _e))

        if "MASIVA_G2" in os.environ and k % 25 == 0:
            en_win0 = any(lo - 500 <= t <= lo + 12000 for lo, _ in choque_regs)
            if en_win0:
                print("G2 t=%5.1f modo=%s err=%6.2f tgt=%7.1f yaw=%7.1f "
                      "base=(%.2f %.2f) en=%d X1r=%+.3f ema=%+.3f Y1=%+.2f"
                      % (t / 1000.0, mando.nombre_modo(), gyro.get_error(),
                         gyro.get_target(), SIM.IMU.get_yaw(),
                         gyro.base_l, gyro.base_r, gyro.enabled,
                         pad.axes[0], mando._ema_x, pad.axes[1]))

        if mando._modo in (MAIN.RECTO, MAIN.PARADO) and gyro.enabled:
            en_ventana_choque = any(lo - 200 <= t <= lo + 6000 for lo, _ in choque_regs)
            if not en_ventana_choque:
                e = abs(gyro.get_error())
                if e > max_err:
                    max_err = e

        atasco_vigente = any(lo - 200 <= t <= lo + dur + 2000 for lo, dur, _ in atascos)
        vivos = []
        for lo, deadline in p1_pend:
            if t >= deadline:
                if abs(gyro.get_error()) <= UMBRAL_P1:
                    p1_rec[lo] = True
            if t < deadline + 5000 or atasco_vigente:
                vivos.append((lo, deadline))
                continue
            if not p1_rec.get(lo):
                fallos.append("P1: crash t=%.0f persistent error (>%.0f: %.1f)"
                              % (lo / 1000.0, UMBRAL_P1, abs(gyro.get_error())))
        p1_pend = vivos

    dist = arma5.distancia_al_hogar()
    clavado = tb.clavado or (abs(DRV.LEFT.rpm) < 1.5 and abs(DRV.RIGHT.rpm) < 1.5)
    park = dist <= A5.TOLERANCIA_CM and clavado
    if not park:
        fallos.append("P3: final dist=%.1f" % dist)
    if max_err > UMBRAL_P2:
        fallos.append("P2: cruise %.1f" % max_err)

    puntos = (kid.entregas * PTS_PRODUCTO +
              (PTS_PARK if park else 0) +
              kid.posesion * PTS_ARRASTRE)
    return {"seed": seed, "puntos": puntos, "entregas": kid.entregas,
            "recogidas": kid.recogidas, "park": park, "dist": dist,
            "max_err": max_err, "fallos": fallos, "trompos": trompos,
            "t_entrega": (kid.t_entregas[0] / 1000.0) if kid.t_entregas else -1.0}


def _trabajo(seed):
    MOD = _recargar()
    return nueva_partida(seed, MOD)


def campana():
    semilla_base = 777000
    print("== IRON ACRES MASS CAMPAIGN == pilot=%s n=%d processes=%d variant=%s" %
          (PILOTO, N_PARTIDAS, WORKERS, VARIANTE))
    with multiprocessing.Pool(WORKERS) as pool:
        res = pool.map(_trabajo, [semilla_base + i for i in range(N_PARTIDAS)],
                       chunksize=8)

    n = len(res)
    parks = [r for r in res if r["park"]]
    limpias = [r for r in res if not r["fallos"]]
    entregas = [r["entregas"] for r in res]
    puntos = [r["puntos"] for r in res]
    dists = [r["dist"] for r in res]
    errs = [r["max_err"] for r in res]
    f1 = sum(1 for r in res if any(f.startswith("P1") for f in r["fallos"]))
    f2 = sum(1 for r in res if any(f.startswith("P2") for f in r["fallos"]))
    f3 = sum(1 for r in res if any(f.startswith("P3") for f in r["fallos"]))

    def media(v):
        return sum(v) / len(v) if v else 0.0

    def pct(v):
        return 100.0 * len(v) / n

    hist = {}
    for e in entregas:
        hist[e] = hist.get(e, 0) + 1

    print("\n-- RESULTS (%d matches, pilot %s) --" % (n, PILOTO))
    print("POINTS: avg=%.1f  min=%d  max=%d" %
          (media(puntos), min(puntos), max(puntos)))
    print("PRODUCTS delivered: avg=%.2f  [0:%d | 1:%d | 2:%d | 3:%d | 4+:%d]"
          % (media(entregas),
             hist.get(0, 0), hist.get(1, 0), hist.get(2, 0), hist.get(3, 0),
             sum(v for k, v in hist.items() if k >= 4)))
    print("PARK in zone: %.1f%%  (avg final dist=%.1f cm)" % (pct(parks), media(dists)))
    desglose = media(entregas) * PTS_PRODUCTO + pct(parks) / 100.0 * PTS_PARK
    print("Theoretical breakdown: %.2f products*%d + park %d*%.2f = %.1f points" %
          (media(entregas), PTS_PRODUCTO, PTS_PARK, pct(parks) / 100.0, desglose))
    print("STRICT with no faults: %.1f%%" % pct(limpias))
    print("Faults  P1(spin post-crash): %d  P2(cruise): %d  P3(park): %d"
          % (f1, f2, f3))
    con_entrega = [r["t_entrega"] for r in res if r["t_entrega"] > 0]
    print("first delivery: avg t = %.1f s (of 138 useful s)" %
          (media(con_entrega) if con_entrega else -1.0))

    dist_media_park = media([r["dist"] for r in parks]) if parks else -1
    print("Closing: final dist when parked: %.1f cm | avg cruise err=%.2f | "
          "avg accumulated spin=%.1f" % (dist_media_park, media(errs),
                                           media([r["trompos"] for r in res])))
    peores = sorted(res, key=lambda r: r["puntos"])[:3]
    print("Worst matches:")
    for r in peores:
        print("  seed=%d points=%d deliveries=%d park=%s dist=%.1f | %s"
              % (r["seed"], r["puntos"], r["entregas"], r["park"],
                 r["dist"], "; ".join(r["fallos"]) if r["fallos"] else "-"))
    return res


if __name__ == "__main__":
    campana()
