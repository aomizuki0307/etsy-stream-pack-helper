"""Etsy listing metadata generator.

Generates SEO-optimized titles, descriptions, tags, and pricing for listings.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from ..config import PackConfig
from ..multi_agent.state import WorkflowState

logger = logging.getLogger(__name__)

# Title template (max 140 chars)
TITLE_TEMPLATE = "Stream Overlay Pack - {theme_name} | Twitch YouTube OBS | Starting BRB Ending"

# Description HTML template
DESCRIPTION_TEMPLATE = """<h2>🎮 Professional Stream Overlay Pack - {theme_name}</h2>

<p>Elevate your streaming setup with this complete pack of professionally designed overlays! Perfect for Twitch, YouTube Gaming, Facebook Gaming, and all major streaming platforms.</p>

<h3>📦 What's Included</h3>
<ul>
  <li><strong>Starting Screen</strong> (3 high-quality variants) - Build anticipation before you go live</li>
  <li><strong>BRB Screen</strong> (3 variants) - Keep viewers engaged during short breaks</li>
  <li><strong>Ending Screen</strong> (3 variants) - Professional stream closure with thank you message</li>
  <li><strong>Thumbnail Backgrounds</strong> (3 variants) - Eye-catching YouTube/Twitch thumbnails</li>
</ul>

<p><strong>Total: 12 premium PNG files</strong> ready to elevate your stream!</p>

<h3>✨ Key Features</h3>
<ul>
  <li><strong>Resolution:</strong> {resolution} (Full HD, perfect for 1080p/1440p streaming)</li>
  <li><strong>Format:</strong> PNG with transparency for easy customization</li>
  <li><strong>Compatibility:</strong> OBS Studio, Streamlabs OBS, XSplit, and all major streaming software</li>
  <li><strong>Professional Design:</strong> AI-powered design with multi-agent quality assurance</li>
  <li><strong>Brand Consistency:</strong> Cohesive visual identity across all screens</li>
  <li><strong>Easy Customization:</strong> Add your logo, text, and alerts with ease</li>
</ul>

<h3>🎨 Theme: {theme_name}</h3>
<p><strong>Style:</strong> {style_description}</p>
<p><strong>Mood:</strong> {mood_keywords}</p>
{color_info}

<h3>📥 Instant Download</h3>
<p>Digital files are delivered <strong>immediately after purchase</strong>. No waiting, no shipping fees!</p>

<p>Each screen type comes in its own organized ZIP file with detailed README.txt including:</p>
<ul>
  <li>Step-by-step setup instructions for OBS Studio</li>
  <li>Technical specifications</li>
  <li>Customization tips and tricks</li>
  <li>License information</li>
</ul>

<h3>💡 Perfect For</h3>
<ul>
  <li>Twitch streamers looking to upgrade their branding</li>
  <li>YouTube Gaming content creators</li>
  <li>Facebook Gaming broadcasters</li>
  <li>Professional esports players</li>
  <li>New streamers wanting a polished look</li>
  <li>Content creators who value quality and consistency</li>
</ul>

<h3>🚀 How to Use</h3>
<ol>
  <li>Download and extract the ZIP files</li>
  <li>Open OBS Studio (or your streaming software)</li>
  <li>Add Image Source and browse to your downloaded files</li>
  <li>Select your favorite variant</li>
  <li>Add text overlays, logos, and alerts as desired</li>
  <li>Start streaming with professional-looking overlays!</li>
</ol>

<h3>⭐ Quality Guarantee</h3>
<p>This pack was created using advanced AI technology with multi-round quality improvements. Each design goes through multiple iterations to ensure the highest visual quality.</p>
{quality_score_info}

<h3>📞 Customer Support</h3>
<p>Have questions or need help? <strong>Message us anytime!</strong> We're here to ensure you get the most out of your purchase.</p>

<h3>📜 License</h3>
<ul>
  <li>✓ Personal and commercial use for streaming content</li>
  <li>✓ Use on YouTube, Twitch, Facebook Gaming, etc.</li>
  <li>✓ Modify and customize for your channel</li>
  <li>✗ No resale or redistribution of files</li>
  <li>✗ No claiming as your own creation</li>
</ul>

