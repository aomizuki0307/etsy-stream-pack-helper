"""Prompt Engineer agent for improving prompts based on Critic feedback."""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# Check if OpenAI is available for LLM-based Prompt Engineer
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI not available, Prompt Engineer will use rule-based mode only")


def load_system_prompt() -> str:
    """Load Prompt Engineer system prompt from prompts/prompt_engineer_system.txt.

    Returns:
        System prompt text.
    """
    prompt_path = Path(__file__).parent.parent.parent.parent / "prompts" / "prompt_engineer_system.txt"

    if not prompt_path.exists():
        logger.warning(f"Prompt Engineer system prompt not found at {prompt_path}, using fallback")
        return "You are an expert Prompt Engineer for AI image generation."

    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def parse_delta(delta: str) -> tuple[str, str, str]:
    """Parse a delta string into (target, action, content).

    Delta format examples:
    - "prompts.starting → Add: 'strong central focal glow, golden ratio'"
    - "prompts.thumbnail_background → Adjust: 'vary: wide cityscape, close-up signs'"
    - "brand_tokens.texture → Change: 'wet glass with specular highlights'"

    Args:
        delta: Delta string from Critic

    Returns:
        Tuple of (target, action, content)
        - target: e.g., "prompts.starting", "brand_tokens.texture"
        - action: e.g., "Add", "Adjust", "Remove", "Change"
        - content: The actual suggestion text
    """
    # Try to match pattern: "target → action: 'content'"
    match = re.match(r"^(.+?)\s*→\s*(\w+):\s*['\"](.+?)['\"]", delta)
    if match:
        target, action, content = match.groups()
        return target.strip(), action.strip(), content.strip()

    # Fallback: treat entire delta as content with "Adjust" action
    logger.warning(f"Could not parse delta format: {delta}")
    return "prompts.general", "Adjust", delta


def apply_delta_to_prompt(
    original_prompt: str,
    action: str,
    content: str,
) -> str:
    """Apply a single delta to a prompt.

    Args:
        original_prompt: Original prompt text
        action: Action type (Add, Adjust, Remove, Change)
        content: Content to apply

    Returns:
        Modified prompt
    """
    action_lower = action.lower()

    if action_lower == "add":
        # Add content at the end
        return f"{original_prompt.rstrip()}, {content}"

    elif action_lower == "adjust":
        # Try to identify what to adjust and replace it
        # For Phase 2, we simply append the adjustment as a refinement
        return f"{original_prompt.rstrip()}. Refinement: {content}"

    elif action_lower == "remove":
        # Remove phrases containing the content
        # Simple approach: remove sentences containing key words
        lines = original_prompt.split(".")
        filtered = [
            line for line in lines
            if content.lower() not in line.lower()
        ]
        return ". ".join(filtered).strip() + "."

    elif action_lower == "change":
        # Replace entire prompt (drastic)
        logger.warning(f"CHANGE action used - replacing entire prompt with: {content}")
        return content

    else:
        # Unknown action, append as adjustment
        logger.warning(f"Unknown action '{action}', treating as adjustment")
        return f"{original_prompt.rstrip()}. Note: {content}"


def refine_prompts_llm(
    original_prompts: Dict[str, str],
    deltas: List[str],
    dimension_scores: Dict[str, float] = None,
    round_num: int = 1,
    model: str = "gpt-4o-mini",
) -> Dict[str, str]:
    """Refine prompts using LLM (Phase 3).

    Args:
        original_prompts: Original prompts dict from config
        deltas: List of improvement suggestions from Critic
        dimension_scores: Scores by dimension (optional)
        round_num: Current round number
        model: OpenAI model to use

    Returns:
        Refined prompts dict
    """
    if not OPENAI_AVAILABLE:
        logger.warning("[Prompt Engineer] OpenAI not available, falling back to rule-based")
        return refine_prompts_rule_based(original_prompts, deltas)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("[Prompt Engineer] OPENAI_API_KEY not set, falling back to rule-based")
        return refine_prompts_rule_based(original_prompts, deltas)

    if not deltas:
        logger.info("[Prompt Engineer] No deltas to apply")
        return original_prompts.copy()

    # Prepare input for LLM
    system_prompt = load_system_prompt()

    dimension_scores_json = json.dumps(dimension_scores, indent=2) if dimension_scores else "{}"

    user_message = f"""# Prompt Refinement Request

## Current Prompts
```json
{json.dumps(original_prompts, indent=2)}
```

## Critic Evaluation

**Round:** {round_num}

**Dimension Scores:**
{dimension_scores_json}

**Improvement Suggestions (Deltas):**
{chr(10).join(f"{i+1}. {delta}" for i, delta in enumerate(deltas))}

## Your Task

Refine the image generation prompts to address the Critic feedback. Return ONLY a valid JSON object:

```json
{{
  "refined_prompts": {{
    "starting": "...",
    "live": "...",
    "brb": "...",
    "ending": "...",
    "thumbnail_background": "..."
  }},
  "changes": [
    {{
      "screen_type": "starting",
      "change_type": "major|minor|polish",
      "before_excerpt": "...",
      "after_excerpt": "...",
      "rationale": "..."
    }}
  ],
  "confidence": 0.85
}}
```

Focus on actionable deltas. Maintain consistency across all prompts.
"""

    try:
        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )

        result_text = response.choices[0].message.content
        result = json.loads(result_text)

        refined_prompts = result.get("refined_prompts", original_prompts)
        changes = result.get("changes", [])
        confidence = result.get("confidence", 0.0)

        logger.info(f"[Prompt Engineer] LLM refinement completed (confidence: {confidence:.2f})")
        logger.info(f"[Prompt Engineer] Made {len(changes)} changes")

        for change in changes[:3]:  # Show first 3
            logger.info(f"  - {change['screen_type']}: {change['change_type']} - {change.get('rationale', '')[:50]}...")

        return refined_prompts

    except Exception as e:
        logger.error(f"[Prompt Engineer] LLM refinement failed: {e}")
        logger.info("[Prompt Engineer] Falling back to rule-based refinement")
        return refine_prompts_rule_based(original_prompts, deltas)


