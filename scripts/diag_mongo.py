"""Diagnose the Atlas TLS failure: print public egress IP + retry ping with certifi CA. No secrets printed."""
import os, certifi, urllib.request
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

try:
    ip = urllib.request.urlopen("https://api.ipify.org", timeout=6).read().decode()
    print("Public egress IP:", ip)
except Exception as e:
    print("IP lookup failed:", e)

from pymongo import MongoClient
uri = os.getenv("MONGODB_URI", "").strip()
try:
    c = MongoClient(uri, serverSelectionTimeoutMS=9000, tlsCAFile=certifi.where())
    c.admin.command("ping")
    print("ping(certifi): OK ->", c.list_database_names())
except Exception as e:
    print("ping(certifi): FAILED", type(e).__name__, "-", str(e)[:220])
