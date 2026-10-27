"""Writing the converted sheets to a folder. The original file is never touched."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..core.output import OutputSheet


def default_folder() -> Path:
    return Path.home() / "Documents" / "RunSpriteRun" / "Converted"


def existing(sheets: list[OutputSheet], folder: Path) -> list[Path]:
    return [folder / s.file_name for s in sheets if s.save and (folder / s.file_name).exists()]


def save_sheets(sheets: list[OutputSheet], folder: Path, replace: Callable[[list[Path]], bool] | None = None) -> list[Path]:
    """Write every sheet that is ticked. If some files exist, `replace(list)` is asked once; False cancels everything.
    Returns the paths written. A file that cannot be written raises OSError with its name in the message."""
    folder = Path(folder)
    chosen = [s for s in sheets if s.save]
    clash = existing(chosen, folder)
    if clash and replace is not None and not replace(clash):
        return []
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for s in chosen:
        path = folder / s.file_name
        try:
            s.image.save(path, "PNG")
        except OSError as e:
            raise OSError(f"{path.name} could not be saved. {e}") from e
        written.append(path)
    return written
