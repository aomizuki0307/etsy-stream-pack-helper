"""Etsy listing photo generator.

Generates 8 professional listing photos for Etsy product pages.
All photos are 2000x2000 JPEG at quality=95.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from ..config import PackConfig
from ..utils import FINAL_DIR

logger = logging.getLogger(__name__)

# Listing photos directory
LISTING_DIR = "05_etsy_listing"

# Standard size for all listing photos
LISTING_SIZE = (2000, 2000)
JPEG_QUALITY = 95

# Default colors (used when brand tokens unavailable)
DEFAULT_PRIMARY = "#4A90E2"
DEFAULT_SECONDARY = "#2C3E50"
DEFAULT_ACCENT = "#E74C3C"


def get_brand_colors(config: PackConfig) -> Tuple[str, str, str]:
    """Extract brand colors from config.

    Args:
        config: Pack configuration

    Returns:
        Tuple of (primary, secondary, accent) hex colors
    """
    if config.brand_tokens and config.brand_tokens.primary_colors:
        primary = config.brand_tokens.primary_colors[0] if len(config.brand_tokens.primary_colors) > 0 else DEFAULT_PRIMARY
        secondary = config.brand_tokens.secondary_colors[0] if config.brand_tokens.secondary_colors else DEFAULT_SECONDARY
        accent = config.brand_tokens.primary_colors[1] if len(config.brand_tokens.primary_colors) > 1 else DEFAULT_ACCENT
        return primary, secondary, accent
    else:
        return DEFAULT_PRIMARY, DEFAULT_SECONDARY, DEFAULT_ACCENT


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple.

    Args:
        hex_color: Hex color string (e.g., "#FF00FF")

    Returns:
        RGB tuple (r, g, b)
    """
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def create_gradient_background(
    size: Tuple[int, int],
    color1: str,
    color2: str,
    vertical: bool = True,
) -> Image.Image:
    """Create a gradient background image.

    Args:
        size: Image size (width, height)
        color1: Start color (hex)
        color2: End color (hex)
        vertical: If True, vertical gradient; else horizontal

    Returns:
        PIL Image with gradient
    """
    width, height = size
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)

    rgb1 = hex_to_rgb(color1)
    rgb2 = hex_to_rgb(color2)

    steps = height if vertical else width

    for i in range(steps):
        ratio = i / steps
        r = int(rgb1[0] + (rgb2[0] - rgb1[0]) * ratio)
        g = int(rgb1[1] + (rgb2[1] - rgb1[1]) * ratio)
        b = int(rgb1[2] + (rgb2[2] - rgb1[2]) * ratio)

        if vertical:
            draw.line([(0, i), (width, i)], fill=(r, g, b))
        else:
            draw.line([(i, 0), (i, height)], fill=(r, g, b))

    return img


def draw_text_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: Tuple[int, int],
    font_size: int = 60,
    color: str = "#FFFFFF",
    bold: bool = False,
) -> None:
    """Draw centered text on an image.

    Args:
        draw: ImageDraw object
        text: Text to draw
        position: Center position (x, y)
        font_size: Font size in pixels
        color: Text color (hex)
        bold: If True, use bold font weight
    """
    try:
        # Try to load a nice font (fallback to default if unavailable)
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    # Get text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Calculate centered position
    x = position[0] - text_width // 2
    y = position[1] - text_height // 2

    # Draw text
    rgb = hex_to_rgb(color)
    draw.text((x, y), text, fill=rgb, font=font)


