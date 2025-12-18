"""Rubric-based evaluation system for stream pack quality assessment."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class EvaluationScore:
    """Individual dimension score with justification."""
    dimension: str
    score: float  # 0-10
    weight: float  # 0-1
    justification: str
    issues: List[str] = field(default_factory=list)


@dataclass
class PackEvaluation:
    """Complete evaluation of a stream pack."""
    pack_name: str
    overall_score: float  # 0-10 weighted average
    dimension_scores: List[EvaluationScore]
    critical_issues: List[str]
    selected_images: dict  # {kind: filename}
    deltas: List[str]  # Improvement suggestions for next round
    automated_checks_passed: bool

    @property
    def passes_threshold(self) -> bool:
        """Check if evaluation meets quality threshold."""
        return self.overall_score >= 8.5 and not self.critical_issues


def validate_technical_overlays(final_dir: Path) -> tuple[List[str], bool]:
    """Validate overlay images meet technical requirements (1920x1080).

    Args:
        final_dir: Path to 03_final/ directory containing overlay PNGs.

    Returns:
        Tuple of (issues list, passes bool)
    """
    issues = []

    if not final_dir.exists():
        issues.append(f"Final directory not found: {final_dir}")
        return issues, False

    overlay_files = list(final_dir.glob("*.png"))
    if not overlay_files:
        issues.append(f"No overlay PNG files found in {final_dir}")
        return issues, False

    for img_path in overlay_files:
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                if (width, height) != (1920, 1080):
                    issues.append(
                        f"Overlay wrong resolution: {img_path.name} is {width}x{height}, "
                        f"expected 1920x1080"
                    )
        except Exception as e:
            issues.append(f"Failed to read {img_path.name}: {e}")

    return issues, len(issues) == 0


def validate_etsy_listings(listing_dir: Path) -> tuple[List[str], List[str], bool]:
    """Validate listing photos meet Etsy requirements (2000x2000+, first landscape/square).

    Etsy official requirements:
    - Minimum 2000px on smallest side
    - First photo should be landscape or square (better thumbnails)
    - Max 1MB per file recommended (2MB hard limit)

    Args:
        listing_dir: Path to listing_images/ directory.

    Returns:
        Tuple of (errors list, warnings list, passes bool)
    """
    errors = []
    warnings = []

    if not listing_dir.exists():
        # Not an error for Phase 1 (listings not yet implemented)
        logger.debug(f"Listing directory not found (expected in Phase 4): {listing_dir}")
        return [], [], True

    listing_files = sorted(listing_dir.glob("*.jpg"))
    if not listing_files:
        # Not an error if no listings yet
        return [], [], True

    for idx, img_path in enumerate(listing_files):
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                size_mb = img_path.stat().st_size / (1024 * 1024)

                # Error: Resolution too small
                if width < 2000 or height < 2000:
                    errors.append(
                        f"{img_path.name}: Too small {width}x{height}, "
                        f"Etsy requires min 2000px on smallest side"
                    )

                # Error: First image should be landscape/square
                if idx == 0 and width < height:
                    errors.append(
                        f"{img_path.name}: First listing image should be landscape or square "
                        f"(current: {width}x{height})"
                    )

                # Warning: File size > 1MB (Etsy recommendation)
                if size_mb > 1.0:
                    warnings.append(
                        f"{img_path.name}: Size {size_mb:.1f}MB > 1MB "
                        f"(Etsy recommends ≤1MB for faster loading)"
                    )

                # Warning: File size > 2MB (Etsy hard limit)
                if size_mb > 2.0:
                    errors.append(
                        f"{img_path.name}: Size {size_mb:.1f}MB exceeds Etsy's 2MB limit"
                    )

        except Exception as e:
            errors.append(f"Failed to validate {img_path.name}: {e}")

    return errors, warnings, len(errors) == 0


def validate_etsy_downloads(zips_dir: Path) -> tuple[List[str], bool]:
    """Validate download ZIPs meet Etsy requirements (max 5 files, 20MB each).

    Etsy official requirements for digital downloads:
    - Maximum 5 files
    - Maximum 20MB per file

    Args:
        zips_dir: Path to zips/ directory.

    Returns:
        Tuple of (issues list, passes bool)
    """
    issues = []

    if not zips_dir.exists():
        # Not an error for Phase 1 (ZIPs not yet implemented)
        logger.debug(f"ZIPs directory not found (expected in Phase 4): {zips_dir}")
        return [], True

    zip_files = list(zips_dir.glob("*.zip"))
    if not zip_files:
        # Not an error if no ZIPs yet
        return [], True

    # Check file count
    if len(zip_files) > 5:
        issues.append(
            f"Too many download files: {len(zip_files)} ZIPs found, "
            f"Etsy allows max 5 files"
        )

    # Check individual file sizes
    for zip_path in zip_files:
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        if size_mb > 20:
            issues.append(
                f"{zip_path.name}: Size {size_mb:.1f}MB exceeds Etsy's 20MB limit"
            )

    return issues, len(issues) == 0


def check_critical_issues(pack_dir: Path) -> List[str]:
    """Check for critical issues that block shipping regardless of score.

    Critical issues:
    - Copyright logos/trademarks visible
    - Inappropriate content
    - File corruption/missing files
    - Resolution mismatches
    - ZIP files exceeding 20MB

    Note: Copyright/content checks require manual or Vision model review.
    This function only checks technical issues.

    Args:
        pack_dir: Path to pack directory.

    Returns:
        List of critical issue descriptions.
    """
    critical = []

    # Check for missing critical directories
    final_dir = pack_dir / "03_final"
    if not final_dir.exists():
        critical.append("Missing 03_final/ directory")
        return critical  # Can't continue checks without this

    # Check for overlay files
    overlay_files = list(final_dir.glob("*.png"))
    if not overlay_files:
        critical.append("No overlay PNG files found in 03_final/")

    # Check for resolution mismatches
    overlay_issues, _ = validate_technical_overlays(final_dir)
    for issue in overlay_issues:
        if "wrong resolution" in issue.lower():
            critical.append(f"CRITICAL: {issue}")

    # Check Etsy download file sizes (if present)
    zips_dir = pack_dir / "zips"
    if zips_dir.exists():
        zip_issues, _ = validate_etsy_downloads(zips_dir)
        for issue in zip_issues:
            if "exceeds" in issue.lower() and "20mb" in issue.lower():
                critical.append(f"CRITICAL: {issue}")

    return critical


def compute_automated_score(pack_dir: Path) -> tuple[float, List[str]]:
    """Compute automated technical quality score (0-10).

    This score is combined with Vision model evaluation:
    - Final technical score = 70% Vision + 30% Automated

    Args:
        pack_dir: Path to pack directory.

    Returns:
        Tuple of (score, issues list)
    """
    all_issues = []

    # Validate overlays (required)
    final_dir = pack_dir / "03_final"
    overlay_issues, overlay_pass = validate_technical_overlays(final_dir)
    all_issues.extend(overlay_issues)

    # Validate listing photos (optional in Phase 1)
    listing_dir = pack_dir / "listing_images"
    listing_errors, listing_warnings, listing_pass = validate_etsy_listings(listing_dir)
    all_issues.extend(listing_errors)
    # Warnings don't count as failures

    # Validate download ZIPs (optional in Phase 1)
    zips_dir = pack_dir / "zips"
    zip_issues, zip_pass = validate_etsy_downloads(zips_dir)
    all_issues.extend(zip_issues)

    # Compute score: start at 10, deduct 0.5 per issue
    score = max(0.0, 10.0 - len(all_issues) * 0.5)

    return score, all_issues


def calculate_overall_score(dimension_scores: List[EvaluationScore]) -> float:
    """Calculate weighted average score from dimension scores.

    Args:
        dimension_scores: List of dimension evaluations.

    Returns:
        Weighted average score (0-10).
    """
    if not dimension_scores:
        return 0.0

    total_weight = sum(score.weight for score in dimension_scores)
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(score.score * score.weight for score in dimension_scores)
    return weighted_sum / total_weight


# Rubric dimension definitions
RUBRIC_DIMENSIONS = {
    "brand_consistency": {
        "weight": 0.30,
        "description": "Colors match brand palette, texture/feel reflects tokens, composition follows guidelines",
    },
    "technical_quality": {
        "weight": 0.25,
        "description": "Overlay resolution 1920x1080, no compression artifacts, clarity and sharpness",
    },
    "etsy_compliance": {
        "weight": 0.20,
        "description": "Listing images ≥2000px, first image landscape/square, file formats correct, ZIPs <20MB, AI disclosure present",
    },
    "visual_appeal": {
        "weight": 0.25,
        "description": "Professional finish, clear focal point, appropriate margins for overlays",
    },
}


__all__ = [
    "EvaluationScore",
    "PackEvaluation",
    "validate_technical_overlays",
    "validate_etsy_listings",
    "validate_etsy_downloads",
    "check_critical_issues",
    "compute_automated_score",
    "calculate_overall_score",
    "RUBRIC_DIMENSIONS",
]
