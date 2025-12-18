"""PM (Project Manager) agent for multi-round workflow control."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

from ..config import PackConfig
from ..multi_agent.state import WorkflowState, RoundState
from ..multi_agent.rubric import PackEvaluation

logger = logging.getLogger(__name__)


def prepare_round_brief(
    round_num: int,
    config: PackConfig,
    workflow_state: WorkflowState,
) -> Dict[str, str]:
    """Prepare briefing for the current round.

    Args:
        round_num: Current round number (1-indexed)
        config: Pack configuration
        workflow_state: Current workflow state

    Returns:
        Dictionary with round context
    """
    brief = {
        "round_num": str(round_num),
        "pack_name": workflow_state.pack_name,
        "theme": config.theme,
        "max_rounds": str(workflow_state.max_rounds),
        "threshold": str(workflow_state.quality_threshold),
    }

    # First round
    if round_num == 1:
        brief["context"] = "Initial generation round. Focus on establishing baseline quality."
        brief["previous_score"] = "N/A"
        brief["deltas"] = "None (first round)"
    else:
        # Subsequent rounds
        prev_eval = workflow_state.latest_evaluation
        if prev_eval:
            brief["context"] = f"Improvement round. Previous score: {prev_eval.overall_score:.1f}/10"
            brief["previous_score"] = f"{prev_eval.overall_score:.1f}"
            brief["deltas"] = "\n".join(f"  - {d}" for d in prev_eval.deltas)

            # Add score trend
            trend = workflow_state.score_trend
            if len(trend) >= 2:
                delta = trend[-1] - trend[-2]
                brief["score_trend"] = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
            else:
                brief["score_trend"] = "N/A"
        else:
            brief["context"] = "Continuing workflow (no previous evaluation)"
            brief["previous_score"] = "N/A"
            brief["deltas"] = "None available"

    logger.info(f"[PM] Round {round_num} brief prepared")
    return brief


def determine_variant_count(round_num: int, max_rounds: int) -> int:
    """Determine number of variants to generate for this round.

    Strategy (lighter payload for API + critic):
    - Round 1: 3 variants (exploration)
    - Round 2: 2 variants (refinement)
    - Round 3+: 1 variant (polish)

    Args:
        round_num: Current round number (1-indexed)
        max_rounds: Maximum rounds configured

    Returns:
        Number of variants to generate
    """
    if round_num == 1:
        return 3
    elif round_num == 2:
        return 2
    else:
        return 1


def check_stopping_conditions(
    workflow_state: WorkflowState,
) -> tuple[bool, str, str]:
    """Check if workflow should stop.

    Args:
        workflow_state: Current workflow state

    Returns:
        Tuple of (should_stop, decision, reason)
        - should_stop: True if workflow should stop
        - decision: "PASS", "BLOCKED", or "CONTINUE"
        - reason: Human-readable reason
    """
    should_continue, reason = workflow_state.should_continue()

    if not should_continue:
        # Determine decision type
        if "BLOCKED" in reason:
            return True, "BLOCKED", reason
        elif "PASS" in reason or "threshold" in reason.lower():
            return True, "PASS", reason
        else:
            # Max rounds reached
            latest_score = workflow_state.latest_score
            if latest_score and latest_score >= workflow_state.quality_threshold:
                return True, "PASS", f"Max rounds reached, but quality acceptable ({latest_score:.1f}/10)"
            else:
                return True, "CONTINUE", f"Max rounds reached with score {latest_score:.1f}/10"

    return False, "CONTINUE", reason


def generate_round_summary(
    round_num: int,
    evaluation: PackEvaluation,
    variants_generated: int,
    decision: str,
    reason: str,
) -> str:
    """Generate human-readable round summary.

    Args:
        round_num: Round number
        evaluation: Pack evaluation results
        variants_generated: Number of variants generated
        decision: PASS/BLOCKED/CONTINUE
        reason: Decision reason

    Returns:
        Formatted summary string
    """
    lines = [
        f"# Round {round_num:02d} Summary",
        f"",
        f"**Overall Score:** {evaluation.overall_score:.1f}/10",
        f"**Variants Generated:** {variants_generated}",
        f"",
        f"## Dimension Scores",
        f"",
    ]

    for dim_score in evaluation.dimension_scores:
        lines.append(
            f"- **{dim_score.dimension.replace('_', ' ').title()}:** "
            f"{dim_score.score:.1f}/10 (weight: {dim_score.weight*100:.0f}%)"
        )

    lines.extend([
        f"",
        f"## Critical Issues",
        f"",
    ])

    if evaluation.critical_issues:
        for issue in evaluation.critical_issues:
            lines.append(f"- ⚠️ {issue}")
    else:
        lines.append("なし (None)")

    lines.extend([
        f"",
        f"## Selected Images",
        f"",
    ])

    for kind, filename in sorted(evaluation.selected_images.items()):
        lines.append(f"- **{kind}:** {filename}")

    lines.extend([
        f"",
        f"## Improvement Deltas",
        f"",
    ])

    if evaluation.deltas:
        for i, delta in enumerate(evaluation.deltas, 1):
            lines.append(f"{i}. {delta}")
    else:
        lines.append("なし (None - quality threshold met)")

    lines.extend([
        f"",
        f"## Decision",
        f"",
        f"**{decision}** - {reason}",
        f"",
    ])

    return "\n".join(lines)


def log_workflow_progress(workflow_state: WorkflowState) -> None:
    """Log workflow progress to console.

    Args:
        workflow_state: Current workflow state
    """
    logger.info("=" * 60)
    logger.info(f"Workflow Progress: {workflow_state.pack_name}")
    logger.info("=" * 60)
    logger.info(f"Rounds completed: {len(workflow_state.rounds)}/{workflow_state.max_rounds}")

    if workflow_state.score_trend:
        score_str = " → ".join(f"{s:.1f}" for s in workflow_state.score_trend)
        logger.info(f"Score trend: {score_str}")

    if workflow_state.completed:
        logger.info(f"Status: COMPLETED - {workflow_state.completion_reason}")
    else:
        should_continue, reason = workflow_state.should_continue()
        if should_continue:
            logger.info(f"Status: IN PROGRESS - {reason}")
        else:
            logger.info(f"Status: READY TO FINALIZE - {reason}")

    logger.info("=" * 60)


__all__ = [
    "prepare_round_brief",
    "determine_variant_count",
    "check_stopping_conditions",
    "generate_round_summary",
    "log_workflow_progress",
]
