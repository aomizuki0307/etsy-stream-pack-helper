"""Critic agent for evaluating stream pack quality."""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any

from ..config import PackConfig
from ..multi_agent.rubric import (
    PackEvaluation,
    EvaluationScore,
    check_critical_issues,
    compute_automated_score,
    calculate_overall_score,
    RUBRIC_DIMENSIONS,
)

logger = logging.getLogger(__name__)


def encode_image_base64(image_path: Path) -> str:
    """Encode image to base64 for OpenAI API.

    Args:
        image_path: Path to image file.

    Returns:
        Base64-encoded image string.
    """
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def load_system_prompt() -> str:
    """Load Critic system prompt from prompts/critic_system.txt.

    Returns:
        System prompt text.
    """
    # Assuming prompts/ is at project root
    prompt_path = Path(__file__).parent.parent.parent.parent / "prompts" / "critic_system.txt"

    if not prompt_path.exists():
        logger.warning(f"Critic system prompt not found at {prompt_path}, using fallback")
        return "You are an expert quality evaluator for streaming overlay images. Evaluate them objectively."

    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def build_evaluation_prompt(
    pack_name: str,
    config: PackConfig,
    images_to_evaluate: Dict[str, List[Path]],
    automated_score: float,
    automated_issues: List[str],
) -> str:
    """Build the evaluation prompt with context.

    Args:
        pack_name: Name of the pack being evaluated.
        config: Pack configuration.
        images_to_evaluate: Dict of {screen_type: [image_paths]}.
        automated_score: Pre-computed automated technical score.
        automated_issues: Issues found by automated checks.

    Returns:
        Formatted prompt string.
    """
    prompt_parts = [
        f"# Pack Evaluation Request",
        f"",
        f"**Pack Name:** {pack_name}",
        f"**Theme:** {config.theme}",
        f"**Target Resolution:** {config.resolution.width}x{config.resolution.height}",
        f"",
        f"## Automated Technical Checks",
        f"",
        f"**Automated Score:** {automated_score}/10",
    ]

    if automated_issues:
        prompt_parts.append(f"**Issues Found:**")
        for issue in automated_issues:
            prompt_parts.append(f"- {issue}")
    else:
        prompt_parts.append(f"**No automated issues found.**")

    prompt_parts.extend([
        f"",
        f"## Images to Evaluate",
        f"",
    ])

    for screen_type, paths in images_to_evaluate.items():
        prompt_parts.append(f"### {screen_type}")
        prompt_parts.append(f"Variants: {len(paths)}")
        for path in paths:
            prompt_parts.append(f"- {path.name}")
        prompt_parts.append("")

    prompt_parts.extend([
        f"## Your Task",
        f"",
        f"1. Evaluate ALL images using the 4-dimension rubric",
        f"2. Identify any critical issues",
        f"3. Select the BEST variant for each screen type",
        f"4. Provide 3-5 actionable improvement deltas",
        f"",
        f"Respond ONLY with valid JSON matching the specified output format.",
    ])

    return "\n".join(prompt_parts)


def prepare_vision_messages(
    system_prompt: str,
    evaluation_prompt: str,
    images_to_evaluate: Dict[str, List[Path]],
    max_images: int = 20,
) -> List[Dict[str, Any]]:
    """Prepare messages for OpenAI Vision API.

    Args:
        system_prompt: System-level instructions.
        evaluation_prompt: Specific evaluation request.
        images_to_evaluate: Dict of {screen_type: [image_paths]}.
        max_images: Maximum number of images to send (cost control).

    Returns:
        List of message dictionaries for OpenAI API.
    """
    messages = [
        {"role": "system", "content": system_prompt},
    ]

    # Build user message with images
    content_parts = [{"type": "text", "text": evaluation_prompt}]

    # Flatten image paths and take first max_images
    all_images = []
    for screen_type, paths in images_to_evaluate.items():
        for path in paths:
            all_images.append((screen_type, path))
            if len(all_images) >= max_images:
                break
        if len(all_images) >= max_images:
            break

    # Add images to content
    for screen_type, image_path in all_images:
        try:
            image_b64 = encode_image_base64(image_path)
            content_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_b64}",
                    "detail": "low",  # Reduce payload to avoid request size errors
                },
            })
        except Exception as e:
            logger.warning(f"Failed to encode image {image_path}: {e}")

    messages.append({"role": "user", "content": content_parts})

    return messages


