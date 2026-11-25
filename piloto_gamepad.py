# =========================================================
# PHYSICAL GAMEPAD: TELEOPERATION + 5 WEAPONS LIVE
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# The match is played with a PHYSICAL GAMEPAD (Logitech/Xbox)
# connected to the operator's computer. That computer sends
# axes and buttons to the XRP over Bluetooth (XRPLib's XPP
# protocol) at 50 Hz. On the board: XRPLib.gamepad.
#   from XRPLib.gamepad import Gamepad
#   pad = Gamepad.get_default_gamepad()
#   pad.get_value(pad.Y1), pad.is_button_pressed(pad.START)
#
# THIS MODULE IS NOT A MACRO: it is a continuous 50 Hz loop
# (uasyncio + ticks_ms, ZERO blocking sleeps) that every
# cycle:
#   1. Reads the Y1 (forward) and X1 (turn) axes.
#   2. Applies the WEAPON 3 curves to the sticks.
#   3. Picks the driving mode with clean transitions:
#        STRAIGHT = turn stick released -> Gyro-Lock PID
#                   (Weapon 1) holds the captured heading.
#        TURN     = the pilot is turning; Weapon 1 steps out.
#        STOP     = sticks released -> active braking of
#                   Weapon 4 (NAILED) + anti-spin at rest.
#        RETURN   = endgame (W5) drives home ONLY if the
#                   pilot released the sticks.
#   4. Every effort goes through the chain: Weapon 2 (anti-
#      stall) -> Weapon 4 (anti-slip ramp, OWNER of the
#      motors).
#   Buttons: START = arm clock/odometry (W5). BACK = toggles
#   the endgame return assist. Sticks ALWAYS countermand:
#   the pilot rules.
# =========================================================
import uasyncio as asyncio
import time
from XRPLib.defaults import imu
from XRPLib.gamepad import Gamepad
from arma1_gyro_lock import gyro_lock
from arma2_torque_boost import torque_boost
import arma3_curvas as curvas
from arma4_traccion import traction_brake
from arma5_endgame import arma5

# ------------------------------------------------------------
# ON-TRACK CALIBRATION
# ------------------------------------------------------------
DT_MS       = 20     # loop period (50 Hz)
GIRO_MIN    = 0.08   # turn stick above this curve = PILOT is turning
AV_MIN      = 0.02   # assisted-drive threshold
SLEW_PREC   = 1.8    # stick ramp in precision mode (BUMPER_L)
TRIM_UMBRAL = 0.12   # FILTERED raw stick above this: heading trim
TRIM_SAT    = 0.25   # stick here or above = trim at max speed
                     # (0.25 is the raw stick that produces GIRO_MIN: no
                     #  dead space between the trim and the pilot's turn)
TRIM_GRADOS_S = 60.0 # maximum trim (degrees/s)
TRIM_TAU    = 0.25   # stick EMA filter (s): cancels the kid pilot's
                     # tremor (zero-mean) and lets the real push through
ASENTAR_MAX_MS = 600  # leaving TURN: cap of the settling phase
                     # (Weapon 4 active braking while the differential
                     # momentum dies; capturing the heading earlier would
                     # lock a target the momentum is still going to drag
                     # 5-18 degrees)
ASENTAR_TASA = 45.0  # deg/s of turn rate below which the momentum has
                     # already died and the heading can be captured

PARADO, RECTO, GIRO, RETORNO = 0, 1, 2, 3
_NOMBRES = ("PARADO", "RECTO", "GIRO", "RETORNO")


def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


