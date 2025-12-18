"""Image generation workflow built on top of the Gemini client."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from . import gemini_client
from .config import PackConfig
from .utils import ensure_dir, RAW_DIR

logger = logging.getLogger(__name__)


def build_pack(
    *,
    config: PackConfig,
    pack_dir: Path,
    num_variants: int = 2,
    seed: Optional[int] = None,
    dry_run: bool = False,
) -> None:
    """Generate raw images for each screen type defined in the config.

    Args:
        config: Parsed pack configuration.
        pack_dir: Path to the pack folder under ``packs/``.
        num_variants: Number of variants per screen type.
        seed: Optional deterministic seed forwarded to the model.
        dry_run: Skip API calls and file writes when True.
    """

    raw_dir = pack_dir / RAW_DIR
    ensure_dir(raw_dir)

    for kind, template in config.prompts.items():
        for idx in range(1, num_variants + 1):
            prompt = template.format(theme=config.theme, kind=kind)
            logger.info("Generating %s variant %d", kind, idx)
            image = gemini_client.generate_image(
                prompt,
                width=config.resolution.width,
                height=config.resolution.height,
                seed=seed,
                dry_run=dry_run,
            )
            filename = config.output.filename_pattern.format(kind=kind, index=idx)
            destination = raw_dir / filename
            if dry_run:
                logger.info("[dry-run] Would save to %s", destination)
            else:
                image.save(destination, format="PNG")
                logger.debug("Saved %s", destination)

    logger.info("Generation finished for pack '%s'", pack_dir.name)


__all__ = ["build_pack"]
