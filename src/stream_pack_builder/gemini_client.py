"""Thin wrapper around Google Gemini image generation (Nano Banana / Pro).

This module isolates the HTTP client so other code can stay framework-agnostic.
The implementation uses the official ``google-genai`` package.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Iterable, Optional
from io import BytesIO
import base64
from PIL import UnidentifiedImageError

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image

logger = logging.getLogger(__name__)
# Elevate to DEBUG if GEMINI_DEBUG is set
if os.getenv("GEMINI_DEBUG"):
    logging.getLogger().setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)

# Default priority: Nano Banana Pro (quality) -> Nano Banana (free/fast)
DEFAULT_IMAGE_MODELS = (
    "gemini-3-pro-image-preview",  # Nano Banana Pro
    "gemini-2.5-flash-image",  # Nano Banana / free tier
)


@dataclass
class GeminiSettings:
    """Runtime settings required to call the Gemini API."""

    api_key: str
    models: tuple[str, ...] = DEFAULT_IMAGE_MODELS

    @classmethod
    def from_env(cls) -> "GeminiSettings":
        """Load settings from environment variables or .env.

        Raises:
            RuntimeError: If no API key is available.
        """

        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. Create a .env or export the variable.")

        model_env = os.getenv("GEMINI_IMAGE_MODELS")
        models: tuple[str, ...] = DEFAULT_IMAGE_MODELS
        if model_env:
            models = tuple(m.strip() for m in model_env.split(",") if m.strip()) or DEFAULT_IMAGE_MODELS

        return cls(api_key=api_key, models=models)


SETTINGS: GeminiSettings | None = None
CLIENT: genai.Client | None = None


def _get_settings() -> GeminiSettings:
    global SETTINGS
    if SETTINGS is None:
        SETTINGS = GeminiSettings.from_env()
    return SETTINGS


def _get_client() -> genai.Client:
    global CLIENT
    if CLIENT is None:
        settings = _get_settings()
        CLIENT = genai.Client(api_key=settings.api_key)
    return CLIENT


def _iter_models() -> Iterable[str]:
    return _get_settings().models


def _get_error_json(exc: genai_errors.ClientError) -> dict:
    """Extract JSON error data from ClientError (version-compatible)."""
    for attr in ["response_json", "json", "error_data", "data"]:
        if hasattr(exc, attr):
            data = getattr(exc, attr)
            if data:
                return data
    return {}


def _handle_quota_error(exc: genai_errors.ClientError) -> Optional[float]:
    """Return retry delay seconds if provided by the API (RetryInfo)."""

    try:
        data = _get_error_json(exc)
        details = data.get("error", {}).get("details", [])
        for detail in details:
            if detail.get("@type", "").endswith("RetryInfo"):
                delay = detail.get("retryDelay")
                if isinstance(delay, str) and delay.endswith("s"):
                    return float(delay[:-1])
    except Exception:  # pragma: no cover - defensive
        return None
    return None


def generate_image(
    prompt: str,
    *,
    width: int,
    height: int,
    seed: Optional[int] = None,
    dry_run: bool = False,
) -> Image.Image:
    """Generate an image using Gemini image-capable models with fallback.

    Args:
        prompt: Full text prompt to send to the model.
        width: Desired output width in pixels (resize after generation).
        height: Desired output height in pixels (resize after generation).
        seed: Optional deterministic seed (not all models support it).
        dry_run: If ``True``, skip HTTP call and return a placeholder image.

    Returns:
        A ``PIL.Image.Image`` instance.

    Raises:
        RuntimeError: If no model succeeds.
    """

    if dry_run:
        logger.info("[dry-run] Would send prompt to Gemini: %s", prompt)
        return Image.new("RGB", (width, height), color=(64, 64, 96))

    client = _get_client()
    last_error: Exception | None = None

    for model in _iter_models():
        logger.info("Calling Gemini image model: %s", model)
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],  # force image return
                ),
            )

            image = _extract_pil_image(response)

            if image is None:
                logger.info("generate_content returned no image; trying generate_images fallback")
                _debug_dump_response(response, level=logging.INFO)
                try:
                    img_resp = client.models.generate_images(
                        model=model,
                        prompt=prompt,
                        config=types.GenerateImagesConfig(number_of_images=1),
                    )
                    image = _extract_pil_image(img_resp)
                except Exception as sub_exc:
                    logger.info("generate_images fallback failed: %s", sub_exc)

            if image is None:
                raise RuntimeError("No image found in API response")

            if image.size != (width, height):
                image = image.resize((width, height), Image.Resampling.LANCZOS)

            return image

        except genai_errors.ClientError as exc:
            last_error = exc
            delay = _handle_quota_error(exc)
            error_data = _get_error_json(exc)
            payload = json.dumps(error_data, ensure_ascii=False) if error_data else str(exc)
            status = getattr(exc, "status_code", None) or error_data.get("error", {}).get("code")
            if status == 429:
                logger.warning("Quota hit on %s: %s", model, payload)
                if delay:
                    logger.info("Retry suggested after %.1fs", delay)
                    time.sleep(delay)
                continue  # try next model
            logger.error("Gemini API error on %s: %s", model, payload)
        except Exception as exc:  # pragma: no cover - fallback
            last_error = exc
            logger.exception("Unexpected error from Gemini model %s", model)

    raise RuntimeError(f"All Gemini image models failed; last error: {last_error}")


def _debug_dump_response(response: types.GenerateContentResponse, level: int = logging.DEBUG) -> None:
    """Log a lightweight summary of the response for debugging."""

    try:
        parts = getattr(response, "parts", []) or []
        cands = getattr(response, "candidates", []) or []
        logger.log(
            level,
            "Response summary: parts=%d, candidates=%d, generated_images=%d",
            len(parts),
            len(cands),
            len(getattr(response, "generated_images", []) or []),
        )
        for idx, part in enumerate(parts):
            inline = getattr(part, "inline_data", None)
            mime = getattr(inline, "mime_type", None) if inline else None
            data_attr = getattr(inline, "data", None) if inline else None
            dlen = len(data_attr) if hasattr(data_attr, "__len__") else 0
            logger.log(level, "  top.part[%d]: inline=%s mime=%s len=%s type=%s", idx, bool(inline), mime, dlen, type(data_attr).__name__ if data_attr is not None else None)
        for c_idx, cand in enumerate(cands):
            content = getattr(cand, "content", None)
            cand_parts = getattr(content, "parts", []) or []
            logger.log(level, "  cand[%d]: parts=%d finish=%s safety=%s", c_idx, len(cand_parts), getattr(cand, "finish_reason", None), getattr(cand, "safety_ratings", None))
            for p_idx, part in enumerate(cand_parts):
                inline = getattr(part, "inline_data", None)
                mime = getattr(inline, "mime_type", None) if inline else None
                data_attr = getattr(inline, "data", None) if inline else None
                dlen = len(data_attr) if hasattr(data_attr, "__len__") else 0
                logger.log(level, "    part[%d]: inline=%s mime=%s len=%s type=%s", p_idx, bool(inline), mime, dlen, type(data_attr).__name__ if data_attr is not None else None)
    except Exception:  # pragma: no cover - debug helper
        logger.log(level, "Could not dump response summary", exc_info=True)

def _extract_pil_image(response: types.GenerateContentResponse) -> Optional[Image.Image]:
    """Best-effort extraction of PIL.Image from a generate_content response."""

    first_blob: bytes | None = None
    first_mime: str | None = None

    def iter_parts() -> Iterable:
        # top-level parts
        for p in getattr(response, "parts", []) or []:
            yield p
        # candidates -> content.parts
        for cand in getattr(response, "candidates", []) or []:
            content = getattr(cand, "content", None)
            if content:
                for p in getattr(content, "parts", []) or []:
                    yield p

    # 1) parts with inline_data / as_image
    for part in iter_parts():
        if hasattr(part, "as_image"):
            try:
                img = part.as_image()
                if isinstance(img, Image.Image):
                    return img
            except Exception as exc:
                logger.debug("part.as_image() failed: %s", exc)
        inline = getattr(part, "inline_data", None)
        if inline is not None:
            data = getattr(inline, "data", None)
            logger.debug("inline_data present: len=%s type=%s mime=%s", len(data) if hasattr(data, "__len__") else None, type(data).__name__ if data is not None else None, getattr(inline, "mime_type", None))
            if isinstance(data, str):
                try:
                    data = base64.b64decode(data)
                except Exception:
                    data = None
            if isinstance(data, memoryview):
                data = data.tobytes()
            if isinstance(data, (bytes, bytearray)) and data:
                if first_blob is None:
                    first_blob = bytes(data)
                    first_mime = getattr(inline, "mime_type", None)
                try:
                    img = _bytes_to_image(data)
                    img.load()
                    logger.debug("Extracted image from inline_data: %s %s", type(img), img.size)
                    return img
                except UnidentifiedImageError as exc:
                    logger.debug("Inline data could not be identified as image: %s", exc)
                except Exception as exc:
                    logger.debug("Inline data bytes failed to open: %s", exc)
                    continue
            # some versions expose inline_data.as_image()
            if hasattr(inline, "as_image"):
                try:
                    img = inline.as_image()
                    if isinstance(img, Image.Image):
                        logger.debug("Extracted image via inline.as_image: %s %s", type(img), getattr(img, "size", None))
                        return img
                except Exception as exc:
                    logger.debug("inline.as_image() failed: %s", exc)

    # 2) generated_images (Imagen-style responses)
    for gen_img in getattr(response, "generated_images", []) or []:
        pil_candidate = getattr(gen_img, "image", None)
        if isinstance(pil_candidate, Image.Image):
            return pil_candidate
        if hasattr(gen_img, "as_image"):
            try:
                img = gen_img.as_image()
                if isinstance(img, Image.Image):
                    return img
            except Exception as exc:
                logger.debug("generated_image.as_image() failed: %s", exc)
        data = getattr(gen_img, "image_bytes", None)
        if isinstance(data, (bytes, bytearray)) and data:
            try:
                img = _bytes_to_image(data)
                img.load()
                logger.debug("Extracted image from image_bytes: %s %s", type(img), img.size)
                return img
            except UnidentifiedImageError as exc:
                logger.debug("image_bytes not a valid image: %s", exc)
            except Exception as exc:
                logger.debug("image_bytes failed to open: %s", exc)
                continue
        if isinstance(data, str):
            try:
                raw = base64.b64decode(data)
                img = Image.open(BytesIO(raw))
                img.load()
                logger.debug("Extracted image from base64 image_bytes: %s %s", type(img), img.size)
                return img
            except UnidentifiedImageError as exc:
                logger.debug("base64 image_bytes not valid image: %s", exc)
            except Exception as exc:
                logger.debug("base64 image_bytes failed: %s", exc)
                continue

    if first_blob:
        try:
            img = Image.open(BytesIO(first_blob))
            img.load()
            logger.debug("Extracted image from first_blob fallback: %s %s", type(img), img.size)
            return img
        except Exception as exc:
            logger.debug("first_blob fallback failed (mime=%s): %s", first_mime, exc)

    return None


def _bytes_to_image(data: bytes) -> Image.Image:
    """Try direct decode; if fails, try base64 decode then decode."""

    try:
        return Image.open(BytesIO(data))
    except UnidentifiedImageError:
        pass

    # Heuristic: if looks like base64 text, attempt to decode
    try:
        decoded = base64.b64decode(data, validate=False)
        return Image.open(BytesIO(decoded))
    except Exception:
        raise


__all__ = ["GeminiSettings", "generate_image"]
