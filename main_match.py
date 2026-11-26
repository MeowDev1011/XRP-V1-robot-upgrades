# =========================================================
# MATCH ENTRY POINT FOR THE XRP BOARD - Team Robots Legends
# ---------------------------------------------------------
# paste/upload in XRPCode (or deploy as main.py). It wires the
# physical gamepad and the 6 weapons (5 assist + the on-board
# brain) into the correct chain.
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
from weapon1_gyro_lock import gyro_lock
from weapon2_torque_boost import torque_boost
from weapon3_curves import slew_fwd, slew_turn
from weapon4_traction import traction_brake
from weapon5_endgame import endgame
from weapon6_brain import brain
from pilot_gamepad import pilot_console


def _gancho(l, r):
    l, r = torque_boost.feed(l, r)
    traction_brake.set_command(l, r)


def start_system():
    gyro_lock.attach(_gancho)          # W1 -> W2 -> W4 (owner of the motors)
    torque_boost.enable()
    traction_brake.enable()
    endgame.connect(gyro_lock)
    endgame.set_return(True)
    brain.wire(gyro_lock, torque_boost, endgame, pilot_console)
    pilot_console.connect(Gamepad.get_default_gamepad())
    traction_brake.start()             # 50 Hz, uasyncio
    gyro_lock.start()                  # 50 Hz, uasyncio
    endgame.start()                    # 50 Hz, uasyncio
    brain.start()                      # 50 Hz, uasyncio (W6: thinks & re-tunes)
    pilot_console.start()              # 50 Hz, uasyncio


async def _vivir():
    while True:
        await asyncio.sleep_ms(1000)   # only the root task sleeps


def main():
    imu.calibrate(1.0)                 # boot-time IMU calibration
    start_system()
    asyncio.run(_vivir())


main()
