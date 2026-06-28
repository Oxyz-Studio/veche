"""Smoke-test Gemini + Voyage keys. Prints model availability, never the keys."""
import os
from dotenv import load_dotenv
load_dotenv()

# --- Gemini ---
print("=== Gemini ===")
try:
    from google import genai
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    names = [m.name for m in client.models.list()]
    print(f"  ✅ key OK — {len(names)} models")
    for kw in ("flash", "gemma", "computer", "3.5", "3-5"):
        hits = [n for n in names if kw in n.lower()]
        if hits:
            print(f"   ~{kw}: {hits[:6]}")
except Exception as e:
    print("  ❌", type(e).__name__, "-", str(e)[:240])

# --- Voyage ---
print("=== Voyage ===")
try:
    import voyageai
    vo = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
    for model in ("voyage-3.5", "voyage-3", "voyage-3-large"):
        try:
            r = vo.embed(["hello world"], model=model)
            print(f"  ✅ key OK — text model '{model}' dim={len(r.embeddings[0])}")
            break
        except Exception as e:
            print(f"   text model '{model}' -> {type(e).__name__}: {str(e)[:120]}")
except Exception as e:
    print("  ❌", type(e).__name__, "-", str(e)[:240])
