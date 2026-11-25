# =========================================================
# VIRTUAL XRP IRON ACRES ROBOT - Team Robots Legends (FUSAMO)
# ---------------------------------------------------------
# Pure-Python simulator. Runs on PC (python3) or on a PHONE
# with the free Pydroid 3 app (Android).
# It loads the team's REAL files UNMODIFIED:
#   piloto_gamepad.py + arma1..arma5
# It replaces XRPLib with a simulated physical plant (inertia,
# static friction, IMU drift, stalls, crashes) and a VIRTUAL
# GAMEPAD "pressed" by a simulated human pilot.
# The game runs through the gamepad EXACTLY as in the real
# match: stick axes -> curves -> weapons -> motors.
#
# USAGE: python3 simulador_xrp.py
# (the arma*.py, piloto_gamepad.py and this file in the same
#  folder)
# =========================================================
import sys
import types
import math

# ---------------------------------------------------------
# 1) Inject virtual uasyncio, time, micropython and
#    XRPLib.gamepad BEFORE importing the pilot and weapons
# ---------------------------------------------------------
class RelojVirtual:
    def __init__(self):
        self.t = 0

    def ticks_ms(self):
        return self.t

    def avanzar(self, ms):
        self.t += ms

RELOJ = RelojVirtual()

uasyncio_stub = types.ModuleType("uasyncio")

async def _sleep_ms(ms):
    raise RuntimeError("the simulator advances in steps, no real waits")

uasyncio_stub.sleep_ms = _sleep_ms
uasyncio_stub.create_task = lambda coro: coro.close()
sys.modules["uasyncio"] = uasyncio_stub

import time as _time_real

time_stub = types.ModuleType("time")
time_stub.__dict__.update(vars(_time_real))
time_stub.ticks_ms = RELOJ.ticks_ms
time_stub.ticks_add = lambda a, b: a + b
time_stub.ticks_diff = lambda a, b: a - b
sys.modules["time"] = time_stub

micropython_stub = types.ModuleType("micropython")
micropython_stub.const = lambda x: x
sys.modules["micropython"] = micropython_stub

# ---------------------------------------------------------
# 2) Simulated physical plant of the XRP (replaces XRPLib)
# ---------------------------------------------------------
RUEDA_DIAM_CM = 6.0
TRACK_CM = 15.5
RPM_A_CM_S = math.pi * RUEDA_DIAM_CM / 60.0
KW = 44.0            # rpm at effort 1.0
TAU = 0.14           # motor inertia (s)
KS = 0.12            # static: minimum effort to move
BIAS_IMU_CS = 0.05   # IMU drift (deg/s)

class RuedaSim:
    def __init__(self):
        self.rpm = 0.0
        self.effort = 0.0
        self.pos_cm = 0.0
        self.atascada = False

    def paso(self, dt_s):
        if self.atascada:
            self.rpm *= max(0.0, 1.0 - dt_s * 15.0)
            return
        if abs(self.effort) < KS and abs(self.rpm) < 1.0:
            self.rpm = 0.0
            return
        objetivo = self.effort * KW
        self.rpm += (objetivo - self.rpm) * (dt_s / TAU)
        self.pos_cm += self.rpm * RPM_A_CM_S * dt_s

class DRIVETRAIN:
    LEFT = RuedaSim()
    RIGHT = RuedaSim()
    yaw = 0.0
    fuente = "inactiva"

    @classmethod
    def set_effort(cls, l, r):
        if abs(l) > 1e-9 or abs(r) > 1e-9:
            cls.fuente = "activa"
        cls.LEFT.effort = l
        cls.RIGHT.effort = r

    @classmethod
    def stop(cls):
        cls.set_effort(0.0, 0.0)
        cls.fuente = "parado"

    @classmethod
    def paso(cls, dt_s):
        cls.LEFT.paso(dt_s)
        cls.RIGHT.paso(dt_s)
        v_r = cls.RIGHT.rpm * RPM_A_CM_S
        v_l = cls.LEFT.rpm * RPM_A_CM_S
        cls.yaw += math.degrees((v_r - v_l) / TRACK_CM * dt_s)
        cls.yaw += BIAS_IMU_CS * dt_s

    @classmethod
    def get_left_encoder_position(cls):
        return cls.LEFT.pos_cm

    @classmethod
    def get_right_encoder_position(cls):
        return cls.RIGHT.pos_cm

