"""QA log generation for evaluation reports."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from ..multi_agent.rubric import PackEvaluation

logger = logging.getLogger(__name__)


def generate_qa_log(
    evaluation: PackEvaluation,
    pack_dir: Path,
    round_num: int = 1,
    *,
    runtime_seconds: float | None = None,
    cost_usd: float | None = None,
) -> Path:
    """Generate QA log markdown file from evaluation.

    Args:
        evaluation: PackEvaluation result.
        pack_dir: Path to pack directory.
        round_num: Round number (for multi-round workflows).
        runtime_seconds: Optional runtime in seconds.
        cost_usd: Optional API cost in USD.

    Returns:
        Path to generated QA log file.
    """
    qa_dir = pack_dir / "qa"
    qa_dir.mkdir(exist_ok=True)

    log_path = qa_dir / f"round{round_num:02d}.md"

    # Build markdown content
    content_lines = [
        f"# Round {round_num:02d} - Quality Assurance Report",
        "",
        f"**Pack:** {evaluation.pack_name}",
        f"**Date:** {datetime.utcnow().isoformat()}Z",
        "",
        "## Critic Evaluation",
        "",
        f"- **Overall Score:** {evaluation.overall_score:.1f}/10",
    ]

    # Add dimension scores
    for dim_score in evaluation.dimension_scores:
        content_lines.append(
            f"- **{dim_score.dimension.replace('_', ' ').title()}:** "
            f"{dim_score.score:.1f}/10 - {dim_score.justification}"
        )

    # Add critical issues
    content_lines.extend(["", "## Critical Issues", ""])
    if evaluation.critical_issues:
        for issue in evaluation.critical_issues:
            content_lines.append(f"- {issue}")
    else:
        content_lines.append("なし")

    # Add selected images
    content_lines.extend(["", "## Selected Images (Auto-Curated)", ""])
    if evaluation.selected_images:
        for screen_type, filename in evaluation.selected_images.items():
            content_lines.append(f"- {screen_type}: {filename}")
    else:
        content_lines.append("(No images selected)")

    # Add deltas
    content_lines.extend(["", "## Deltas for Next Round", ""])
    if evaluation.deltas:
        for idx, delta in enumerate(evaluation.deltas, start=1):
            content_lines.append(f"{idx}. {delta}")
    else:
        content_lines.append("(No improvements suggested)")

    # Add decision
    content_lines.extend(["", "## Next Steps", ""])

    if evaluation.passes_threshold:
        content_lines.extend([
            f"**Decision:** COMPLETE",
            f"**Reason:** Score ({evaluation.overall_score:.1f}) ≥ threshold (8.5) and no critical issues",
        ])
    elif evaluation.critical_issues:
        content_lines.extend([
            f"**Decision:** BLOCKED",
            f"**Reason:** Critical issues must be resolved",
        ])
    else:
        content_lines.extend([
            f"**Decision:** CONTINUE to Round {round_num + 1:02d}",
            f"**Reason:** Score ({evaluation.overall_score:.1f}) < threshold (8.5)",
        ])

    # Add metadata footer
    content_lines.extend(["", "---"])

    if runtime_seconds is not None:
        minutes, seconds = divmod(int(runtime_seconds), 60)
        content_lines.append(f"**Runtime:** {minutes}分{seconds}秒")

    if cost_usd is not None:
        content_lines.append(f"**Cost:** ${cost_usd:.2f} USD")

    content_lines.append(f"**Generated:** Multi-Agent Critic v1.0.0 (Phase 1 MVP)")

    # Write file
    content = "\n".join(content_lines) + "\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"QA log saved: {log_path}")
    return log_path


def generate_summary_report(
    evaluations: list[PackEvaluation],
    pack_dir: Path,
    *,
    total_runtime_seconds: float | None = None,
    total_cost_usd: float | None = None,
) -> Path:
    """Generate summary report for multi-round evaluations.

    Args:
        evaluations: List of evaluations from all rounds.
        pack_dir: Path to pack directory.
        total_runtime_seconds: Optional total runtime.
        total_cost_usd: Optional total cost.

    Returns:
        Path to summary report file.
    """
    qa_dir = pack_dir / "qa"
    qa_dir.mkdir(exist_ok=True)

    summary_path = qa_dir / "summary.md"

    # Build markdown content
    content_lines = [
        f"# Multi-Round Evaluation Summary",
        "",
        f"**Pack:** {evaluations[0].pack_name if evaluations else 'Unknown'}",
        f"**Total Rounds:** {len(evaluations)}",
        f"**Date:** {datetime.utcnow().isoformat()}Z",
        "",
        "## Score Progression",
        "",
    ]

    # Score progression table
    if evaluations:
        content_lines.append("| Round | Overall | Brand | Technical | Etsy | Visual | Decision |")
        content_lines.append("|-------|---------|-------|-----------|------|--------|----------|")

        for idx, eval_result in enumerate(evaluations, start=1):
            # Extract dimension scores by name
            dim_scores = {ds.dimension: ds.score for ds in eval_result.dimension_scores}
            brand = dim_scores.get("brand_consistency", 0)
            tech = dim_scores.get("technical_quality", 0)
            etsy = dim_scores.get("etsy_compliance", 0)
            visual = dim_scores.get("visual_appeal", 0)

            if eval_result.passes_threshold:
                decision = "✅ PASS"
            elif eval_result.critical_issues:
                decision = "🚫 BLOCKED"
            else:
                decision = "⏭️ CONTINUE"

            content_lines.append(
                f"| {idx:02d} | {eval_result.overall_score:.1f} | "
                f"{brand:.1f} | {tech:.1f} | {etsy:.1f} | {visual:.1f} | {decision} |"
            )

    # Final result
    content_lines.extend(["", "## Final Result", ""])

    if evaluations:
        final_eval = evaluations[-1]
        if final_eval.passes_threshold:
            content_lines.append(
                f"✅ **PASSED** with score {final_eval.overall_score:.1f}/10 "
                f"(Round {len(evaluations)})"
            )
        elif final_eval.critical_issues:
            content_lines.append(
                f"🚫 **BLOCKED** due to critical issues "
                f"(Round {len(evaluations)})"
            )
        else:
            content_lines.append(
                f"⏸️ **INCOMPLETE** - stopped at Round {len(evaluations)} "
                f"with score {final_eval.overall_score:.1f}/10"
            )
    else:
        content_lines.append("(No evaluations recorded)")

    # Metadata footer
    content_lines.extend(["", "---"])

    if total_runtime_seconds is not None:
        minutes, seconds = divmod(int(total_runtime_seconds), 60)
        content_lines.append(f"**Total Runtime:** {minutes}分{seconds}秒")

    if total_cost_usd is not None:
        content_lines.append(f"**Total Cost:** ${total_cost_usd:.2f} USD")

    content_lines.append(f"**Generated:** Multi-Agent Orchestrator v1.0.0")

    # Write file
    content = "\n".join(content_lines) + "\n"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Summary report saved: {summary_path}")
    return summary_path


__all__ = ["generate_qa_log", "generate_summary_report"]
