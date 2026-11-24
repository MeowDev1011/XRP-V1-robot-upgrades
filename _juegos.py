# =========================================================
# JUEGOS INDIVIDUALES Y EN EQUIPO - Team Robots Legends (FUSAMO)
# ---------------------------------------------------------
# Bateria multi-modo con el CODIGO REAL de la placa
# (piloto_gamepad + 5 armas) jugada por el PILOTO KID
# de _masiva.py (temblor, decisiones ~200 ms, reaccion ~180 ms,
# ojo con ruido). Modos:
#
#   CONDUCIR: circuito de 4 puertas en loop (60 s), individual.
#   SUMO    : duelo de empuje 1 vs 1 en anillo de r=76 cm (45 s).
#   SUMO2   : EQUIPOS 2 vs 2: nosotros + aliado scriptado vs 2
#             rivales; ganar = expulsar a los 2 del anillo.
#   FUTBOL  : pelota fisica 1 vs 1; anotar en el gol (120 s).
#   FUTBOL2 : EQUIPOS 2 vs 2: pelota + aliado y 2 rivales dinamicos;
#             gol nuestro arriba (City Center), gol rival cerca de
#             nuestra pared; gana quien anota mas.
#
# PRECISION DEL MANDO: el perfil del piloto se elige con
# JUEGOS_PILOTO=KID|BUENO|REGULAR|ADULTO (misma tabla que _masiva).
#
# FIDELIDAD DEL MANDO (detectar movimientos contrarios o
# involuntarios de lo que quiso el piloto; SOLO nuestro bot):
#   F1 contrario   : intento de avance SOSTENIDO (Y1>0.3 por
#                    >=15 ticks) y el robot retrocede la mayoria
#                    de ese tramo (v <-2.5 cm/s). Nunca debe pasar.
#   F2 derrape     : distancia recorrida tras soltar palancas en
#                    velocidad alta (el Arma 4 debe clavar; >8 cm fallo).
#   F3 involuntario: kid con palancas sueltas >1 s y el robot
#                    se desplazo >3 cm en total.
#   F4 paneo       : kid SIN tocar X1 >1 s y el rumbo cambio >3
#                    grados (fuera de ventanas de choque).
#   F5 latencia    : ms desde Y1>=0.5 hasta ruedas >8 cm/s.
#
# NOTA: las colisiones del equipo/rivales con nuestro robot usan el
# mismo modelo que 1v1 (empuje reciproco + desliz de encoders en
# nosotros); el empuje RECIBIDO no cuenta como fallo del mando.
#
# USO:   python3 _juegos.py                     (5 modos x 400)
#        JUEGOS_MODO=SUMO2 JUEGOS_N=300 python3 _juegos.py
#        JUEGOS_PILOTO=REGULAR JUEGOS_N=200 python3 _juegos.py
# =========================================================
import os

if "JUEGOS_PILOTO" in os.environ:
    os.environ["MASIVA_PILOTO"] = os.environ["JUEGOS_PILOTO"]

import math
import random
import multiprocessing

import simulador_xrp as SIM
from _masiva import (PilotoKid, wrap180, _recargar, PILOTO,
                     TREMOR_SIGMA, DECISION_MS, REACCION_MS,
                     KP_KID, MUERTE_PUNTERIA, RUIDO_VISTA_CM,
                     RUIDO_VISTA_GRADOS, V_KID, STOP_CM, FRENA_A_CM)

N_PARTIDAS = int(os.environ.get("JUEGOS_N", "400"))
WORKERS = int(os.environ.get("JUEGOS_W", "4"))
MODO = os.environ.get("JUEGOS_MODO", "TODOS")

T_MODO = {"CONDUCIR": 60000.0, "SUMO": 45000.0, "SUMO2": 45000.0,
          "FUTBOL": 120000.0, "FUTBOL2": 120000.0}
UMBRAL_AV_KID = 0.30          # Y1 encima: intencion de avanzar
F1_RACHA_MIN = 15             # ticks (0.3 s) de intencion sostenida
F1_V_CONTRARIO = -2.5         # cm/s: retroceder con avance ordenado
F2_CM_MAX = 8.0               # derrape tolerado tras soltar
F3_CM_MAX = 3.0               # deriva tolerada en quieto
F4_GRADOS = 3.0               # paneo tolerado sin X1
F5_V_STALL = 8.0              # cm/s para dar la respuesta

CIRCUITO = ((35.0, 35.0), (60.0, 70.0), (5.0, 105.0), (-35.0, 55.0))
R_PUERTA = 20.0               # radio de paso de puerta
ANILLO_R = 76.0               # sumo
R_CUERPO = 10.0               # radio de los cuerpos (cm)
PELOTA_R = 4.0
GOL_XY = (-5.0, 121.0)        # nuestro gol de ataque (City Center)
GOL_RIVAL_XY = (5.0, 10.0)    # gol que defendemos (cerca de nuestra pared)
R_GOL = 18.0                  # la pelota entra al gol
R_PATEO = 14.0                # contacto robot-pelota
APROX_PELOTA = 2.0            # el kid apunta casi A la pelota: dribble continuo
GOL2_XY = (-5.0, 127.0)       # en FUTBOL2: nuestro gol de ataque (PARED opuesta)
SUMO_EXT = float(os.environ.get("JUEGOS_EXT", "56.0"))
                             # extension del wp "a traves del rival":
                             # con E>=14 el kid NO entra en la zona de freno
                             # (FRENA_A_CM desde el wp) y embiste a fondo