def generate_01_hero_showcase(
    pack_name: str,
    config: PackConfig,
    final_dir: Path,
    output_path: Path,
) -> None:
    """Generate hero showcase photo (main visual).

    Args:
        pack_name: Pack name
        config: Pack configuration
        final_dir: Path to 03_final/ directory
        output_path: Output JPEG path
    """
    logger.info("Generating 01_hero_showcase.jpg...")

    primary, secondary, accent = get_brand_colors(config)

    # Create gradient background
    img = create_gradient_background(LISTING_SIZE, secondary, primary, vertical=True)
    draw = ImageDraw.Draw(img)

    # Try to load a hero image from final/
    hero_image = None
    for png_path in sorted(final_dir.glob("starting*.png")):
        try:
            hero_image = Image.open(png_path).convert("RGBA")
            break
        except Exception as e:
            logger.warning(f"Could not load {png_path.name}: {e}")

    # Place hero image in center if available
    if hero_image:
        # Resize to fit (max 1400x1400)
        hero_image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)

        # Center it
        x = (LISTING_SIZE[0] - hero_image.width) // 2
        y = (LISTING_SIZE[1] - hero_image.height) // 2 - 100  # Offset up for text

        # Paste with alpha channel
        img.paste(hero_image, (x, y), hero_image)

    # Add text
    title = pack_name.replace("_", " ").title()
    draw_text_centered(draw, title, (LISTING_SIZE[0] // 2, 150), font_size=80, color="#FFFFFF", bold=True)
    draw_text_centered(draw, "Professional Stream Overlays", (LISTING_SIZE[0] // 2, 1850), font_size=50, color="#FFFFFF")

    # Save
    img.save(output_path, "JPEG", quality=JPEG_QUALITY)
    logger.info(f"  Saved: {output_path.name}")


def generate_02_04_screen_demo(
    screen_type: str,
    pack_name: str,
    config: PackConfig,
    final_dir: Path,
    output_path: Path,
) -> None:
    """Generate screen demo photo (OBS-style mockup).

    Args:
        screen_type: Screen type (e.g., "starting", "brb", "ending")
        pack_name: Pack name
        config: Pack configuration
        final_dir: Path to 03_final/ directory
        output_path: Output JPEG path
    """
    logger.info(f"Generating screen demo for {screen_type}...")

    primary, secondary, accent = get_brand_colors(config)

    # Create dark background (OBS-style)
    img = Image.new("RGB", LISTING_SIZE, hex_to_rgb("#1E1E1E"))
    draw = ImageDraw.Draw(img)

    # Load screen image
    screen_image = None
    for png_path in sorted(final_dir.glob(f"{screen_type}*.png")):
        try:
            screen_image = Image.open(png_path).convert("RGBA")
            break
        except Exception as e:
            logger.warning(f"Could not load {png_path.name}: {e}")

    # Main canvas area (center)
    if screen_image:
        # Resize to fit main area (1200x675 = 16:9)
        screen_image.thumbnail((1200, 675), Image.Resampling.LANCZOS)

        # Center it
        x = (LISTING_SIZE[0] - screen_image.width) // 2
        y = (LISTING_SIZE[1] - screen_image.height) // 2

        # Draw border (OBS-style red outline)
        border_color = hex_to_rgb(accent)
        draw.rectangle(
            [x - 5, y - 5, x + screen_image.width + 5, y + screen_image.height + 5],
            outline=border_color,
            width=5
        )

        # Paste image
        img.paste(screen_image, (x, y), screen_image)

    # Add title at top
    screen_title = screen_type.replace("_", " ").title() + " - In OBS Studio"
    draw_text_centered(draw, screen_title, (LISTING_SIZE[0] // 2, 150), font_size=60, color="#FFFFFF")

    # Save
    img.save(output_path, "JPEG", quality=JPEG_QUALITY)
    logger.info(f"  Saved: {output_path.name}")


def generate_05_thumbnail_showcase(
    pack_name: str,
    config: PackConfig,
    final_dir: Path,
    output_path: Path,
) -> None:
    """Generate thumbnail showcase photo.

    Args:
        pack_name: Pack name
        config: Pack configuration
        final_dir: Path to 03_final/ directory
        output_path: Output JPEG path
    """
    logger.info("Generating 05_thumbnail_showcase.jpg...")

    primary, secondary, accent = get_brand_colors(config)

    # Create gradient background
    img = create_gradient_background(LISTING_SIZE, primary, secondary, vertical=False)
    draw = ImageDraw.Draw(img)

    # Load thumbnail image
    thumb_image = None
    for png_path in sorted(final_dir.glob("thumbnail*.png")):
        try:
            thumb_image = Image.open(png_path).convert("RGBA")
            break
        except Exception as e:
            logger.warning(f"Could not load {png_path.name}: {e}")

    # Place thumbnail
    if thumb_image:
        thumb_image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
        x = (LISTING_SIZE[0] - thumb_image.width) // 2
        y = (LISTING_SIZE[1] - thumb_image.height) // 2 - 100
        img.paste(thumb_image, (x, y), thumb_image)

    # Add text
    draw_text_centered(draw, "Thumbnail Backgrounds Included", (LISTING_SIZE[0] // 2, 1850), font_size=50, color="#FFFFFF")

    # Save
    img.save(output_path, "JPEG", quality=JPEG_QUALITY)
    logger.info(f"  Saved: {output_path.name}")


def generate_06_all_screens_grid(
    pack_name: str,
    config: PackConfig,
    final_dir: Path,
    output_path: Path,
) -> None:
    """Generate all screens grid (2x2).

    Args:
        pack_name: Pack name
        config: Pack configuration
        final_dir: Path to 03_final/ directory
        output_path: Output JPEG path
    """
    logger.info("Generating 06_all_screens_grid.jpg...")

    primary, secondary, accent = get_brand_colors(config)

    # Create neutral background
    img = Image.new("RGB", LISTING_SIZE, hex_to_rgb(secondary))
    draw = ImageDraw.Draw(img)

    # Load 4 images (starting, brb, ending, thumbnail)
    screen_types = ["starting", "brb", "ending", "thumbnail"]
    images = []

    for screen_type in screen_types:
        screen_img = None
        for png_path in sorted(final_dir.glob(f"{screen_type}*.png")):
            try:
                screen_img = Image.open(png_path).convert("RGBA")
                break
            except Exception:
                pass

        if screen_img:
            # Resize to fit quadrant (900x900)
            screen_img.thumbnail((900, 900), Image.Resampling.LANCZOS)
        else:
            # Placeholder
            screen_img = Image.new("RGBA", (900, 900), (50, 50, 50, 255))

        images.append(screen_img)

    # Place in 2x2 grid
    positions = [(50, 150), (1050, 150), (50, 1050), (1050, 1050)]
    labels = ["Starting", "BRB", "Ending", "Thumbnail"]

    for i, (screen_img, pos, label) in enumerate(zip(images, positions, labels)):
        # Paste image
        img.paste(screen_img, pos, screen_img)

        # Add label below
        label_y = pos[1] + screen_img.height + 30
        draw_text_centered(draw, label, (pos[0] + 450, label_y), font_size=40, color="#FFFFFF")

    # Title at top
    draw_text_centered(draw, "Complete Stream Pack - All Screens", (LISTING_SIZE[0] // 2, 80), font_size=60, color="#FFFFFF")

    # Save
    img.save(output_path, "JPEG", quality=JPEG_QUALITY)
    logger.info(f"  Saved: {output_path.name}")


def generate_07_file_contents(
    pack_name: str,
    config: PackConfig,
    output_path: Path,
) -> None:
    """Generate file contents infographic.

    Args:
        pack_name: Pack name
        config: Pack configuration
        output_path: Output JPEG path
    """
    logger.info("Generating 07_file_contents.jpg...")

    primary, secondary, accent = get_brand_colors(config)

    # Create background
    img = create_gradient_background(LISTING_SIZE, secondary, primary, vertical=True)
    draw = ImageDraw.Draw(img)

    # Title
    draw_text_centered(draw, "What You'll Receive", (LISTING_SIZE[0] // 2, 200), font_size=70, color="#FFFFFF")

    # File list
    files = [
        "📦 starting_screen.zip (3 variants + README)",
        "📦 brb_screen.zip (3 variants + README)",
        "📦 ending_screen.zip (3 variants + README)",
        "📦 thumbnail_backgrounds.zip (3 variants + README)",
    ]

    y_start = 600
    y_spacing = 200

    for i, file_text in enumerate(files):
        y = y_start + i * y_spacing
        draw_text_centered(draw, file_text, (LISTING_SIZE[0] // 2, y), font_size=45, color="#FFFFFF")

    # Footer
    draw_text_centered(draw, "Total: 12 High-Quality PNG Files", (LISTING_SIZE[0] // 2, 1700), font_size=50, color=accent)
    draw_text_centered(draw, "Ready to Use in OBS, Streamlabs, & More", (LISTING_SIZE[0] // 2, 1800), font_size=40, color="#FFFFFF")

    # Save
    img.save(output_path, "JPEG", quality=JPEG_QUALITY)
    logger.info(f"  Saved: {output_path.name}")


def generate_08_usage_guide(
    pack_name: str,
    config: PackConfig,
    output_path: Path,
) -> None:
    """Generate usage guide infographic.

    Args:
        pack_name: Pack name
        config: Pack configuration
        output_path: Output JPEG path
    """
    logger.info("Generating 08_usage_guide.jpg...")

    primary, secondary, accent = get_brand_colors(config)

    # Create background
    img = create_gradient_background(LISTING_SIZE, primary, secondary, vertical=False)
    draw = ImageDraw.Draw(img)

    # Title
    draw_text_centered(draw, "Quick Setup Guide", (LISTING_SIZE[0] // 2, 200), font_size=70, color="#FFFFFF")

    # Steps
    steps = [
        "1️⃣ Download & Extract ZIP files",
        "2️⃣ Open OBS Studio or Streamlabs",
        "3️⃣ Add Image Source → Browse",
        "4️⃣ Select your favorite variant",
        "5️⃣ Add text overlays & customize",
        "6️⃣ Start streaming! 🎮✨",
    ]

    y_start = 500
    y_spacing = 200

    for i, step in enumerate(steps):
        y = y_start + i * y_spacing
        draw_text_centered(draw, step, (LISTING_SIZE[0] // 2, y), font_size=50, color="#FFFFFF")

    # Footer
    draw_text_centered(draw, "Professional Results in Minutes!", (LISTING_SIZE[0] // 2, 1850), font_size=45, color=accent)

    # Save
    img.save(output_path, "JPEG", quality=JPEG_QUALITY)
    logger.info(f"  Saved: {output_path.name}")


def generate_listing_photos(
    pack_name: str,
    pack_dir: Path,
    config: PackConfig,
    dry_run: bool = False,
) -> int:
    """Generate all 8 Etsy listing photos.

    Args:
        pack_name: Name of the pack
        pack_dir: Pack directory path
        config: Pack configuration
        dry_run: If True, skip actual file creation

    Returns:
        Number of photos generated

    Raises:
        FileNotFoundError: If 03_final/ directory doesn't exist
    """
    final_dir = pack_dir / FINAL_DIR
    listing_dir = pack_dir / LISTING_DIR

    if not final_dir.exists():
        raise FileNotFoundError(f"Final directory not found: {final_dir}")

    if dry_run:
        logger.info("[dry-run] Would generate 8 Etsy listing photos")
        return 0

    # Create listing directory
    if listing_dir.exists():
        shutil.rmtree(listing_dir)
    listing_dir.mkdir(parents=True)

    # Generate each photo
    count = 0

    try:
        # 01: Hero showcase
        generate_01_hero_showcase(pack_name, config, final_dir, listing_dir / "01_hero_showcase.jpg")
        count += 1

        # 02-04: Screen demos
        for i, screen_type in enumerate(["starting", "brb", "ending"], start=2):
            output_name = f"0{i}_{screen_type}_screen_demo.jpg"
            generate_02_04_screen_demo(screen_type, pack_name, config, final_dir, listing_dir / output_name)
            count += 1

        # 05: Thumbnail showcase
        generate_05_thumbnail_showcase(pack_name, config, final_dir, listing_dir / "05_thumbnail_showcase.jpg")
        count += 1

        # 06: All screens grid
        generate_06_all_screens_grid(pack_name, config, final_dir, listing_dir / "06_all_screens_grid.jpg")
        count += 1

        # 07: File contents
        generate_07_file_contents(pack_name, config, listing_dir / "07_file_contents.jpg")
        count += 1

        # 08: Usage guide
        generate_08_usage_guide(pack_name, config, listing_dir / "08_usage_guide.jpg")
        count += 1

    except Exception as e:
        logger.error(f"Error generating listing photos: {e}")
        raise

    logger.info(f"Listing photos complete: {count} photos generated in {LISTING_DIR}/")

    return count


__all__ = [
    "generate_listing_photos",
]
