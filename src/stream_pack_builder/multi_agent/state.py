"""Multi-agent workflow state management."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from .rubric import PackEvaluation, EvaluationScore

logger = logging.getLogger(__name__)


@dataclass
class RoundState:
    """State for a single evaluation round."""

    round_num: int
    timestamp: str
    prompts_used: Dict[str, str]  # {kind: prompt_text}
    evaluation: Optional[PackEvaluation] = None
    variants_generated: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert PackEvaluation to dict if present
        if self.evaluation:
            data["evaluation"] = {
                "pack_name": self.evaluation.pack_name,
                "overall_score": self.evaluation.overall_score,
                "dimension_scores": [
                    {
                        "dimension": s.dimension,
                        "score": s.score,
                        "weight": s.weight,
                        "justification": s.justification,
                        "issues": s.issues,
                    }
                    for s in self.evaluation.dimension_scores
                ],
                "critical_issues": self.evaluation.critical_issues,
                "selected_images": self.evaluation.selected_images,
                "deltas": self.evaluation.deltas,
                "automated_checks_passed": self.evaluation.automated_checks_passed,
            }
        return data


@dataclass
class WorkflowState:
    """Complete state for multi-round workflow."""

    pack_name: str
    started_at: str
    max_rounds: int
    quality_threshold: float = 8.5
    rounds: List[RoundState] = field(default_factory=list)
    completed: bool = False
    completion_reason: str = ""

    @property
    def current_round(self) -> int:
        """Get current round number (1-indexed)."""
        return len(self.rounds) + 1

    @property
    def latest_evaluation(self) -> Optional[PackEvaluation]:
        """Get most recent evaluation."""
        if not self.rounds:
            return None
        return self.rounds[-1].evaluation

    @property
    def latest_deltas(self) -> List[str]:
        """Get improvement suggestions from latest round."""
        eval = self.latest_evaluation
        return eval.deltas if eval else []

    @property
    def latest_score(self) -> Optional[float]:
        """Get latest overall score."""
        eval = self.latest_evaluation
        return eval.overall_score if eval else None

    @property
    def score_trend(self) -> List[float]:
        """Get score progression across rounds."""
        return [
            r.evaluation.overall_score
            for r in self.rounds
            if r.evaluation
        ]

    def should_continue(self) -> tuple[bool, str]:
        """Determine if workflow should continue to next round.

        Returns:
            Tuple of (should_continue: bool, reason: str)
        """
        # No evaluation yet (first round)
        if not self.latest_evaluation:
            return True, "No evaluation yet"

        # Check critical issues (blocker)
        if self.latest_evaluation.critical_issues:
            return False, f"BLOCKED by {len(self.latest_evaluation.critical_issues)} critical issue(s)"

        # Check quality threshold
        if self.latest_evaluation.passes_threshold:
            return False, f"PASS - Score {self.latest_score:.1f} ≥ threshold {self.quality_threshold}"

        # Check max rounds
        if self.current_round > self.max_rounds:
            return False, f"Max rounds ({self.max_rounds}) reached"

        # Continue
        return True, f"Score {self.latest_score:.1f} < threshold {self.quality_threshold}"

    def add_round(self, round_state: RoundState) -> None:
        """Add completed round to workflow state."""
        self.rounds.append(round_state)
        logger.info(f"Round {round_state.round_num} completed: score={round_state.evaluation.overall_score if round_state.evaluation else 'N/A'}")

    def finalize(self, reason: str) -> None:
        """Mark workflow as completed."""
        self.completed = True
        self.completion_reason = reason
        logger.info(f"Workflow completed: {reason}")

    def save(self, pack_dir: Path) -> None:
        """Save workflow state to JSON file.

        Args:
            pack_dir: Pack directory (will save to pack_dir/qa/workflow_state.json)
        """
        qa_dir = pack_dir / "qa"
        qa_dir.mkdir(exist_ok=True)

        state_file = qa_dir / "workflow_state.json"

        # Convert to dict
        data = asdict(self)
        # Convert RoundState objects
        data["rounds"] = [r.to_dict() for r in self.rounds]

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.debug(f"Workflow state saved to {state_file}")

    @classmethod
    def load(cls, pack_dir: Path) -> Optional["WorkflowState"]:
        """Load workflow state from JSON file.

        Args:
            pack_dir: Pack directory

        Returns:
            WorkflowState if file exists, None otherwise
        """
        state_file = pack_dir / "qa" / "workflow_state.json"

        if not state_file.exists():
            return None

        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Reconstruct RoundState objects
        rounds = []
        for r_data in data.get("rounds", []):
            eval_data = r_data.get("evaluation")
            evaluation = None
            if eval_data:
                # Reconstruct EvaluationScore objects
                dimension_scores = [
                    EvaluationScore(**s) for s in eval_data["dimension_scores"]
                ]
                evaluation = PackEvaluation(
                    pack_name=eval_data["pack_name"],
                    overall_score=eval_data["overall_score"],
                    dimension_scores=dimension_scores,
                    critical_issues=eval_data["critical_issues"],
                    selected_images=eval_data["selected_images"],
                    deltas=eval_data["deltas"],
                    automated_checks_passed=eval_data["automated_checks_passed"],
                )

            rounds.append(RoundState(
                round_num=r_data["round_num"],
                timestamp=r_data["timestamp"],
                prompts_used=r_data["prompts_used"],
                evaluation=evaluation,
                variants_generated=r_data.get("variants_generated", 0),
                cost_usd=r_data.get("cost_usd", 0.0),
            ))

        state = cls(
            pack_name=data["pack_name"],
            started_at=data["started_at"],
            max_rounds=data["max_rounds"],
            quality_threshold=data.get("quality_threshold", 8.5),
            rounds=rounds,
            completed=data.get("completed", False),
            completion_reason=data.get("completion_reason", ""),
        )

        logger.debug(f"Workflow state loaded from {state_file}")
        return state

    @classmethod
    def create_new(cls, pack_name: str, max_rounds: int, quality_threshold: float = 8.5) -> "WorkflowState":
        """Create new workflow state for a pack.

        Args:
            pack_name: Name of the pack
            max_rounds: Maximum number of rounds
            quality_threshold: Quality threshold for passing (default 8.5)

        Returns:
            New WorkflowState instance
        """
        return cls(
            pack_name=pack_name,
            started_at=datetime.now(timezone.utc).isoformat(),
            max_rounds=max_rounds,
            quality_threshold=quality_threshold,
        )


__all__ = ["RoundState", "WorkflowState"]
