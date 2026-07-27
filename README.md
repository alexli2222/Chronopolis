# Chronopolis

An app to analyze synchronization of human activity across regions as part of the City Rhythms research project

## Dependencies

- ffmpeg installed and on system PATH
- Python 3.11+
    - Python 3.14+ requires compiler:
        - Windows: Microsoft C++ Build Tools, gcc
        - macOS: xcode-select, clang[\+\+]
        - Linux: build-essential, gcc
- Git

## Installation

Download and run the Chronopolis installer (located in releases) in a folder. Chronopolis will be installed in a subfolder in that folder given the dependencies are present.

Windows: .bat
macOS / Linux: .sh (run in a terminal: `bash /path/to/chronopolis_installer.sh`, or just `bash chronopolis_installer.sh` in terminal at folder, can drag and drop file into terminal to autofill path)

## Usage

Two major sections are present (explained below). Launch with the `run` script in the installed folder (`run.sh` on macOS/Linux, `run.bat` on Windows).

### Complete Analysis

Full pipeline condensed into one feature. Choose two spreadsheets of `x,y` data and press **Run**; Chronopolis carries out the whole [Method](#method) on each and reports its progress in the status box.

- The `x` column may be plain numbers or timestamps (e.g. `2025-06-01`, `2024-01-15T10:30:00` for local, or `2024-01-15T10:30:00Z` for UTC; accepts only YYYY/MM/DD). The `y` column is the numeric activity signal.
- Everything goes into the **Output path** (default: the current folder's `media/`): `sync.mfunc` — the synchronization `r(t)` between the two regions — and a rendered video of `r(t)`. Manim's temporary build files are tucked into a hidden `.manim_cache` inside it, so the folder shows only your results.

#### Flags

Type these in the Flags box (space-separated):

- `-o` — open finished video automatically
- `-p` — renders low quality preview video for faster testing
- `-hd` — render at 1080p
- `-k` — keep intermediate files (`<name>.mfunc`, `<name>.cfunc`, `<name>.oscillator`)
- `-h=N` — fit `N` harmonics instead of the automatic best guess
- `-n=NAME` — name the output

### Individual Tasks

Individual parts of Complete Analysis, exposed for precise analysis. Pick a task from the dropdown and its input fields appear.

- **Point Series from Spreadsheet** — convert a spreadsheet into a `.pseries` set of data points.
- **Regression** — fit a sum of sinusoids to `x,y` data → `.mfunc` ( *Harmonics* field sets the count; blank picks the best guess automatically).
- **Transform Function** — apply certain transforms to functions
- **Create Function** / **Create Complex Function** — build a function (or a `real + i·imag` complex function) from expressions; reference saved functions with `[name]`.
- **Complex → Oscillator** — extract the phase `θ(t) = atan2(imag, real)` of a `.cfunc` → `.oscillator`.
- **Oscillator Synchronization** — the Kuramoto `r(t)` of two `.oscillator` files → `.mfunc`.
- **Visualize Function(s)** / **Complex** / **Oscillator** — render an animation of the given functions with Manim.

Every file field accepts typed text, the **Browse** button, or a file dragged and dropped onto it. The Visualize tasks have an **Output path** (default: the current folder's `media/`) where the rendered video is written; Manim's temporary build files go into a hidden `.manim_cache` there.

#### Flags

Apply to the three Visualize tasks (typed in the Flags box):

- `-o` — open finished video automatically
- `-p` — renders low quality preview video for faster testing
- `-hd` — render at 1080p
- `-s` — draw a segment from the origin to the moving point (Visualize Complex / Oscillator only)
- `-n=NAME` — name the output

## Method

Each region's proxy dataset for human activity (e.g. CO₂ emissions, nighttime lights) is treated as a signal in time and turned into a phase oscillator:

1. **Sinusoidal (harmonic) regression.** A sum of sinusoids is fit to the data by least squares.
2. **Hilbert transform → complex function.** The fit is centered on zero (its vertical shift removed) to form the real part, and its Hilbert transform forms the imaginary part, giving a complex function.
3. **Extract the phase → oscillator.** The instantaneous phase `θ(t) = atan2(imag, real)` describes the dataset as a single phase oscillator.
4. **Kuramoto order parameter.** Two oscillators' phases are combined with the Kuramoto order parameter `r(t) = |(1/N) Σ e^{iθ}|`, which runs from 1 (fully synchronized) down to 0 (anti-phase) and measures how in-step the two regions' rhythms are through time.

## Contributors

Alex Li (@alexli2222)

## License

This project is licensed under the MIT License.
