"""Per-site files (marker baseline, taught cage target): saving a new one keeps the old one."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def write_keeping_previous(path: str | Path, text: str) -> Path:
    """Write `text` to `path`. An existing file is first copied to `backups/<stem>_<time><suffix>` beside it."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        backups = p.parent / "backups"
        backups.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(p, backups / f"{p.stem}_{stamp}{p.suffix}")
    p.write_text(text, encoding="utf-8")
    return p
