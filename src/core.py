"""
Chronopolis core - non-interactive task functions shared by the GUI.

Each function performs exactly one toolkit task from explicit arguments (no
console prompts), writes any output file(s), and returns a short human-readable
result string. Bad input raises ValueError/OSError so the caller can surface the
message. The heavy visual work (Manim) is imported lazily inside the functions
that need it, so the rest of the toolkit runs without it installed.
"""

from pathlib import Path

import paths
import regression
import transforms
from cfunc import ComplexFunction
from mfunc import MathFunction
from pointseries import PointSeries


# ---- shared helpers ----------------------------------------------------

def _resolver(name):
    """Resolves a [name] reference in an expression to a .mfunc MathFunction."""
    found = paths.find_existing(name, (".mfunc",))
    if found is None:
        raise ValueError(f"referenced function not found: {name} (looked for {name}.mfunc)")
    return MathFunction.from_file(found)


def _out_or_default(out_path, input_path, suffix, fallback):
    """Chooses the output path: what the user typed, else a default derived from
    the input file's name (or `fallback` when there is no input file)."""
    text = (out_path or "").strip()
    if text:
        return paths.ensure_suffix(text, suffix)
    if input_path:
        return paths.ensure_suffix(Path(input_path).with_suffix(suffix).name, suffix)
    return paths.ensure_suffix(fallback, suffix)


def _sync_function(theta1: MathFunction, theta2: MathFunction) -> MathFunction:
    """Kuramoto order parameter r(t) of two oscillator phase functions."""
    t1, t2 = theta1.expression(), theta2.expression()
    r_expr = f"sqrt((cos(({t1}))+cos(({t2})))^2+(sin(({t1}))+sin(({t2})))^2)/2"
    return MathFunction([r_expr], name="sync",
                        time_based=theta1.time_based or theta2.time_based)


# ---- individual tasks --------------------------------------------------

def task_pointseries(spreadsheet, out_path):
    data = PointSeries.from_file(spreadsheet)
    out = _out_or_default(out_path, spreadsheet, ".pseries", "pointseries.pseries")
    data.save(out, source=Path(spreadsheet).name)
    return f"Wrote {out}  ({len(data)} points, time_based={data.time_based})"


def task_regression(data_file, harmonics, out_path):
    data = PointSeries.from_file(data_file)
    sinusoids = regression.fit(data, harmonics)  # harmonics None -> best guess
    fn = MathFunction([str(s) for s in sinusoids], name=Path(data_file).stem,
                      time_based=data.time_based)
    out = _out_or_default(out_path, data_file, ".mfunc", "regression.mfunc")
    fn.save(out, header=f"Sinusoidal regression fit of {Path(data_file).name}")
    return f"Wrote {out}  ({len(sinusoids)} sinusoid term(s))\n  f(x) = {fn.expression()}"


def task_transform(mfunc_file, transform_name, out_path):
    fn = MathFunction.from_file(mfunc_file)
    transform = transforms.TRANSFORMS.get(transform_name)
    if transform is None:
        raise ValueError(f"unknown transform {transform_name!r}; "
                         f"available: {', '.join(transforms.TRANSFORMS)}")
    result = transform(fn)
    stem = f"{Path(mfunc_file).stem}_{transform_name}"
    out = _out_or_default(out_path, None, ".mfunc", f"{stem}.mfunc")
    result.save(out, header=f"{transform_name} transform of {Path(mfunc_file).name}")
    return f"Wrote {out}"


def task_create_function(expr, out_path):
    if not expr.strip():
        raise ValueError("enter an expression in x, e.g. sin(x)+x")
    fn = MathFunction.from_combined(expr, _resolver, name="function")
    out = _out_or_default(out_path, None, ".mfunc", "function.mfunc")
    fn.save(out, header=f"Created function: {expr}")
    return f"Wrote {out}\n  f(x) = {fn.expression()}"


def task_create_complex(real_expr, imag_expr, out_path):
    if not real_expr.strip() or not imag_expr.strip():
        raise ValueError("enter both the real and imaginary parts")
    real = MathFunction.from_combined(real_expr, _resolver)
    imag = MathFunction.from_combined(imag_expr, _resolver)
    cf = ComplexFunction(real, imag, name="complex")
    out = _out_or_default(out_path, None, ".cfunc", "complex.cfunc")
    cf.save(out, header="Created complex function")
    return f"Wrote {out}\n  {cf}"


