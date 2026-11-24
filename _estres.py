# =========================================================
# BATERIA DE ESTRES - Team Robots Legends (FUSAMO)
# 30 partidas aleatorias. El piloto juega CON EL MANDO
# (gamepad virtual + piloto_gamepad: el mismo codigo que corre
# en la placa) y la planta agrede al robot:
#   - choques de hasta 40 grados de trompo (0 a 3 por partida)
#   - atascos fisicos de rueda de 2-5 s (0 a 2, cualquier rueda)
#   - bateria entre 82% y 100%
#   - deriva de IMU hasta 0.2 grados/s + ruido gaussiano
# CRITERIOS (por partida):
#   P1: todo trompo por choque queda < 3 grados (medido 10 s
#       despues del choque, con el Gyro-Lock activo)
#   P2: rumbo estable en crucero (err max < 12 grados, sin
#       contar ventanas de choques ni del giro del piloto)
#   P3: ENDGAME regresa a casa y queda CLAVADO (<= 6 cm)
#   P4: ni una sola excepcion en ninguna partida
# USO: python3 _estres.py
# =========================================================
import sys
import importlib
import os

import simulador_xrp as SIM          # inyecta planta + stubs, no corre partida

_MODULOS = ("arma3_curvas", "arma2_torque_boost", "arma4_traccion",
            "arma5_endgame", "arma1_gyro_lock", "piloto_gamepad")


def recargar():
    for nombre in _MODULOS:
        importlib.reload(sys.modules[nombre])
    return sys.modules


