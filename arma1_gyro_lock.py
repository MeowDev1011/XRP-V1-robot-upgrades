# =========================================================
# ARMA 1: AUTOCORRECTOR DE RUMBO Y ANTI-TROMPOS (Gyro-Lock PID)
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# Lazo cerrado de rumbo a 50 Hz contra imu.get_yaw().
# Constantes ancladas al PID de rumbo de fabrica de XRPLib
# (differential_drive.py: kp=0.064, ki=0.12, kd=0.0055,
#  integral_zone=4, max_integral=3).
# ---------------------------------------------------------
# Uso desde bloques XRPCode:
#   from arma1_gyro_lock import gyro_lock
#   gyro_lock.start()                 # una vez al arrancar
#   gyro_lock.engage_straight(0.5)    # recto con rumbo clavado
#   gyro_lock.hold_pose()             # anti-trompo en parado
#   gyro_lock.disable()               # soltar control (giro libre)
#   gyro_lock.set_target(ang)         # reclavar rumbo absoluto
# ---------------------------------------------------------
# Cadena de armas (composicion): gyro_lock.attach(fn) hace que
# los esfuerzos finales pasen por `fn(l, r)` antes del motor.
# =========================================================
import uasyncio as asyncio
import time
from XRPLib.defaults import drivetrain, imu

# ------------------------------------------------------------
# CALIBRACION EN PISTA  (un parametro a la vez, en este orden)
# ------------------------------------------------------------
KP        = 0.064   # [paso 1] esfuerzo por grado de error. Oscila -> baja 30-40%.
KI        = 0.06    # [paso 3] deriva constante. Solo si KP/KD ya son estables.
KD        = 0.0055  # [paso 2] amortigua trompos y choques. Sube si hay rebote.
I_ZONE    = 4.0     # grados: la integral solo acumula dentro de esta banda
MAX_I     = 0.3     # tope del integral (fabrica usa 3, pero con retardo de
                    # rampa+motor provoca caza sostenida +-4 grados: probado
                    # en bateria: MAX_I <= 0.3 elimina la oscilacion)
OUT_LIMIT = 0.5     # techo del esfuerzo de correccion
DEADBAND  = 1.5     # zona muerta en grados: evita temblor con el robot quieto
MIN_EFFORT = 0.14   # fabrica: esfuerzo minimo para que la rueda gire
SIGN      = 1.0     # -1.0 si al corregir el robot se aparta MAS
DT_MS     = 20      # periodo del lazo (50 Hz). La IMU integra a 208 Hz.


def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


class PID:
    """PID espejo del de XRPLib (zona integral + tope integral),
    con derivada sobre la medida para evitar el pico de derivada
    al cambiar de setpoint."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.i = 0.0
        self.prev = None
        self.p = 0.0
        self.d = 0.0

    def update(self, error, dt):
        self.p = KP * error
        if abs(error) <= I_ZONE:
            self.i += error * dt
            self.i = max(-MAX_I, min(MAX_I, self.i))
        else:
            self.i = 0.0
        d = 0.0
        if self.prev is not None and dt > 0:
            d = -KD * (error - self.prev) / dt
        self.prev = error
        self.d = d
        return max(-OUT_LIMIT, min(OUT_LIMIT, self.p + KI * self.i + d))


class GyroLock:
    """Bloqueo continuo de rumbo. Mientras este activo, es el DUENO de los
    motores: no llamar drivetrain.straight()/turn()/set_speed() a la vez."""

    def __init__(self):
        self.pid = PID()
        self.enabled = False
        self.target = 0.0
        self.base_l = 0.0
        self.base_r = 0.0
        self.last_error = 0.0
        self.last_out = 0.0
        self._post = None
        self._task = None

    # ---------------- composicion con otras armas ----------------
    def attach(self, fn):
        """fn(left, right) recibe los esfuerzos finales corregidos y los
        aplica (por ejemplo, el Arma 2). Si no hay gancho, escribe directo."""
        self._post = fn

    # ---------------- API para bloques XRPCode ----------------
    def set_target_here(self):
        self.target = imu.get_yaw()
        self.pid.reset()
        return self.target

    def set_target(self, ang):
        self.target = _wrap180(ang)
        self.pid.reset()
        return self.target

    def get_target(self):
        return self.target

    def get_error(self):
        return self.last_error

    def set_base(self, left, right):
        self.base_l = left
        self.base_r = right

    def enable(self):
        if not self.enabled:
            self.pid.reset()
            self.enabled = True

    def disable(self):
        self.enabled = False
        self.base_l = 0.0
        self.base_r = 0.0
        self.pid.reset()
        if self._post is None:
            drivetrain.set_effort(0.0, 0.0)
        # Con gancho (cadena de armas) NO escribe: el dueno de los
        # motores (Arma 4) decide el paro con su frenado activo.

    def hold_pose(self):
        """Anti-trompo en parado: bloquea el rumbo actual sin avanzar."""
        self.set_target_here()
        self.set_base(0.0, 0.0)
        self.enable()

    def engage_straight(self, speed):
        """Avance recto con el rumbo clavado en el angulo actual."""
        self.set_target_here()
        self.set_base(speed, speed)
        self.enable()

    def start(self):
        """Corre siempre en background a 50 Hz. Idempotente."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self

    # ---------------- lazo no bloqueante ----------------
    async def _run(self):
        next_tick = time.ticks_ms()
        while True:
            next_tick = time.ticks_add(next_tick, DT_MS)
            self._tick()
            delay = time.ticks_diff(next_tick, time.ticks_ms())
            if delay <= 0:
                delay = 1
                next_tick = time.ticks_add(time.ticks_ms(), DT_MS)
            await asyncio.sleep_ms(delay)

    def _tick(self):
        if not self.enabled:
            self.last_error = 0.0
            self.last_out = 0.0
            return
        err = _wrap180(self.target - imu.get_yaw())
        if abs(err) < DEADBAND and self.base_l == 0.0 and self.base_r == 0.0:
            # en hold y dentro de la banda: esfuerzo CERO, sin reset del
            # integral (conserva el trim anti-deriva para cuando salga)
            u = 0.0
            self.pid.prev = err
        else:
            u = self.pid.update(err, DT_MS / 1000.0)
        self.last_error = err
        self.last_out = u
        l = self.base_l - SIGN * u
        r = self.base_r + SIGN * u
        # Con base de avance (piloto pidiendo marchar) se pisa el umbral de
        # fabrica para que ordenes suaves SI muevan el robot. En HOLD (base 0,
        # anti-trompo en parado / llegada a casa) NO hay piso: el esfuerzo
        # natural bajo el rozamiento estatico corrige derivas diminutas sin
        # arrancar pulsos que sacuden al robot del sitio.
        if (self.base_l != 0.0 or self.base_r != 0.0):
            if 0.0 < abs(l) < MIN_EFFORT:
                l = MIN_EFFORT if l > 0 else -MIN_EFFORT
            if 0.0 < abs(r) < MIN_EFFORT:
                r = MIN_EFFORT if r > 0 else -MIN_EFFORT
        if self._post is not None:
            self._post(l, r)
        else:
            drivetrain.set_effort(l, r)


gyro_lock = GyroLock()
