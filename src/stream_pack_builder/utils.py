"""Utility helpers for the Stream Pack Builder CLI."""
from __future__ import annotations

import logging
import os
from pathlib import Path

# Default subfolder names (ordered for human clarity)
RAW_DIR = "01_raw"
SELECTED_DIR = "02_selected"
FINAL_DIR = "03_final"
MOCKUPS_DIR = "04_mockups"
METADATA_DIR = "metadata"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure global logging style for CLI use.

    Args:
        level: Logging level passed to ``logging.basicConfig``.
    """

    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(message)s",
    )


def ensure_dir(path: Path) -> None:
    """Create directory if missing.

    Args:
        path: Directory path to create.

    Raises:
        RuntimeError: If the directory cannot be created.
    """

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover - trivial wrapper
        raise RuntimeError(f"Could not create directory: {path}") from exc


def packs_root() -> Path:
    """Return base directory for packs (env STREAM_PACK_ROOT overrides)."""

    return Path(os.getenv("STREAM_PACK_ROOT", "packs"))