def parse_critic_response(response_text: str) -> Dict[str, Any]:
    """Parse JSON response from Critic.

    Args:
        response_text: Raw text response from model.

    Returns:
        Parsed JSON dictionary.

    Raises:
        ValueError: If response is not valid JSON.
    """
    # Try to extract JSON from markdown code blocks if present
    text = response_text.strip()

    if "```json" in text:
        # Extract content between ```json and ```
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end != -1:
            text = text[start:end].strip()
    elif "```" in text:
        # Extract content between ``` and ```
        start = text.find("```") + 3
        end = text.find("```", start)
        if end != -1:
            text = text[start:end].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Critic response as JSON: {e}")
        logger.debug(f"Raw response: {response_text[:500]}")
        raise ValueError(f"Critic response is not valid JSON: {e}")


def evaluate_pack(
    pack_name: str,
    config: PackConfig,
    pack_dir: Path,
    *,
    model: str = "gpt-4o",  # Note: Will use gpt-5-mini in production
    dry_run: bool = False,
) -> PackEvaluation:
    """Evaluate a stream pack using the Critic agent.

    Args:
        pack_name: Name of the pack.
        config: Pack configuration.
        pack_dir: Path to pack directory.
        model: OpenAI model ID (default: gpt-4o for Phase 1 MVP).
        dry_run: Skip API call and return mock evaluation.

    Returns:
        PackEvaluation with scores and recommendations.

    Raises:
        ValueError: If OpenAI API key not set or response invalid.
        FileNotFoundError: If no images found to evaluate.
    """
    # Check for OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key and not dry_run:
        raise ValueError(
            "OPENAI_API_KEY environment variable not set. "
            "Set it to use the Critic agent."
        )

    # Collect images to evaluate from 03_final/
    final_dir = pack_dir / "03_final"
    if not final_dir.exists():
        raise FileNotFoundError(f"Final images directory not found: {final_dir}")

    # Group images by screen type
    images_to_evaluate: Dict[str, List[Path]] = {}
    for img_path in sorted(final_dir.glob("*.png")):
        # Extract screen type from filename (e.g., "starting_01.png" -> "starting")
        parts = img_path.stem.split("_")
        if len(parts) >= 2:
            screen_type = "_".join(parts[:-1])  # Everything except last part (index)
        else:
            screen_type = img_path.stem

        if screen_type not in images_to_evaluate:
            images_to_evaluate[screen_type] = []
        images_to_evaluate[screen_type].append(img_path)

    if not images_to_evaluate:
        raise FileNotFoundError(f"No PNG images found in {final_dir}")

    logger.info(f"Found {sum(len(v) for v in images_to_evaluate.values())} images across {len(images_to_evaluate)} screen types")

    # Run automated checks
    automated_score, automated_issues = compute_automated_score(pack_dir)
    critical_issues = check_critical_issues(pack_dir)

    logger.info(f"Automated score: {automated_score}/10")
    if automated_issues:
        logger.warning(f"Automated issues: {automated_issues}")
    if critical_issues:
        logger.error(f"CRITICAL ISSUES: {critical_issues}")

    # Dry run: return mock evaluation
    if dry_run:
        logger.info("[DRY RUN] Skipping OpenAI API call")
        return _create_mock_evaluation(
            pack_name, images_to_evaluate, automated_score, automated_issues, critical_issues
        )

    # Load system prompt
    system_prompt = load_system_prompt()

    # Build evaluation prompt
    evaluation_prompt = build_evaluation_prompt(
        pack_name, config, images_to_evaluate, automated_score, automated_issues
    )

    # Prepare messages for Vision API
    messages = prepare_vision_messages(
        system_prompt, evaluation_prompt, images_to_evaluate, max_images=12
    )

    # Call OpenAI API
    logger.info(f"Calling OpenAI API with model: {model}")
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2000,
            temperature=0.3,  # Lower temperature for consistent evaluation
        )

        response_text = response.choices[0].message.content
        logger.debug(f"Critic response: {response_text[:200]}...")

    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        raise

    # Parse response
    try:
        parsed = parse_critic_response(response_text)
    except ValueError as e:
        logger.error(f"Failed to parse Critic response: {e}")
        # Return fallback evaluation
        return _create_fallback_evaluation(
            pack_name, images_to_evaluate, automated_score, automated_issues, critical_issues
        )

    # Build PackEvaluation from parsed response
    return _build_evaluation_from_response(
        pack_name, parsed, automated_score, automated_issues, critical_issues
    )


