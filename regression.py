"""
Least-squares harmonic regression (a truncated Fourier-series fit).

This is the standard, textbook way to fit a sum of sinusoids to sampled data,
and is preferred here over an FFT because the data is often unevenly sampled
(arbitrary timestamps), which an FFT cannot handle - ordinary least squares can.

The model is a truncated Fourier series over the data window: the full x-span is
taken as one period of a fundamental frequency w = 2*pi / span, and K harmonics
of it are fit,

    y(x) = a0 + sum_{k=1..K} [ a_k*cos(k*w*x) + b_k*sin(k*w*x) ].

Because each term is a fixed sinusoid multiplied by an unknown coefficient, the
model is LINEAR in the unknowns (a0, a_k, b_k). Collect the basis functions as
the columns of a design matrix A (a column of ones, then cos/sin for each k) and
the coefficients as a vector c; the fit is the ordinary-least-squares solution

    minimize || A c - y ||^2 ,

solved with numpy.linalg.lstsq (a numerically stable SVD-based solver - no
hand-rolled normal equations). Each harmonic's cos/sin pair is then rewritten in
amplitude-phase form, a_k*cos(t) + b_k*sin(t) = A_k*sin(t + phi_k) with
A_k = hypot(a_k, b_k) and phi_k = atan2(a_k, b_k), giving one Sinusoid per
harmonic; the constant a0 is folded into the first sinusoid's vertical shift.

The number of harmonics K can be given explicitly or chosen automatically (see
best_harmonics).
"""

import math
from typing import List, Optional

import numpy as np

from sinusoid import Sinusoid


