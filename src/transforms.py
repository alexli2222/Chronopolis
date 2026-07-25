"""
Signal transforms that operate on a MathFunction whose terms are sinusoids
(i.e. a Fourier series exported by the regression tool).
"""

import math

from mfunc import MathFunction
from sinusoid import Sinusoid


def hilbert(function: MathFunction) -> MathFunction:
    """Hilbert transform of a sum of sinusoids.

    Shifts every frequency component's phase by -90 degrees: for angular
    frequency b > 0, H[A*sin(b(x-h))] = -A*cos(b(x-h)); the sign flips for
    b < 0. Constant (zero-frequency / DC / midline) terms transform to 0 and
    drop out - so, correctly, the result always has a zero mean.

    Raises ValueError if any term is neither a sinusoid nor a constant.
    """
    new_terms = []
    for term in function.terms:
        if _is_constant(term):
            continue  # Hilbert transform of a constant (DC) is 0
        try:
            s = Sinusoid.from_notation(term)
        except ValueError as e:
            raise ValueError(
                f"The Hilbert transform requires every term to be a sinusoid "
                f"(or a constant); cannot transform term {term!r}"
            ) from e
        b = s.angular_frequency
        if b == 0:
            continue  # Hilbert transform of a constant is 0
        new_amplitude = -math.copysign(1.0, b) * s.amplitude
        new_phase = s.phase_shift - math.pi / (2 * b)
        new_terms.append(str(Sinusoid(new_amplitude, b / (2 * math.pi), new_phase, 0.0)))

    if not new_terms:
        new_terms.append("0")
    return MathFunction(new_terms, time_based=function.time_based)


def remove_shift(function: MathFunction) -> MathFunction:
    """Removes the vertical shift (DC / midline) from a sum of sinusoids,
    centering it on 0.

    Each sinusoid keeps its amplitude, frequency, and phase but loses its
    vertical shift; pure constant terms drop out entirely. The result oscillates
    around 0.

    Raises ValueError if any term is neither a sinusoid nor a constant.
    """
    new_terms = []
    for term in function.terms:
        if _is_constant(term):
            continue  # a bare constant is entirely vertical shift
        try:
            s = Sinusoid.from_notation(term)
        except ValueError as e:
            raise ValueError(
                f"Removing the vertical shift requires every term to be a sinusoid "
                f"(or a constant); cannot handle term {term!r}"
            ) from e
        new_terms.append(str(Sinusoid(s.amplitude, s.frequency, s.phase_shift, 0.0)))

    if not new_terms:
        new_terms.append("0")
    return MathFunction(new_terms, time_based=function.time_based)


def _is_constant(term: str) -> bool:
    try:
        float(term)
        return True
    except ValueError:
        return False


# Registry so the CLI can present transforms generically and grow later.
TRANSFORMS = {
    "hilbert": hilbert,
    "remove_shift": remove_shift,
}

# One-line descriptions shown in the transform menu.
DESCRIPTIONS = {
    "hilbert": "phase-shift every component by -90 degrees (also removes the mean)",
    "remove_shift": "remove the vertical shift / midline, centering the function on 0",
}
