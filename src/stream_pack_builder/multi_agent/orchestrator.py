"""Multi-agent orchestrator for iterative pack improvement workflow."""
from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from ..config import PackConfig
from ..generator import build_pack
from ..postprocess import postprocess_selected
from ..utils import packs_root, RAW_DIR, SELECTED_DIR, FINAL_DIR

from .state import WorkflowState, RoundState
from ..agents.pm import (
    prepare_round_brief,
    determine_variant_count,
    check_stopping_conditions,
    generate_round_summary,
    log_workflow_progress,
)
from ..agents.prompt_engineer import refine_prompts, generate_prompt_diff, validate_prompts
from ..agents.art_director import (
    get_default_brand_tokens,
    adjust_brand_tokens,
    validate_brand_tokens,
    generate_brand_summary,
)
from ..agents.critic import evaluate_pack
from ..automation.qa_log import generate_qa_log

logger = logging.getLogger(__name__)


def auto_select_images(pack_dir: Path, dry_run: bool = False) -> int:
    """Auto-select all generated images from 01_raw/ to 02_selected/.

    Phase 2 simple implementation: Copy all images.
    Phase 3 will use Critic's selected_images for intelligent selection.

    Args:
        pack_dir: Pack directory
        dry_run: Skip file operations if True

    Returns:
        Number of images selected
    """
    raw_dir = pack_dir / RAW_DIR
    selected_dir = pack_dir / SELECTED_DIR

    if not raw_dir.exists():
        logger.warning(f"Raw directory not found: {raw_dir}")
        return 0

    # Clear selected directory
    if selected_dir.exists() and not dry_run:
        shutil.rmtree(selected_dir)
    selected_dir.mkdir(exist_ok=True)

    # Copy all images
    count = 0
    for img_path in sorted(raw_dir.glob("*.png")):
        dest_path = selected_dir / img_path.name
        if dry_run:
            logger.debug(f"[dry-run] Would copy {img_path.name} to selected/")
        else:
            shutil.copy2(img_path, dest_path)
        count += 1

    logger.info(f"Auto-selected {count} images from 01_raw/ to 02_selected/")
    return count


def update_config_prompts(
    config_path: Path,
    new_prompts: dict,
    dry_run: bool = False,
) -> None:
    """Update config.yaml with new prompts.

    Args:
        config_path: Path to config.yaml
        new_prompts: New prompts dict
        dry_run: Skip file write if True
    """
    if dry_run:
        logger.info("[dry-run] Would update config.yaml with refined prompts")
        return

    # Read existing config
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    # Update prompts
    config_data["prompts"] = new_prompts

    # Write back
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False)

    logger.info(f"Updated config.yaml with refined prompts")


def update_config_brand_tokens(
    config_path: Path,
    new_brand_tokens: dict,
    dry_run: bool = False,
) -> None:
    """Update config.yaml with new brand tokens.

    Args:
        config_path: Path to config.yaml
        new_brand_tokens: New brand tokens dict
        dry_run: Skip file write if True
    """
    if dry_run:
        logger.info("[dry-run] Would update config.yaml with refined brand tokens")
        return

    # Read existing config
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    # Update brand_tokens
    config_data["brand_tokens"] = new_brand_tokens

    # Write back
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False)

    logger.info(f"Updated config.yaml with refined brand tokens")


