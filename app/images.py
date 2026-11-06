import secrets
import threading
import warnings
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import UPLOAD_DIR

MAX_FILE_BYTES = 30 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000
_image_lock = threading.Lock()


def make_preview(upload: UploadFile) -> tuple[str, str]:
    filename = (upload.filename or "").replace("\\", "/").split("/")[-1]
    if not filename or len(filename) > 255 or any(ord(c) < 32 or ord(c) == 127 for c in filename):
        raise HTTPException(400, "Geçersiz dosya adı.")
    if Path(filename).suffix.lower() not in (".jpg", ".jpeg", ".png"):
        raise HTTPException(400, "Yalnızca JPG ve PNG dosyaları yüklenebilir.")
    upload.file.seek(0, 2)
    if upload.file.tell() > MAX_FILE_BYTES:
        raise HTTPException(413, "Her dosya en fazla 30 MB olabilir.")
    upload.file.seek(0)
    name = f"{secrets.token_hex(24)}.webp"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOAD_DIR / name
    try:
        with _image_lock, warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload.file) as image:
                if image.format not in ("JPEG", "PNG"):
                    raise HTTPException(400, "Dosya geçerli bir JPG veya PNG değil.")
                image.thumbnail((1200, 1200))
                with ImageOps.exif_transpose(image) as oriented:
                    if oriented.mode not in ("RGB", "RGBA"):
                        with oriented.convert("RGB") as converted:
                            converted.save(target, "WEBP", quality=78, method=4)
                    else:
                        oriented.save(target, "WEBP", quality=78, method=4)
        return filename, name
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "Görsel okunamadı veya güvenli boyut sınırını aşıyor.") from exc
    finally:
        upload.file.close()
