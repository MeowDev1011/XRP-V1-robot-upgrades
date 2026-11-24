# Banco de verificacion en PC (no corre en la placa).
# Simula XRPLib + uasyncio y pone a prueba la matematica
# de las 5 armas con una planta fisica simulada del XRP.
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

# planta fisica fake del XRP
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
        # yaw responde a la diferencia de esfuerzos (r-l -> CCW)
        self.yaw += (self.eff_r - self.eff_l) * 130.0 * dt
        # ruedas arrancan solas con esfuerzo bajo (friccion simple)
        ganancia = 20.0
        self.l += (self.eff_l * ganancia - self.l) * min(1.0, dt * 8)
        self.r += (self.eff_r * ganancia - self.r) * min(1.0, dt * 8)

    # --- senales para XRPLib ---
    def pos_cm(self, rpm):
        return rpm * math.pi * 6.0 / 60.0  # cm/s acumulados abajo

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

faltas = []

def check(nombre, cond, detalle=""):
    estado = "OK " if cond else "FALLA"
    print("[%s] %s %s" % (estado, nombre, detalle))
    if not cond:
        faltas.append(nombre)

# ---------------- pruebas ----------------
import arma1_gyro_lock as a1
import arma2_torque_boost as a2
import arma3_curvas as a3
import arma4_traccion as a4
import arma5_endgame as a5

# ARMA 1: PID acotado, integral solo en zona, salida con limites
a1.gyro_lock.pid.reset()
u = a1.gyro_lock.pid.update(10.0, 0.02)
check("A1 salida saturada", abs(u - 0.5) < 1e-6, "u=%.3f" % u)
a1.gyro_lock.pid.reset()
u = a1.gyro_lock.pid.update(3.0, 0.02)
check("A1 integral actua en zona", u > a1.KP * 3.0, "u=%.3f" % u)
a1.gyro_lock.pid.reset()
u = a1.gyro_lock.pid.update(40.0, 0.02)
check("A1 integral silencio fuera de zona", abs(u - 0.5) < 1e-6, "u=%.3f" % u)
check("A1 wrap", abs(a1._wrap180(190) - (-170)) < 1e-9)

# ARMA 2: atasco detectado, boost escala y libera
a2.torque_boost.enable()
for _ in range(40):
    l, r = a2.torque_boost.feed(0.5, 0.5)
check("A2 boost sube en atasco", a2.torque_boost.boost_l > 0.1,
      "boost=%.3f" % a2.torque_boost.boost_l)
planta.l = 19.0                       # rueda libre: rpm esperadas
for _ in range(30):
    l, r = a2.torque_boost.feed(0.5, 0.5)
check("A2 boost se libera", a2.torque_boost.boost_l < 0.05,
      "boost=%.3f" % a2.torque_boost.boost_l)
a2.torque_boost.disable()

# ARMA 3: curva cubica: propiedades y redondeo
check("A3 forma(1)==1", abs(a3.forma(1.0) - 1.0) < 1e-9)
check("A3 forma(-1)==-1", abs(a3.forma(-1.0) + 1.0) < 1e-9)
check("A3 fina cerca de cero", abs(a3.forma(0.1)) < 0.05,
      "y=%.4f" % a3.forma(0.1))
pasa = True
for x in [0.2, 0.4, 0.6, 0.8]:
    if abs(a3.invertida(a3.forma(x)) - x) > 0.02:
        pasa = False
check("A3 inversa consistente", pasa)
s = a3.Suavizador(slew=10.0)
v = 0.0
for _ in range(3):
    v = s.update(1.0, 0.02)
check("A3 rampa limita", v < 1.0, "v=%.3f" % v)

# ARMA 4: rampa + frenado activo con brake() real
eje = a4._Eje(drivetrain.left_motor)
eje.e = 0.0
for _ in range(3):
    e = eje.step(0.5)
check("A4 rampa suave al arrancar", 0.0 < e < 0.5, "e=%.3f" % e)
planta.l = 40.0
e = eje.step(0.0)
check("A4 pulso inverso", e < -0.2, "e=%.3f" % e)
planta.l = 1.0
eje.step(0.0)
check("A4 clava con brake", planta.brakes > 0)

# ARMA 5: reloj, odometria y endgame
a5.arma5.iniciar_partida()
a5.arma5.conectar(a1.gyro_lock)
planta.l = planta.r = 20.0             # avanza recto
for _ in range(50):
    a5.arma5._odometria()
x, y, th = a5.arma5.pose()
check("A5 avanza en +X", x > 5.0 and abs(y) < 0.5, "x=%.1f y=%.1f" % (x, y))
a5.arma5._t0 = _ticks() - 131000
check("A5 antes de endgame (19 s rest.)", not a5.arma5.is_endgame())
a5.arma5._t0 = _ticks() - 139000
check("A5 endgame activo", a5.arma5.is_endgame())
a5.arma5.modo_retorno(True)
a1.gyro_lock.set_target_here()
a1.gyro_lock.enable()
a5.arma5._logica_endgame()
check("A5 reintegra rumbo vivo", abs(a1.gyro_lock.get_error()) < 20.0,
      "err=%.1f" % a1.gyro_lock.get_error())

print()
if faltas:
    print("FALLAS:", faltas)
    sys.exit(1)
print("TODAS LAS PRUEBAS PASAN (%d/12)" % 12)