def run_round(
    pack_name: str,
    pack_dir: Path,
    config_path: Path,
    round_num: int,
    workflow_state: WorkflowState,
    dry_run: bool = False,
    seed: Optional[int] = None,
) -> RoundState:
    """Execute a single round of the multi-agent workflow.

    Args:
        pack_name: Pack name
        pack_dir: Pack directory path
        config_path: Path to config.yaml
        round_num: Current round number (1-indexed)
        workflow_state: Current workflow state
        dry_run: Skip API calls and file writes if True
        seed: Optional seed for reproducibility

    Returns:
        RoundState for this round
    """
    logger.info("=" * 60)
    logger.info(f"ROUND {round_num:02d} START")
    logger.info("=" * 60)

    round_start = time.time()

    # Load current config
    config = PackConfig.load(config_path)

    # PM: Prepare brief
    brief = prepare_round_brief(round_num, config, workflow_state)
    logger.info(f"[PM] Round brief: {brief['context']}")

    # Determine variant count
    num_variants = determine_variant_count(round_num, workflow_state.max_rounds)
    logger.info(f"[PM] Variants to generate: {num_variants}")

    # Prompt Engineer: Refine prompts (skip round 1)
    current_prompts = config.prompts.copy()
    if round_num > 1 and workflow_state.latest_deltas:
        logger.info("[Prompt Engineer] Applying deltas to prompts...")

        # Extract dimension scores from latest evaluation
        dimension_scores = {
            score.dimension: score.score
            for score in workflow_state.latest_evaluation.dimension_scores
        } if workflow_state.latest_evaluation else {}

        # Refine prompts (LLM-based in Phase 3, rule-based fallback)
        refined_prompts = refine_prompts(
            original_prompts=current_prompts,
            deltas=workflow_state.latest_deltas,
            dimension_scores=dimension_scores,
            round_num=round_num,
            use_llm=True,  # Enable LLM-based refinement
        )

        # Validate prompts
        warnings = validate_prompts(refined_prompts)
        if warnings:
            logger.warning(f"[Prompt Engineer] Validation warnings: {warnings}")

        # Show diff
        diff = generate_prompt_diff(current_prompts, refined_prompts)
        if diff:
            logger.info("[Prompt Engineer] Prompt changes:")
            for line in diff[:10]:  # Limit output
                logger.info(f"  {line}")

        # Update config.yaml
        update_config_prompts(config_path, refined_prompts, dry_run=dry_run)

        # Reload config with new prompts
        config = PackConfig.load(config_path)
    else:
        logger.info("[Prompt Engineer] Using original prompts (Round 1)")

    # Art Director: Adjust brand tokens (Phase 3)
    if round_num > 1 and workflow_state.latest_evaluation:
        logger.info("[Art Director] Adjusting brand tokens based on Critic feedback...")

        # Get current brand tokens or create defaults
        if config.brand_tokens is None:
            logger.info("[Art Director] No brand tokens found, creating defaults")
            brand_dict = get_default_brand_tokens(config.theme)
        else:
            brand_dict = config.brand_tokens.to_dict()

        # Extract dimension scores from latest evaluation
        dimension_scores = {
            score.dimension: score.score
            for score in workflow_state.latest_evaluation.dimension_scores
        }

        # Adjust tokens based on Critic feedback
        refined_brand_tokens, brand_changes = adjust_brand_tokens(
            original_tokens=brand_dict,
            critic_deltas=workflow_state.latest_deltas,
            dimension_scores=dimension_scores,
            round_num=round_num,
            dry_run=dry_run,
        )

        if brand_changes:
            logger.info(f"[Art Director] Made {len(brand_changes)} brand token adjustments:")
            for change in brand_changes[:3]:  # Show first 3 changes
                logger.info(f"  - {change['token']}: {change['action']} - {change['rationale'][:50]}...")

        # Validate refined tokens
        token_warnings = validate_brand_tokens(refined_brand_tokens)
        if token_warnings:
            logger.warning(f"[Art Director] Token validation warnings: {token_warnings}")

        # Update config.yaml with refined brand tokens
        if not dry_run:
            update_config_brand_tokens(config_path, refined_brand_tokens)
            config = PackConfig.load(config_path)

    elif round_num == 1:
        # Initialize brand tokens for first round
        if config.brand_tokens is None:
            logger.info("[Art Director] Initializing default brand tokens (Round 1)")
            brand_dict = get_default_brand_tokens(config.theme)
            if not dry_run:
                update_config_brand_tokens(config_path, brand_dict)
                config = PackConfig.load(config_path)

    # Executor: Build pack
    logger.info(f"[Executor] Generating {num_variants} variants...")
    build_pack(
        config=config,
        pack_dir=pack_dir,
        num_variants=num_variants,
        seed=seed,
        dry_run=dry_run,
    )

    # Auto-select images
    selected_count = auto_select_images(pack_dir, dry_run=dry_run)
    logger.info(f"[Executor] Auto-selected {selected_count} images")

    # Executor: Postprocess
    logger.info("[Executor] Post-processing...")
    postprocess_selected(
        config=config,
        pack_dir=pack_dir,
        dry_run=dry_run,
    )

    # Critic: Evaluate
    logger.info("[Critic] Evaluating pack...")
    evaluation = evaluate_pack(
        pack_name=pack_name,
        config=config,
        pack_dir=pack_dir,
        dry_run=dry_run,
    )

    logger.info(f"[Critic] Overall score: {evaluation.overall_score:.1f}/10")
    if evaluation.critical_issues:
        logger.warning(f"[Critic] Critical issues: {evaluation.critical_issues}")

    # PM: Check stopping conditions
    should_stop, decision, reason = check_stopping_conditions(workflow_state)
    logger.info(f"[PM] Decision: {decision} - {reason}")

    # Generate round summary
    summary = generate_round_summary(
        round_num=round_num,
        evaluation=evaluation,
        variants_generated=num_variants,
        decision=decision,
        reason=reason,
    )

    # Write QA log
    generate_qa_log(
        evaluation=evaluation,
        pack_dir=pack_dir,
        round_num=round_num,
        runtime_seconds=time.time() - round_start,
    )

    # Create round state
    round_state = RoundState(
        round_num=round_num,
        timestamp=datetime.now(timezone.utc).isoformat(),
        prompts_used=config.prompts,
        evaluation=evaluation,
        variants_generated=num_variants,
        cost_usd=0.0,  # TODO: Track actual costs in Phase 3
    )

    logger.info(f"ROUND {round_num:02d} COMPLETE ({time.time() - round_start:.1f}s)")
    logger.info("=" * 60)

    return round_state


