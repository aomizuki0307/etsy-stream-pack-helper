# Etsy API Setup Guide

This guide helps you configure Etsy API credentials for automated listing creation.

## Prerequisites

1. Etsy Developer Account
2. Approved Etsy App with API credentials (Keystring + Shared Secret)
3. GitHub Pages site (for OAuth callback URL)

## Step 1: Get Etsy API Credentials

1. Go to [Etsy Developer Portal](https://www.etsy.com/developers/)
2. Create a new app or use your existing app
3. Note down:
   - **API Keystring** (public identifier)
   - **Shared Secret** (private secret key)

## Step 2: Configure Environment Variables

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your credentials:
   ```env
   # Gemini API (for image generation)
   GEMINI_API_KEY=your_gemini_key_here
   
   # Etsy API Credentials
   ETSY_API_KEY=<your_keystring>
   ETSY_SHARED_SECRET=<your_shared_secret>
   ```

⚠️ **IMPORTANT:** Never commit `.env` to git. It's already in `.gitignore`.

## Step 3: Test API Key Validity

Run the connectivity test:

```bash
python test_etsy_connectivity.py
```

Expected output:
```
✓ ETSY_API_KEY found (24 chars)
Testing API connectivity...
Response status: 200
✓ API key is valid!
```

## Step 4: Set Up OAuth 2.0

Etsy API uses OAuth 2.0 for authentication. You need an access token to make API calls.

### 4.1 Configure Callback URL

In your Etsy App settings, add this redirect URI:
```
http://localhost:8000/callback
```

### 4.2 Run OAuth Setup Script

```bash
python scripts/setup_etsy_oauth.py
```

This will:
1. Generate an OAuth authorization URL
2. Open your browser for authorization
3. Guide you through obtaining an access token
4. Save the token to `.env`

### 4.3 Required Environment Variables

After OAuth setup, your `.env` should contain:

```env
ETSY_API_KEY=<your_keystring>
ETSY_SHARED_SECRET=<your_shared_secret>
ETSY_SHOP_ID=<your_shop_id>
ETSY_ACCESS_TOKEN=<oauth_access_token>
ETSY_REFRESH_TOKEN=<oauth_refresh_token>
```

## Step 5: Verify Setup

Run the authentication test:

```bash
python test_etsy_auth.py
```

Expected output:
```
✓ Etsy credentials found in .env
  API Key: ABC123XYZ456DEF789... (24 chars)
  Shop ID: 12345678
  Access Token: ABC123XYZ456DEF789... (64 chars)
  Refresh Token: ABC123XYZ456DEF789... (64 chars)

Initializing Etsy API client...
✓ Successfully initialized Etsy API client
```

## Required API Scopes

Your Etsy app needs these OAuth scopes:

- `listings_r` - Read listings
- `listings_w` - Write/update listings
- `listings_d` - Delete listings (optional)
- `shops_r` - Read shop info
- `files_w` - Upload digital files

## Security Best Practices

1. ✅ `.env` is in `.gitignore` - never commit secrets
2. ✅ Use `.env.example` with placeholder values for documentation
3. ✅ Never log full API keys/tokens (use `key[:20]...` for debugging)
4. ✅ For CI/CD, use GitHub Secrets instead of `.env`
5. ✅ Rotate tokens regularly
6. ✅ Keep `Shared Secret` absolutely private

## Troubleshooting

### "ETSY_API_KEY not found"
- Make sure `.env` file exists in project root
- Check that `ETSY_API_KEY=<value>` has no spaces around `=`
- Run `python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('ETSY_API_KEY'))"` to verify

### "Authentication failed (401)"
- Your API key may be invalid
- Check that you copied the full keystring
- Verify your app is still active in Etsy Developer Portal

### "Access token expired"
- Access tokens expire after 1 hour
- Run `python scripts/setup_etsy_oauth.py` again
- Or implement automatic token refresh (using `ETSY_REFRESH_TOKEN`)

## Next Steps

Once setup is complete, you can:

1. Generate pack assets:
   ```bash
   stream-pack build my_pack --num-variants 3
   stream-pack postprocess my_pack
   ```

2. Upload to Etsy:
   ```bash
   stream-pack upload my_pack --dry-run  # Test without uploading
   stream-pack upload my_pack            # Actually upload
   ```

## References

- [Etsy Open API v3 Documentation](https://developers.etsy.com/documentation/)
- [OAuth 2.0 Flow Guide](https://developers.etsy.com/documentation/essentials/authentication/)
- Project GitHub: https://github.com/aomizuki0307/etsy-stream-pack-helper