R_GOL2 = 15.0                 # boca de ambos goles de pared (FUTBOL2)
Y_MAX2 = 132.0                # pared del fondo en FUTBOL2 (campo 137 cm)
FRICCION_PELOTA = 0.98        # por tick (20 ms): ~1.0 s de rodada real

_ORDEN_MODO = {"CONDUCIR": 0, "SUMO": 1, "SUMO2": 2, "FUTBOL": 3, "FUTBOL2": 4}


def _clave_modo(modo):
    return sum(ord(c) for c in modo)


class Cuerpo:
    def __init__(self, x, y, th):
        self.x = x
        self.y = y
        self.th = th
        self.vx = 0.0
        self.vy = 0.0
        self.fuera = False


def _chocar(m1, c1, m2, c2):
    """Impulso elastico 1D + separacion posicional entre dos cuerpos."""
    dx = c2.x - c1.x
    dy = c2.y - c1.y
    d = math.hypot(dx, dy)
    if d >= 2 * R_CUERPO:
        return False
    nx, ny = dx / max(d, 1e-6), dy / max(d, 1e-6)
    vrel = (c1.vx - c2.vx) * nx + (c1.vy - c2.vy) * ny
    p = max(0.0, vrel) * (2.0 * m1 * m2 / (m1 + m2))
    c1.vx -= p * nx / m1
    c1.vy -= p * ny / m1
    c2.vx += p * nx / m2
    c2.vy += p * ny / m2
    sep = (2 * R_CUERPO - d) * 0.5
    c1.x -= nx * sep * (m2 / (m1 + m2))
    c1.y -= ny * sep * (m2 / (m1 + m2))
    c2.x += nx * sep * (m1 / (m1 + m2))
    c2.y += ny * sep * (m1 / (m1 + m2))
    return True


