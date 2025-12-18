"""Digital delivery file creator for Etsy."""
from __future__ import annotations

import logging
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import List, Dict

from ..config import PackConfig
from ..utils import FINAL_DIR
from .readme_generator import generate_readme, generate_master_readme

logger = logging.getLogger(__name__)

# Delivery directory name
DELIVERY_DIR = "06_digital_delivery"

# Screen type mapping (file prefix → screen type)
SCREEN_TYPE_PREFIXES = {
    "starting": "starting",
    "live": "live",
    "brb": "brb",
    "ending": "ending",
    "thumbnail": "thumbnail_background",
}


def extract_screen_type(filename: str) -> str | None:
    """Extract screen type from filename.

    Args:
        filename: Image filename (e.g., "starting_v001.png")

    Returns:
        Screen type key or None if not recognized
    """
    name_lower = filename.lower()

    for prefix, screen_type in SCREEN_TYPE_PREFIXES.items():
        if name_lower.startswith(prefix):
            return screen_type

    return None


def group_files_by_screen_type(final_dir: Path) -> Dict[str, List[Path]]:
    """Group PNG files by screen type.

    Args:
        final_dir: Path to 03_final/ directory

    Returns:
        Dict mapping screen_type to list of PNG file paths
    """
    if not final_dir.exists():
        logger.warning(f"Final directory not found: {final_dir}")
        return {}

    grouped = defaultdict(list)

    for png_path in sorted(final_dir.glob("*.png")):
        screen_type = extract_screen_type(png_path.name)
        if screen_type:
            grouped[screen_type].append(png_path)
        else:
            logger.debug(f"Skipping file with unrecognized type: {png_path.name}")

    return dict(grouped)


def create_zip_for_screen_type(
    screen_type: str,
    png_files: List[Path],
    output_dir: Path,
    pack_name: str,
    config: PackConfig,
    max_variants: int = 3,
) -> Path:
    """Create a ZIP file for a single screen type.

    Args:
        screen_type: Screen type key (e.g., "starting")
        png_files: List of PNG file paths
        output_dir: Output directory for ZIP
        pack_name: Pack name
        config: Pack configuration
        max_variants: Maximum number of variants to include (default 3)

    Returns:
        Path to created ZIP file
    """
    # Select best variants (first N files, already sorted)
    selected_files = png_files[:max_variants]
    actual_count = len(selected_files)

    # Determine ZIP filename
    zip_filename = f"{screen_type}.zip"
    zip_path = output_dir / zip_filename

    logger.info(f"Creating {zip_filename} with {actual_count} variants...")

    # Generate README content
    readme_content = generate_readme(
        pack_name=pack_name,
        screen_type=screen_type,
        config=config,
        variant_count=actual_count,
    )

    # Create ZIP
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add PNG files with numbered names
        for i, png_path in enumerate(selected_files, start=1):
            # Rename to standardized format: {screen_type}_v{i}.png
            archive_name = f"{screen_type}_v{i}.png"
            zf.write(png_path, arcname=archive_name)
            logger.debug(f"  Added: {archive_name} ({png_path.name})")

        # Add README.txt
        zf.writestr("README.txt", readme_content)
        logger.debug(f"  Added: README.txt")

    logger.info(f"Created: {zip_path.name} ({zip_path.stat().st_size / 1024:.1f} KB)")

    return zip_path


def create_digital_delivery_files(
    pack_name: str,
    pack_dir: Path,
    config: PackConfig,
    dry_run: bool = False,
) -> List[Path]:
    """Create digital delivery ZIP files for Etsy.

    This function:
    1. Groups PNG files from 03_final/ by screen type
    2. Creates a ZIP for each screen type (max 3 variants each)
    3. Includes README.txt in each ZIP
    4. Saves to 06_digital_delivery/

    Args:
        pack_name: Name of the pack
        pack_dir: Pack directory path
        config: Pack configuration
        dry_run: If True, skip actual file creation

    Returns:
        List of created ZIP file paths

    Raises:
        FileNotFoundError: If 03_final/ directory doesn't exist
    """
    final_dir = pack_dir / FINAL_DIR
    delivery_dir = pack_dir / DELIVERY_DIR

    if not final_dir.exists():
        raise FileNotFoundError(f"Final directory not found: {final_dir}")

    # Group files by screen type
    grouped_files = group_files_by_screen_type(final_dir)

    if not grouped_files:
        logger.warning("No PNG files found to package for delivery")
        return []

    logger.info(f"Found {len(grouped_files)} screen types to package:")
    for screen_type, files in grouped_files.items():
        logger.info(f"  - {screen_type}: {len(files)} variants")

    if dry_run:
        logger.info("[dry-run] Would create digital delivery ZIPs")
        return []

    # Create delivery directory
    if delivery_dir.exists():
        shutil.rmtree(delivery_dir)
    delivery_dir.mkdir(parents=True)

    # Create ZIP for each screen type
    created_zips = []

    for screen_type, png_files in sorted(grouped_files.items()):
        try:
            zip_path = create_zip_for_screen_type(
                screen_type=screen_type,
                png_files=png_files,
                output_dir=delivery_dir,
                pack_name=pack_name,
                config=config,
                max_variants=3,
            )
            created_zips.append(zip_path)
        except Exception as e:
            logger.error(f"Failed to create ZIP for {screen_type}: {e}")

    # Create master README.txt
    total_pngs = sum(min(len(files), 3) for files in grouped_files.values())
    master_readme = generate_master_readme(
        pack_name=pack_name,
        config=config,
        total_files=total_pngs,
    )

    master_readme_path = delivery_dir / "README.txt"
    with open(master_readme_path, "w", encoding="utf-8") as f:
        f.write(master_readme)

    logger.info(f"Created master README.txt")

    logger.info(f"Digital delivery complete: {len(created_zips)} ZIPs created in {DELIVERY_DIR}/")

    return created_zips


__all__ = [
    "create_digital_delivery_files",
    "group_files_by_screen_type",
    "extract_screen_type",
]
