import hmac
import time
from collections import defaultdict, deque
from threading import Lock
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from .config import ADMIN_PASSWORD

_attempts = defaultdict(deque)
_lock = Lock()


def require_admin(request: Request):
    if not request.session.get("admin"):
        raise HTTPException(401, "Yönetici girişi gerekli.")


def check_origin(request: Request):
    # JSON/custom-header requests cannot be sent cross-origin by browser forms.
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(403, "Geçersiz istek.")
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in ("http", "https") or parsed.netloc != request.headers.get("host"):
            raise HTTPException(403, "İstek kaynağı doğrulanamadı.")


def login(request: Request, password: str):
    # Local, single-worker throttle. The reverse proxy should also rate-limit.
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _lock:
        for key in list(_attempts):
            while _attempts[key] and _attempts[key][0] <= now - 900:
                _attempts[key].popleft()
            if not _attempts[key]:
                del _attempts[key]
        attempts = _attempts[ip]
        if len(attempts) >= 5:
            raise HTTPException(429, "Çok fazla deneme. 15 dakika sonra tekrar deneyin.")
        if not hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
            attempts.append(now)
            raise HTTPException(401, "Parola hatalı.")
        _attempts.pop(ip, None)
    request.session.clear()
    request.session["admin"] = True