def partida(modo, seed, MOD):
    RNG = random.Random(seed * 31 + _clave_modo(modo))
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
    SIM.BOARD.voltage_scale = RNG.uniform(0.85, 1.0)
    SIM.BIAS_IMU_CS = RNG.uniform(0.0, 0.15)
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
    arma5.modo_retorno(False)          # en juegos no hay endgame
    imu = SIM.IMU
    imu.reset_yaw()
    mando.conectar(pad)
    gyro.set_target_here()
    arma5.iniciar_partida()

    kid = PilotoKid(pad, RNG, GP, arma5)
    T_PARTIDA = T_MODO[modo]
    TICKS = int(T_PARTIDA // 20)

    # ------- Arrange del modo -------
    puerta = 0
    vueltas = 0
    resultado = ""
    metas = 0
    contra = 0
    kicks = 0
    rivales = []                       # (cuerpo, vmax, masa)
    aliado = None
    contact_t = [-1e9]                 # ultimo toque de cualquier cuerpo
    if modo in ("SUMO", "SUMO2"):
        equipo = modo == "SUMO2"
        n_riv = 2 if equipo else 1
        for _ in range(n_riv):
            ang = RNG.uniform(0.0, 2.0 * math.pi)
            d = RNG.uniform(45.0, 60.0)
            rivales.append((Cuerpo(math.cos(ang) * d, math.sin(ang) * d,
                                   RNG.uniform(0, 6.3)),
                            RNG.uniform(30.0, 40.0) if equipo else
                            RNG.uniform(22.0, 34.0),
                            RNG.uniform(2.2, 2.8) if equipo else
                            RNG.uniform(1.0, 1.6)))
        if modo == "SUMO2":
            ang_c = math.atan2(rivales[0][0].y, rivales[0][0].x)
            aa = ang_c + math.pi + RNG.uniform(-0.6, 0.6)
            dd = RNG.uniform(28.0, 42.0)
            aliado = (Cuerpo(math.cos(aa) * dd, math.sin(aa) * dd, 0.0),
                      RNG.uniform(24.0, 32.0), 1.2)
    elif modo in ("FUTBOL", "FUTBOL2"):
        pelota = Cuerpo(RNG.uniform(-25.0, 25.0), RNG.uniform(40.0, 70.0), 0.0)
        if modo == "FUTBOL2":
            for _ in range(2):
                rivales.append((Cuerpo(RNG.uniform(-35.0, 35.0),
                                       RNG.uniform(88.0, 112.0), 0.0),
                                RNG.uniform(23.0, 29.0), 1.0))
            aliado = (Cuerpo(RNG.uniform(-25.0, 25.0),
                             RNG.uniform(24.0, 38.0), 0.0),
                      RNG.uniform(26.0, 32.0), 1.2)

    choques = [RNG.uniform(4000, T_PARTIDA * 0.25)
               for _ in range(RNG.randint(0, 2))]
    riv_info = [dict(hasta=0.0, wx=0.0, wy=0.0, pateo=0.0)
                for _ in rivales]
    aliado_cd = [0.0]
    dbg = dict(rk=0, ak_def=0, ak_atq=0, kk=0, bal_lo=0, bal_hi=0)
    atascos = []
    for _ in range(RNG.randint(0, 1)):
        atascos.append((RNG.uniform(5000, T_PARTIDA * 0.8),
                        RNG.uniform(1500.0, 3000.0), RNG.choice(("L", "R"))))

    # ------- helpers de cuerpos scriptados -------
    def _chase(c, wx, wy, vmax):
        aa = math.atan2(wy - c.y, wx - c.x)
        c.vx += (math.cos(aa) * vmax - c.vx) * 0.25
        c.vy += (math.sin(aa) * vmax - c.vy) * 0.25

    def _integra(c):
        c.x += c.vx * 0.02
        c.y += c.vy * 0.02

    def _empuja_robot(c, masa, px, py):
        """Contacto cuerpo-vs-NUESTRO bot (mismo modelo que 1v1).
        Devuelve True si hubo contacto."""
        dx = px - c.x
        dy = py - c.y
        dist = math.hypot(dx, dy)
        if dist >= 2 * R_CUERPO:
            return False
        contact_t[0] = SIM.RELOJ.ticks_ms()
        nx, ny = dx / max(dist, 1e-6), dy / max(dist, 1e-6)
        v_rel = math.hypot(px - prev_pose[0], py - prev_pose[1]) / 0.02
        v_op = math.hypot(c.vx, c.vy)
        imp = max(0.0, v_rel * 1.0 - v_op * 0.6) * 0.02
        c.vx -= nx * imp / masa * 50.0
        c.vy -= ny * imp / masa * 50.0
        if imp > 0.25:
            DRV.yaw += RNG.uniform(-8.0, 8.0)
        if dist < 1.6 * R_CUERPO:
            sep = (1.6 * R_CUERPO - dist) * 0.5
            # a nosotros nos corren las ruedas; lo proyectamos como
            # desliz del encoder (empuje externo), CAPADO por tick para
            # que una penetracion profunda no dispare la odometria
            desliz = min(sep * 0.25, 0.3)
            DRV.LEFT.pos_cm -= nx * desliz
            DRV.RIGHT.pos_cm -= nx * desliz
            # el desplazamiento escala con la masa rival: la "masa"
            # modela el peso de empuje del rival sobre el contacto
            c.x += nx * sep * 0.5 * masa
            c.y += ny * sep * 0.5 * masa
        return True

    # ------- fidelidad -------
    f1_ticks = 0
    f1_racha = 0
    f1_contrario = 0
    f2_eventos = 0
    f2_peor = 0.0
    f3_eventos = 0
    f4_eventos = 0
    f5_ms = []
    y1_prev = 0.0
    frenando = False
    fren_d = 0.0
    fren_t0 = 0.0
    quieto_t = -1.0
    quieto_dist = 0.0
    sin_x1_t = -1.0
    sin_x1_yaw0 = None
    lat_en_vuelo = None
    prev_pose = (0.0, 0.0, 0.0)

    for k in range(TICKS):
        SIM.RELOJ.avanzar(20)
        t = SIM.RELOJ.ticks_ms()

        # ---------- piloto KID ----------
        if k == 0:
            pad.botones[GP.START - 4] = 1
        else:
            pad.botones[GP.START - 4] = 0

        px, py, pth = arma5.pose()

        if modo == "CONDUCIR":
            gx, gy = CIRCUITO[puerta]
            kid.wp_x, kid.wp_y = gx, gy
        elif modo in ("SUMO", "SUMO2"):
            vivos = [c for c, _v, _m in rivales if not c.fuera]
            if vivos:
                cero = min(vivos, key=lambda c: (c.x - px) ** 2 + (c.y - py) ** 2)
                drc = math.hypot(cero.x, cero.y)
                if drc > 1e-6:
                    # empuje sostenido: wp MAS ALLA del rival hacia el
                    # borde, asi el nino nunca suelta el contacto
                    kid.wp_x = cero.x + cero.x / drc * SUMO_EXT
                    kid.wp_y = cero.y + cero.y / drc * SUMO_EXT
                    if modo == "SUMO2":
                        # en equipo el kid no persigue puntos fuera del
                        # anillo: con 2 rivales encima se auto-expulsaria
                        dw = math.hypot(kid.wp_x, kid.wp_y)
                        if dw > ANILLO_R - 12.0:
                            kid.wp_x *= (ANILLO_R - 12.0) / dw
                            kid.wp_y *= (ANILLO_R - 12.0) / dw
        elif modo == "FUTBOL":
            # el kid NO puede retroceder y un contacto tangencial clava la
            # pelota contra banda (traza: la pelota murio en la esquina y el
            # kid orbito a 2 cm/s). Tactica en 3 roles:
            #   ALINEADO  -> carrerilla A TRAVES del arco (wp 35 cm despues del
            #                gol: no cae en su banda de frenado antes de anotar)
            #   EN CONTACTO desalineado -> esquiva lateral 26 cm por SU lado,
            #                alejandose ANTES de volver a entrar (moverse hacia
            #                aca no patea: salio del radio de contacto)
            #   DESPEJADO  -> punto de entrada 24 cm DETRAS de la pelota, con
            #                trayectoria libre (rodearla y volver a alinear)
            atq = GOL_XY
            ang_gol = math.atan2(atq[1] - pelota.y, atq[0] - pelota.x)
            cg, sg = math.cos(ang_gol), math.sin(ang_gol)
            dxp = pelota.x - px
            dyp = pelota.y - py
            d_ball = math.hypot(dxp, dyp)
            alineado = dxp * cg + dyp * sg >= 8.0
            if alineado:
                kid.wp_x = pelota.x + cg * 20.0
                kid.wp_y = pelota.y + sg * 20.0
            elif d_ball < 20.0:
                lado_sin = (-sg, cg)
                lado = 1.0 if (dxp * lado_sin[0] + dyp * lado_sin[1]) >= 0 else -1.0
                kid.wp_x = px - sg * lado * 26.0
                kid.wp_y = py + cg * lado * 26.0
            else:
                kid.wp_x = pelota.x - cg * 24.0
                kid.wp_y = pelota.y - sg * 24.0
        elif modo == "FUTBOL2":
            # aqui el kid es SOPORTE: se queda CASI a la pelota (a +6
            # no alcanza R_PATEO y no la toca: con punteria de nino sus
            # palazos rompen el juego del aliado experto, probado en A/B)
            atq = GOL2_XY
            ang_gol = math.atan2(atq[1] - pelota.y, atq[0] - pelota.x)
            kid.wp_x = pelota.x + math.cos(ang_gol) * 6.0
            kid.wp_y = pelota.y + math.sin(ang_gol) * 6.0
        kid.paso(t, (px, py, pth), SIM.IMU.get_yaw())

        # eventos del modo (verdad del campo)
        if modo == "CONDUCIR" and t >= 1000:
            if math.hypot(px - kid.wp_x, py - kid.wp_y) < R_PUERTA:
                puerta += 1
                if puerta % len(CIRCUITO) == 0:
                    vueltas += 1
                puerta %= len(CIRCUITO)

        elif modo in ("SUMO", "SUMO2"):
            for ri, (rc, vmax_r, masa_r) in enumerate(rivales):
                if rc.fuera:
                    continue
                if _empuja_robot(rc, masa_r, px, py):
                    continue        # en contacto SOLO empuje (como 1v1)
                                # sumo: en 1v1 carga directo; en 2v2 postura entre presa
                # y centro, carga de cerca y autocuidado cerca del borde
                if aliado:
                    dkid = (px - rc.x) ** 2 + (py - rc.y) ** 2
                    dali = ((aliado[0].x - rc.x) ** 2 +
                            (aliado[0].y - rc.y) ** 2)
                    prey = (px, py) if dkid < dali else \
                        (aliado[0].x, aliado[0].y)
                    do = math.hypot(rc.x, rc.y)
                    dprey = math.hypot(prey[0] - rc.x, prey[1] - rc.y)
                    if do > ANILLO_R - 12.0:
                        _chase(rc, 0.0, 0.0, vmax_r)
                    elif dprey < 42.0:
                        _chase(rc, prey[0], prey[1], vmax_r)
                    else:
                        _chase(rc, rc.x * 0.30 + prey[0] * 0.70,
                               rc.y * 0.30 + prey[1] * 0.70, vmax_r)
                else:
                    _chase(rc, px, py, vmax_r)
                if os.environ.get("JUEGOS_DEBUG"):
                    riv_info[ri]["lt"] = t
            if aliado:
                vivos = [c for c, _v, _m in rivales if not c.fuera]
                if vivos:
                    obj = min(vivos, key=lambda c: (c.x - aliado[0].x) ** 2 +
                              (c.y - aliado[0].y) ** 2)
                    do = math.hypot(obj.x, obj.y)
                    lim = ANILLO_R - 12.0
                    if do > lim:
                        esc = lim / do
                        ox, oy = obj.x * esc, obj.y * esc
                    else:
                        ox, oy = obj.x, obj.y
                    _chase(aliado[0], ox, oy, aliado[1])
            if aliado:
                for rc, _v, mr in rivales:
                    if not rc.fuera:
                        _chocar(mr, rc, aliado[1], aliado[0])
            for i in range(len(rivales)):
                for j in range(i + 1, len(rivales)):
                    _chocar(rivales[i][2], rivales[i][0],
                            rivales[j][2], rivales[j][0])
            for c, _v, _m in rivales:
                _integra(c)
            if aliado:
                _integra(aliado[0])
            riv_fuera = sum(1 for c, _v, _m in rivales
                            if c.fuera or math.hypot(c.x, c.y) > ANILLO_R)
            for c, _v, _m in rivales:
                if math.hypot(c.x, c.y) > ANILLO_R and not c.fuera:
                    c.fuera = True
                    c.vx = c.vy = 0.0
            if os.environ.get("JUEGOS_TRACE") and k % 25 == 0:
                print("  t=%.1f r=(%.1f,%.1f) rival0=(%.1f,%.1f) v=(%.1f,%.1f) "
                      "fuera=%s lt=%.1f f=%.1f modo=%s y1=%.2f" %
                      (t / 1000.0, px, py, rivales[0][0].x, rivales[0][0].y,
                       rivales[0][0].vx, rivales[0][0].vy,
                       rivales[0][0].fuera,
                       riv_info[0].get("lt", -9.0) / 1000.0,
                       math.hypot(px - rivales[0][0].x,
                                  py - rivales[0][0].y),
                       mando.nombre_modo(), pad.axes[1]))
            nosotros_afuera = math.hypot(px, py) > ANILLO_R
            if riv_fuera == len(rivales) and not nosotros_afuera:
                resultado = "GANAMOS"
                break
            if nosotros_afuera and riv_fuera < len(rivales):
                resultado = "PERDEMOS"
                break

        elif modo in ("FUTBOL", "FUTBOL2"):
            dx = px - pelota.x
            dy = py - pelota.y
            dist = math.hypot(dx, dy)
            if dist < R_PATEO:
                nx, ny = -dx / max(dist, 1e-6), -dy / max(dist, 1e-6)
                vrx = (px - prev_pose[0]) / 0.02
                vry = (py - prev_pose[1]) / 0.02
                w = max(0.0, vrx * nx + vry * ny)
                obj_v = w * 1.15 + 2.0
                pelota.vx += (nx * obj_v - pelota.vx) * 0.5
                pelota.vy += (ny * obj_v - pelota.vy) * 0.5
                kicks += 1
                if os.environ.get("JUEGOS_DEBUG"):
                    dbg["kk"] += 1

            if modo == "FUTBOL2":
                for ri, (rc, vmax_r, _m) in enumerate(rivales):
                    info = riv_info[ri]
                    if t >= info["hasta"]:
                        dr = math.hypot(GOL_RIVAL_XY[0] - pelota.x,
                                        GOL_RIVAL_XY[1] - pelota.y)
                        axn = (GOL_RIVAL_XY[0] - pelota.x) / max(dr, 1e-6)
                        ayn = (GOL_RIVAL_XY[1] - pelota.y) / max(dr, 1e-6)
                        # rodean la pelota por lados opuestos (no se apilan)
                        lat = 7.0 if ri == 0 else -7.0
                        # rivales tambien son ninos: deciden cada 220-450 ms
                        # y ven la pelota con ruido de +-5 cm
                        info["wx"] = (pelota.x - axn * 10.0 - ayn * lat +
                                      RNG.uniform(-5.0, 5.0))
                        info["wy"] = (pelota.y - ayn * 10.0 + axn * lat +
                                      RNG.uniform(-5.0, 5.0))
                        info["hasta"] = t + RNG.uniform(220.0, 450.0)
                    _chase(rc, info["wx"], info["wy"], vmax_r)
                    dbx = rc.x - pelota.x
                    dby = rc.y - pelota.y
                    if (math.hypot(dbx, dby) < R_PATEO and
                            t >= info["pateo"] and
                            math.hypot(pelota.vx, pelota.vy) < 12.0):
                        dr2 = math.hypot(GOL_RIVAL_XY[0] - pelota.x,
                                         GOL_RIVAL_XY[1] - pelota.y)
                        axn = (GOL_RIVAL_XY[0] - pelota.x) / max(dr2, 1e-6)
                        ayn = (GOL_RIVAL_XY[1] - pelota.y) / max(dr2, 1e-6)
                        # nino real: CONDUCE con empujones lejos del arco,
                        # solo TIRA a menos de 45 cm del arco
                        v = math.hypot(rc.vx, rc.vy)
                        if dr2 < 30.0:
                            ru = RNG.uniform(-0.8, 0.8)
                            vf = min(max(v * 1.2 + 4.0, dr2 * 1.1), 20.0)
                        else:
                            ru = RNG.uniform(-0.35, 0.35)
                            vf = min(v * 1.15 + 2.0, 12.0)
                        cr, sr = math.cos(ru), math.sin(ru)
                        pelota.vx = (axn * cr - ayn * sr) * vf
                        pelota.vy = (axn * sr + ayn * cr) * vf
                        # balance 2v2: cd del rival (antes 800) para que
                        # el kid + aliado puedan disputar la pelota
                        info["pateo"] = t + 1200.0
                        if os.environ.get("JUEGOS_DEBUG"):
                            dbg["rk"] += 1
                if aliado:
                    # aliado CON LAS ARMAS (mismo software que nosotros):
                    # cazapelota directo, sin retardo de decision; en caja
                    # de NUESTRO arco defiende la boca (entre pelota y
                    # linea de gol) y despeja, fuera conduce o tira.
                    dp_gol = math.hypot(pelota.x - GOL_RIVAL_XY[0],
                                        pelota.y - GOL_RIVAL_XY[1])
                    da = math.hypot(GOL2_XY[0] - pelota.x,
                                    GOL2_XY[1] - pelota.y)
                    en_caja = dp_gol < 40.0
                    v_pelota = math.hypot(pelota.vx, pelota.vy)
                    if en_caja:
                        if v_pelota > 12.0:
                            # tiro en curso: se planta en la LINEA pelota-gol
                            gx = GOL_RIVAL_XY[0] + (pelota.x -
                                                    GOL_RIVAL_XY[0]) / \
                                max(dp_gol, 1e-6) * 9.0
                            gy = GOL_RIVAL_XY[1] + (pelota.y -
                                                    GOL_RIVAL_XY[1]) / \
                                max(dp_gol, 1e-6) * 9.0
                        else:
                            # pelota lenta en nuestra caja: sale A DISPUTARLA
                            gx, gy = pelota.x, pelota.y
                        _chase(aliado[0], gx, gy, aliado[1] + 5.0)
                    else:
                        _chase(aliado[0], pelota.x, pelota.y, aliado[1] + 5.0)
                    dbx = aliado[0].x - pelota.x
                    dby = aliado[0].y - pelota.y
                    alcance = (R_PATEO + 6.0) if en_caja else R_PATEO
                    v_pel_ok = (True if en_caja else v_pelota < 12.0)
                    if (math.hypot(dbx, dby) < alcance and
                            t >= aliado_cd[0] and v_pel_ok):
                        cr, sr = 1.0, 0.0
                        if dp_gol < da:
                            # despeje LARGO hacia arriba del campo
                            # (nunca contra la pared lateral)
                            axn = (GOL2_XY[0] - pelota.x) / \
                                max(da, 1e-6)
                            ayn = (GOL2_XY[1] - pelota.y) / \
                                max(da, 1e-6)
                            ru = RNG.uniform(-0.45, 0.45)
                            cr, sr = math.cos(ru), math.sin(ru)
                            vf = RNG.uniform(26.0, 34.0)
                            pelota.vx = (axn * cr - ayn * sr) * vf
                            pelota.vy = (axn * sr + ayn * cr) * vf
                            if os.environ.get("JUEGOS_DEBUG"):
                                dbg["ak_def"] += 1
                        else:
                            axn = (GOL2_XY[0] - pelota.x) / max(da, 1e-6)
                            ayn = (GOL2_XY[1] - pelota.y) / max(da, 1e-6)
                            v = math.hypot(aliado[0].vx, aliado[0].vy)
                            if da < 30.0:
                                ru = RNG.uniform(-0.7, 0.7)
                                vf = min(max(v * 1.2 + 4.0, da * 1.1), 24.0)
                            else:
                                ru = RNG.uniform(-0.25, 0.25)
                                vf = min(v * 1.15 + 2.0, 12.0)
                            cr, sr = math.cos(ru), math.sin(ru)
                            pelota.vx = (axn * cr - ayn * sr) * vf
                            pelota.vy = (axn * sr + ayn * cr) * vf
                            if os.environ.get("JUEGOS_DEBUG"):
                                dbg["ak_atq"] += 1
                        aliado_cd[0] = t + (250.0 if en_caja else 700.0)
                for c, _v, _m in rivales:
                    _empuja_robot(c, _m, px, py)
                for i in range(len(rivales)):
                    for j in range(i + 1, len(rivales)):
                        _chocar(rivales[i][2], rivales[i][0],
                                rivales[j][2], rivales[j][0])
                if aliado:
                    _empuja_robot(aliado[0], aliado[2], px, py)
                    for rc, _v, mr in rivales:
                        _chocar(mr, rc, aliado[2], aliado[0])
                for c, _v, _m in rivales:
                    _integra(c)
                if aliado:
                    _integra(aliado[0])

            if os.environ.get("JUEGOS_DEBUG"):
                if pelota.y < 68.5:
                    dbg["bal_lo"] += 1
                else:
                    dbg["bal_hi"] += 1
            pelota.vx *= FRICCION_PELOTA
            pelota.vy *= FRICCION_PELOTA
            pelota.x += pelota.vx * 0.02
            pelota.y += pelota.vy * 0.02
            if abs(pelota.x) > 60.0:
                pelota.vx *= -0.5
                pelota.x = 60.0 * (1 if pelota.x > 0 else -1)
            y_max = Y_MAX2 if modo == "FUTBOL2" else 250.0
            if pelota.y > y_max or pelota.y < 5.0:
                pelota.vy *= -0.5
                pelota.y = min(y_max, max(5.0, pelota.y))
            atq_xy, r_gol = (GOL2_XY, R_GOL2) if modo == "FUTBOL2" \
                else (GOL_XY, R_GOL)
            if math.hypot(pelota.x - atq_xy[0],
                          pelota.y - atq_xy[1]) < r_gol:
                metas += 1
                pelota.x, pelota.y = RNG.uniform(-25, 25), RNG.uniform(40, 70)
                pelota.vx = pelota.vy = 0.0
            if (modo == "FUTBOL2" and
                    math.hypot(pelota.x - GOL_RIVAL_XY[0],
                               pelota.y - GOL_RIVAL_XY[1]) < R_GOL2):
                contra += 1
                if os.environ.get("JUEGOS_DEBUG"):
                    vb = math.hypot(pelota.vx, pelota.vy)
                    dbg["gol_v"] = dbg.get("gol_v", 0.0) + vb
                    dbg["gol_n"] = dbg.get("gol_n", 0) + 1
                pelota.x, pelota.y = RNG.uniform(-25, 25), RNG.uniform(40, 70)
                pelota.vx = pelota.vy = 0.0
            if os.environ.get("JUEGOS_TRACE") and k % 25 == 0:
                resto = ""
                for _i, (c, _v, _m) in enumerate(rivales):
                    resto += " r%d=(%.1f,%.1f)" % (_i, c.x, c.y)
                if aliado:
                    resto += " AL=(%.1f,%.1f)" % (aliado[0].x, aliado[0].y)
                print("  t=%.1f robot=(%.1f,%.1f) th=%.0f pelota=(%.1f,%.1f) "
                      "v_pel=(%.1f,%.1f) d=%.1f wp=(%.1f,%.1f) y1=%.2f "
                      "mando=%s%s" %
                      (t / 1000.0, px, py, pth, pelota.x, pelota.y,
                       pelota.vx, pelota.vy, dist, kid.wp_x, kid.wp_y,
                       pad.axes[1], mando.nombre_modo(), resto))

        # ---------- fisica hostil ----------
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

        mando._paso()
        gyro._tick()
        tb.paso()
        arma5._odometria()
        arma5._logica_endgame()
        DRV.paso(0.02)

        # ---------- fidelidad del mando ----------
        p2 = arma5.pose()
        pth_rad = math.radians(pth)
        dprog = (p2[0] - prev_pose[0]) * math.cos(pth_rad) + \
                (p2[1] - prev_pose[1]) * math.sin(pth_rad)
        dist2 = math.hypot(p2[0] - prev_pose[0], p2[1] - prev_pose[1])
        v_cm_s = dprog / 0.02
        y1i = kid.y1
        x1i = kid.x1
        yaw_now = SIM.IMU.get_yaw()

        # el rival que nos empuja NO es un defecto del mando
        empujados = (t - contact_t[0] < 1000) or \
            any(lo - 200 <= t <= lo + 1000 for lo in choques)
        if not empujados and y1i > UMBRAL_AV_KID:
            f1_racha += 1
            if v_cm_s < F1_V_CONTRARIO:
                f1_contrario += 1
                if "JUEGOS_TRACE" in os.environ:
                    print("  tick t=%.2f modo_mando=%s y1=%.2f x1=%.2f "
                          "v=%.1f yaw=%.1f pth=%.1f dpos=(%.2f,%.2f)" %
                          (t / 1000.0, mando.nombre_modo(), y1i, x1i,
                           v_cm_s, yaw_now, pth, prev_pose[0], prev_pose[1]))
        elif empujados:
            f1_racha = 0
            f1_contrario = 0
        else:
            if f1_racha >= F1_RACHA_MIN and f1_contrario * 2 > f1_racha:
                f1_ticks += f1_racha
                if "JUEGOS_TRACE" in os.environ:
                    print("F1 t=%.1f modo=%s racha=%d contrario=%d "
                          "modo_mando=%s yaw=%.1f" %
                          (t / 1000.0, modo, f1_racha, f1_contrario,
                           mando.nombre_modo(), yaw_now))
            f1_racha = 0
            f1_contrario = 0

        if empujados:
            frenando = False
        elif not frenando:
            if y1_prev >= 0.4 and y1i < 0.02 and abs(v_cm_s) > 10.0:
                frenando = True
                fren_d = 0.0
                fren_t0 = t
        elif y1i > 0.05:
            frenando = False          # el kid volvio a mandar: no es derrape
        else:
            fren_d += dist2
            if abs(v_cm_s) < 1.0 or t - fren_t0 > 2000:
                if fren_d > F2_CM_MAX:
                    f2_eventos += 1
                    f2_peor = max(f2_peor, fren_d)
                    if "JUEGOS_TRACE" in os.environ:
                        print("F2 t=%.1f derrape=%.1f dur=%.1fs atascos=%s "
                              "modo_mando=%s" %
                              (t / 1000.0, fren_d, (t - fren_t0) / 1000.0,
                               [(a, b) for a, b, _ in atascos],
                               mando.nombre_modo()))
                frenando = False

        if lat_en_vuelo is None and y1i >= 0.5:
            lat_en_vuelo = t
        if lat_en_vuelo is not None and v_cm_s >= F5_V_STALL:
            f5_ms.append(t - lat_en_vuelo)
            lat_en_vuelo = None
        elif lat_en_vuelo is not None and y1i < 0.5:
            lat_en_vuelo = None

        if y1i <= 0.02 and x1i <= 0.02 and abs(pad.axes[0]) < 0.05:
            if quieto_t < 0:
                quieto_t = t
                quieto_dist = 0.0
            quieto_dist += dist2
            if t - quieto_t > 1000 and quieto_dist > F3_CM_MAX:
                f3_eventos += 1
                quieto_t = t
                quieto_dist = 0.0
        else:
            quieto_t = -1.0
            quieto_dist = 0.0

        if abs(x1i) < 0.05:
            en_ventana_choque = any(lo - 500 <= t <= lo + 6000
                                    for lo in choques)
            if sin_x1_t < 0:
                sin_x1_t = t
                sin_x1_yaw0 = yaw_now
            elif (not en_ventana_choque and t - sin_x1_t > 1000 and
                    abs(wrap180(yaw_now - sin_x1_yaw0)) > F4_GRADOS):
                f4_eventos += 1
                if "JUEGOS_TRACE" in os.environ:
                    print("F4 t=%.1f d_yaw=%.2f dur=%.1fs modo_mando=%s "
                          "ema=%+.3f y1=%.2f x1=%.3f tgt=%.1f "
                          "enabled=%s yaw=%.1f" %
                          (t / 1000.0, wrap180(yaw_now - sin_x1_yaw0),
                           (t - sin_x1_t) / 1000.0, mando.nombre_modo(),
                           mando._ema_x, y1i, x1i,
                           gyro.target, gyro.enabled, yaw_now))
                sin_x1_t = -1.0
                sin_x1_yaw0 = None
            elif os.environ.get("JUEGOS_DEBUG"):
                print("  F4row t=%.1f modo=%s x1=%+.4f y1=%.2f ema=%+.4f "
                      "yaw=%.2f tgt=%.2f lerr=%.2f L=(%.1f,%.3f) "
                      "R=(%.1f,%.3f)" %
                      (t / 1000.0, mando.nombre_modo(), x1i, y1i,
                       mando._ema_x, yaw_now, gyro.target,
                       gyro.last_error, DRV.LEFT.rpm, DRV.LEFT.effort,
                       DRV.RIGHT.rpm, DRV.RIGHT.effort))
        else:
            sin_x1_t = -1.0
            sin_x1_yaw0 = None

        y1_prev = y1i
        prev_pose = p2

        if resultado or arma5.ms_transcurridos() >= T_PARTIDA:
            break

    if f1_racha >= F1_RACHA_MIN and f1_contrario * 2 > f1_racha:
        f1_ticks += f1_racha
        if "JUEGOS_TRACE" in os.environ:
            print("F1 FINAL racha=%d contrario=%d (%s)" %
                  (f1_racha, f1_contrario, resultado))

    if os.environ.get("JUEGOS_DEBUG"):
        gn = dbg.get("gol_n", 0)
        print("DBG %s kicks rk=%d ak_def=%d ak_atq=%d kk=%d "
              "bal_lo=%d bal_hi=%d metas=%d contra=%d "
              "gol_v_media=%.1f" %
              (modo, dbg["rk"], dbg["ak_def"], dbg["ak_atq"], dbg["kk"],
               dbg["bal_lo"], dbg["bal_hi"], metas, contra,
               (dbg.get("gol_v", 0.0) / gn) if gn else -1))

    if modo in ("SUMO", "SUMO2") and not resultado:
        riv_fuera = sum(1 for c, _v, _m in rivales
                        if c.fuera or math.hypot(c.x, c.y) > ANILLO_R)
        if modo == "SUMO":
            resultado = "EMPATE"
        else:
            resultado = "GANAMOS" if riv_fuera == len(rivales) else \
                "EMPATE outs=%d" % riv_fuera
    if modo == "CONDUCIR":
        resultado = "puertas=%d" % puerta
    elif modo in ("FUTBOL", "FUTBOL2"):
        if modo == "FUTBOL":
            resultado = "metas=%d" % metas
        else:
            resultado = ("GANAMOS" if metas > contra else
                         "PERDEMOS" if metas < contra else "EMPATE") + \
                " %d-%d" % (metas, contra)

    f5_med = sum(f5_ms) / len(f5_ms) if f5_ms else -1.0
    return {"seed": seed, "modo": modo, "resultado": resultado,
            "metas": metas if modo in ("FUTBOL", "FUTBOL2") else -1,
            "contra": contra if modo == "FUTBOL2" else -1,
            "kicks": kicks if modo in ("FUTBOL", "FUTBOL2") else -1,
            "puertas": puerta if modo == "CONDUCIR" else -1,
            "vueltas": vueltas if modo == "CONDUCIR" else -1,
            "gano": ("GANAMOS" in resultado) if modo in ("SUMO", "SUMO2",
                                                         "FUTBOL2") else False,
            "f1": f1_ticks, "f2": f2_eventos, "f2_cm": f2_peor,
            "f3": f3_eventos, "f4": f4_eventos, "f5": f5_med}


def evaluacion(modo, n):
    base = 900000 + _clave_modo(modo) % 5000
    with multiprocessing.Pool(WORKERS) as pool:
        res = pool.map(_trabajo_modo, [(modo, base + i) for i in range(n)],
                       chunksize=8)
    m = [r for r in res if r["modo"] == modo]
    if not m:
        return
    f1 = sum(1 for r in m if r["f1"] > 25)
    f2 = sum(1 for r in m if r["f2"] > 0)
    f3 = sum(1 for r in m if r["f3"] > 0)
    f4 = sum(1 for r in m if r["f4"] > 0)
    f5_ok = [r["f5"] for r in m if r["f5"] > 0]
    f5_med = sum(f5_ok) / len(f5_ok) if f5_ok else -1
    print("\n== MODO %s : %d partidas %s ==" % (modo, len(m), PILOTO))
    if modo in ("SUMO", "SUMO2"):
        g = sum(1 for r in m if r["gano"])
        p = sum(1 for r in m if r["resultado"].startswith("PERDEMOS"))
        print("%s ganadas %.1f%% / perdidas %.1f%% / empates %.1f%%" %
              (modo, 100.0 * g / len(m), 100.0 * p / len(m),
               100.0 * (len(m) - g - p) / len(m)))
    elif modo in ("FUTBOL", "FUTBOL2"):
        gs = [r["metas"] for r in m]
        ks = [r["kicks"] for r in m]
        g = sum(1 for r in m if r["gano"])
        p = sum(1 for r in m if r["resultado"].startswith("PERDEMOS"))
        extra = "  encajadas media %.2f" % \
            (sum(r["contra"] for r in m) / len(m)) if modo == "FUTBOL2" else ""
        print("%s goles: media %.2f [0:%d 1:%d 2:%d 3+:%d] kicks/p %.1f | "
              "ganamos %.1f%% / perdemos %.1f%%%s" %
              (modo, sum(gs) / len(gs), gs.count(0), gs.count(1),
               gs.count(2), sum(1 for x in gs if x >= 3),
               sum(ks) / len(ks), 100.0 * g / len(m),
               100.0 * p / len(m), extra))
    else:
        ps = [r["puertas"] for r in m]
        vs = [r["vueltas"] for r in m]
        print("CONDUCIR puertas: media %.2f  min %d  max %d | "
              "vueltas completas: media %.2f  max %d" %
              (sum(ps) / len(ps), min(ps), max(ps),
               sum(vs) / len(vs), max(vs)))
    print("FIDELIDAD: contrarios(F1)=%d  derrape(F2)=%d  involuntarios(F3)=%d  "
          "paneo(F4)=%d | latencia media=%.0f ms" % (f1, f2, f3, f4, f5_med))
    malos = [r for r in m if r["f1"] > 25 or r["f2"] or r["f3"] or r["f4"]]
    if malos:
        print("  partidas con fallo: %d/%d" % (len(malos), len(m)))
        for r in malos[:5]:
            print("  semilla %d: f1=%d f2=%d(%.1fcm) f3=%d f4=%d  %s" %
                  (r["seed"], r["f1"], r["f2"], r["f2_cm"],
                   r["f3"], r["f4"], r["resultado"]))
    return m


def _trabajo_modo(arg):
    modo, seed = arg
    MOD = _recargar()
    return partida(modo, seed, MOD)


def campania_juegos():
    if MODO == "TODOS":
        modos = ("CONDUCIR", "SUMO", "SUMO2", "FUTBOL", "FUTBOL2")
    else:
        modos = (MODO,)
    print("== CAMPAÑA JUEGOS INDIVIDUALES Y EN EQUIPO == piloto=%s "
          "n=%d/%s procesos=%d" % (PILOTO, N_PARTIDAS, MODO, WORKERS))
    for modo in modos:
        evaluacion(modo, N_PARTIDAS)


if __name__ == "__main__":
    campania_juegos()
