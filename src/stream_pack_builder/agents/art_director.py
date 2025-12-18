"""Art Director agent for brand token management and visual consistency."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Check if OpenAI is available for LLM-based Art Director
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI not available, Art Director will use rule-based mode only")


def load_system_prompt() -> str:
    """Load Art Director system prompt from prompts/art_director_system.txt.

    Returns:
        System prompt text.
    """
    prompt_path = Path(__file__).parent.parent.parent.parent / "prompts" / "art_director_system.txt"

    if not prompt_path.exists():
        logger.warning(f"Art Director system prompt not found at {prompt_path}, using fallback")
        return "You are an expert Art Director managing brand tokens for visual consistency."

    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def get_default_brand_tokens(theme: str) -> Dict[str, Any]:
    """Generate default brand tokens for a theme.

    Args:
        theme: Theme description (e.g., "neon cyberpunk cityscape")

    Returns:
        Default brand tokens dict
    """
    # Simple keyword-based defaults
    # Phase 3.5 will use LLM to generate these
    if "cyberpunk" in theme.lower() or "neon" in theme.lower():
        return {
            "primary_colors": ["#FF00FF", "#00FFFF", "#FFD700"],
            "secondary_colors": ["#1A1A2E", "#16213E", "#0F3460"],
            "texture": "wet glass with specular highlights, chrome reflections",
            "composition": "rule of thirds, golden ratio focal point, dynamic asymmetry",
            "lighting": "neon glow, strong backlight, volumetric fog, rim lighting",
            "mood": "cyberpunk, energetic, futuristic, mysterious"
        }
    elif "fantasy" in theme.lower() or "magic" in theme.lower():
        return {
            "primary_colors": ["#8B00FF", "#FF1493", "#FFD700"],
            "secondary_colors": ["#2C003E", "#4B0082", "#6A0DAD"],
            "texture": "ethereal glow, particle effects, magical sparkles",
            "composition": "centered symmetry, mystical framing, depth of field",
            "lighting": "soft ambient glow, magical aura, ethereal backlight",
            "mood": "magical, enchanting, mystical, dreamlike"
        }
    else:
        # Generic defaults
        return {
            "primary_colors": ["#FF6B6B", "#4ECDC4", "#FFE66D"],
            "secondary_colors": ["#2C2C2C", "#3D3D3D", "#4E4E4E"],
            "texture": "clean surface, subtle gradients",
            "composition": "balanced layout, clear focal point",
            "lighting": "soft natural light, balanced shadows",
            "mood": "modern, professional, engaging"
        }


def adjust_brand_tokens_llm(
    original_tokens: Dict[str, Any],
    critic_deltas: List[str],
    dimension_scores: Dict[str, float],
    round_num: int,
    model: str = "gpt-4o-mini",
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Adjust brand tokens using LLM (Phase 3).

    Args:
        original_tokens: Current brand tokens
        critic_deltas: Improvement suggestions from Critic
        dimension_scores: Scores by dimension (brand_consistency, etc.)
        round_num: Current round number
        model: OpenAI model to use

    Returns:
        Tuple of (refined_tokens, changes_list)
    """
    if not OPENAI_AVAILABLE:
        logger.warning("[Art Director] OpenAI not available, falling back to rule-based")
        return adjust_brand_tokens_rule_based(
            original_tokens, critic_deltas, dimension_scores, round_num
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("[Art Director] OPENAI_API_KEY not set, falling back to rule-based")
        return adjust_brand_tokens_rule_based(
            original_tokens, critic_deltas, dimension_scores, round_num
        )

    # Prepare input for LLM
    system_prompt = load_system_prompt()

    user_message = f"""# Brand Token Adjustment Request

## Current Brand Tokens
```json
{json.dumps(original_tokens, indent=2)}
```

## Critic Evaluation

**Round:** {round_num}

**Dimension Scores:**
{json.dumps(dimension_scores, indent=2)}

**Improvement Suggestions (Deltas):**
{chr(10).join(f"{i+1}. {delta}" for i, delta in enumerate(critic_deltas))}

## Your Task

Analyze the Critic feedback and adjust the brand tokens accordingly. Return ONLY a valid JSON object with this structure:

```json
{{
  "refined_tokens": {{
    "primary_colors": ["#...", "#...", "#..."],
    "secondary_colors": ["#...", "#...", "#..."],
    "texture": "...",
    "composition": "...",
    "lighting": "...",
    "mood": "..."
  }},
  "changes": [
    {{
      "token": "primary_colors",
      "action": "adjusted",
      "before": "...",
      "after": "...",
      "rationale": "..."
    }}
  ],
  "confidence": 0.85
}}
```

Focus on brand-related deltas. If no brand issues are mentioned, maintain current tokens.
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

        refined_tokens = result.get("refined_tokens", original_tokens)
        changes = result.get("changes", [])
        confidence = result.get("confidence", 0.0)

        logger.info(f"[Art Director] LLM adjustment completed (confidence: {confidence:.2f})")
        logger.info(f"[Art Director] Made {len(changes)} changes")

        return refined_tokens, changes

    except Exception as e:
        logger.error(f"[Art Director] LLM adjustment failed: {e}")
        logger.info("[Art Director] Falling back to rule-based adjustment")
        return adjust_brand_tokens_rule_based(
            original_tokens, critic_deltas, dimension_scores, round_num
        )


def adjust_brand_tokens_rule_based(
    original_tokens: Dict[str, Any],
    critic_deltas: List[str],
    dimension_scores: Dict[str, float],
    round_num: int,
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Adjust brand tokens using rule-based approach (Phase 2 fallback).

    Args:
        original_tokens: Current brand tokens
        critic_deltas: Improvement suggestions from Critic
        dimension_scores: Scores by dimension (brand_consistency, etc.)
        round_num: Current round number

    Returns:
        Tuple of (refined_tokens, changes_list)
    """
    if not critic_deltas:
        logger.info("[Art Director] No deltas, maintaining current tokens")
        return original_tokens.copy(), []

    # Phase 2: Simple rule-based adjustments
    refined_tokens = original_tokens.copy()
    changes = []

    brand_score = dimension_scores.get("brand_consistency", 8.0)

    # Analyze deltas for brand-related keywords
    brand_keywords = {
        "color": ["color", "palette", "hue", "saturation", "temperature"],
        "texture": ["texture", "surface", "material", "finish"],
        "composition": ["composition", "layout", "framing", "focal"],
        "lighting": ["lighting", "glow", "backlight", "shadow", "brightness"],
        "mood": ["mood", "atmosphere", "feeling", "tone"]
    }

    for delta in critic_deltas:
        delta_lower = delta.lower()

        # Check which token type this delta relates to
        for token_type, keywords in brand_keywords.items():
            if any(kw in delta_lower for kw in keywords):
                logger.info(f"[Art Director] Detected {token_type}-related delta: {delta[:50]}...")

                if token_type in refined_tokens:
                    # Simple adjustment: append suggestion
                    current_value = refined_tokens[token_type]

                    if isinstance(current_value, list):
                        # Colors - for now just log, Phase 3 will adjust
                        logger.info(f"[Art Director] Would adjust {token_type} colors")
                    elif isinstance(current_value, str):
                        # Text token - append refinement
                        if "add" in delta_lower or "more" in delta_lower:
                            # Extract suggestion (simple heuristic)
                            words = delta.split()
                            suggestion = " ".join(words[-5:])  # Last 5 words
                            refined_tokens[token_type] = f"{current_value}, {suggestion}"

                            changes.append({
                                "token": token_type,
                                "action": "enhanced",
                                "before": current_value[:50],
                                "after": refined_tokens[token_type][:50],
                                "rationale": delta[:100]
                            })

    logger.info(f"[Art Director] Made {len(changes)} brand token adjustments")

    return refined_tokens, changes


def adjust_brand_tokens(
    original_tokens: Dict[str, Any],
    critic_deltas: List[str],
    dimension_scores: Dict[str, float],
    round_num: int,
    dry_run: bool = False,
    use_llm: bool = True,
    model: str = "gpt-4o-mini",
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Adjust brand tokens based on Critic feedback (unified interface).

    This function automatically selects between LLM-based (Phase 3) and
    rule-based (Phase 2) adjustments based on availability and settings.

    Args:
        original_tokens: Current brand tokens
        critic_deltas: Improvement suggestions from Critic
        dimension_scores: Scores by dimension (brand_consistency, etc.)
        round_num: Current round number
        dry_run: Skip API calls if True
        use_llm: Try to use LLM if available (default True)
        model: OpenAI model to use for LLM mode

    Returns:
        Tuple of (refined_tokens, changes_list)
    """
    if dry_run or not critic_deltas:
        logger.info("[Art Director] Dry-run mode or no deltas, maintaining current tokens")
        return original_tokens.copy(), []

    # Choose implementation based on availability and settings
    if use_llm and OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
        logger.info("[Art Director] Using LLM-based brand token adjustment")
        return adjust_brand_tokens_llm(
            original_tokens, critic_deltas, dimension_scores, round_num, model
        )
    else:
        logger.info("[Art Director] Using rule-based brand token adjustment")
        return adjust_brand_tokens_rule_based(
            original_tokens, critic_deltas, dimension_scores, round_num
        )


def validate_brand_tokens(tokens: Dict[str, Any]) -> List[str]:
    """Validate brand tokens for completeness and correctness.

    Args:
        tokens: Brand tokens dict

    Returns:
        List of validation warnings (empty if all valid)
    """
    warnings = []

    required_keys = ["primary_colors", "secondary_colors", "texture", "composition", "lighting", "mood"]

    for key in required_keys:
        if key not in tokens:
            warnings.append(f"Missing required token: {key}")

    # Validate color codes
    for color_key in ["primary_colors", "secondary_colors"]:
        if color_key in tokens:
            colors = tokens[color_key]
            if not isinstance(colors, list):
                warnings.append(f"{color_key} must be a list")
            else:
                for color in colors:
                    if not isinstance(color, str) or not color.startswith("#"):
                        warnings.append(f"Invalid color format in {color_key}: {color}")

    # Validate text token lengths
    for text_key in ["texture", "composition", "lighting", "mood"]:
        if text_key in tokens:
            value = tokens[text_key]
            if isinstance(value, str) and len(value) > 200:
                warnings.append(f"{text_key} exceeds 200 characters ({len(value)})")

    return warnings


def generate_brand_summary(tokens: Dict[str, Any]) -> str:
    """Generate human-readable brand summary.

    Args:
        tokens: Brand tokens dict

    Returns:
        Formatted summary string
    """
    lines = [
        "## Brand Tokens Summary",
        "",
        f"**Primary Colors:** {', '.join(tokens.get('primary_colors', []))}",
        f"**Secondary Colors:** {', '.join(tokens.get('secondary_colors', []))}",
        f"**Texture:** {tokens.get('texture', 'N/A')}",
        f"**Composition:** {tokens.get('composition', 'N/A')}",
        f"**Lighting:** {tokens.get('lighting', 'N/A')}",
        f"**Mood:** {tokens.get('mood', 'N/A')}",
        ""
    ]

    return "\n".join(lines)


__all__ = [
    "load_system_prompt",
    "get_default_brand_tokens",
    "adjust_brand_tokens",
    "validate_brand_tokens",
    "generate_brand_summary",
]
