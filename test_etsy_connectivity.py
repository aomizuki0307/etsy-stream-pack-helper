"""Etsy API簡易疎通テスト

Keystringの有効性を確認します。
"""

import os
import sys
from dotenv import load_dotenv
import requests

# Load .env
load_dotenv()

print("=" * 70)
print("  Etsy API Connectivity Test")
print("=" * 70)
print()

# Check if API key is set
api_key = os.getenv("ETSY_API_KEY")
if not api_key:
    print("❌ ETSY_API_KEY not found in .env")
    print()
    print("Please add your Etsy API credentials to .env:")
    print("  ETSY_API_KEY=<your_keystring>")
    print("  ETSY_SHARED_SECRET=<your_shared_secret>")
    print()
    sys.exit(1)

print(f"✓ ETSY_API_KEY found ({len(api_key)} chars)")
print()

# Test API connectivity with a simple ping endpoint
print("Testing API connectivity...")
print()

# Use the /v3/application/openapi-ping endpoint (doesn't require auth)
url = "https://openapi.etsy.com/v3/application/openapi-ping"
headers = {
    "x-api-key": api_key
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    
    print(f"Response status: {response.status_code}")
    
    if response.status_code == 200:
        print("✓ API key is valid!")
        print()
        print("Response:", response.json())
    elif response.status_code == 401:
        print("❌ Authentication failed (401)")
        print("   Your API key may be invalid or inactive.")
    elif response.status_code == 403:
        print("❌ Forbidden (403)")
        print("   Your API key may not have the required permissions.")
    else:
        print(f"❌ Unexpected response: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
    
    print()
    
except requests.exceptions.RequestException as e:
    print(f"❌ Network error: {e}")
    print()
    sys.exit(1)

print("=" * 70)
print("Next steps:")
print("  1. If API key is valid, run OAuth setup:")
print("     python scripts/setup_etsy_oauth.py")
print("  2. Set callback URL in Etsy Developer Portal to match your setup")
print("=" * 70)
