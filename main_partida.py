# =========================================================
# MAIN DE PARTIDA PARA LA PLACA XRP - Team Robots Legends
# ---------------------------------------------------------
# Pegar/copiar en XRPCode (o subir como main.py). Conecta el
# gamepad fisico y las 5 armas en la cadena correcta.
# REQUISITOS DE PISTA:
#   - IMU calibrada y robot quieto al encender.
#   - XRP conectado por BLUETOOTH a la estacion de conduccion
#     (con cable USB el gamepad no funciona, guia oficial).
#   - Gamepad USB conectado a la computadora de operacion.
# CONTROLES:
#   Y1 = avance / retroceso     X1 = giro
#   START = armar reloj y casa (A5). BACK = retorno on/off
#   BUMPER_L (mantener) = modo precision
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
    gyro_lock.attach(_gancho)          # A1 -> A2 -> A4 (dueno de motores)
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
        await asyncio.sleep_ms(1000)   # solo la tarea raiz duerme


def main():
    imu.calibrate(1.0)                 # calibracion de arranque de la IMU
    iniciar_sistema()
    asyncio.run(_vivir())


main()
