"""Colour-vision simulation and contrast maths for the position palette.

The board encodes its core datum, a state's position, in the fill of a band.
That makes colour-vision deficiency a correctness problem rather than a polish
problem: a reader who cannot separate two fills cannot read the board at all.
This module is the arithmetic behind that check, so the guarantee can be
asserted in tests instead of eyeballed.

Simulation is the Brettel/Vienot-style linear projection in LMS space, the
standard approach behind Coblis and similar tools. Separation is a weighted
Euclidean distance in sRGB; SEPARATION_THRESHOLD is the point below which two
fills stop reading as different colours.

No network, no model calls: pure arithmetic over config.PALETTE.
"""

# Two fills closer than this read as the same colour to an affected reader.
SEPARATION_THRESHOLD = 90

CVD_KINDS = ("protanopia", "deuteranopia", "tritanopia")

# sRGB <-> LMS (Hunt-Pointer-Estevez, normalised)
_RGB2LMS = ((0.31399022, 0.63951294, 0.04649755),
            (0.15537241, 0.75789446, 0.08670142),
            (0.01775239, 0.10944209, 0.87256922))
_LMS2RGB = ((5.47221206, -4.6419601, 0.16963708),
            (-1.1252419, 2.29317094, -0.1678952),
            (0.02980165, -0.19318073, 1.16364789))

_SIM = {
    "protanopia": ((0, 1.05118294, -0.05116099), (0, 1, 0), (0, 0, 1)),
    "deuteranopia": ((1, 0, 0), (0.9513092, 0, 0.04866992), (0, 0, 1)),
    "tritanopia": ((1, 0, 0), (0, 1, 0), (-0.86744736, 1.86727089, 0)),
}


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _to_linear(channel):
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(channel):
    c = max(0.0, min(1.0, channel))
    v = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return round(v * 255)


def _mat_mul(m, v):
    return tuple(sum(m[i][j] * v[j] for j in range(3)) for i in range(3))


def relative_luminance(hex_color):
    r, g, b = (_to_linear(v) for v in hex_to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    """WCAG contrast ratio between two hex colours. 3:1 is the floor for a
    meaningful non-text UI element; 4.5:1 is the floor for body text."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def simulate(hex_color, kind):
    """Return hex_color as seen under the named colour-vision deficiency."""
    if kind not in _SIM:
        raise ValueError(f"unknown CVD kind: {kind}")
    rgb = tuple(_to_linear(v) for v in hex_to_rgb(hex_color))
    out = _mat_mul(_LMS2RGB, _mat_mul(_SIM[kind], _mat_mul(_RGB2LMS, rgb)))
    return "#%02X%02X%02X" % tuple(_to_srgb(v) for v in out)


def separation(a, b):
    """Weighted Euclidean distance in sRGB: how far apart two fills read."""
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    mean_r = (ra[0] + rb[0]) / 2
    dr, dg, db = (ra[i] - rb[i] for i in range(3))
    return (((2 + mean_r / 256) * dr * dr) + 4 * dg * dg
            + ((2 + (255 - mean_r) / 256) * db * db)) ** 0.5


def worst_separation(a, b):
    """Separation between two fills under the least forgiving CVD type."""
    return min(separation(simulate(a, k), simulate(b, k)) for k in CVD_KINDS)
