# =========================================================
# VIRTUAL XRP IRON ACRES ROBOT - Team Robots Legends (FUSAMO)
# ---------------------------------------------------------
# Pure-Python simulator. Runs on PC (python3) or on a PHONE
# with the free Pydroid 3 app (Android).
# It loads the team's REAL files UNMODIFIED:
#   pilot_gamepad.py + arma1..endgame
# It replaces XRPLib with a simulated physical plant (inertia,
# static friction, IMU drift, stalls, crashes) and a VIRTUAL
# GAMEPAD "pressed" by a simulated human pilot.
# The game runs through the gamepad EXACTLY as in the real
# match: stick axes -> curves -> weapons -> motors.
#
# USAGE: python3 simulador_xrp.py
# (the weapon*.py, pilot_gamepad.py and this file in the same
#  folder)
# =========================================================
import sys
import types
import math

# ---------------------------------------------------------
# 1) Inject virtual uasyncio, time, micropython and
#    XRPLib.gamepad BEFORE importing the pilot and weapons
# ---------------------------------------------------------
class VirtualClock:
    def __init__(self):
        self.t = 0

    def ticks_ms(self):
        return self.t

    def advance(self, ms):
        self.t += ms

CLOCK = VirtualClock()

uasyncio_stub = types.ModuleType("uasyncio")

async def _sleep_ms(ms):
    raise RuntimeError("the simulator advances in steps, no real waits")

uasyncio_stub.sleep_ms = _sleep_ms
uasyncio_stub.create_task = lambda coro: coro.close()
sys.modules["uasyncio"] = uasyncio_stub

import time as _time_real

time_stub = types.ModuleType("time")
time_stub.__dict__.update(vars(_time_real))
time_stub.ticks_ms = CLOCK.ticks_ms
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

class WheelSim:
    def __init__(self):
        self.rpm = 0.0
        self.effort = 0.0
        self.pos_cm = 0.0
        self.stalled = False

    def step(self, dt_s):
        if self.stalled:
            self.rpm *= max(0.0, 1.0 - dt_s * 15.0)
            return
        if abs(self.effort) < KS and abs(self.rpm) < 1.0:
            self.rpm = 0.0
            return
        target = self.effort * KW
        self.rpm += (target - self.rpm) * (dt_s / TAU)
        self.pos_cm += self.rpm * RPM_A_CM_S * dt_s

class DRIVETRAIN:
    LEFT = WheelSim()
    RIGHT = WheelSim()
    yaw = 0.0
    source = "idle"

    @classmethod
    def set_effort(cls, l, r):
        if abs(l) > 1e-9 or abs(r) > 1e-9:
            cls.source = "active"
        cls.LEFT.effort = l
        cls.RIGHT.effort = r

    @classmethod
    def stop(cls):
        cls.set_effort(0.0, 0.0)
        cls.source = "stopped"

    @classmethod
    def step(cls, dt_s):
        cls.LEFT.step(dt_s)
        cls.RIGHT.step(dt_s)
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
        g.buttons = [0] * len(_BOTONES)
        return g

    def __init__(self):
        self.axes = [0.0] * 4
        self.buttons = [0] * len(_BOTONES)

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
            return self.buttons[index - 4] > 0
        return False

gp_module = types.ModuleType("XRPLib.gamepad")
gp_module.Gamepad = GamepadSim
XRPLib.gamepad = gp_module
sys.modules["XRPLib.gamepad"] = gp_module

# ---------------------------------------------------------
# 3) Import the REAL stick console and the 5 weapons
#    (without touching them)
# ---------------------------------------------------------
import weapon1_gyro_lock as A1
import weapon2_torque_boost as A2
import weapon3_curves as A3
import weapon4_traction as A4
import weapon5_endgame as A5
import pilot_gamepad as MAIN

# ---------- TEAM PARAMETERS (overridable, as on the track) ----------
A5.V_RETORNO = 0.85     # the return is only viable if home is <= ~150 cm away
DT_S = 0.02
EVENTOS = []

def _log(line):
    EVENTOS.append(line)
    print("   >> " + line)

def wire():
    tb = A4.traction_brake

    def hook(l, r):
        l, r = A2.torque_boost.feed(l, r)
        tb.set_command(l, r)

    A1.gyro_lock.attach(hook)
    return tb

class VirtualHands:
    """The human pilot 'presses' the physical gamepad at moments
    of the match. Everything else is done by the weapons alone."""

    def __init__(self):
        self.pad = GamepadSim.get_default_gamepad()
        self.prev_mode = "STARTUP"
        self._desired_heading = 0.0
        self._turning = False
        self._max_dist = 0.0

    def press_start(self):
        self.pad.buttons[GamepadSim.START - 4] = 1

    def release_start(self):
        self.pad.buttons[GamepadSim.START - 4] = 0

    def drive(self, t_ms):
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
            self._desired_heading = IMU.get_yaw() + 180.0
            self._turning = True
            _log("t=%5.1f s PILOT: half turn with stick X1" % (t_ms / 1000.0))
        if self._turning:
            if abs(((self._desired_heading - IMU.get_yaw()) + 180.0) % 360.0 - 180.0) > 4.0:
                pad.axes[GamepadSim.X1] = 1.0     # keeps turning (manual pilot)
            else:
                pad.axes[GamepadSim.X1] = 0.0     # releases the stick: gyro recaptures
                self._turning = False
                _log("t=%5.1f s PILOT: completes the turn, releases stick" % (t_ms / 1000.0))
        if (not self._turning) and 64000 <= t_ms < 64500:
            pad.axes[GamepadSim.Y1] = 0.4         # drives toward home (already facing home)
            _log("t=%5.1f s PILOT: drives toward home at %.0f cm" % (t_ms / 1000.0, A5.endgame.home_distance()))
        self._max_dist = max(self._max_dist, A5.endgame.home_distance())
        if (not self._turning) and pad.axes[GamepadSim.Y1] > 0.0:
            if self._max_dist >= 90.0 and A5.endgame.home_distance() <= 80.0:
                pad.axes[GamepadSim.Y1] = 0.0
                _log("t=%5.1f s PILOT: stops at %.0f cm from home (waits for ENDGAME)"
                     % (t_ms / 1000.0, A5.endgame.home_distance()))

        if MAIN.pilot_console.mode_name() != self.prev_mode:
            self.prev_mode = MAIN.pilot_console.mode_name()
            _log("t=%5.1f s MODE -> %s" % (t_ms / 1000.0, self.prev_mode))

