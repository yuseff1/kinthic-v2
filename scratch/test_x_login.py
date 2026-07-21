"""
scratch/test_x_login.py — Diagnostic script to verify X (Twitter) login.

Run this script on your VM to verify that Kinthic can connect to X and
save cookies before you go on your trip.
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from silex_core.tools.social_x import PostXStatusTool

async def main():
    # Load environment variables
    load_dotenv()
    
    print("====================================================")
    print("          Kinthic X/Twitter Login Test")
    print("====================================================")
    
    tool = PostXStatusTool()
    
    # 1. API Verification
    api_key = os.getenv("X_API_KEY")
    print(f"\n[1] Checking API v2 configuration...")
    if api_key:
        print(" -> API keys found in environment. Testing post via API...")
        res = await tool._execute_api("Testing Kinthic v2 API connection! #dev")
        print(f" -> Result: {res}")
    else:
        print(" -> No API keys configured in environment.")

    # 2. Browser Verification
    username = os.getenv("X_USERNAME")
    print(f"\n[2] Checking Browser configuration...")
    if username:
        print(f" -> Username '{username}' found in environment. Testing browser login...")
        res = await tool._execute_browser("Testing Kinthic v2 browser automation! #dev")
        print(f" -> Result: {res}")
        
        # Verify if cookies were successfully saved
        cookies_path = Path.home() / ".kinthic" / "x_cookies.json"
        if cookies_path.exists():
            print(f" -> SUCCESS: Login cookies saved to {cookies_path}")
        else:
            print(" -> WARNING: Cookies were not saved. Verify credentials or email prompts.")
    else:
        print(" -> No Browser credentials (X_USERNAME / X_PASSWORD) configured.")

    print("\n====================================================")

if __name__ == "__main__":
    asyncio.run(main())
