"""Test module for Critic agent evaluation (Phase 1 MVP).

Usage:
    python -m stream_pack_builder.test_critic <pack_name> [--dry-run] [-v]

Example:
    python -m stream_pack_builder.test_critic sample_pack
    python -m stream_pack_builder.test_critic neon_cyberpunk --dry-run -v
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

from .agents.critic import evaluate_pack
from .automation.qa_log import generate_qa_log
from .config import PackConfig
from .utils import packs_root, setup_logging

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


def main() -> int:
    """Main entry point for test_critic module."""
    parser = argparse.ArgumentParser(
        description="Test Critic agent evaluation on a pack (Phase 1 MVP)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m stream_pack_builder.test_critic sample_pack
  python -m stream_pack_builder.test_critic neon_cyberpunk --dry-run
  python -m stream_pack_builder.test_critic my_pack -v
        """,
    )

    parser.add_argument(
        "pack_name",
        help="Name of the pack directory under packs/",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip OpenAI API call and return mock evaluation",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="OpenAI model ID to use (default: gpt-4o)",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    # Resolve pack directory
    pack_dir = packs_root() / args.pack_name

    if not pack_dir.exists():
        logger.error(f"Pack directory not found: {pack_dir}")
        logger.info(f"Available packs in {packs_root()}:")
        for p in packs_root().iterdir():
            if p.is_dir() and not p.name.startswith("."):
                logger.info(f"  - {p.name}")
        return 1

    # Load config
    config_path = pack_dir / "config.yaml"
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        return 1

    try:
        config = PackConfig.load(config_path)
        logger.info(f"Loaded config for pack: {args.pack_name}")
        logger.info(f"  Theme: {config.theme}")
        logger.info(f"  Resolution: {config.resolution.width}x{config.resolution.height}")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return 1

    # Check for 03_final/ directory
    final_dir = pack_dir / "03_final"
    if not final_dir.exists():
        logger.error(f"Final images directory not found: {final_dir}")
        logger.info(
            f"\nPlease run the following commands first:\n"
            f"  stream-pack build {args.pack_name} --num-variants 2\n"
            f"  stream-pack postprocess {args.pack_name}\n"
        )
        return 1

    image_count = len(list(final_dir.glob("*.png")))

    # If dry-run and no images, create lightweight placeholders so mock評価が通る
    if image_count == 0 and args.dry_run:
        logger.info(f"No images found in {final_dir}, creating placeholders for dry-run...")
        final_dir.mkdir(exist_ok=True)
        for kind in config.prompts.keys():
            placeholder = Image.new(
                "RGB",
                (config.resolution.width, config.resolution.height),
                color=(64, 64, 96),
            )
            placeholder_path = final_dir / f"{kind}_01.png"
            placeholder.save(placeholder_path, format="PNG")
        image_count = len(list(final_dir.glob("*.png")))

    if image_count == 0:
        logger.error(f"No PNG images found in {final_dir}")
        return 1

    logger.info(f"Found {image_count} images to evaluate")

    # Run evaluation
    logger.info("Starting Critic evaluation...")
    start_time = time.time()

    try:
        evaluation = evaluate_pack(
            pack_name=args.pack_name,
            config=config,
            pack_dir=pack_dir,
            model=args.model,
            dry_run=args.dry_run,
        )
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    runtime_seconds = time.time() - start_time

    # Display results
    logger.info("\n" + "=" * 60)
    logger.info("EVALUATION RESULTS")
    logger.info("=" * 60)
    logger.info(f"Pack: {evaluation.pack_name}")
    logger.info(f"Overall Score: {evaluation.overall_score:.1f}/10")
    logger.info("")

    logger.info("Dimension Scores:")
    for dim_score in evaluation.dimension_scores:
        logger.info(
            f"  {dim_score.dimension.replace('_', ' ').title()}: "
            f"{dim_score.score:.1f}/10 (weight: {dim_score.weight:.0%})"
        )
        logger.info(f"    {dim_score.justification}")
        if dim_score.issues:
            for issue in dim_score.issues:
                logger.info(f"      - {issue}")

    logger.info("")

    if evaluation.critical_issues:
        logger.error("CRITICAL ISSUES:")
        for issue in evaluation.critical_issues:
            logger.error(f"  - {issue}")
        logger.info("")

    if evaluation.selected_images:
        logger.info("Selected Images (Auto-Curated):")
        for screen_type, filename in evaluation.selected_images.items():
            logger.info(f"  {screen_type}: {filename}")
        logger.info("")

    if evaluation.deltas:
        logger.info("Improvement Deltas for Next Round:")
        for idx, delta in enumerate(evaluation.deltas, start=1):
            logger.info(f"  {idx}. {delta}")
        logger.info("")

    # Generate QA log
    try:
        qa_log_path = generate_qa_log(
            evaluation,
            pack_dir,
            round_num=1,
            runtime_seconds=runtime_seconds,
        )
        logger.info(f"QA log saved: {qa_log_path}")
    except Exception as e:
        logger.warning(f"Failed to generate QA log: {e}")

    # Final verdict
    logger.info("=" * 60)
    if evaluation.passes_threshold:
        logger.info("✅ PASSED - Score meets threshold (≥8.5) with no critical issues")
        return 0
    elif evaluation.critical_issues:
        logger.error("🚫 BLOCKED - Critical issues must be resolved")
        return 1
    else:
        logger.info(f"⏭️ CONTINUE - Score ({evaluation.overall_score:.1f}) below threshold (8.5)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