def task_oscillator(cfunc_file, out_path):
    cf = ComplexFunction.from_file(cfunc_file)
    osc = MathFunction([cf.phase_expression()], name=Path(cfunc_file).stem,
                       time_based=cf.time_based)
    out = _out_or_default(out_path, cfunc_file, ".oscillator", "oscillator.oscillator")
    osc.save(out, header=f"Oscillator phase theta(t) = atan2(imag, real) of {Path(cfunc_file).name}")
    return f"Wrote {out}"


def task_sync(osc1_file, osc2_file, out_path):
    theta1 = MathFunction.from_file(osc1_file)
    theta2 = MathFunction.from_file(osc2_file)
    result = _sync_function(theta1, theta2)
    out = _out_or_default(out_path, None, ".mfunc", "sync.mfunc")
    result.save(out, header="Synchronization r(t) - Kuramoto order parameter of two oscillators")
    return f"Wrote {out}"


# ---- visualization -----------------------------------------------------

def _resolve_output_dir(output_dir):
    """The single folder all outputs go to (the final video and any function
    files). Defaults to 'out'. Created if it does not exist yet."""
    text = (output_dir or "").strip() if isinstance(output_dir, str) else str(output_dir or "")
    target = Path(text) if text else Path("out")
    target.mkdir(parents=True, exist_ok=True)
    return target


def task_visualize_functions(items_text, open_video, test, hd, output_dir, name=None):
    import visualize_functions as vf

    items = []
    for line in items_text.splitlines():
        line = line.strip()
        if line:
            items.append(vf.load_item(line))
    if not items:
        raise ValueError("enter at least one item (a file path or an expression in x)")

    target = _resolve_output_dir(output_dir)
    x_min, x_max = vf.suggest_x_bounds(items)
    y_min, y_max = vf.suggest_y_bounds(items, x_min, x_max)
    output_name = name or "_".join(lbl for lbl, _ in items)
    vf.render(functions=items, x_range=(x_min, x_max), y_range=(y_min, y_max),
              preview=open_video, test=test, hd=hd, output_name=output_name, output_dir=str(target))
    return f"Rendered {len(items)} item(s) -> {target}"


def task_visualize_complex(cfunc_file, open_video, test, hd, segment, output_dir, name=None):
    import visualize_functions as vf

    cf = ComplexFunction.from_file(cfunc_file)
    target = _render_complex(vf, cf.real, cf.imag, subject=name or Path(cfunc_file).stem,
                             kind="complex", segment=segment, open_video=open_video,
                             test=test, hd=hd, output_dir=output_dir)
    return f"Rendered complex trajectory -> {target}"


def task_visualize_oscillator(osc_file, open_video, test, hd, segment, output_dir, name=None):
    import visualize_functions as vf

    theta = MathFunction.from_file(osc_file)
    th = theta.expression()
    real_fn = MathFunction.from_expression(f"cos(({th}))", time_based=theta.time_based)
    imag_fn = MathFunction.from_expression(f"sin(({th}))", time_based=theta.time_based)
    target = _render_complex(vf, real_fn, imag_fn, subject=name or Path(osc_file).stem,
                             kind="oscillator", segment=segment, open_video=open_video,
                             test=test, hd=hd, output_dir=output_dir)
    return f"Rendered oscillator phasor -> {target}"


def _render_complex(vf, real_fn, imag_fn, subject, kind, segment, open_video, test, hd, output_dir):
    target = _resolve_output_dir(output_dir)
    x_min, x_max = vf.suggest_x_bounds([("re", real_fn), ("im", imag_fn)])
    speed, dur = vf.suggest_complex_speed(real_fn, imag_fn, x_min, x_max)
    duration = max(1.0, min(120.0, (x_max - x_min) / speed)) if speed > 0 else dur
    vf.render_complex(real_fn, imag_fn, (x_min, x_max), duration, segment, preview=open_video,
                      test=test, hd=hd, output_name=subject, output_dir=str(target), kind=kind)
    return target


