# =========================================================
# WEAPON 3: EXPONENTIAL & DYNAMIC CONTROL CURVES
# (Surgical Handling)
# Team Robots Legends - FUSAMO - XRP Iron Acres
# ---------------------------------------------------------
# Transforms forward/turn orders with a cubic mix:
#   y(v) = MIX * v + (1 - MIX) * v^3
#   - For small v the cube dominates -> millimeter movements.
#   - At v = 1 the output is EXACTLY 1 -> 100% top speed.
#   - MIX = sensitivity: 0 = maximum precision, 1 = linear response.
# Includes:
#   - re-scaled deadband (no jump when leaving rest)
#   - Slew limiter to avoid jerks, complementary to the
#     physical ramp of Weapon 4.
# ---------------------------------------------------------
# Usage from XRPCode blocks:
#   from weapon3_curves import curve, SlewRamp, slew_fwd, slew_turn
#   v = curve(stick_order)                     # curve alone
#   v = slew_fwd.update(curve(order), dt)   # curve + ramp
# Pure math: consumes no tasks nor sensors.
# =========================================================

# ------------------------------------------------------------
# ON-TRACK CALIBRATION
# ------------------------------------------------------------
MIX        = 0.4   # 0 = pure cubic (surgical), 1 = linear (aggressive)
MIX_PRECISION = 0.12   # precision mode (BUMPER_L held)
DEADBAND   = 0.04   # smaller orders move nothing (filters stick noise)
SLEW_DEFAULT   = 3.0    # effort per second: input ramp
SLEW_RELEASE = 12.0  # on release: fast drop (anti-pan with stick at zero)


def curve(v, mix=MIX, deadband=DEADBAND):
    """Cubic response curve with a re-scaled deadband.
    Input and output in [-1, 1]. Continuous and jump-free."""
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


def invert(y, mix=MIX, deadband=DEADBAND):
    """Approximation to the inverse of curve(): useful for calibration
    (tells which order is needed for a desired output)."""
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


class SlewRamp:
    """Input slew limiter: prevents abrupt changes of order.
    One instance per axis (forward and turn)."""

    def __init__(self, slew=SLEW_DEFAULT):
        self.slew = slew
        self.v = 0.0

    def reset(self):
        self.v = 0.0

    def update(self, target, dt):
        # the ramp protects ONLY the rise: on stick release the order
        # falls fast (wheel inertia is already a physical filter);
        # limiting the descent too left the robot turning "ghost-style"
        # for ~1 s with the stick at zero (F4 pans)
        if target > self.v:
            step = max(self.slew, SLEW_RELEASE) * dt
            if target - self.v <= step:
                self.v = target
            else:
                self.v += step
        else:
            self.v = target
        return self.v


# instances ready for the sticks (forward and turn)
slew_fwd = SlewRamp()
slew_turn = SlewRamp()
