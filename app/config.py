import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(ROOT / "uploads"))).resolve()

allow_insecure_pin = os.getenv("ALLOW_INSECURE_PIN", "false").lower() == "true"
is_pin = len(ADMIN_PASSWORD) == 6 and ADMIN_PASSWORD.isascii() and ADMIN_PASSWORD.isdigit()
if len(ADMIN_PASSWORD) < 12 and not (allow_insecure_pin and is_pin):
    raise RuntimeError("ADMIN_PASSWORD must contain at least 12 characters, or be a six-digit PIN with ALLOW_INSECURE_PIN=true.")
if len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY must contain at least 32 characters.")