def choose_harmonics(n_points: int) -> int:
    return min(10, max(1, (n_points - 1) // 2))


def _design(xs: np.ndarray, omega: float, harmonics: int) -> np.ndarray:
    """Least-squares design matrix [1, cos(k w x), sin(k w x)] for k=1..harmonics."""
    n = xs.size
    columns = [np.ones(n)]
    for k in range(1, harmonics + 1):
        columns.append(np.cos(k * omega * xs))
        columns.append(np.sin(k * omega * xs))
    return np.column_stack(columns)


def best_harmonics(points, max_harmonics: Optional[int] = None) -> int:
    """Picks a good number of harmonics automatically.

    The goal here is to capture a dataset's rhythm (e.g. a daily cycle) with as
    few harmonics as possible, without chasing noise. The method:

      * Fit k = 1..hi harmonics and record each fit's explained-variance
        fraction EV(k) = 1 - RSS(k)/RSS_total.
      * When there is real periodic structure (the richest allowed fit explains
        a solid share of the variance), return the SMALLEST k that reaches 95%
        of that achievable EV - the elbow just past the dominant cycle. This is
        why a month of 6-hourly data lands near harmonic ~30 (the daily cycle)
        instead of at a single slow wave.
      * When there is little structure (mostly noise), fall back to the
        Bayesian Information Criterion, which conservatively prefers few terms.

    `hi` is capped below the interpolation regime: as the parameter count
    (2k+1) approaches n the residual collapses artificially, so params are kept
    to ~3/4 of the points. A generous absolute ceiling bounds work on big data."""
    xs = np.asarray(points.xs, dtype=float)
    ys = np.asarray(points.ys, dtype=float)
    n = xs.size
    if n < 5:
        return max(1, (n - 1) // 2)

    period = xs.max() - xs.min()
    if period <= 0:
        return 1
    omega = 2 * math.pi / period

    if max_harmonics is not None:
        hi = min((n - 1) // 2, max_harmonics)
    else:
        param_guard = int((0.75 * n - 1) // 2)  # keep 2k+1 <= 0.75 n
        hi = min((n - 1) // 2, 200, param_guard)
    hi = max(hi, 1)

    ss_total = float(np.sum((ys - ys.mean()) ** 2))
    if ss_total <= 1e-12:  # y is constant - nothing to fit
        return 1

    rss = []
    for k in range(1, hi + 1):
        design = _design(xs, omega, k)
        coeffs, *_ = np.linalg.lstsq(design, ys, rcond=None)
        resid = ys - design @ coeffs
        rss.append(float(resid @ resid))

    explained = [1.0 - r / ss_total for r in rss]  # index i -> k = i + 1

    # Adjusted R^2 discounts the variance that extra parameters explain by
    # chance, so it stays near 0 for noise but high for a real cycle. It tells us
    # (a) whether there IS structure worth fitting and (b) the richest k still
    # worth reaching (where adjusted R^2 peaks) - our reference for "achievable".
    adjusted = []
    for i, r in enumerate(rss):
        dof = n - (2 * (i + 1) + 1)
        adjusted.append(1.0 - (r / dof) * (n - 1) / ss_total if dof > 0 else -math.inf)
    max_adj = max(adjusted)

    # Enough real structure: take the elbow at 95% of the explained variance the
    # best (adjusted) model reaches - the fewest harmonics past the main cycle.
    if max_adj >= 0.5:
        k_ref = adjusted.index(max_adj) + 1
        target = 0.95 * explained[k_ref - 1]
        for k in range(1, k_ref + 1):
            if explained[k - 1] >= target:
                return k
        return k_ref

    # Little structure (mostly noise): BIC conservatively prefers few terms.
    best_k, best_bic = 1, math.inf
    for k in range(1, hi + 1):
        r = rss[k - 1]
        if r <= 1e-12:
            return k
        bic = n * math.log(r / n) + (2 * k + 1) * math.log(n)
        if bic < best_bic:
            best_bic, best_k = bic, k
    return best_k


def fit(points, harmonics: Optional[int] = None) -> List[Sinusoid]:
    xs = np.asarray(points.xs, dtype=float)
    ys = np.asarray(points.ys, dtype=float)
    n = xs.size
    if n == 0:
        raise ValueError("No data points to fit")

    if harmonics is None:
        harmonics = best_harmonics(points)
    if harmonics < 1:
        raise ValueError("harmonics must be >= 1")

    unknowns = 2 * harmonics + 1
    if unknowns > n:
        raise ValueError(
            f"Not enough points for {harmonics} harmonics; need at least {unknowns} points"
        )

    x_min, x_max = xs.min(), xs.max()
    period = x_max - x_min
    if period <= 0:
        raise ValueError("x values must span a positive range")
    # Fundamental frequency: one cycle across the whole data window.
    omega = 2 * math.pi / period

    # Ordinary least-squares harmonic regression. `design` is the matrix A whose
    # columns are the model's basis functions evaluated at every x: a constant
    # column, then cos(k*w*x) and sin(k*w*x) for each harmonic k. lstsq returns
    # the coefficient vector c minimizing ||A c - y||^2 via SVD (stable even when
    # columns are nearly collinear). coeffs = [a0, a1, b1, a2, b2, ...].
    design = _design(xs, omega, harmonics)
    coeffs, *_ = np.linalg.lstsq(design, ys, rcond=None)
    a0 = coeffs[0]

    sinusoids: List[Sinusoid] = []
    for k in range(1, harmonics + 1):
        a = coeffs[2 * k - 1]  # cosine coefficient
        b = coeffs[2 * k]      # sine coefficient
        amplitude = math.hypot(a, b)
        angular = k * omega
        # a*cos(t) + b*sin(t) = amplitude*sin(t + phi), phi = atan2(a, b)
        phi = math.atan2(a, b)
        phase_shift = -phi / angular
        frequency = angular / (2 * math.pi)
        vertical = a0 if k == 1 else 0.0  # fold the DC term into the first harmonic
        sinusoids.append(Sinusoid(amplitude, frequency, phase_shift, vertical))

    if not sinusoids:
        sinusoids.append(Sinusoid(0.0, 0.0, 0.0, a0))
    return sinusoids
