"""
Shared file-path helpers so the tools can accept names without an extension.

If a user types "function", we look for function.mfunc / function.pseries / etc.
(whichever extensions the feature accepts); if more than one exists the user is
asked to choose. An explicit extension is always honored.
"""

from pathlib import Path

# Every data-file extension the toolkit understands.
DATA_EXTS = (".mfunc", ".pseries", ".cfunc", ".oscillator", ".csv", ".xlsx", ".xlsm")


def find_existing(name, extensions):
    """Resolve a user-typed name to an existing file.

    `extensions` is the ordered list this feature accepts (e.g. [".mfunc"]).
    Returns a Path, or None if nothing matches. If the name has no known data
    extension, each candidate extension is tried; when several exist the user
    is prompted to pick one.
    """
    name = name.strip()
    if not name:
        return None
    p = Path(name)
    suffix = p.suffix.lower()

    # Explicit, recognized extension: honor it (only if this feature accepts it).
    if suffix in DATA_EXTS:
        return p if (suffix in extensions and p.exists()) else None

    # No known extension (or a pseudo-suffix like ".5x" from an expression):
    # try appending each accepted extension.
    existing = [Path(name + ext) for ext in extensions if Path(name + ext).exists()]
    if not existing:
        return None
    if len(existing) == 1:
        return existing[0]
    return _choose(existing)


def _choose(candidates):
    print(f"Multiple files match:")
    for i, path in enumerate(candidates, 1):
        print(f"  {i}. {path.name}")
    while True:
        raw = input(f"Choose 1-{len(candidates)}: ").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(candidates):
                return candidates[idx - 1]
        except ValueError:
            pass
        print("  please enter a valid number.")


def ensure_suffix(name, suffix):
    """Assume a file ending for an output name: add `suffix` if none is given."""
    p = Path(name)
    return p if p.suffix else p.with_suffix(suffix)
