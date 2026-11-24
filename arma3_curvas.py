# =========================================================
# ARMA 3: CURVAS EXPONENCIALES Y DINAMICAS DE CONTROL
# (Manejo Quirurgico)
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# Transforma ordenes de avance/giro con una mezcla cubica:
#   y(v) = MIX * v + (1 - MIX) * v^3
#   - En v pequeno domina el cubo -> movimientos de milimetros.
#   - En v = 1 la salida es EXACTAMENTE 1 -> velocidad punta 100%.
#   - MIX = sensibilidad: 0 = maxima precision, 1 = respuesta lineal.
# Incluye:
#   - banda muerta re-escalada (sin salto al salir de reposo)
#   - Suavizador (limitador de rampa) para evitar tirones,
#     complementario a la rampa fisica del Arma 4.
# ---------------------------------------------------------
# Uso desde bloques XRPCode:
#   from arma3_curvas import forma, Suavizador, suav_avance, suav_giro
#   v = forma(orden_del_mando)                     # curva sola
#   v = suav_avance.update(forma(orden), dt)       # curva + rampa
# Es matematica pura: no consume tareas ni sensores.
# =========================================================

# ------------------------------------------------------------
# CALIBRACION EN PISTA
# ------------------------------------------------------------
MIX        = 0.35   # 0 = cubico puro (quirurgico), 1 = lineal (agresivo)
MIX_PRECIS = 0.12   # modo precision (BUMPER_L del mando mantenido)
DEADBAND   = 0.04   # ordenes menores no mueven nada (filtra ruido del mando)
SLEW_DEF   = 3.0    # esfuerzo por segundo: rampa de entrada
SLEW_SUELTA = 12.0  # al soltar: caida rapida (antipaneo con stick a cero)


def forma(v, mix=MIX, deadband=DEADBAND):
    """Curva de respuesta cubica con banda muerta re-escalada.
    Entrada y salida en [-1, 1]. Continua y sin saltos."""
    if v > 1.0:
        v = 1.0
    elif v < -1.0:
        v = -1.0
    if abs(v) <= deadband:
        return 0.0
    d = deadband * (1.0 if v > 0 else -1.0)
    v = (v - d) / (1.0 - deadband)
    cubo = v * v * v
    return mix * v + (1.0 - mix) * cubo


def invertida(y, mix=MIX, deadband=DEADBAND):
    """Aproximacion a la inversa de forma(): util para calibracion
    (dice que orden hace falta para una salida deseada)."""
    if abs(y) < 1e-6:
        return 0.0
    v = y
    for _ in range(3):
        f = mix * v + (1.0 - mix) * v * v * v - y
        fp = mix + 3.0 * (1.0 - mix) * v * v
        if fp > 1e-6:
            v -= f / fp
    if abs(v) <= deadband:
        return 0.0
    d = deadband * (1.0 if v > 0 else -1.0)
    v = v * (1.0 - deadband) + d
    if v > 1.0:
        v = 1.0
    elif v < -1.0:
        v = -1.0
    return v


class Suavizador:
    """Limitador de rampa de entrada: impide cambios bruscos de orden.
    Una instancia por eje (avance y giro)."""

    def __init__(self, slew=SLEW_DEF):
        self.slew = slew
        self.v = 0.0

    def reset(self):
        self.v = 0.0

    def update(self, objetivo, dt):
        # la rampa protege SOLO la subida: al soltar la palanca la
        # orden cae rapido (la inercia de la rueda ya es un filtro
        # fisico); limitar tambien la bajada dejaba al robot girando
        # "fantasma" hasta ~1 s con el stick en cero (paneos F4)
        if objetivo > self.v:
            paso = max(self.slew, SLEW_SUELTA) * dt
            if objetivo - self.v <= paso:
                self.v = objetivo
            else:
                self.v += paso
        else:
            self.v = objetivo
        return self.v


# instancias listas para el mando (avance y giro)
suav_avance = Suavizador()
suav_giro = Suavizador()
