"""Verify credentials are present and that MongoDB connects. Never prints secret values."""
import os
from dotenv import load_dotenv

load_dotenv()

KEYS = ["GEMINI_API_KEY", "VOYAGE_API_KEY", "MONGODB_URI", "DIGITALOCEAN_TOKEN"]
print("=== Credentials (presence only) ===")
for k in KEYS:
    v = os.getenv(k, "").strip()
    print(f"  {k}: {'SET (' + str(len(v)) + ' chars)' if v else 'empty'}")

uri = os.getenv("MONGODB_URI", "").strip()
print("\n=== MongoDB connection ===")
if not uri:
    print("  MONGODB_URI empty — skipping")
else:
    try:
        from pymongo import MongoClient
        c = MongoClient(uri, serverSelectionTimeoutMS=8000)
        c.admin.command("ping")
        print("  ✅ ping OK")
        print("  databases:", c.list_database_names())
    except Exception as e:
        print("  ❌", type(e).__name__, "-", str(e)[:240])