def run_multi_agent_workflow(
    pack_name: str,
    max_rounds: int = 3,
    quality_threshold: float = 8.5,
    dry_run: bool = False,
    seed: Optional[int] = None,
    upload_to_etsy: bool = False,
) -> WorkflowState:
    """Run complete multi-agent workflow for a pack.

    Args:
        pack_name: Name of the pack to process
        max_rounds: Maximum number of rounds (default 3)
        quality_threshold: Quality threshold for passing (default 8.5)
        dry_run: Skip API calls and file writes if True
        seed: Optional seed for reproducibility
        upload_to_etsy: Upload to Etsy after Phase 4 (default False)

    Returns:
        Final WorkflowState

    Raises:
        FileNotFoundError: If pack directory or config not found
    """
    logger.info("=" * 60)
    logger.info(f"MULTI-AGENT WORKFLOW START: {pack_name}")
    logger.info(f"Max rounds: {max_rounds}, Threshold: {quality_threshold}")
    logger.info("=" * 60)

    workflow_start = time.time()

    # Resolve pack directory
    pack_dir = packs_root() / pack_name
    if not pack_dir.exists():
        raise FileNotFoundError(f"Pack directory not found: {pack_dir}")

    config_path = pack_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    # Initialize or load workflow state
    workflow_state = WorkflowState.load(pack_dir)
    if workflow_state:
        logger.info("Resuming existing workflow...")
        log_workflow_progress(workflow_state)
    else:
        logger.info("Starting new workflow...")
        workflow_state = WorkflowState.create_new(
            pack_name=pack_name,
            max_rounds=max_rounds,
            quality_threshold=quality_threshold,
        )

    # Main loop
    while True:
        current_round = workflow_state.current_round

        # Check if we should continue before starting round
        should_continue, reason = workflow_state.should_continue()
        if not should_continue:
            logger.info(f"Stopping workflow: {reason}")
            workflow_state.finalize(reason)
            break

        # Run round
        round_state = run_round(
            pack_name=pack_name,
            pack_dir=pack_dir,
            config_path=config_path,
            round_num=current_round,
            workflow_state=workflow_state,
            dry_run=dry_run,
            seed=seed,
        )

        # Add round to state
        workflow_state.add_round(round_state)

        # Save state after each round
        workflow_state.save(pack_dir)

        # Check stopping conditions after adding round
        should_stop, decision, reason = check_stopping_conditions(workflow_state)
        if should_stop:
            logger.info(f"Stopping workflow: {decision} - {reason}")
            workflow_state.finalize(f"{decision}: {reason}")
            break

    # Final state save
    workflow_state.save(pack_dir)

    # Phase 4: Etsy Deliverables Automation
    if not dry_run:
        logger.info("=" * 60)
        logger.info("PHASE 4: ETSY DELIVERABLES GENERATION")
        logger.info("=" * 60)

        etsy_start = time.time()

        # Load final config
        config = PackConfig.load(config_path)

        # Generate listing photos (8 JPG)
        try:
            from ..etsy.listing_photos import generate_listing_photos
            photo_count = generate_listing_photos(pack_name, pack_dir, config, dry_run=False)
            logger.info(f"✓ Generated {photo_count} Etsy listing photos")
        except Exception as e:
            logger.error(f"✗ Failed to generate listing photos: {e}")

        # Create digital delivery files (4 ZIP)
        try:
            from ..etsy.digital_delivery import create_digital_delivery_files
            zip_files = create_digital_delivery_files(pack_name, pack_dir, config, dry_run=False)
            logger.info(f"✓ Created {len(zip_files)} digital delivery ZIPs")
        except Exception as e:
            logger.error(f"✗ Failed to create delivery files: {e}")

        logger.info(f"Phase 4 complete ({time.time() - etsy_start:.1f}s)")
        logger.info("=" * 60)
    else:
        logger.info("[dry-run] Phase 4: Etsy deliverables generation skipped")

    # Phase 5: Etsy Upload (optional)
    if upload_to_etsy and not dry_run:
        logger.info("=" * 60)
        logger.info("PHASE 5: ETSY UPLOAD")
        logger.info("=" * 60)

        upload_start = time.time()

        # Load final config
        config = PackConfig.load(config_path)

        # Upload to Etsy
        try:
            from ..etsy.uploader import upload_pack_to_etsy
            upload_result = upload_pack_to_etsy(
                pack_name=pack_name,
                pack_dir=pack_dir,
                config=config,
                workflow_state=workflow_state,
                dry_run=False,
            )

            if upload_result["success"]:
                logger.info(f"✓ Successfully uploaded to Etsy")
                logger.info(f"  Listing ID: {upload_result['listing_id']}")
                logger.info(f"  URL: {upload_result['listing_url']}")
                logger.info(f"  Photos: {upload_result['photos_uploaded']}")
                logger.info(f"  Files: {upload_result['files_uploaded']}")
            else:
                logger.error(f"✗ Etsy upload failed: {upload_result.get('error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"✗ Etsy upload failed: {e}")

        logger.info(f"Phase 5 complete ({time.time() - upload_start:.1f}s)")
        logger.info("=" * 60)
    elif upload_to_etsy and dry_run:
        logger.info("[dry-run] Phase 5: Etsy upload skipped")

    # Log final summary
    logger.info("=" * 60)
    logger.info(f"WORKFLOW COMPLETE: {pack_name}")
    logger.info(f"Total rounds: {len(workflow_state.rounds)}")
    logger.info(f"Score progression: {' → '.join(f'{s:.1f}' for s in workflow_state.score_trend)}")
    logger.info(f"Final decision: {workflow_state.completion_reason}")
    logger.info(f"Total time: {time.time() - workflow_start:.1f}s")
    logger.info("=" * 60)

    return workflow_state


__all__ = [
    "auto_select_images",
    "update_config_prompts",
    "run_round",
    "run_multi_agent_workflow",
]
