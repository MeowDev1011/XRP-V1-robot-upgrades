# =========================================================
# WEAPON 5: CLOCK MANAGER & CLOSING ODOMETRY (AUTO-ENDGAME)
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# Match = exactly 150,000 ms (ticks_ms, no drift).
# Fusion odometry: encoder distance (drivetrain positions,
# in cm) + IMU heading (get_yaw, integrated at 208 Hz by the
# library itself). If the IMU drops, heading is backed up by
# the encoder difference (factory constants: wheels 6 cm,
# track 15.5 cm).
# Endgame: at the last ULTIMOS_MS it raises the alert and, if
# RETURN mode is enabled, drives continuously toward the
# starting pose: NOT a macro, it recalculates heading and
# speed every cycle (live heading) and yields to front obstacles.
# ---------------------------------------------------------
# Usage from XRPCode blocks:
#   from arma5_endgame import arma5
#   arma5.conectar(gyro_lock)     # injects Weapon 1
#   arma5.start()                 # 50 Hz background task
#   arma5.iniciar_partida()       # robot ALREADY in the start zone
#   arma5.modo_retorno(True)      # enables closing assist
#   arma5.restante_s() / arma5.is_endgame() / arma5.pose()
# =========================================================
import uasyncio as asyncio
import time
import math
from XRPLib.defaults import drivetrain, imu, board, rangefinder

# ------------------------------------------------------------
# ON-TRACK CALIBRATION
# ------------------------------------------------------------
PARTIDA_MS        = 150000   # exactly 2:30
ULTIMOS_MS        = 12000    # endgame duration: alert + return
DT_MS             = 20
V_RETORNO         = 0.85     # base return effort (calibrated: covers home
                             # at ~130 cm within the 12 s; 0.45 arrives late)
K_LLEGADA_SUAVE   = 0.04     # per remaining cm: lowers speed on approach
V_MIN_LLEGADA     = 0.18     # speed floor so it does not die before arriving
TOLERANCIA_CM     = 10.0     # "we are home" (confirm with manual: the real
                             # 'In Zone' is a band, not a 6 cm point)
PUNTO_CLAVAR_CM   = 8.0      # do not release the return right at tolerance:
                             # aim 2 cm DEEPER so the final slide leaves the
                             # robot inside the zone with margin
SEGURO_FINAL_MS  = 2000     # in the last 2 s: if already inside the zone and
                             # still ordering motion, zero command -> Weapon 4
                             # nails the robot no matter what the odometry says
PIVOTE_GRADOS     = 45.0     # if home is farther than this angle: pivot first
DIST_SEGURIDAD_CM = 12.0     # minimum front obstacle during the return
TRACK_CM          = 15.5     # factory track (fallback without IMU)
LED_HZ            = 4        # LED blink rate during the endgame


def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


class Arma5:
    def __init__(self):
        self._t0 = None
        self._x = 0.0
        self._y = 0.0
        self._th = 0.0
        self._dic = [0.0, 0.0]
        self.con_imu = 0
        self._home_x = 0.0
        self._home_y = 0.0
        self.retorno_on = False
        self._alerta_dada = False
        self._en_casa = False
        self._gyro = None
        self._task = None

    # ---------------- configuration ----------------
    def conectar(self, gyro_lock):
        """Injects Weapon 1, which executes the assisted return."""
        self._gyro = gyro_lock

    def iniciar_partida(self):
        """Starts the clock and takes the CURRENT pose as home.
        Place the robot in the start zone BEFORE calling."""
        self._t0 = time.ticks_ms()
        self.con_imu = 1 if imu.is_connected() else 0
        self._dic = [drivetrain.get_left_encoder_position(),
                     drivetrain.get_right_encoder_position()]
        self._x = 0.0
        self._y = 0.0
        self._th = 0.0
        self._home_x = 0.0
        self._home_y = 0.0
        self._alerta_dada = False
        self._en_casa = False

    def hogar_aqui(self):
        """Recaptures the current pose as home (e.g. after repositioning)."""
        self._home_x = self._x
        self._home_y = self._y

    def modo_retorno(self, on):
        self.retorno_on = on

    # ---------------- queries (all O(1)) ----------------
    def ms_transcurridos(self):
        if self._t0 is None:
            return 0
        return max(0, time.ticks_diff(time.ticks_ms(), self._t0))

    def transcurrido_s(self):
        return self.ms_transcurridos() / 1000

    def ms_restantes(self):
        return max(0, PARTIDA_MS - self.ms_transcurridos())

    def restante_s(self):
        return self.ms_restantes() / 1000

    def is_endgame(self):
        return self.ms_restantes() <= ULTIMOS_MS

    def pose(self):
        return (self._x, self._y, math.degrees(self._th))

    def distancia_al_hogar(self):
        return math.sqrt((self._home_x - self._x) ** 2 +
                         (self._home_y - self._y) ** 2)

    # ---------------- 50 Hz task ----------------
    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self

    async def _run(self):
        next_tick = time.ticks_ms()
        while True:
            next_tick = time.ticks_add(next_tick, DT_MS)
            self._odometria()
            if self._t0 is not None:
                self._logica_endgame()
            delay = time.ticks_diff(next_tick, time.ticks_ms())
            if delay <= 0:
                delay = 1
                next_tick = time.ticks_add(time.ticks_ms(), DT_MS)
            await asyncio.sleep_ms(delay)

    def _odometria(self):
        dl = drivetrain.get_left_encoder_position() - self._dic[0]
        dr = drivetrain.get_right_encoder_position() - self._dic[1]
        self._dic[0] += dl
        self._dic[1] += dr
        d = (dl + dr) / 2.0
        if self.con_imu:
            self._th = math.radians(imu.get_yaw())
        elif abs(d) > 1e-9:
            self._th += (dr - dl) / TRACK_CM
        self._x += d * math.cos(self._th)
        self._y += d * math.sin(self._th)

    def _logica_endgame(self):
        if not self.is_endgame():
            return
        if not self._alerta_dada:
            self._alerta_dada = True
            try:
                board.led_blink(LED_HZ)
            except Exception:
                pass
        if not (self.retorno_on and self._gyro is not None and self._gyro.enabled):
            return
        dist = self.distancia_al_hogar()
        en_zona = dist <= TOLERANCIA_CM
        if en_zona and self.ms_restantes() <= SEGURO_FINAL_MS:
            # closing safety: guarantees the NAILING even if the minimum
            # effort floor keeps nudging the robot at the buzzer
            self._gyro.set_base(0.0, 0.0)
            self._en_casa = True
            return
        if dist <= PUNTO_CLAVAR_CM:
            if not self._en_casa:
                self._en_casa = True
                self._gyro.set_base(0.0, 0.0)
            return
        # LIVE heading: the target is recalculated every cycle
        beta = math.atan2(self._home_y - self._y, self._home_x - self._x)
        err_rumbo = _wrap180(math.degrees(beta - self._th))
        self._gyro.set_target(math.degrees(beta))
        if abs(err_rumbo) > PIVOTE_GRADOS:
            # face home first (pivot in place: no distance is lost)
            self._gyro.set_base(0.0, 0.0)
            return
        v = V_RETORNO
        v_llegada = K_LLEGADA_SUAVE * dist
        if v_llegada < v:
            v = max(V_MIN_LLEGADA, v_llegada)
        try:
            if rangefinder.distance() < DIST_SEGURIDAD_CM:
                v = 0.0
        except Exception:
            pass
        self._gyro.set_base(v, v)


arma5 = Arma5()