class LEFT_MOTOR:
    @staticmethod
    def get_speed():
        return DRIVETRAIN.LEFT.rpm
    @staticmethod
    def brake():
        DRIVETRAIN.LEFT.rpm = 0.0

class RIGHT_MOTOR:
    @staticmethod
    def get_speed():
        return DRIVETRAIN.RIGHT.rpm
    @staticmethod
    def brake():
        DRIVETRAIN.RIGHT.rpm = 0.0

class IMU:
    connected = True
    @staticmethod
    def get_yaw():
        return DRIVETRAIN.yaw
    @staticmethod
    def is_connected():
        return IMU.connected
    @staticmethod
    def calibrate(t=1.0):
        pass
    @staticmethod
    def reset_yaw():
        DRIVETRAIN.yaw = 0.0

class BOARD:
    voltage_scale = 1.0
    @staticmethod
    def led_blink(hz):
        print("   [LED: ENDGAME, blinking %s Hz]" % hz)

class RANGEFINDER:
    dist = 300.0
    @staticmethod
    def distance():
        return RANGEFINDER.dist

XRPLib = types.ModuleType("XRPLib")
DEFAULTS = types.ModuleType("XRPLib.defaults")
DEFAULTS.drivetrain = DRIVETRAIN
DEFAULTS.left_motor = LEFT_MOTOR
DEFAULTS.right_motor = RIGHT_MOTOR
DEFAULTS.imu = IMU
DEFAULTS.board = BOARD
DEFAULTS.rangefinder = RANGEFINDER
sys.modules["XRPLib"] = XRPLib
sys.modules["XRPLib.defaults"] = DEFAULTS

# --------- VIRTUAL GAMEPAD (like the physical one, via XPP) ---------
_BOTONES = ["BUTTON_A", "BUTTON_B", "BUTTON_X", "BUTTON_Y",
            "BUMPER_L", "BUMPER_R", "TRIGGER_L", "TRIGGER_R",
            "BACK", "START", "DPAD_UP", "DPAD_DN", "DPAD_L", "DPAD_R"]

class GamepadSim:
    X1, Y1, X2, Y2 = 0, 1, 2, 3
    BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y = 4, 5, 6, 7
    BUMPER_L, BUMPER_R = 8, 9
    TRIGGER_L, TRIGGER_R = 10, 11
    BACK, START = 12, 13
    DPAD_UP, DPAD_DN, DPAD_L, DPAD_R = 14, 15, 16, 17

    _SINGLETON = None

    @classmethod
    def get_default_gamepad(cls):
        if cls._SINGLETON is None:
            cls._SINGLETON = cls()
        return cls._SINGLETON

    @classmethod
    def nueva(cls):
        if cls._SINGLETON is None:
            cls._SINGLETON = cls()
        g = cls._SINGLETON
        g.axes = [0.0, 0.0, 0.0, 0.0]
        g.botones = [0] * len(_BOTONES)
        return g

    def __init__(self):
        self.axes = [0.0] * 4
        self.botones = [0] * len(_BOTONES)

    def start(self):
        pass

    def stop(self):
        pass

    def get_value(self, index):
        if 0 <= index < 4:
            return self.axes[index]
        return 0.0

    def is_button_pressed(self, index):
        if 4 <= index < 4 + len(_BOTONES):
            return self.botones[index - 4] > 0
        return False

gp_module = types.ModuleType("XRPLib.gamepad")
gp_module.Gamepad = GamepadSim
XRPLib.gamepad = gp_module
sys.modules["XRPLib.gamepad"] = gp_module

# ---------------------------------------------------------
# 3) Import the REAL stick console and the 5 weapons
#    (without touching them)
# ---------------------------------------------------------
import arma1_gyro_lock as A1
import arma2_torque_boost as A2
import arma3_curvas as A3
import arma4_traccion as A4
import arma5_endgame as A5
import piloto_gamepad as MAIN

# ---------- TEAM PARAMETERS (overridable, as on the track) ----------
A5.V_RETORNO = 0.85     # the return is only viable if home is <= ~150 cm away
DT_S = 0.02
EVENTOS = []

