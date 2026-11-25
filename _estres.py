# =========================================================
# STRESS BATTERY - Team Robots Legends (FUSAMO)
# 30 random matches. The pilot plays WITH THE STICKS
# (virtual gamepad + piloto_gamepad: the same code that runs
# on the board) while the plant attacks the robot:
#   - crashes of up to 40 degrees of spin (0 to 3 per match)
#   - physical wheel stalls of 2-5 s (0 to 2, either wheel)
#   - battery between 82% and 100%
#   - IMU drift up to 0.2 deg/s + gaussian noise
# CRITERIA (per match):
#   P1: every crash spin stays < 3 degrees (measured 10 s
#       after the crash, with the Gyro-Lock active)
#   P2: stable heading in cruise (max err < 12 degrees, not
#       counting crash windows nor the pilot's turn)
#   P3: ENDGAME returns home and stays NAILED (<= 6 cm)
#   P4: not a single exception in any match
# USAGE: python3 _estres.py
# =========================================================
import sys
import importlib
import os

import simulador_xrp as SIM          # injects plant + stubs, no match run

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

    # -------- plant at zero + random conditions --------
    SIM.RELOJ.t = 0
    DRV.LEFT = SIM.RuedaSim()
    DRV.RIGHT = SIM.RuedaSim()
    DRV.yaw = 0.0
    DRV.fuente = "inactiva"
    SIM.BOARD.voltage_scale = RNG.uniform(0.82, 1.0)
    bias = RNG.uniform(0.0, 0.2)
    SIM.BIAS_IMU_CS = bias
    pad = GP.nueva()

    # -------- full chain, same as main_partida.py --------
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

    # -------- pilot script (random per seed) --------
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

    # -------- metrics --------
    fallos = []
    max_err = 0.0
    choque_regs = []
    p1_pend = []
    giro_iniciado = False
    giro_terminado = False    # the pilot releases the stick forever after the turn
    objetivo_rumbo = 0.0

    # -------- match (150 s in 20 ms steps) --------
    for k in range(7500):
        SIM.RELOJ.avanzar(20)
        t = SIM.RELOJ.ticks_ms()

        # ---------- pilot with the sticks ----------
        pad.botones[GP.START - 4] = 1 if 400 <= t < 420 else 0

        if not giro_iniciado:
            if t >= t_giro:
                giro_iniciado = True
                objetivo_rumbo = SIM.IMU.get_yaw() + delta_giro
                pad.axes[GP.Y1] = 0.0
                pad.axes[GP.X1] = 1.0 if delta_giro > 0 else -1.0
            elif t >= 2000:
                # drives toward its target distance and releases on arrival
                if arma5.distancia_al_hogar() < dist_objetivo:
                    pad.axes[GP.Y1] = vel
                elif pad.axes[GP.Y1] > 0.0:
                    pad.axes[GP.Y1] = 0.0
        elif not giro_terminado:
            # the pilot turns with stick X1 guided by the IMU
            err_giro = (objetivo_rumbo - SIM.IMU.get_yaw() + 180.0) % 360.0 - 180.0
            if abs(err_giro) > 4.0 and pad.axes[GP.X1] == 0.0:
                pad.axes[GP.X1] = 1.0 if err_giro > 0 else -1.0
            elif abs(err_giro) <= 4.0 and pad.axes[GP.X1] != 0.0:
                pad.axes[GP.X1] = 0.0
                giro_terminado = True

        # ---------- physical events ----------
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

        # ---------- weapons (same order as on the board) ----------
        mando._paso()
        gyro._tick()
        tb.paso()
        arma5._odometria()
        arma5._logica_endgame()
        DRV.paso(0.02)

        # ---------- P2 metrics ----------
        if mando._modo in (MAIN.RECTO, MAIN.PARADO) and gyro.enabled:
            en_ventana_choque = any(lo - 200 <= t <= lo + 6000 for lo, _ in choque_regs)
            if not en_ventana_choque:
                e = abs(gyro.get_error())
                if e > max_err:
                    max_err = e

        # ---------- P1 metrics ----------
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
                    fallos.append("P1: crash t=%.1f residual err %.1f" % (lo / 1000.0, e))
            elif t < deadline + 5000:
                vivos.append((lo, deadline))
        p1_pend = vivos

    # ---------------- closing ----------------
    dist = arma5.distancia_al_hogar()
    clavado = tb.clavado or (abs(DRV.LEFT.rpm) < 1.5 and abs(DRV.RIGHT.rpm) < 1.5)
    en_zona = dist <= A5.TOLERANCIA_CM and clavado
    if not en_zona:
        fallos.append("P3: final dist=%.1f clavado=%s (axes %s/%s, cmd %.2f/%.2f, "
                      "rpm %.2f/%.2f, en_casa=%s)"
                      % (dist, clavado, tb.estado_izq, tb.estado_der,
                         tb._cmd_l, tb._cmd_r,
                         DRV.LEFT.rpm, DRV.RIGHT.rpm, arma5._en_casa))
    if max_err > 12.0:
        fallos.append("P2: max cruise err %.1f" % max_err)

    return {"seed": seed, "en_zona": en_zona, "dist": dist,
            "max_err": max_err, "fallos": fallos,
            "bateria": SIM.BOARD.voltage_scale, "bias": bias,
            "choques": len(choque_regs), "atascos": len(atascos)}


def estres(n=30):
    print("== STRESS BATTERY: %d random matches (virtual physical sticks) ==" % n)
    malas = []
    for i in range(n):
        MOD = recargar()
        r = nueva_partida(1000 + i * 17, MOD)
        marca = "OK  " if (r["en_zona"] and not r["fallos"]) else "BAD"
        print("match %2d | %s | end=%5.1f cm | max err=%5.2f | bat=%.2f | "
              "bias=%.2f | crashes=%d stalls=%d%s"
              % (i, marca, r["dist"], r["max_err"], r["bateria"], r["bias"],
                 r["choques"], r["atascos"],
                 (" | " + "; ".join(r["fallos"])) if r["fallos"] else ""))
        if marca == "BAD":
            malas.append(r)
    print()
    print("RESULT: %d/%d matches approved" % (n - len(malas), n))
    if malas:
        print("Failure detail:")
        for r in malas:
            for f in r["fallos"]:
                print("  - match %d: %s" % (r["seed"], f))
    return malas


if __name__ == "__main__":
    estres(30)
