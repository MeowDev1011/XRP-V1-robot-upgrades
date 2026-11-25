# =========================================================
# MATCH ENTRY POINT FOR THE XRP BOARD - Team Robots Legends
# ---------------------------------------------------------
# Paste/upload in XRPCode (or deploy as main.py). It wires the
# physical gamepad and the 5 weapons into the correct chain.
# TRACK REQUIREMENTS:
#   - IMU calibrated and robot still at power-on.
#   - XRP connected by BLUETOOTH to the driving station
#     (over USB cable the gamepad does not work, official guide).
#   - USB gamepad connected to the operator's computer.
# CONTROLS:
#   Y1 = forward / backward     X1 = turn
#   START = arm clock & home (W5). BACK = return assist on/off
#   BUMPER_L (hold) = precision mode
# =========================================================
import asyncio
from XRPLib.defaults import imu
from XRPLib.gamepad import Gamepad
from arma1_gyro_lock import gyro_lock
from arma2_torque_boost import torque_boost
from arma3_curvas import suav_avance, suav_giro
from arma4_traccion import traction_brake
from arma5_endgame import arma5
from piloto_gamepad import piloto_mando


def _gancho(l, r):
    l, r = torque_boost.feed(l, r)
    traction_brake.set_command(l, r)


def iniciar_sistema():
    gyro_lock.attach(_gancho)          # W1 -> W2 -> W4 (owner of the motors)
    torque_boost.enable()
    traction_brake.enable()
    arma5.conectar(gyro_lock)
    arma5.modo_retorno(True)
    piloto_mando.conectar(Gamepad.get_default_gamepad())
    traction_brake.start()             # 50 Hz, uasyncio
    gyro_lock.start()                  # 50 Hz, uasyncio
    arma5.start()                      # 50 Hz, uasyncio
    piloto_mando.start()               # 50 Hz, uasyncio


async def _vivir():
    while True:
        await asyncio.sleep_ms(1000)   # only the root task sleeps


def main():
    imu.calibrate(1.0)                 # boot-time IMU calibration
    iniciar_sistema()
    asyncio.run(_vivir())


main()
