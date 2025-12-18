"""Etsy OAuth 2.0 setup script.

This script helps users configure Etsy API access by:
1. Guiding through app creation on Etsy Developer
2. Facilitating OAuth 2.0 authorization flow
3. Saving credentials to .env file

Run this script once before using Etsy upload features.
"""

import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import requests

print("=" * 70)
print("  Etsy OAuth 2.0 Setup")
print("=" * 70)
print()

# Step 1: Get API Key
print("STEP 1: Get your Etsy API Key")
print("-" * 70)
print()
print("1. Go to: https://www.etsy.com/developers/your-apps")
print("2. Create a new app (or use existing)")
print("3. Copy your API Key (keystring)")
print()

api_key = input("Enter your Etsy API Key: ").strip()

if not api_key:
    print("Error: API Key is required")
    sys.exit(1)

print()

# Step 2: Get Shop ID
print("STEP 2: Get your Shop ID")
print("-" * 70)
print()
print("1. Go to your Etsy shop")
print("2. Your Shop ID is in the URL: etsy.com/shop/{SHOP_ID}")
print("   OR you can find it in your shop settings")
print()

shop_id = input("Enter your Shop ID: ").strip()

if not shop_id:
    print("Error: Shop ID is required")
    sys.exit(1)

print()

# Step 3: Configure redirect URI
print("STEP 3: Configure OAuth Redirect URI")
print("-" * 70)
print()
print("In your Etsy App settings, add this redirect URI:")
print("  http://localhost:8000/callback")
print()
input("Press Enter when done...")
print()

# OAuth parameters
REDIRECT_URI = "http://localhost:8000/callback"
SCOPE = "listings_w listings_r listings_d shops_r shops_w"
STATE = "etsy_oauth_state_12345"

# Step 4: Authorization URL
print("STEP 4: Authorize the App")
print("-" * 70)
print()
print("Opening browser for authorization...")
print()

# Build authorization URL
auth_params = {
    "response_type": "code",
    "client_id": api_key,
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPE,
    "state": STATE,
}

auth_url = f"https://www.etsy.com/oauth/connect?{urlencode(auth_params)}"

# Open browser
webbrowser.open(auth_url)

print("If browser didn't open, go to:")
print(auth_url)
print()
print("After authorizing, you'll be redirected to:")
print("  http://localhost:8000/callback?code=...")
print()
print("The page will show an error (localhost not running), but that's OK!")
print("Copy the FULL URL from your browser address bar.")
print()

# Get callback URL from user
callback_url = input("Paste the callback URL here: ").strip()

if not callback_url:
    print("Error: Callback URL is required")
    sys.exit(1)

# Parse callback URL to extract code
parsed = urlparse(callback_url)
params = parse_qs(parsed.query)

if "code" not in params:
    print("Error: No authorization code found in URL")
    print("Make sure you copied the full URL including '?code=...'")
    sys.exit(1)

auth_code = params["code"][0]
print()
print(f"✓ Got authorization code: {auth_code[:20]}...")
print()

# Step 5: Exchange code for tokens
print("STEP 5: Getting Access Token")
print("-" * 70)
print()

token_url = "https://api.etsy.com/v3/public/oauth/token"
token_data = {
    "grant_type": "authorization_code",
    "client_id": api_key,
    "redirect_uri": REDIRECT_URI,
    "code": auth_code,
}

print("Exchanging authorization code for access token...")

try:
    response = requests.post(token_url, data=token_data)
    response.raise_for_status()
    token_response = response.json()

    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    expires_in = token_response.get("expires_in")

    if not access_token:
        print("Error: Failed to get access token")
        print(f"Response: {token_response}")
        sys.exit(1)

    print(f"✓ Got access token (expires in {expires_in}s)")
    print(f"✓ Got refresh token")
    print()

except requests.exceptions.RequestException as e:
    print(f"Error: Failed to exchange code for token: {e}")
    if hasattr(e.response, "text"):
        print(f"Response: {e.response.text}")
    sys.exit(1)

# Step 6: Save to .env
print("STEP 6: Saving to .env file")
print("-" * 70)
print()

env_path = project_root / ".env"

# Read existing .env
env_lines = []
if env_path.exists():
    with open(env_path, "r") as f:
        env_lines = f.readlines()

# Remove existing Etsy variables
env_lines = [
    line for line in env_lines
    if not any(line.startswith(key) for key in [
        "ETSY_API_KEY=",
        "ETSY_SHOP_ID=",
        "ETSY_ACCESS_TOKEN=",
        "ETSY_REFRESH_TOKEN=",
    ])
]

# Add new Etsy variables
env_lines.append(f"\n# Etsy API Configuration\n")
env_lines.append(f"ETSY_API_KEY={api_key}\n")
env_lines.append(f"ETSY_SHOP_ID={shop_id}\n")
env_lines.append(f"ETSY_ACCESS_TOKEN={access_token}\n")
env_lines.append(f"ETSY_REFRESH_TOKEN={refresh_token}\n")

# Write back
with open(env_path, "w") as f:
    f.writelines(env_lines)

print(f"✓ Saved credentials to {env_path}")
print()

# Step 7: Success
print("=" * 70)
print("  ✓ Etsy OAuth Setup Complete!")
print("=" * 70)
print()
print("Your Etsy API credentials have been configured.")
print()
print("You can now upload packs to Etsy:")
print()
print("  python -m stream_pack_builder.cli multi-agent-build neon_cyberpunk \\")
print("      --max-rounds 3 --upload-to-etsy")
print()
print("Or upload an existing pack:")
print()
print("  python -m stream_pack_builder.cli upload-to-etsy neon_cyberpunk")
print()
print("Note: Access tokens expire after 1 hour. The refresh token will be")
print("used automatically to get a new access token when needed.")
print()
print("=" * 70)