def _create_mock_evaluation(
    pack_name: str,
    images_to_evaluate: Dict[str, List[Path]],
    automated_score: float,
    automated_issues: List[str],
    critical_issues: List[str],
) -> PackEvaluation:
    """Create a mock evaluation for dry-run mode."""
    # Select first variant of each screen type
    selected_images = {
        screen_type: paths[0].name for screen_type, paths in images_to_evaluate.items()
    }

    dimension_scores = [
        EvaluationScore(
            dimension="brand_consistency",
            score=7.5,
            weight=0.30,
            justification="[DRY RUN] Mock evaluation - brand consistency not assessed",
            issues=[],
        ),
        EvaluationScore(
            dimension="technical_quality",
            score=automated_score * 0.7 + 7.0 * 0.3,  # Hybrid score
            weight=0.25,
            justification=f"[DRY RUN] Automated checks score: {automated_score}/10",
            issues=automated_issues,
        ),
        EvaluationScore(
            dimension="etsy_compliance",
            score=9.0,
            weight=0.20,
            justification="[DRY RUN] Mock evaluation - compliance not assessed",
            issues=[],
        ),
        EvaluationScore(
            dimension="visual_appeal",
            score=7.0,
            weight=0.25,
            justification="[DRY RUN] Mock evaluation - visual appeal not assessed",
            issues=[],
        ),
    ]

    overall_score = calculate_overall_score(dimension_scores)

    return PackEvaluation(
        pack_name=pack_name,
        overall_score=overall_score,
        dimension_scores=dimension_scores,
        critical_issues=critical_issues,
        selected_images=selected_images,
        deltas=[
            "[DRY RUN] This is a mock evaluation",
            "[DRY RUN] Run without --dry-run for real AI evaluation",
        ],
        automated_checks_passed=len(automated_issues) == 0,
    )


def _create_fallback_evaluation(
    pack_name: str,
    images_to_evaluate: Dict[str, List[Path]],
    automated_score: float,
    automated_issues: List[str],
    critical_issues: List[str],
) -> PackEvaluation:
    """Create fallback evaluation when parsing fails."""
    selected_images = {
        screen_type: paths[0].name for screen_type, paths in images_to_evaluate.items()
    }

    dimension_scores = [
        EvaluationScore(
            dimension="technical_quality",
            score=automated_score,
            weight=1.0,  # Only automated score available
            justification=f"Automated checks only (Vision model parse failed)",
            issues=automated_issues,
        ),
    ]

    return PackEvaluation(
        pack_name=pack_name,
        overall_score=automated_score,
        dimension_scores=dimension_scores,
        critical_issues=critical_issues,
        selected_images=selected_images,
        deltas=["ERROR: Failed to parse Critic response, only automated checks applied"],
        automated_checks_passed=len(automated_issues) == 0,
    )


def _build_evaluation_from_response(
    pack_name: str,
    parsed: Dict[str, Any],
    automated_score: float,
    automated_issues: List[str],
    critical_issues: List[str],
) -> PackEvaluation:
    """Build PackEvaluation from parsed Critic response."""
    # Parse dimension scores
    dimension_scores = []
    for dim_data in parsed.get("dimension_scores", []):
        dimension_scores.append(
            EvaluationScore(
                dimension=dim_data["dimension"],
                score=dim_data["score"],
                weight=dim_data["weight"],
                justification=dim_data["justification"],
                issues=dim_data.get("issues", []),
            )
        )

    # Combine critical issues from response and automated checks
    all_critical_issues = critical_issues + parsed.get("critical_issues", [])

    return PackEvaluation(
        pack_name=pack_name,
        overall_score=parsed.get("overall_score", automated_score),
        dimension_scores=dimension_scores,
        critical_issues=all_critical_issues,
        selected_images=parsed.get("selected_images", {}),
        deltas=parsed.get("deltas", []),
        automated_checks_passed=len(automated_issues) == 0,
    )


__all__ = ["evaluate_pack"]
