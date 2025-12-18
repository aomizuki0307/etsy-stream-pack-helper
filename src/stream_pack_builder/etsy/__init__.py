"""Etsy deliverables automation and API integration module.

This module handles:
- Listing photos (8 JPG mockups)
- Digital delivery files (4 ZIP archives)
- README.txt files (usage instructions)
- Etsy API integration (OAuth 2.0, listing upload)
"""

from .readme_generator import generate_readme, generate_master_readme
from .digital_delivery import create_digital_delivery_files
from .listing_photos import generate_listing_photos
from .uploader import upload_pack_to_etsy
from .api_client import EtsyAPIClient, EtsyAPIError
from .listing_metadata import (
    generate_listing_title,
    generate_listing_description,
    generate_tags,
    calculate_price,
)

__all__ = [
    # Phase 4: Deliverables generation
    "generate_readme",
    "generate_master_readme",
    "create_digital_delivery_files",
    "generate_listing_photos",
    # Phase 5: Etsy API integration
    "upload_pack_to_etsy",
    "EtsyAPIClient",
    "EtsyAPIError",
    "generate_listing_title",
    "generate_listing_description",
    "generate_tags",
    "calculate_price",
]