def _log(linea):
    EVENTOS.append(linea)
    print("   >> " + linea)

def cablear():
    tb = A4.traction_brake

    def gancho(l, r):
        l, r = A2.torque_boost.feed(l, r)
        tb.set_command(l, r)

    A1.gyro_lock.attach(gancho)
    return tb

class ManosVirtuales:
    """The human pilot 'presses' the physical gamepad at moments
    of the match. Everything else is done by the weapons alone."""

    def __init__(self):
        self.pad = GamepadSim.get_default_gamepad()
        self.prev_modo = "STARTUP"
        self._rumbo_deseado = 0.0
        self._girando = False
        self._max_dist = 0.0

    def presentar(self):
        self.pad.botones[GamepadSim.START - 4] = 1

    def soltar_start(self):
        self.pad.botones[GamepadSim.START - 4] = 0

    def ordena(self, t_ms):
        pad = self.pad

        if 2000 <= t_ms < 2050:
            pad.axes[GamepadSim.Y1] = 0.45
            _log("t=%5.1f s PILOT: pushes Y1 (assisted straight drive)" % (t_ms / 1000.0))
        if 18000 <= t_ms < 18500:
            pad.axes[GamepadSim.Y1] = 0.0
            _log("t=%5.1f s PILOT: releases sticks (active braking + hold)" % (t_ms / 1000.0))
        if 30000 <= t_ms < 30500:
            pad.axes[GamepadSim.Y1] = 0.7
            _log("t=%5.1f s PILOT: pushes Y1 hard (with a stalled wheel)" % (t_ms / 1000.0))
        if 40000 <= t_ms < 40050:
            pad.axes[GamepadSim.Y1] = 0.45
        if 52000 <= t_ms < 52050:
            pad.axes[GamepadSim.Y1] = 0.0
            _log("t=%5.1f s PILOT: full stop " % (t_ms / 1000.0))
        if 62000 <= t_ms < 62020:
            pad.axes[GamepadSim.X1] = 1.0
            self._rumbo_deseado = IMU.get_yaw() + 180.0
            self._girando = True
            _log("t=%5.1f s PILOT: half turn with stick X1" % (t_ms / 1000.0))
        if self._girando:
            if abs(((self._rumbo_deseado - IMU.get_yaw()) + 180.0) % 360.0 - 180.0) > 4.0:
                pad.axes[GamepadSim.X1] = 1.0     # keeps turning (manual pilot)
            else:
                pad.axes[GamepadSim.X1] = 0.0     # releases the stick: gyro recaptures
                self._girando = False
                _log("t=%5.1f s PILOT: completes the turn, releases stick" % (t_ms / 1000.0))
        if (not self._girando) and 64000 <= t_ms < 64500:
            pad.axes[GamepadSim.Y1] = 0.4         # drives toward home (already facing home)
            _log("t=%5.1f s PILOT: drives toward home at %.0f cm" % (t_ms / 1000.0, A5.arma5.distancia_al_hogar()))
        self._max_dist = max(self._max_dist, A5.arma5.distancia_al_hogar())
        if (not self._girando) and pad.axes[GamepadSim.Y1] > 0.0:
            if self._max_dist >= 90.0 and A5.arma5.distancia_al_hogar() <= 80.0:
                pad.axes[GamepadSim.Y1] = 0.0
                _log("t=%5.1f s PILOT: stops at %.0f cm from home (waits for ENDGAME)"
                     % (t_ms / 1000.0, A5.arma5.distancia_al_hogar()))

        if MAIN.piloto_mando.nombre_modo() != self.prev_modo:
            self.prev_modo = MAIN.piloto_mando.nombre_modo()
            _log("t=%5.1f s MODE -> %s" % (t_ms / 1000.0, self.prev_modo))