<p><em>Ready to level up your stream? Download now and start broadcasting with style!</em> 🎮✨</p>
"""

# Common streaming/overlay keywords for tags
BASE_TAGS = [
    "stream overlay",
    "twitch overlay",
    "obs overlay",
    "gaming overlay",
    "youtube overlay",
    "streamlabs",
    "starting screen",
    "brb screen",
    "ending screen",
    "digital download",
    "instant download",
    "streamer graphics",
]


def generate_listing_title(pack_name: str, config: PackConfig) -> str:
    """Generate SEO-optimized Etsy listing title.

    Args:
        pack_name: Pack name (e.g., "neon_cyberpunk")
        config: Pack configuration

    Returns:
        Title string (max 140 chars)
    """
    # Format theme name
    theme_name = pack_name.replace("_", " ").title()

    # Use config theme if more descriptive
    if len(config.theme) > len(theme_name):
        theme_name = config.theme.title()

    # Generate title from template
    title = TITLE_TEMPLATE.format(theme_name=theme_name)

    # Truncate if too long (Etsy limit: 140 chars)
    if len(title) > 140:
        # Shorten theme name
        max_theme_len = 30
        if len(theme_name) > max_theme_len:
            theme_name = theme_name[:max_theme_len - 3] + "..."
            title = TITLE_TEMPLATE.format(theme_name=theme_name)

    # Final truncation if still too long
    title = title[:140]

    logger.debug(f"Generated title ({len(title)} chars): {title}")
    return title


def generate_listing_description(
    pack_name: str,
    config: PackConfig,
    workflow_state: Optional[WorkflowState] = None,
) -> str:
    """Generate comprehensive Etsy listing description (HTML).

    Args:
        pack_name: Pack name
        config: Pack configuration
        workflow_state: Optional workflow state for quality info

    Returns:
        Description HTML string
    """
    # Format theme name
    theme_name = pack_name.replace("_", " ").title()
    if len(config.theme) > len(theme_name):
        theme_name = config.theme.title()

    # Extract style info from brand tokens
    style_description = "Modern, professional design"
    mood_keywords = "Engaging, dynamic, professional"

    if config.brand_tokens:
        if config.brand_tokens.texture or config.brand_tokens.lighting:
            style_parts = []
            if config.brand_tokens.texture:
                style_parts.append(config.brand_tokens.texture)
            if config.brand_tokens.lighting:
                style_parts.append(config.brand_tokens.lighting)
            style_description = ", ".join(style_parts)

        if config.brand_tokens.mood:
            mood_keywords = config.brand_tokens.mood

    # Color information
    color_info = ""
    if config.brand_tokens and config.brand_tokens.primary_colors:
        primary_colors = config.brand_tokens.primary_colors[:3]
        color_list = ", ".join(primary_colors)
        color_info = f'<p><strong>Color Palette:</strong> {color_list}</p>'

    # Resolution
    resolution = f"{config.resolution.width}x{config.resolution.height}"

    # Quality score information
    quality_score_info = ""
    if workflow_state and workflow_state.rounds:
        final_score = workflow_state.rounds[-1].evaluation.overall_score
        rounds_count = len(workflow_state.rounds)
        quality_score_info = f'<p><strong>Quality Score:</strong> {final_score:.1f}/10 (achieved through {rounds_count} rounds of AI-powered refinement)</p>'

    # Generate description from template
    description = DESCRIPTION_TEMPLATE.format(
        theme_name=theme_name,
        resolution=resolution,
        style_description=style_description,
        mood_keywords=mood_keywords,
        color_info=color_info,
        quality_score_info=quality_score_info,
    )

    logger.debug(f"Generated description ({len(description)} chars)")
    return description


def generate_tags(pack_name: str, config: PackConfig) -> List[str]:
    """Generate SEO-optimized tags for listing.

    Args:
        pack_name: Pack name
        config: Pack configuration

    Returns:
        List of tags (max 13, each max 20 chars)
    """
    tags = BASE_TAGS.copy()

    # Add theme-specific tags
    theme_words = pack_name.replace("_", " ").lower().split()
    for word in theme_words:
        if len(word) > 3 and word not in ["pack", "stream"]:
            # Truncate to 20 chars
            tag = word[:20]
            if tag not in tags:
                tags.append(tag)

    # Add brand token mood keywords as tags
    if config.brand_tokens and config.brand_tokens.mood:
        mood_words = config.brand_tokens.mood.lower().split(",")
        for word in mood_words:
            word = word.strip()
            if len(word) > 3 and word not in tags:
                tag = word[:20]
                tags.append(tag)

    # Limit to 13 tags (Etsy max)
    tags = tags[:13]

    # Ensure each tag is max 20 chars
    tags = [tag[:20] for tag in tags]

    logger.debug(f"Generated {len(tags)} tags: {tags}")
    return tags


def calculate_price(
    pack_name: str,
    config: PackConfig,
    workflow_state: Optional[WorkflowState] = None,
    base_price: float = 9.99,
) -> float:
    """Calculate price based on quality score and theme.

    Args:
        pack_name: Pack name
        config: Pack configuration
        workflow_state: Optional workflow state for quality scoring
        base_price: Base price in USD (default 9.99)

    Returns:
        Final price in USD
    """
    price = base_price

    # Quality bonus
    if workflow_state and workflow_state.rounds:
        final_score = workflow_state.rounds[-1].evaluation.overall_score

        if final_score >= 9.0:
            # Premium quality
            price += 5.00
            logger.debug(f"Quality bonus: +$5.00 (score {final_score:.1f}/10)")
        elif final_score >= 8.5:
            # High quality
            price += 3.00
            logger.debug(f"Quality bonus: +$3.00 (score {final_score:.1f}/10)")
        elif final_score >= 8.0:
            # Good quality
            price += 1.00
            logger.debug(f"Quality bonus: +$1.00 (score {final_score:.1f}/10)")

    # Theme premium
    premium_keywords = ["premium", "pro", "deluxe", "ultimate"]
    if any(kw in pack_name.lower() for kw in premium_keywords):
        price += 2.00
        logger.debug(f"Theme bonus: +$2.00 (premium theme)")

    # Round to 2 decimals
    price = round(price, 2)

    logger.info(f"Calculated price: ${price:.2f} (base: ${base_price:.2f})")
    return price


def generate_slug(pack_name: str) -> str:
    """Generate URL slug for listing.

    Args:
        pack_name: Pack name

    Returns:
        URL-friendly slug
    """
    # Replace underscores with hyphens, lowercase
    slug = pack_name.replace("_", "-").lower()

    # Add "stream-overlay-pack" suffix
    slug = f"{slug}-stream-overlay-pack"

    return slug


__all__ = [
    "generate_listing_title",
    "generate_listing_description",
    "generate_tags",
    "calculate_price",
    "generate_slug",
]