# ---------------------------------------------------------
# 4) Match run: 150 s in 20 ms steps (instantaneous)
# ---------------------------------------------------------
def match():
    print("== VIRTUAL IRON ACRES MATCH (150 s, virtual physical sticks) ==")
    A5.imu.calibrate(1.0)
    A5.imu.reset_yaw()
    tb = wire()
    tb.enable()
    A2.torque_boost.enable()
    endgame = A5.endgame
    endgame.connect(A1.gyro_lock)
    endgame.set_return(True)          # closing assist (BACK toggles it)
    weapons_ready = False
    pad = GamepadSim.fresh()
    MAIN.pilot_console.connect(pad)
    manos = ManosVirtuales()

    tray = []
    prev_boost = 0.0
    prev_home = False
    steps = int(150000 / 20)
    for k in range(steps):
        CLOCK.advance(20)
        t_ms = CLOCK.ticks_ms()

        if not weapons_ready and t_ms >= 400:
            manos.press_start()
            MAIN.pilot_console._cycle()   # START: arms clock + home + heading
            manos.release_start()
            weapons_ready = True
            _log("t=%5.1f s PILOT: START pressed (A5 clock armed)"
                 % (t_ms / 1000.0,))
            continue

        manos.drive(t_ms)
        MAIN.pilot_console._cycle()    # stick loop, same as on the board
        A1.gyro_lock._tick()
        tb.step()
        endgame._odometry()
        endgame._endgame_logic()
        DRIVETRAIN.step(DT_S)

        b = A2.torque_boost.boost_l + A2.torque_boost.boost_r
        if prev_boost == 0.0 and b > 0.02:
            _log("t=%5.1f s WEAPON 2: BOOST ACTIVE [L=%.2f R=%.2f]"
                 % (t_ms / 1000.0, A2.torque_boost.boost_l, A2.torque_boost.boost_r))
        prev_boost = b

        at_home = endgame.home_distance() <= A5.HOME_TOL_CM and tb.nailed
        if not prev_home and at_home and t_ms > 5000:
            _log("t=%5.1f s WEAPON 5: AUTOMATIC HOME ARRIVAL, nailed until the buzzer"
                 % (t_ms / 1000.0))
        prev_home = at_home

        if k % 250 == 0:
            x, y, th = endgame.pose()
            console = MAIN.pilot_console
            print("t=%6.1f s | yaw=%7.2f | pos=(%6.1f, %6.1f) | err=%6.2f | "
                  "boost=[%.2f %.2f] | axis=%s/%s | mode=%s | home=%5.1f cm" % (
                      t_ms / 1000.0, IMU.get_yaw(), x, y,
                      A1.gyro_lock.get_error(),
                      A2.torque_boost.boost_l, A2.torque_boost.boost_r,
                      tb.state_left, tb.state_right,
                      console.mode_name(),
                      endgame.home_distance()))
        if k % 50 == 0:
            x, y, th = endgame.pose()
            tray.append((t_ms / 1000.0, x, y))
        if endgame.ms_left() <= 0:
            break

    DRIVETRAIN.stop()
    print()
    print("== MATCH SUMMARY ==")
    for line in EVENTOS:
        print(" ", line)
    dist = endgame.home_distance()
    print("  Final distance to home: %.1f cm -> %s"
          % (dist,
             "IN ZONE (closing score)" if dist <= A5.HOME_TOL_CM else "OUT OF ZONE"))
    print()
    plot(tray, endgame)

def plot(tray, endgame):
    xs = [t[1] for t in tray]
    ys = [t[2] for t in tray]
    min_x, max_x = min(xs + [0.0]) - 20.0, max(xs + [0.0]) + 20.0
    min_y, max_y = min(ys + [0.0]) - 20.0, max(ys + [0.0]) + 20.0
    W, H = 72, 26

    def px(x):
        return min(W - 1, max(0, int((x - min_x) / (max_x - min_x) * (W - 1))))

    def py(y):
        return min(H - 1, max(0, int((y - min_y) / (max_y - min_y) * (H - 1))))

    canvas = [[" "] * W for _ in range(H)]
    canvas[H - 1 - py(endgame._home_y)][px(endgame._home_x)] = "H"
    for t, x, y in tray:
        cx, cy = px(x), py(y)
        canvas[H - 1 - cy][cx] = "."
    print("TRAJECTORY (H = home/start zone; X %d..%d cm, Y %d..%d cm)"
          % (min_x, max_x, min_y, max_y))
    for row in canvas:
        print("".join(row))

if __name__ == "__main__":
    match()