# ---------------------------------------------------------
# 4) Match run: 150 s in 20 ms steps (instantaneous)
# ---------------------------------------------------------
def partida():
    print("== VIRTUAL IRON ACRES MATCH (150 s, virtual physical sticks) ==")
    A5.imu.calibrate(1.0)
    A5.imu.reset_yaw()
    tb = cablear()
    tb.enable()
    A2.torque_boost.enable()
    arma5 = A5.arma5
    arma5.conectar(A1.gyro_lock)
    arma5.modo_retorno(True)          # closing assist (BACK toggles it)
    armas_listas = False
    pad = GamepadSim.nueva()
    MAIN.piloto_mando.conectar(pad)
    manos = ManosVirtuales()

    tray = []
    prev_boost = 0.0
    prev_casa = False
    pasos = int(150000 / 20)
    for k in range(pasos):
        RELOJ.avanzar(20)
        t_ms = RELOJ.ticks_ms()

        if not armas_listas and t_ms >= 400:
            manos.presentar()
            MAIN.piloto_mando._paso()   # START: arms clock + home + heading
            manos.soltar_start()
            armas_listas = True
            _log("t=%5.1f s PILOT: START pressed (A5 clock armed)"
                 % (t_ms / 1000.0,))
            continue

        manos.ordena(t_ms)
        MAIN.piloto_mando._paso()    # stick loop, same as on the board
        A1.gyro_lock._tick()
        tb.paso()
        arma5._odometria()
        arma5._logica_endgame()
        DRIVETRAIN.paso(DT_S)

        b = A2.torque_boost.boost_l + A2.torque_boost.boost_r
        if prev_boost == 0.0 and b > 0.02:
            _log("t=%5.1f s WEAPON 2: BOOST ACTIVE [L=%.2f R=%.2f]"
                 % (t_ms / 1000.0, A2.torque_boost.boost_l, A2.torque_boost.boost_r))
        prev_boost = b

        en_casa = arma5.distancia_al_hogar() <= A5.TOLERANCIA_CM and tb.clavado
        if not prev_casa and en_casa and t_ms > 5000:
            _log("t=%5.1f s WEAPON 5: AUTOMATIC HOME ARRIVAL, nailed until the buzzer"
                 % (t_ms / 1000.0))
        prev_casa = en_casa

        if k % 250 == 0:
            x, y, th = arma5.pose()
            mando = MAIN.piloto_mando
            print("t=%6.1f s | yaw=%7.2f | pos=(%6.1f, %6.1f) | err=%6.2f | "
                  "boost=[%.2f %.2f] | axis=%s/%s | mode=%s | home=%5.1f cm" % (
                      t_ms / 1000.0, IMU.get_yaw(), x, y,
                      A1.gyro_lock.get_error(),
                      A2.torque_boost.boost_l, A2.torque_boost.boost_r,
                      tb.estado_izq, tb.estado_der,
                      mando.nombre_modo(),
                      arma5.distancia_al_hogar()))
        if k % 50 == 0:
            x, y, th = arma5.pose()
            tray.append((t_ms / 1000.0, x, y))
        if arma5.ms_restantes() <= 0:
            break

    DRIVETRAIN.stop()
    print()
    print("== MATCH SUMMARY ==")
    for linea in EVENTOS:
        print(" ", linea)
    dist = arma5.distancia_al_hogar()
    print("  Final distance to home: %.1f cm -> %s"
          % (dist,
             "IN ZONE (closing score)" if dist <= A5.TOLERANCIA_CM else "OUT OF ZONE"))
    print()
    plot(tray, arma5)

def plot(tray, arma5):
    xs = [t[1] for t in tray]
    ys = [t[2] for t in tray]
    min_x, max_x = min(xs + [0.0]) - 20.0, max(xs + [0.0]) + 20.0
    min_y, max_y = min(ys + [0.0]) - 20.0, max(ys + [0.0]) + 20.0
    W, H = 72, 26

    def px(x):
        return min(W - 1, max(0, int((x - min_x) / (max_x - min_x) * (W - 1))))

    def py(y):
        return min(H - 1, max(0, int((y - min_y) / (max_y - min_y) * (H - 1))))

    lienzo = [[" "] * W for _ in range(H)]
    lienzo[H - 1 - py(arma5._home_y)][px(arma5._home_x)] = "H"
    for t, x, y in tray:
        cx, cy = px(x), py(y)
        lienzo[H - 1 - cy][cx] = "."
    print("TRAJECTORY (H = home/start zone; X %d..%d cm, Y %d..%d cm)"
          % (min_x, max_x, min_y, max_y))
    for fila in lienzo:
        print("".join(fila))

if __name__ == "__main__":
    partida()
