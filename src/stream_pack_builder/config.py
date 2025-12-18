"""Configuration loader for pack settings."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any

import yaml


@dataclass
class Resolution:
    """Target resolution for generated and final images."""

    width: int
    height: int


@dataclass
class OutputSpec:
    """Rules for naming and exporting images."""

    filename_pattern: str = "{kind}_{index:02d}.png"
    mockup_texts: Dict[str, str] | None = None


@dataclass
class BrandTokens:
    """Brand visual identity tokens."""

    primary_colors: List[str] = field(default_factory=list)
    secondary_colors: List[str] = field(default_factory=list)
    texture: str = ""
    composition: str = ""
    lighting: str = ""
    mood: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "primary_colors": self.primary_colors,
            "secondary_colors": self.secondary_colors,
            "texture": self.texture,
            "composition": self.composition,
            "lighting": self.lighting,
            "mood": self.mood,
        }


@dataclass
class PackConfig:
    """Full configuration for a pack."""

    theme: str
    prompts: Dict[str, str]
    resolution: Resolution
    output: OutputSpec
    brand_tokens: BrandTokens | None = None

    @classmethod
    def load(cls, path: Path) -> "PackConfig":
        """Load configuration YAML into a ``PackConfig`` instance.

        Args:
            path: Path to ``config.yaml`` inside the pack directory.

        Raises:
            FileNotFoundError: If the config file does not exist.
            ValueError: If mandatory fields are missing.
        """

        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

        try:
            resolution = Resolution(**raw["resolution"])
            output = OutputSpec(**raw.get("output", {}))
            prompts = raw["prompts"]
            theme = raw["theme"]

            # Load brand_tokens if present (Phase 3 feature)
            brand_tokens = None
            if "brand_tokens" in raw:
                brand_tokens = BrandTokens(**raw["brand_tokens"])
        except KeyError as exc:  # pragma: no cover - simple mapping
            raise ValueError(f"Missing config field: {exc}") from exc

        return cls(
            theme=theme,
            prompts=prompts,
            resolution=resolution,
            output=output,
            brand_tokens=brand_tokens
        )


__all__ = ["Resolution", "OutputSpec", "BrandTokens", "PackConfig"]
