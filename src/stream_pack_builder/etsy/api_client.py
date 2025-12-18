"""Etsy API v3 client for listing management."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

import requests

logger = logging.getLogger(__name__)

# Etsy API v3 base URL
ETSY_API_BASE = "https://openapi.etsy.com/v3"

# Rate limit: 10 requests/second per shop
RATE_LIMIT_DELAY = 0.11  # seconds between requests


class EtsyAPIError(Exception):
    """Base exception for Etsy API errors."""
    pass


class EtsyRateLimitError(EtsyAPIError):
    """Rate limit exceeded error."""
    pass


class EtsyAuthenticationError(EtsyAPIError):
    """Authentication error."""
    pass


class EtsyAPIClient:
    """Etsy API v3 client.

    Handles OAuth 2.0 authentication and all listing-related operations.
    """

    def __init__(
        self,
        api_key: str,
        shop_id: str,
        access_token: str,
        refresh_token: Optional[str] = None,
    ):
        """Initialize Etsy API client.

        Args:
            api_key: Etsy API key (keystring)
            shop_id: Shop ID
            access_token: OAuth 2.0 access token
            refresh_token: OAuth 2.0 refresh token (optional, for token refresh)
        """
        self.api_key = api_key
        self.shop_id = shop_id
        self.access_token = access_token
        self.refresh_token = refresh_token

        self._last_request_time = 0.0

    def _wait_for_rate_limit(self) -> None:
        """Wait to respect rate limit (10 req/sec)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _get_headers(self, content_type: str = "application/json") -> Dict[str, str]:
        """Get request headers with authentication.

        Args:
            content_type: Content-Type header value

        Returns:
            Headers dict
        """
        return {
            "x-api-key": self.api_key,
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": content_type,
        }

    def _handle_response(self, response: requests.Response) -> Dict[Any, Any]:
        """Handle API response and errors.

        Args:
            response: requests Response object

        Returns:
            Parsed JSON response

        Raises:
            EtsyRateLimitError: Rate limit exceeded
            EtsyAuthenticationError: Authentication failed
            EtsyAPIError: Other API errors
        """
        # Rate limit
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            raise EtsyRateLimitError(
                f"Rate limit exceeded. Retry after {retry_after} seconds."
            )

        # Authentication errors
        if response.status_code == 401:
            raise EtsyAuthenticationError(
                "Authentication failed. Access token may be expired."
            )

        # Other errors
        if response.status_code >= 400:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", response.text)
            except Exception:
                error_msg = response.text

            raise EtsyAPIError(
                f"API request failed (status {response.status_code}): {error_msg}"
            )

        # Success
        return response.json()

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        files: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[Any, Any]:
        """Make API request with rate limiting and error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., "/application/shops/{shop_id}/listings")
            data: JSON data for request body
            files: Files for multipart upload
            params: URL query parameters

        Returns:
            Parsed JSON response

        Raises:
            EtsyAPIError: API request failed
        """
        # Wait for rate limit
        self._wait_for_rate_limit()

        # Build URL
        url = f"{ETSY_API_BASE}{endpoint}"

        # Prepare headers
        if files:
            # For multipart uploads, don't set Content-Type (requests will set it)
            headers = {
                "x-api-key": self.api_key,
                "Authorization": f"Bearer {self.access_token}",
            }
        else:
            headers = self._get_headers()

        # Make request
        logger.debug(f"{method} {url}")

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=data if not files else None,
            files=files,
            params=params,
        )

        # Handle response
        return self._handle_response(response)

    def create_draft_listing(
        self,
        title: str,
        description: str,
        price: float,
        quantity: int = 999,
        taxonomy_id: int = 1656,
        **kwargs
    ) -> Dict[Any, Any]:
        """Create a draft listing.

        Args:
            title: Listing title (max 140 chars)
            description: Listing description (HTML allowed)
            price: Price in USD
            quantity: Available quantity (default 999 for digital)
            taxonomy_id: Etsy category taxonomy ID (default 1656 for Digital)
            **kwargs: Additional listing fields

        Returns:
            Created listing data including listing_id

        Raises:
            EtsyAPIError: Failed to create listing
        """
        # Prepare listing data
        listing_data = {
            "title": title[:140],  # Enforce 140 char limit
            "description": description,
            "price": price,
            "quantity": quantity,
            "state": "draft",
            "taxonomy_id": taxonomy_id,
            "who_made": "i_did",
            "when_made": "made_to_order",
            "is_supply": False,
            "type": "download",  # Digital download
            **kwargs
        }

        endpoint = f"/application/shops/{self.shop_id}/listings"
        result = self._request("POST", endpoint, data=listing_data)

        logger.info(f"Created draft listing: {result.get('listing_id')}")
        return result

    def upload_listing_image(
        self,
        listing_id: int,
        image_path: Path,
        rank: int = 1,
    ) -> Dict[Any, Any]:
        """Upload an image to a listing.

        Args:
            listing_id: Listing ID
            image_path: Path to image file (JPEG recommended)
            rank: Image rank/position (1 = first/main image)

        Returns:
            Uploaded image data

        Raises:
            EtsyAPIError: Failed to upload image
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        endpoint = f"/application/shops/{self.shop_id}/listings/{listing_id}/images"

        # Prepare multipart upload
        with open(image_path, "rb") as f:
            files = {
                "image": (image_path.name, f, "image/jpeg")
            }
            data = {
                "rank": rank
            }

            # For multipart, use form data instead of JSON
            response = requests.post(
                f"{ETSY_API_BASE}{endpoint}",
                headers={
                    "x-api-key": self.api_key,
                    "Authorization": f"Bearer {self.access_token}",
                },
                files=files,
                data=data,
            )

        result = self._handle_response(response)
        logger.debug(f"Uploaded image: {image_path.name} (rank {rank})")
        return result

    def upload_digital_file(
        self,
        listing_id: int,
        file_path: Path,
        name: Optional[str] = None,
        rank: int = 1,
    ) -> Dict[Any, Any]:
        """Upload a digital file to a listing.

        Args:
            listing_id: Listing ID
            file_path: Path to file (ZIP recommended, max 250MB)
            name: Display name for file (defaults to filename)
            rank: File rank/position

        Returns:
            Uploaded file data

        Raises:
            EtsyAPIError: Failed to upload file
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Check file size (250MB limit)
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        if file_size_mb > 250:
            raise EtsyAPIError(
                f"File too large: {file_size_mb:.1f}MB (max 250MB): {file_path.name}"
            )

        endpoint = f"/application/shops/{self.shop_id}/listings/{listing_id}/files"

        display_name = name or file_path.name

        # Prepare multipart upload
        with open(file_path, "rb") as f:
            files = {
                "file": (file_path.name, f, "application/zip")
            }
            data = {
                "name": display_name,
                "rank": rank,
            }

            response = requests.post(
                f"{ETSY_API_BASE}{endpoint}",
                headers={
                    "x-api-key": self.api_key,
                    "Authorization": f"Bearer {self.access_token}",
                },
                files=files,
                data=data,
            )

        result = self._handle_response(response)
        logger.debug(f"Uploaded digital file: {file_path.name} ({file_size_mb:.1f}MB)")
        return result

    def update_listing(
        self,
        listing_id: int,
        **kwargs
    ) -> Dict[Any, Any]:
        """Update listing fields.

        Args:
            listing_id: Listing ID
            **kwargs: Fields to update (title, description, price, tags, etc.)

        Returns:
            Updated listing data

        Raises:
            EtsyAPIError: Failed to update listing
        """
        endpoint = f"/application/shops/{self.shop_id}/listings/{listing_id}"
        result = self._request("PUT", endpoint, data=kwargs)

        logger.debug(f"Updated listing {listing_id}")
        return result

    def add_listing_tags(
        self,
        listing_id: int,
        tags: List[str],
    ) -> Dict[Any, Any]:
        """Add tags to a listing.

        Args:
            listing_id: Listing ID
            tags: List of tags (max 13, each max 20 chars)

        Returns:
            Updated listing data

        Raises:
            EtsyAPIError: Failed to add tags
        """
        # Validate tags
        if len(tags) > 13:
            logger.warning(f"Too many tags ({len(tags)}), truncating to 13")
            tags = tags[:13]

        # Truncate long tags
        tags = [tag[:20] for tag in tags]

        # Update listing with tags
        return self.update_listing(listing_id, tags=tags)

    def publish_listing(
        self,
        listing_id: int,
    ) -> Dict[Any, Any]:
        """Publish a draft listing (set state to 'active').

        Args:
            listing_id: Listing ID

        Returns:
            Published listing data

        Raises:
            EtsyAPIError: Failed to publish listing
        """
        result = self.update_listing(listing_id, state="active")
        logger.info(f"Published listing {listing_id}")
        return result

    def get_listing(
        self,
        listing_id: int,
    ) -> Dict[Any, Any]:
        """Get listing details.

        Args:
            listing_id: Listing ID

        Returns:
            Listing data

        Raises:
            EtsyAPIError: Failed to get listing
        """
        endpoint = f"/application/listings/{listing_id}"
        return self._request("GET", endpoint)

    def get_listing_url(self, listing_id: int, slug: str = "") -> str:
        """Generate Etsy listing URL.

        Args:
            listing_id: Listing ID
            slug: URL slug (optional, for SEO-friendly URLs)

        Returns:
            Full Etsy listing URL
        """
        if slug:
            return f"https://www.etsy.com/listing/{listing_id}/{slug}"
        else:
            return f"https://www.etsy.com/listing/{listing_id}"


__all__ = [
    "EtsyAPIClient",
    "EtsyAPIError",
    "EtsyRateLimitError",
    "EtsyAuthenticationError",
]
