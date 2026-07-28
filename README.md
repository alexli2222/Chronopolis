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

Re-running the installer repairs the install: restores missing or changed files, updates to the latest version, keeps your virtual environment, outputs, and preferences. The app also self-updates on launch when a newer version is released.

## Usage

Two major sections are present (explained below). Launch with the `run` script in the installed folder (`run.sh` on macOS/Linux, `run.bat` on Windows).

### Complete Analysis

Full pipeline condensed into one feature. Choose two spreadsheets of `x,y` data and press **Run**. Runs the whole [Method](#method) on each, progress in the status box.

- `x` column: numbers or timestamps (`2025-06-01`, `2024-01-15T10:30:00` local, `2024-01-15T10:30:00Z` UTC; dates YYYY/MM/DD or YYYY-MM-DD). `y` column: the numeric activity signal.
- All outputs into the **Output path** (default: the current folder's `out/`): `sync.mfunc` is the synchronization `r(t)` between the two regions. Complete analysis renders a video of `r(t)`.

First usage may take extra time to cache building.

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

- **Point Series from Spreadsheet** — spreadsheet → `.pseries` data points.
- **Regression** — fit a sum of sinusoids to `x,y` data → `.mfunc` ( *Harmonics* field sets the count; blank picks the best guess automatically).
- **Transform Function** — apply certain transforms to functions
- **Create Function** / **Create Complex Function** — build a function (or a `real + i·imag` complex function) from expressions; reference saved functions with `[name]`.
- **Complex → Oscillator** — phase `θ(t) = atan2(imag, real)` of a `.cfunc` → `.oscillator`.
- **Oscillator Synchronization** — Kuramoto `r(t)` of two `.oscillator` files → `.mfunc`.
- **Visualize Function(s)** / **Complex** / **Oscillator** — render an animation with Manim.

File fields take typed text, the **Browse** button, or a dropped file. Visualize tasks have an **Output path** (default: `out/`) for the rendered video; Manim's build files go in a hidden `.manim_cache` there.

#### Flags

Apply to the three Visualize tasks (typed in the Flags box):

- `-o` — open finished video automatically
- `-p` — renders low quality preview video for faster testing
- `-hd` — render at 1080p
- `-s` — draw a segment from the origin to the moving point (Visualize Complex / Oscillator only)
- `-n=NAME` — name the output

## Method

Each region's activity proxy (e.g. CO₂ emissions, nighttime lights) is a signal in time, turned into a phase oscillator:

1. **Sinusoidal (harmonic) regression.** A sum of sinusoids is fit to the data by least squares.
2. **Hilbert transform → complex function.** The centered fit (vertical shift removed) is the real part; its Hilbert transform is the imaginary part. Together, a complex function.
3. **Extract the phase → oscillator.** The phase `θ(t) = atan2(imag, real)` is the oscillator.
4. **Kuramoto order parameter.** Two oscillators' phases go into `r(t) = |(1/N) Σ e^{iθ}|`: 1 is fully synchronized, 0 is anti-phase. That is the synchronization through time.

## Contributors

Alex Li (@alexli2222)

## License

This project is licensed under the MIT License.
