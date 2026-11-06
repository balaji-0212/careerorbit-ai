"""Collision-safe destination reservation for generated resume files."""
from pathlib import Path


def reserve_unique_output(path: Path) -> Path:
    """Create a new empty destination without replacing any existing user file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path
    suffix = 2
    while True:
        try:
            with candidate.open("xb"):
                pass
            return candidate
        except FileExistsError:
            candidate = path.with_name(f"{path.stem}_{suffix}{path.suffix}")
            suffix += 1