# ---- complete analysis -------------------------------------------------

def complete_analysis(spreadsheet1, spreadsheet2, output_dir="", open_video=False,
                      test=False, hd=False, keep=False, harmonics=None, name="sync",
                      log=print):
    """Full pipeline for two spreadsheets:

        each -> regression -> remove shift (real) & Hilbert (imag) -> complex ->
        oscillator; both -> synchronization r(t) -> saved .mfunc -> visualization.

    All outputs (the .mfunc and the video, plus any kept intermediates) go into
    `output_dir` (default "media"); Manim's scaffolding stays in a hidden cache
    there. Flags: `open_video` opens the finished video; `test` renders a fast
    low-res preview; `hd` renders at 1080p; `keep` also saves each city's
    intermediate files (<stem>.mfunc/.cfunc/.oscillator); `harmonics` overrides
    the automatic count; `name` is the output base name (default "sync").
    `log(str)` receives progress lines. Returns the path of the final .mfunc."""
    target = _resolve_output_dir(output_dir)
    oscillators, names = [], []
    data_xs = []  # every input x, so we can anchor the plot to the real domain
    for spreadsheet in (spreadsheet1, spreadsheet2):
        data = PointSeries.from_file(spreadsheet)
        stem = Path(spreadsheet).stem
        log(f"Loaded {Path(spreadsheet).name}: {len(data)} points "
            f"(time_based={data.time_based})")
        if data.xs:
            data_xs.append(min(data.xs))
            data_xs.append(max(data.xs))
        oscillators.append(_analyze_to_oscillator(data, stem, harmonics, keep, target, log))
        names.append(stem)

    sync = _sync_function(oscillators[0], oscillators[1])
    base = (name or "sync").strip() or "sync"
    out = target / paths.ensure_suffix(base, ".mfunc").name
    sync.save(out, header=f"Complete analysis: synchronization r(t) of "
                          f"{names[0]} and {names[1]}")
    log(f"Wrote {out}")

    import visualize_functions as vf
    label = out.stem
    items = [(label, sync)]
    # Anchor the x-range to the actual data domain. The sync r(t) is a symbolic
    # sum of sinusoids, so suggest_x_bounds would reset the origin to 0 - which,
    # for time-based data, renders the x-axis starting at the Unix epoch (1970)
    # instead of the real dates. Fall back to the estimate only without data.
    if len(data_xs) >= 2:
        x_min, x_max = min(data_xs), max(data_xs)
    else:
        x_min, x_max = vf.suggest_x_bounds(items)
    y_min, y_max = vf.suggest_y_bounds(items, x_min, x_max)
    log("Rendering synchronization r(t)...")
    vf.render(functions=items, x_range=(x_min, x_max), y_range=(y_min, y_max),
              preview=open_video, test=test, hd=hd, output_name=label, output_dir=str(target))
    log(f"Done. All outputs in {target}")
    return str(out)


def _analyze_to_oscillator(data, stem, harmonics, keep, out_dir, log):
    """One dataset -> regression -> remove shift (real) & Hilbert (imag) ->
    complex -> oscillator phase MathFunction. `harmonics` None means auto-pick.
    When `keep`, the regression/complex/oscillator files are saved in `out_dir`."""
    sinusoids = regression.fit(data, harmonics)  # None -> best_harmonics guess
    log(f"  {stem}: fit {len(sinusoids)} harmonic(s)")
    regression_fit = MathFunction([str(s) for s in sinusoids], name=stem,
                                  time_based=data.time_based)
    real = transforms.remove_shift(regression_fit)
    imag = transforms.hilbert(real)
    cf = ComplexFunction(real, imag, name=stem)
    oscillator = MathFunction([cf.phase_expression()], name=stem, time_based=cf.time_based)
    if keep:
        base = Path(out_dir)
        regression_fit.save(base / f"{stem}.mfunc", header=f"Regression fit of {stem}")
        cf.save(base / f"{stem}.cfunc", header=f"Complex function of {stem}")
        oscillator.save(base / f"{stem}.oscillator", header=f"Oscillator of {stem}")
        log(f"  {stem}: kept {stem}.mfunc, {stem}.cfunc, {stem}.oscillator")
    return oscillator
