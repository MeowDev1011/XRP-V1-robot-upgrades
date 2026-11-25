# PC verification bench (does not run on the board).
# It simulates XRPLib + uasyncio and tests the math of the
# 5 weapons against a simulated physical plant of the XRP.
import sys
import types
import asyncio as _asyncio
import time as _realtime

# ---------------- stubs ----------------
uasyncio = types.ModuleType("uasyncio")

async def _sleep_ms(ms):
    await _asyncio.sleep(ms / 1000.0)

def _ticks():
    return int(_realtime.time() * 1000)

def _ticks_add(t, d):
    return t + d

def _ticks_diff(a, b):
    return a - b

def _create_task(coro):
    return _asyncio.get_event_loop().create_task(coro)

uasyncio.sleep_ms = _sleep_ms
uasyncio.create_task = _create_task
sys.modules["uasyncio"] = uasyncio

fake_time = types.ModuleType("time")
fake_time.ticks_ms = _ticks
fake_time.ticks_add = _ticks_add
fake_time.ticks_diff = _ticks_diff
sys.modules["time"] = fake_time

# fake physical plant of the XRP
class Planta:
    def __init__(self):
        self.l = 0.0
        self.r = 0.0
        self.eff_l = 0.0
        self.eff_r = 0.0
        self.yaw = 0.0
        self.last = _ticks()
        self.brakes = 0

    def step(self):
        now = _ticks()
        dt = (now - self.last) / 1000.0
        self.last = now
        # yaw responds to the effort difference (r-l -> CCW)
        self.yaw += (self.eff_r - self.eff_l) * 130.0 * dt
        # wheels start moving on their own with low effort (simple friction)
        gain = 20.0
        self.l += (self.eff_l * gain - self.l) * min(1.0, dt * 8)
        self.r += (self.eff_r * gain - self.r) * min(1.0, dt * 8)

    # --- signals for XRPLib ---
    def pos_cm(self, rpm):
        return rpm * math.pi * 6.0 / 60.0  # accumulated cm/s down here

import math
planta = Planta()

xrplib = types.ModuleType("XRPLib")
defaults = types.ModuleType("XRPLib.defaults")

class _Motor:
    def get_speed(self):
        return planta.l

    def brake(self):
        planta.brakes += 1

class _DT:
    def set_effort(self, l, r):
        planta.eff_l, planta.eff_r = l, r
        planta.step()

    left_motor = _Motor()
    right_motor = _Motor()
drivetrain = _DT()
drivetrain.get_left_encoder_position = lambda: planta.l * (3.0 * 0.314)
drivetrain.get_right_encoder_position = lambda: planta.r * (3.0 * 0.314)

class _IMU:
    def get_yaw(self):
        return planta.yaw

    def is_connected(self):
        return True

    def calibrate(self, t=1):
        pass

    def reset_yaw(self):
        planta.yaw = 0.0

imu = _IMU()

class _Board:
    voltage_scale = 1.0
    def led_blink(self, hz):
        pass

    def is_button_pressed(self):
        return False

board = _Board()

class _RF:
    def distance(self):
        return 100.0

rangefinder = _RF()

defaults.drivetrain = drivetrain
defaults.imu = imu
defaults.board = board
defaults.rangefinder = rangefinder
defaults.left_motor = drivetrain.left_motor
defaults.right_motor = drivetrain.right_motor
sys.modules["XRPLib"] = xrplib
sys.modules["XRPLib.defaults"] = defaults

faults = []

def check(nombre, cond, detalle=""):
    estado = "OK " if cond else "FAIL"
    print("[%s] %s %s" % (estado, nombre, detalle))
    if not cond:
        faults.append(nombre)

# ---------------- tests ----------------
import weapon1_gyro_lock as a1
import weapon2_torque_boost as a2
import weapon3_curves as a3
import weapon4_traction as a4
import weapon5_endgame as a5