def nueva_partida(seed, MOD):
    import random
    RNG = random.Random(seed)

    A1 = MOD["arma1_gyro_lock"]
    A2 = MOD["arma2_torque_boost"]
    A4 = MOD["arma4_traccion"]
    A5 = MOD["arma5_endgame"]
    MAIN = MOD["piloto_gamepad"]

    DRV = SIM.DRIVETRAIN
    GP = SIM.GamepadSim

    # -------- planta a cero + condiciones aleatorias --------
    SIM.RELOJ.t = 0
    DRV.LEFT = SIM.RuedaSim()
    DRV.RIGHT = SIM.RuedaSim()
    DRV.yaw = 0.0
    DRV.fuente = "inactiva"
    SIM.BOARD.voltage_scale = RNG.uniform(0.82, 1.0)
    bias = RNG.uniform(0.0, 0.2)
    SIM.BIAS_IMU_CS = bias
    pad = GP.nueva()

    # -------- cadena completa, igual que main_partida.py --------
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
    arma5.modo_retorno(True)
    A5.V_RETORNO = 0.85
    imu = SIM.IMU
    imu.reset_yaw()
    mando.conectar(pad)
    gyro.set_target_here()

    # -------- guion del piloto (aleatorio por seed) --------
    t_giro = RNG.uniform(25000.0, 50000.0)
    delta_giro = RNG.choice((-180.0, 180.0, 90.0, -90.0))
    vel = RNG.uniform(0.38, 0.55)
    dist_objetivo = RNG.uniform(60.0, 110.0)
    choques = [RNG.uniform(5000, 120000) for _ in range(RNG.randint(0, 3))]
    choques = [t for t in choques if not (t_giro - 1500 <= t <= t_giro + 6500)]
    atascos = []
    for _ in range(RNG.randint(0, 2)):
        t0 = RNG.uniform(5000, 115000)
        atascos.append((t0, RNG.uniform(2000.0, 5000.0), RNG.choice(("L", "R"))))

    # -------- metricas --------
    fallos = []
    max_err = 0.0
    choque_regs = []
    p1_pend = []
    giro_iniciado = False
    giro_terminado = False    # el piloto suelta el stick para siempre tras el giro
    objetivo_rumbo = 0.0

    # -------- partida (150 s a pasos de 20 ms) --------
    for k in range(7500):
        SIM.RELOJ.avanzar(20)
        t = SIM.RELOJ.ticks_ms()

        # ---------- piloto con el mando ----------
        pad.botones[GP.START - 4] = 1 if 400 <= t < 420 else 0

        if not giro_iniciado:
            if t >= t_giro:
                giro_iniciado = True
                objetivo_rumbo = SIM.IMU.get_yaw() + delta_giro
                pad.axes[GP.Y1] = 0.0
                pad.axes[GP.X1] = 1.0 if delta_giro > 0 else -1.0
            elif t >= 2000:
                # avanza hacia su distancia objetivo y suelta al llegar
                if arma5.distancia_al_hogar() < dist_objetivo:
                    pad.axes[GP.Y1] = vel
                elif pad.axes[GP.Y1] > 0.0:
                    pad.axes[GP.Y1] = 0.0
        elif not giro_terminado:
            # el piloto gira con el stick X1 guiandose por la IMU
            err_giro = (objetivo_rumbo - SIM.IMU.get_yaw() + 180.0) % 360.0 - 180.0
            if abs(err_giro) > 4.0 and pad.axes[GP.X1] == 0.0:
                pad.axes[GP.X1] = 1.0 if err_giro > 0 else -1.0
            elif abs(err_giro) <= 4.0 and pad.axes[GP.X1] != 0.0:
                pad.axes[GP.X1] = 0.0
                giro_terminado = True

        # ---------- eventos fisicos ----------
        for lo, dur, rueda in atascos:
            if lo <= t < lo + dur:
                DRV.LEFT.atascada = (rueda == "L")
                DRV.RIGHT.atascada = (rueda == "R")
            elif getattr(DRV.LEFT, "atascada", False) and rueda == "L" and t >= lo + dur:
                DRV.LEFT.atascada = False
            elif getattr(DRV.RIGHT, "atascada", False) and rueda == "R" and t >= lo + dur:
                DRV.RIGHT.atascada = False
        for lo in choques:
            if lo <= t < lo + 20:
                salto = RNG.uniform(15.0, 40.0) * RNG.choice((-1.0, 1.0))
                DRV.yaw += salto
                choque_regs.append((lo, salto))
                p1_pend.append([lo, lo + 10000])
        DRV.yaw += RNG.gauss(0.0, 0.05)

        if "ESTRES_DEBUG" in os.environ and t >= 136000 and k % 25 == 0:
            A3M = MOD["arma3_curvas"]
            print("DBG t=%.1f modo=%s endgame=%s retorno_on=%s gyro_en=%s "
                  "dist=%.1f base=(%.2f %.2f) tgt=%.1f yaw=%.1f V=%.2f "
                  "Y1=%.2f X1=%.2f suav_v=%.2f suav_g=%.2f cmd=(%.2f %.2f) e=(%.2f %.2f)"
                  % (t / 1000.0, mando.nombre_modo(), arma5.is_endgame(),
                     arma5.retorno_on, gyro.enabled, arma5.distancia_al_hogar(),
                     gyro.base_l, gyro.base_r, gyro.get_target(),
                     SIM.IMU.get_yaw(), A5.V_RETORNO,
                     pad.axes[1], pad.axes[0],
                     A3M.suav_avance.v, A3M.suav_giro.v,
                     tb._cmd_l, tb._cmd_r,
                     tb._izq.e, tb._der.e))

        # ---------- armas (mismo orden que en la placa) ----------
        mando._paso()
        gyro._tick()
        tb.paso()
        arma5._odometria()
        arma5._logica_endgame()
        DRV.paso(0.02)

        # ---------- metricas P2 ----------
        if mando._modo in (MAIN.RECTO, MAIN.PARADO) and gyro.enabled:
            en_ventana_choque = any(lo - 200 <= t <= lo + 6000 for lo, _ in choque_regs)
            if not en_ventana_choque:
                e = abs(gyro.get_error())
                if e > max_err:
                    max_err = e

        # ---------- metricas P1 ----------
        atasco_vigente = any(lo - 200 <= t <= lo + dur + 2000 for lo, dur, _ in atascos)
        if "ESTRES_DEBUG" in os.environ:
            for lo, _d in choque_regs:
                if lo <= t <= lo + 12000 and k % 25 == 0:
                    print("P1DBG t=%.1f modo=%s err=%.2f base=(%.2f %.2f) "
                          "tgt=%.1f yaw=%.1f atascos_vig=%s en_giro_win=%s"
                          % (t / 1000.0, mando.nombre_modo(), gyro.get_error(),
                             gyro.base_l, gyro.base_r, gyro.get_target(),
                             SIM.IMU.get_yaw(), atasco_vigente,
                             t_giro - 1500 <= t <= t_giro + 6500))
        vivos = []
        for lo, deadline in p1_pend:
            if t < deadline or atasco_vigente:
                vivos.append((lo, deadline))
                continue
            if mando._modo in (MAIN.RECTO, MAIN.PARADO) and gyro.enabled:
                e = abs(gyro.get_error())
                if e > 3.0:
                    fallos.append("P1: choque t=%.1f err residuo %.1f" % (lo / 1000.0, e))
            elif t < deadline + 5000:
                vivos.append((lo, deadline))
        p1_pend = vivos

    # ---------------- cierres ----------------
    dist = arma5.distancia_al_hogar()
    clavado = tb.clavado or (abs(DRV.LEFT.rpm) < 1.5 and abs(DRV.RIGHT.rpm) < 1.5)
    en_zona = dist <= A5.TOLERANCIA_CM and clavado
    if not en_zona:
        fallos.append("P3: final dist=%.1f clavado=%s (ejes %s/%s, cmd %.2f/%.2f, "
                      "rpm %.2f/%.2f, en_casa=%s)"
                      % (dist, clavado, tb.estado_izq, tb.estado_der,
                         tb._cmd_l, tb._cmd_r,
                         DRV.LEFT.rpm, DRV.RIGHT.rpm, arma5._en_casa))
    if max_err > 12.0:
        fallos.append("P2: err maximo de crucero %.1f" % max_err)

    return {"seed": seed, "en_zona": en_zona, "dist": dist,
            "max_err": max_err, "fallos": fallos,
            "bateria": SIM.BOARD.voltage_scale, "bias": bias,
            "choques": len(choque_regs), "atascos": len(atascos)}


def estres(n=30):
    print("== BATERIA DE ESTRES: %d partidas aleatorias (mando fisico virtual) ==" % n)
    malas = []
    for i in range(n):
        MOD = recargar()
        r = nueva_partida(1000 + i * 17, MOD)
        marca = "OK  " if (r["en_zona"] and not r["fallos"]) else "MALA"
        print("partida %2d | %s | fin=%5.1f cm | err max=%5.2f | bat=%.2f | "
              "bias=%.2f | choques=%d atascos=%d%s"
              % (i, marca, r["dist"], r["max_err"], r["bateria"], r["bias"],
                 r["choques"], r["atascos"],
                 (" | " + "; ".join(r["fallos"])) if r["fallos"] else ""))
        if marca == "MALA":
            malas.append(r)
    print()
    print("RESULTADO: %d/%d partidas aprobadas" % (n - len(malas), n))
    if malas:
        print("Detalle de fallas:")
        for r in malas:
            for f in r["fallos"]:
                print("  - partida %d: %s" % (r["seed"], f))
    return malas


if __name__ == "__main__":
    estres(30)
