"""Post-processing steps for generated images."""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict

from PIL import Image, ImageDraw, ImageFont

from .config import PackConfig
from .utils import ensure_dir, SELECTED_DIR, FINAL_DIR, MOCKUPS_DIR

logger = logging.getLogger(__name__)


def postprocess_selected(*, config: PackConfig, pack_dir: Path, dry_run: bool = False) -> None:
    """Resize selected images and create mockups.

    Args:
        config: Parsed pack configuration.
        pack_dir: Path to the pack folder under ``packs/``.
        dry_run: Skip file writes when True.
    """

    selected_dir = pack_dir / SELECTED_DIR
    final_dir = pack_dir / FINAL_DIR
    mockups_dir = pack_dir / MOCKUPS_DIR
    ensure_dir(final_dir)
    ensure_dir(mockups_dir)

    counters: Dict[str, int] = defaultdict(int)

    for path in sorted(selected_dir.glob("*.png")):
        kind = path.stem.split("_")[0] if "_" in path.stem else path.stem
        counters[kind] += 1
        index = counters[kind]
        dest_name = config.output.filename_pattern.format(kind=kind, index=index)
        dest_path = final_dir / dest_name

        if dry_run:
            logger.info("[dry-run] Would resize %s -> %s", path.name, dest_name)
            continue

        with Image.open(path) as img:
            resized = img.resize((config.resolution.width, config.resolution.height), Image.LANCZOS)
            resized.save(dest_path, format="PNG")
            logger.debug("Saved final image %s", dest_path)

    if config.output.mockup_texts:
        _create_mockups(config, final_dir, mockups_dir, dry_run=dry_run)

    logger.info("Post-process finished for pack '%s'", pack_dir.name)


def _create_mockups(config: PackConfig, final_dir: Path, mockups_dir: Path, *, dry_run: bool = False) -> None:
    """Overlay simple text labels onto a subset of final images."""

    font = ImageFont.load_default()
    for kind, label in config.output.mockup_texts.items():
        source = next((p for p in sorted(final_dir.glob(f"{kind}_*.png"))), None)
        if not source:
            logger.warning("No final image found for mockup kind '%s'", kind)
            continue

        dest = mockups_dir / f"mockup_{kind}.png"
        if dry_run:
            logger.info("[dry-run] Would create mockup %s", dest)
            continue

        with Image.open(source) as img:
            canvas = img.copy()
            draw = ImageDraw.Draw(canvas)
            text = label or kind.title()
            draw.rectangle([(20, 20), (220, 80)], fill=(0, 0, 0, 128))
            draw.text((30, 35), text, font=font, fill=(255, 255, 255))
            canvas.save(dest, format="PNG")
            logger.debug("Saved mockup %s", dest)


__all__ = ["postprocess_selected"]
