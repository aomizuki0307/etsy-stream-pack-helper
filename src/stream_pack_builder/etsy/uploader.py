"""Etsy uploader orchestrator.

Handles the complete flow of uploading a pack to Etsy.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

from ..config import PackConfig
from ..multi_agent.state import WorkflowState
from ..utils import packs_root

from .api_client import EtsyAPIClient, EtsyAPIError
from .listing_metadata import (
    generate_listing_title,
    generate_listing_description,
    generate_tags,
    calculate_price,
    generate_slug,
)

logger = logging.getLogger(__name__)

# Directory names
LISTING_PHOTOS_DIR = "05_etsy_listing"
DIGITAL_DELIVERY_DIR = "06_digital_delivery"

# Etsy taxonomy ID for digital downloads
# TODO: Verify correct taxonomy ID via Etsy API
DIGITAL_TAXONOMY_ID = 1656


def upload_pack_to_etsy(
    pack_name: str,
    pack_dir: Optional[Path] = None,
    config: Optional[PackConfig] = None,
    workflow_state: Optional[WorkflowState] = None,
    dry_run: bool = False,
    base_price: float = 9.99,
) -> Dict[str, Any]:
    """Upload a pack to Etsy.

    This function orchestrates the complete upload process:
    1. Create draft listing with metadata
    2. Upload listing photos (8 images)
    3. Upload digital files (4 ZIPs)
    4. Add tags
    5. Publish listing

    Args:
        pack_name: Name of the pack
        pack_dir: Pack directory path (optional, will resolve from pack_name)
        config: Pack configuration (optional, will load from pack_dir)
        workflow_state: Workflow state (optional, for quality scoring)
        dry_run: If True, skip actual API calls
        base_price: Base price in USD (default 9.99)

    Returns:
        Upload result dict with:
        {
            "success": bool,
            "listing_id": int,
            "listing_url": str,
            "state": str,
            "photos_uploaded": int,
            "files_uploaded": int,
            "error": str (if failed),
        }

    Raises:
        FileNotFoundError: If pack directory or required files not found
        EtsyAPIError: If API calls fail
    """
    # Resolve pack directory
    if pack_dir is None:
        pack_dir = packs_root() / pack_name

    if not pack_dir.exists():
        raise FileNotFoundError(f"Pack directory not found: {pack_dir}")

    # Load config if not provided
    if config is None:
        config_path = pack_dir / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        config = PackConfig.load(config_path)

    # Load workflow state if available and not provided
    if workflow_state is None:
        try:
            workflow_state = WorkflowState.load(pack_dir)
        except Exception:
            logger.debug("No workflow state found, continuing without quality scoring")

    # Check for required directories
    listing_photos_dir = pack_dir / LISTING_PHOTOS_DIR
    digital_delivery_dir = pack_dir / DIGITAL_DELIVERY_DIR

    if not listing_photos_dir.exists():
        raise FileNotFoundError(
            f"Listing photos directory not found: {listing_photos_dir}. "
            "Run Phase 4 first to generate Etsy deliverables."
        )

    if not digital_delivery_dir.exists():
        raise FileNotFoundError(
            f"Digital delivery directory not found: {digital_delivery_dir}. "
            "Run Phase 4 first to generate Etsy deliverables."
        )

    # Initialize result
    result = {
        "success": False,
        "listing_id": None,
        "listing_url": None,
        "state": None,
        "photos_uploaded": 0,
        "files_uploaded": 0,
    }

    # Dry-run mode
    if dry_run:
        logger.info("[dry-run] Would upload pack to Etsy")
        logger.info(f"[dry-run]   Pack: {pack_name}")
        logger.info(f"[dry-run]   Photos dir: {listing_photos_dir}")
        logger.info(f"[dry-run]   Files dir: {digital_delivery_dir}")
        result["success"] = True
        return result

    # Get Etsy credentials from environment
    api_key = os.getenv("ETSY_API_KEY")
    shop_id = os.getenv("ETSY_SHOP_ID")
    access_token = os.getenv("ETSY_ACCESS_TOKEN")
    refresh_token = os.getenv("ETSY_REFRESH_TOKEN")

    if not all([api_key, shop_id, access_token]):
        raise ValueError(
            "Etsy credentials not configured. Set ETSY_API_KEY, ETSY_SHOP_ID, "
            "and ETSY_ACCESS_TOKEN in .env file. "
            "Run scripts/setup_etsy_oauth.py to configure."
        )

    # Initialize API client
    client = EtsyAPIClient(
        api_key=api_key,
        shop_id=shop_id,
        access_token=access_token,
        refresh_token=refresh_token,
    )

    logger.info("=" * 60)
    logger.info("ETSY UPLOAD START")
    logger.info("=" * 60)

    try:
        # Step 1: Generate metadata
        logger.info("Step 1: Generating listing metadata...")

        title = generate_listing_title(pack_name, config)
        description = generate_listing_description(pack_name, config, workflow_state)
        tags = generate_tags(pack_name, config)
        price = calculate_price(pack_name, config, workflow_state, base_price)
        slug = generate_slug(pack_name)

        logger.info(f"  Title: {title}")
        logger.info(f"  Price: ${price:.2f}")
        logger.info(f"  Tags: {len(tags)} tags")

        # Step 2: Create draft listing
        logger.info("Step 2: Creating draft listing...")

        listing_data = client.create_draft_listing(
            title=title,
            description=description,
            price=price,
            quantity=999,  # Digital downloads - high quantity
            taxonomy_id=DIGITAL_TAXONOMY_ID,
        )

        listing_id = listing_data.get("listing_id")
        result["listing_id"] = listing_id
        logger.info(f"  Created listing: {listing_id}")

        # Step 3: Upload listing photos
        logger.info(f"Step 3: Uploading listing photos...")

        photo_files = sorted(listing_photos_dir.glob("*.jpg"))
        if not photo_files:
            logger.warning("No listing photos found")
        else:
            for i, photo_path in enumerate(photo_files, start=1):
                logger.info(f"  [{i}/{len(photo_files)}] Uploading {photo_path.name}...")
                try:
                    client.upload_listing_image(
                        listing_id=listing_id,
                        image_path=photo_path,
                        rank=i,
                    )
                    result["photos_uploaded"] += 1
                    logger.info(f"    ✓ Uploaded")
                except EtsyAPIError as e:
                    logger.error(f"    ✗ Failed: {e}")

        logger.info(f"  Uploaded {result['photos_uploaded']}/{len(photo_files)} photos")

        # Step 4: Upload digital files
        logger.info(f"Step 4: Uploading digital files...")

        zip_files = sorted(digital_delivery_dir.glob("*.zip"))
        if not zip_files:
            logger.warning("No digital files found")
        else:
            for i, zip_path in enumerate(zip_files, start=1):
                # Get file size
                file_size_mb = zip_path.stat().st_size / (1024 * 1024)
                logger.info(f"  [{i}/{len(zip_files)}] Uploading {zip_path.name} ({file_size_mb:.1f}MB)...")

                try:
                    client.upload_digital_file(
                        listing_id=listing_id,
                        file_path=zip_path,
                        name=zip_path.stem.replace("_", " ").title(),
                        rank=i,
                    )
                    result["files_uploaded"] += 1
                    logger.info(f"    ✓ Uploaded")
                except EtsyAPIError as e:
                    logger.error(f"    ✗ Failed: {e}")

        logger.info(f"  Uploaded {result['files_uploaded']}/{len(zip_files)} files")

        # Step 5: Add tags
        logger.info(f"Step 5: Adding tags...")
        try:
            client.add_listing_tags(listing_id, tags)
            logger.info(f"  ✓ Added {len(tags)} tags")
        except EtsyAPIError as e:
            logger.error(f"  ✗ Failed to add tags: {e}")

        # Step 6: Publish listing
        logger.info(f"Step 6: Publishing listing...")
        try:
            publish_result = client.publish_listing(listing_id)
            result["state"] = publish_result.get("state", "unknown")
            logger.info(f"  ✓ Published (state: {result['state']})")
        except EtsyAPIError as e:
            logger.error(f"  ✗ Failed to publish: {e}")
            result["state"] = "draft"

        # Generate listing URL
        result["listing_url"] = client.get_listing_url(listing_id, slug)

        # Success
        result["success"] = True

        logger.info("=" * 60)
        logger.info("ETSY UPLOAD COMPLETE")
        logger.info(f"  Listing ID: {listing_id}")
        logger.info(f"  State: {result['state']}")
        logger.info(f"  URL: {result['listing_url']}")
        logger.info(f"  Photos: {result['photos_uploaded']} uploaded")
        logger.info(f"  Files: {result['files_uploaded']} uploaded")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Etsy upload failed: {e}")
        result["success"] = False
        result["error"] = str(e)
        raise

    return result


__all__ = [
    "upload_pack_to_etsy",
]