class Mando:
    """Pilot's console: gamepad -> curves -> weapons -> motors."""

    def __init__(self):
        self.pad = None
        self._modo = PARADO
        self._task = None
        self._btn_prev = {}
        self._ema_x = 0.0
        self._asentar_hasta = 0
        self._yaw_prev = None
        self.n_partidas = 0

    # ---------------- configuration ----------------
    def conectar(self, pad):
        self.pad = pad
        return self

    def nombre_modo(self):
        return _NOMBRES[self._modo]

    # ---------------- buttons (edge detection) ----------------
    def _borde(self, btn):
        act = bool(self.pad.is_button_pressed(btn))
        prev = self._btn_prev.get(btn, False)
        self._btn_prev[btn] = act
        return act and not prev

    # ---------------- arcade mix (official XRPLib convention) ----------------
    @staticmethod
    def _arcade(v, g):
        """left = v - g, right = v + g, scaled to avoid clipping.
        In reverse the turn inverts (steer toward stick)."""
        if v == 0.0 and g == 0.0:
            return 0.0, 0.0
        if v < 0.0:
            g = -g
        s = max(abs(v), abs(g)) / (abs(v) + abs(g))
        return (v - g) * s, (v + g) * s

    # ---------------- ONE control cycle (50 Hz) ----------------
    def _paso(self):
        if self.pad is None:
            return

        # event buttons
        if self._borde(self.pad.START):
            imu.reset_yaw()
            gyro_lock.set_target_here()
            arma5.iniciar_partida()
            self.n_partidas += 1
        if self._borde(self.pad.BACK):
            arma5.modo_retorno(not arma5.retorno_on)

        # Weapon 3 curves over the sticks
        mix = curvas.MIX_PRECIS if self.pad.is_button_pressed(self.pad.BUMPER_L) else curvas.MIX
        slew = SLEW_PREC if self.pad.is_button_pressed(self.pad.BUMPER_L) else curvas.SLEW_DEF
        curvas.suav_avance.slew = slew
        curvas.suav_giro.slew = slew
        dt = DT_MS / 1000.0
        x_raw = self.pad.get_value(self.pad.X1)
        self._ema_x += (x_raw - self._ema_x) * (dt / TRIM_TAU)
        v = curvas.suav_avance.update(
            curvas.forma(self.pad.get_value(self.pad.Y1), mix), dt)
        g = curvas.suav_giro.update(
            curvas.forma(x_raw, mix), dt)

        # mode selection (clean transitions, WITH HYSTERESIS:
        # leaving TURN only below half the threshold avoids TURN/STRAIGHT
        # chatter from the tremor, which re-captured the heading at every
        # edge and left residual pans with the stick already still)
        if False:                      # TEST: hysteresis disabled
            en_giro = abs(g) > GIRO_MIN * 0.5
        else:
            en_giro = abs(g) > GIRO_MIN
        if en_giro:
            nuevo = GIRO
        elif abs(v) > AV_MIN:
            nuevo = RECTO
        elif arma5.is_endgame() and arma5.retorno_on:
            nuevo = RETORNO
        else:
            nuevo = PARADO
        if nuevo != self._modo:
            salio_giro = (self._modo == GIRO)
            self._modo = nuevo
            if nuevo in (RECTO, PARADO) and not salio_giro:
                # official pattern: capture the heading ONCE on entry
                gyro_lock.set_target_here()
                gyro_lock.enable()
            elif nuevo in (RECTO, PARADO) and salio_giro:
                # SETTLING: the differential momentum of the curve keeps
                # turning the robot (encoders prove it). Do NOT capture
                # yet: zero order -> Weapon 4 brakes actively and kills
                # the drift; capture when the turn rate falls.
                self._asentar_hasta = time.ticks_add(time.ticks_ms(),
                                                     ASENTAR_MAX_MS)
                gyro_lock.disable()
            elif nuevo == GIRO:
                gyro_lock.disable()      # the pilot owns the turn
            elif nuevo == RETORNO:
                gyro_lock.enable()       # Weapon 5 drives (live heading)

        # real turn rate (to release settling with no fixed pauses)
        ahora = time.ticks_ms()
        yaw = imu.get_yaw()
        if self._yaw_prev is None:
            self._yaw_prev = yaw
            tasa_viraje = 0.0
        else:
            tasa_viraje = abs(_wrap180(yaw - self._yaw_prev)) / (DT_MS / 1000.0)
            self._yaw_prev = yaw
        asentando = (time.ticks_diff(self._asentar_hasta, ahora) > 0 and
                     tasa_viraje > ASENTAR_TASA and self._modo != GIRO)

        # per-mode application (ONLY Weapon 4 writes motors)
        if asentando:
            l, r = torque_boost.feed(0.0, 0.0)
            traction_brake.set_command(l, r)
        elif self._modo == GIRO:
            l, r = self._arcade(v, g)
            l, r = torque_boost.feed(l, r)
            traction_brake.set_command(l, r)
        elif self._modo == RECTO and not asentando:
            # end of settling: capture the heading ONCE (the momentum is
            # dead, the target will be true to where the robot now rests)
            if not gyro_lock.enabled:
                gyro_lock.set_target_here()
                gyro_lock.enable()
            # PILOT AUTOCORRECTION: the small SUSTAINED push (EMA ~0.25 s,
            # the zero-mean tremor does not pass) that the curve leaves
            # under GIRO_MIN is NOT ignored: it pans the locked heading
            # in an assisted way (Weapon 1 keeps stabilizing). Large
            # sticks remain plain pilot TURN.
            ax = abs(self._ema_x)
            sigue_presionada = abs(x_raw) >= 0.5 * ax
            if TRIM_UMBRAL <= ax <= TRIM_SAT and sigue_presionada:
                fraccion = (ax - TRIM_UMBRAL) / (TRIM_SAT - TRIM_UMBRAL)
                fraccion = max(0.0, min(1.0, fraccion))
                recorte = TRIM_GRADOS_S * fraccion * dt
                gyro_lock.set_target(gyro_lock.get_target() +
                                     (recorte if self._ema_x > 0 else -recorte))
            gyro_lock.set_base(v, v)
        elif self._modo == PARADO:
            if not gyro_lock.enabled and not asentando:
                gyro_lock.set_target_here()
                gyro_lock.enable()
            gyro_lock.set_base(0.0, 0.0)
        elif self._modo == RETORNO:
            pass          # Weapon 5 sets base and heading every cycle

    # ---------------- non-blocking 50 Hz task ----------------
    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self

    async def _run(self):
        next_tick = time.ticks_ms()
        while True:
            next_tick = time.ticks_add(next_tick, DT_MS)
            self._paso()
            delay = time.ticks_diff(next_tick, time.ticks_ms())
            if delay <= 0:
                delay = 1
                next_tick = time.ticks_add(time.ticks_ms(), DT_MS)
            await asyncio.sleep_ms(delay)


piloto_mando = Mando()