def refine_prompts_rule_based(
    original_prompts: Dict[str, str],
    deltas: List[str],
) -> Dict[str, str]:
    """Refine prompts using rule-based approach (Phase 2 fallback).

    Phase 2 implementation: Simple rule-based refinement.

    Args:
        original_prompts: Original prompts dict from config
        deltas: List of improvement suggestions from Critic

    Returns:
        Refined prompts dict
    """
    if not deltas:
        logger.info("[Prompt Engineer] No deltas to apply")
        return original_prompts.copy()

    refined_prompts = original_prompts.copy()

    for delta in deltas:
        target, action, content = parse_delta(delta)

        # Check if target is a prompt
        if not target.startswith("prompts."):
            logger.debug(f"Skipping non-prompt delta: {target}")
            continue

        # Extract prompt kind (e.g., "starting" from "prompts.starting")
        parts = target.split(".", 1)
        if len(parts) < 2:
            logger.warning(f"Invalid prompt target: {target}")
            continue

        prompt_kind = parts[1]

        # Check if this prompt kind exists
        if prompt_kind not in refined_prompts:
            logger.warning(f"Prompt kind not found: {prompt_kind}")
            continue

        # Apply delta
        original = refined_prompts[prompt_kind]
        refined = apply_delta_to_prompt(original, action, content)

        logger.info(f"[Prompt Engineer] Applied delta to '{prompt_kind}': {action} - {content[:50]}...")
        refined_prompts[prompt_kind] = refined

    return refined_prompts


def generate_prompt_diff(
    original: Dict[str, str],
    refined: Dict[str, str],
) -> List[str]:
    """Generate human-readable diff of prompt changes.

    Args:
        original: Original prompts
        refined: Refined prompts

    Returns:
        List of diff strings
    """
    diffs = []

    for kind in sorted(set(original.keys()) | set(refined.keys())):
        orig_prompt = original.get(kind, "")
        new_prompt = refined.get(kind, "")

        if orig_prompt != new_prompt:
            diffs.append(f"## {kind}")
            diffs.append(f"**Before:**")
            diffs.append(f"  {orig_prompt[:100]}..." if len(orig_prompt) > 100 else f"  {orig_prompt}")
            diffs.append(f"**After:**")
            diffs.append(f"  {new_prompt[:100]}..." if len(new_prompt) > 100 else f"  {new_prompt}")
            diffs.append("")

    return diffs


def validate_prompts(prompts: Dict[str, str]) -> List[str]:
    """Validate refined prompts for common issues.

    Args:
        prompts: Prompts dict to validate

    Returns:
        List of validation warnings
    """
    warnings = []

    for kind, text in prompts.items():
        # Check minimum length
        if len(text) < 10:
            warnings.append(f"{kind}: Prompt too short ({len(text)} chars)")

        # Check maximum length (Gemini has limits)
        if len(text) > 2000:
            warnings.append(f"{kind}: Prompt very long ({len(text)} chars, may hit API limits)")

        # Check for empty prompts
        if not text.strip():
            warnings.append(f"{kind}: Empty prompt")

    return warnings


def refine_prompts(
    original_prompts: Dict[str, str],
    deltas: List[str],
    dimension_scores: Dict[str, float] = None,
    round_num: int = 1,
    use_llm: bool = True,
    model: str = "gpt-4o-mini",
) -> Dict[str, str]:
    """Refine prompts based on Critic deltas (unified interface).

    This function automatically selects between LLM-based (Phase 3) and
    rule-based (Phase 2) refinement based on availability and settings.

    Args:
        original_prompts: Original prompts dict from config
        deltas: List of improvement suggestions from Critic
        dimension_scores: Scores by dimension (optional)
        round_num: Current round number
        use_llm: Try to use LLM if available (default True)
        model: OpenAI model to use for LLM mode

    Returns:
        Refined prompts dict
    """
    if not deltas:
        logger.info("[Prompt Engineer] No deltas to apply")
        return original_prompts.copy()

    # Choose implementation based on availability and settings
    if use_llm and OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
        logger.info("[Prompt Engineer] Using LLM-based prompt refinement")
        return refine_prompts_llm(
            original_prompts, deltas, dimension_scores, round_num, model
        )
    else:
        logger.info("[Prompt Engineer] Using rule-based prompt refinement")
        return refine_prompts_rule_based(original_prompts, deltas)


__all__ = [
    "parse_delta",
    "apply_delta_to_prompt",
    "refine_prompts",
    "generate_prompt_diff",
    "validate_prompts",
]
