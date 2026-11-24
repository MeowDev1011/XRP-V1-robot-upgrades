# =========================================================
# ARMA 2: REFUERZO DE TORQUE INTELIGENTE (ANTI-ATASCO)
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# Lazo cerrado por RUEDA: esfuerzo pedido vs. rpm real.
# get_speed() es muestreada cada 20 ms por la propia XRPLib
# (encoded_motor.py: timer de _UPDATE_PERIOD_MS), asi que la
# medicion es gratis y siempre fresca.
# Modelo de friccion del fuente oficial: kS=0.12, kV=0.02.
#   rpm esperadas = (efectivo - kS) / kV
# Si la rueda gira mucho menos de lo esperado durante
# TICKS_CONFIRMAR, es un atasco real: el boost sube escalando
# solo en ESA rueda y se libera en cuanto recupera fluidez.
# ---------------------------------------------------------
# Dos modos:
#   1) Compuesto (recomendado): gyro_lock.attach(arma2.feed)
#      y el ultimo eslabon llama a torque_boost.aplicar().
#   2) Solo: set_command(l, r) + enable() + start().
# =========================================================
import uasyncio as asyncio
import time
from XRPLib.defaults import drivetrain, board, left_motor, right_motor

# ------------------------------------------------------------
# CALIBRACION EN PISTA
# ------------------------------------------------------------
KS             = 0.12   # de fabrica: esfuerzo de "romper el estatico"
KV             = 0.02   # de fabrica: esfuerzo por cada rpm
COMP_BATERIA   = True   # multiplica por board.voltage_scale (torque estable)
STALL_CMD_MIN  = 0.25   # no vigilar atascos por debajo de este esfuerzo
RPM_MIN_FALLO  = 8.0    # velocidad esperada minima para hablar de atasco
RATIO_ATASCO   = 0.4    # atasco si gira < 40% de lo esperado
TICKS_CONFIRMAR = 8     # 8 x 20 ms = 160 ms confirmando atasco (anti-ruido)
BOOST_MAX      = 0.35   # esfuerzo extra maximo por rueda
BOOST_PASO     = 0.012  # sube ~0.6 esfuerzo/seg: fuerte pero sensible
BOOST_FUGA     = 0.05   # liberacion por ciclo al recuperar fluidez
DT_MS          = 20


class _Rueda:
    """Estado de una rueda: boost actual + contador de ciclos de atasco."""

    def __init__(self, motor):
        self.motor = motor
        self.boost = 0.0
        self.ticks = 0

    def step(self, cmd):
        e = abs(cmd)
        if e < STALL_CMD_MIN:
            self.boost = 0.0
            self.ticks = 0
            return cmd
        expected = (e - KS) / KV
        if expected < RPM_MIN_FALLO:
            return cmd
        real = self.motor.get_speed()
        if abs(real) < RATIO_ATASCO * expected:
            self.ticks += 1
            if self.ticks >= TICKS_CONFIRMAR:
                self.boost = min(BOOST_MAX, self.boost + BOOST_PASO)
        else:
            self.ticks = 0
            self.boost = max(0.0, self.boost - BOOST_FUGA)
        sgn = 1.0 if cmd >= 0 else -1.0
        return cmd + sgn * self.boost


class TorqueBoost:
    def __init__(self):
        self.enabled = False
        self._izq = _Rueda(left_motor)
        self._der = _Rueda(right_motor)
        self._cmd_l = 0.0
        self._cmd_r = 0.0
        self._task = None

    # ---------------- estado observable para telemetria ----------------
    @property
    def boost_l(self):
        return self._izq.boost

    @property
    def boost_r(self):
        return self._der.boost

    @property
    def atasco_l(self):
        return self._izq.ticks >= TICKS_CONFIRMAR

    @property
    def atasco_r(self):
        return self._der.ticks >= TICKS_CONFIRMAR

    # ---------------- modo compuesto ----------------
    def feed(self, left, right):
        """Devuelve los esfuerzos con boost aplicado. NO escribe motores;
        el ultimo eslabon de la cadena llama a aplicar(). En modo solo,
        _run() hace de ultimo eslabon."""
        return self._izq.step(left), self._der.step(right)

    def aplicar(self, left, right):
        """Eslabon final de cualquier cadena: escribe motores, con
        compensacion de bateria si procede."""
        if not self.enabled:
            self._izq.boost = 0.0
            self._der.boost = 0.0
        vs = board.voltage_scale if COMP_BATERIA else 1.0
        drivetrain.set_effort(max(-1.0, min(1.0, left * vs)),
                              max(-1.0, min(1.0, right * vs)))

    # ---------------- modo solo ----------------
    def set_command(self, left, right):
        self._cmd_l = left
        self._cmd_r = right

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False
        self._cmd_l = 0.0
        self._cmd_r = 0.0
        self._izq.boost = 0.0
        self._der.boost = 0.0
        self._izq.ticks = 0
        self._der.ticks = 0
        drivetrain.set_effort(0.0, 0.0)

    def start(self):
        """Tarea propia a 50 Hz. SOLO si no esta compuesto con el Arma 1."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self

    async def _run(self):
        next_tick = time.ticks_ms()
        while True:
            next_tick = time.ticks_add(next_tick, DT_MS)
            l, r = self.feed(self._cmd_l, self._cmd_r)
            self.aplicar(l, r)
            delay = time.ticks_diff(next_tick, time.ticks_ms())
            if delay <= 0:
                delay = 1
                next_tick = time.ticks_add(time.ticks_ms(), DT_MS)
            await asyncio.sleep_ms(delay)


torque_boost = TorqueBoost()