# WEAPON 1: bounded PID, integral only in zone, limited output
a1.gyro_lock.pid.reset()
u = a1.gyro_lock.pid.update(10.0, 0.02)
check("A1 saturated output", abs(u - 0.5) < 1e-6, "u=%.3f" % u)
a1.gyro_lock.pid.reset()
u = a1.gyro_lock.pid.update(3.0, 0.02)
check("A1 integral acts in zone", u > a1.KP * 3.0, "u=%.3f" % u)
a1.gyro_lock.pid.reset()
u = a1.gyro_lock.pid.update(40.0, 0.02)
check("A1 integral silent out of zone", abs(u - 0.5) < 1e-6, "u=%.3f" % u)
check("A1 wrap", abs(a1._wrap180(190) - (-170)) < 1e-9)

# WEAPON 2: stall detected, boost scales and releases
a2.torque_boost.enable()
for _ in range(40):
    l, r = a2.torque_boost.feed(0.5, 0.5)
check("A2 boost climbs on stall", a2.torque_boost.boost_l > 0.1,
      "boost=%.3f" % a2.torque_boost.boost_l)
planta.l = 19.0                       # free wheel: expected rpm
for _ in range(30):
    l, r = a2.torque_boost.feed(0.5, 0.5)
check("A2 boost releases", a2.torque_boost.boost_l < 0.05,
      "boost=%.3f" % a2.torque_boost.boost_l)
a2.torque_boost.disable()

# WEAPON 3: cubic curve: properties and round-trip
check("A3 curve(1)==1", abs(a3.curve(1.0) - 1.0) < 1e-9)
check("A3 curve(-1)==-1", abs(a3.curve(-1.0) + 1.0) < 1e-9)
check("A3 fine near zero", abs(a3.curve(0.1)) < 0.05,
      "y=%.4f" % a3.curve(0.1))
pasa = True
for x in [0.2, 0.4, 0.6, 0.8]:
    if abs(a3.invert(a3.curve(x)) - x) > 0.02:
        pasa = False
check("A3 inverse consistent", pasa)
s = a3.SlewRamp(slew=10.0)
v = 0.0
for _ in range(3):
    v = s.update(1.0, 0.02)
check("A3 ramp limits", v < 1.0, "v=%.3f" % v)

# WEAPON 4: ramp + active braking with real brake()
axis = a4._Axis(drivetrain.left_motor)
axis.e = 0.0
for _ in range(3):
    e = axis.step(0.5)
check("A4 soft ramp on start", 0.0 < e < 0.5, "e=%.3f" % e)
planta.l = 40.0
e = axis.step(0.0)
check("A4 inverse pulse", e < -0.2, "e=%.3f" % e)
planta.l = 1.0
axis.step(0.0)
check("A4 nails with brake", planta.brakes > 0)

# WEAPON 5: clock, odometry and endgame
a5.endgame.start_match()
a5.endgame.connect(a1.gyro_lock)
planta.l = planta.r = 20.0             # drives straight
for _ in range(50):
    a5.endgame._odometry()
x, y, th = a5.endgame.pose()
check("A5 advances on +X", x > 5.0 and abs(y) < 0.5, "x=%.1f y=%.1f" % (x, y))
a5.endgame._t0 = _ticks() - 131000
check("A5 before endgame (19 s left)", not a5.endgame.is_endgame())
a5.endgame._t0 = _ticks() - 139000
check("A5 endgame active", a5.endgame.is_endgame())
a5.endgame.set_return(True)
a1.gyro_lock.set_target_here()
a1.gyro_lock.enable()
a5.endgame._endgame_logic()
check("A5 reintroduces live heading", abs(a1.gyro_lock.get_error()) < 20.0,
      "err=%.1f" % a1.gyro_lock.get_error())

print()
if faults:
    print("FAILURES:", faults)
    sys.exit(1)
print("ALL TESTS PASS (%d/12)" % 12)
