"""Extract structured invoice data through the local OpenCode vision proxy."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from openai import OpenAI


PROJECT_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = PROJECT_DIR.parent
DEFAULT_BASE_URL = "http://localhost:4096/v1"
DEFAULT_MODEL = "gpt-5.4"

INVOICE_SCHEMA = {
    "header": {
        "invoice_no": "string",
        "invoice_date": "MM/DD/YYYY",
        "seller": "string",
        "client": "string",
        "seller_tax_id": "string",
        "client_tax_id": "string",
        "iban": "string",
    },
    "items": [
        {
            "item_desc": "string",
            "item_qty": "string",
            "item_net_price": "string",
            "item_net_worth": "string",
            "item_vat": "string",
            "item_gross_worth": "string",
        }
    ],
    "summary": {
        "total_net_worth": "string",
        "total_vat": "string",
        "total_gross_worth": "string",
    },
}

PROMPT = f"""Extract the invoice in this image into the exact JSON structure below.

Return ONLY valid JSON. No markdown, no explanation, and no code fences.
Use empty strings for unreadable scalar values and an empty array when no line items are visible.
Preserve the invoice's displayed text and numeric formatting where possible.

Required JSON schema:
{json.dumps(INVOICE_SCHEMA, indent=2)}
"""


class ExtractionError(RuntimeError):
    """Raised when the local proxy cannot produce a valid invoice object."""


def proxy_settings() -> tuple[str, str]:
    """Load proxy settings from the local environment."""
    load_dotenv(REPOSITORY_DIR / ".env")
    return (
        os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
    )


def create_client(base_url: str | None = None) -> OpenAI:
    """Create a bounded-timeout OpenAI-compatible client for the proxy."""
    resolved_base_url, _ = proxy_settings()
    return OpenAI(
        base_url=base_url or resolved_base_url,
        api_key=os.getenv("OPENAI_API_KEY", "not-needed"),
        timeout=httpx.Timeout(connect=5.0, read=90.0, write=30.0, pool=5.0),
        max_retries=0,
    )


def verify_proxy(client: OpenAI | None = None) -> str:
    """Make a tiny text request so unavailable proxies fail before batch work starts."""
    base_url, model = proxy_settings()
    active_client = client or create_client(base_url)
    try:
        response = active_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with exactly: ok"}],
            max_tokens=5,
        )
    except Exception as error:
        raise ExtractionError(
            f"OpenCode proxy is unavailable or incompatible at {base_url}: {error}. "
            "Start it on port 4096 before running extraction."
        ) from error

    if not response.choices or not response.choices[0].message.content:
        raise ExtractionError("OpenCode proxy text-only verification returned an empty response.")
    return model


def parse_json_response(content: str) -> dict[str, Any]:
    """Parse a model response while tolerating accidental Markdown fences."""
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1] if "\n" in candidate else ""
        if candidate.endswith("```"):
            candidate = candidate[:-3].strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise ExtractionError("Model response did not contain a JSON object.") from None
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as error:
            raise ExtractionError(f"Model returned malformed JSON: {error}") from error

    if not isinstance(parsed, dict):
        raise ExtractionError("Model response JSON must be an object.")
    return parsed


def extract_invoice(image_path: str | Path, client: OpenAI | None = None, model: str | None = None) -> dict[str, Any]:
    """Send one invoice image to the proxy and return its structured JSON result."""
    image = Path(image_path)
    if not image.is_file():
        raise FileNotFoundError(f"Invoice image not found: {image}")

    base_url, configured_model = proxy_settings()
    mime_type = mimetypes.guess_type(image.name)[0] or "image/jpeg"
    encoded_image = base64.b64encode(image.read_bytes()).decode("ascii")
    active_client = client or create_client(base_url)

    try:
        response = active_client.chat.completions.create(
            model=model or configured_model,
            messages=[
                {"role": "system", "content": "You are a precise invoice data extraction service."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{encoded_image}"},
                        },
                    ],
                },
            ],
            max_tokens=8192,
        )
    except Exception as error:
        raise ExtractionError(f"Invoice extraction request failed for {image.name}: {error}") from error

    if not response.choices or not response.choices[0].message.content:
        raise ExtractionError(f"Invoice extraction returned an empty response for {image.name}.")
    return parse_json_response(response.choices[0].message.content)


def main() -> int:
    """Extract one image and print its JSON result."""
    parser = argparse.ArgumentParser(description="Extract one invoice through the OpenCode vision proxy.")
    parser.add_argument("image_path", type=Path)
    args = parser.parse_args()
    try:
        verify_proxy()
        print(json.dumps(extract_invoice(args.image_path), indent=2, ensure_ascii=True))
    except (ExtractionError, OSError) as error:
        print(f"ERROR: {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
