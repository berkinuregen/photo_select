import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from .config import COOKIE_SECURE, ROOT, SECRET_KEY, UPLOAD_DIR
from .database import connect, init_db
from .images import make_preview
from .security import check_origin, login, require_admin


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Atölye Proofing", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=COOKIE_SECURE,
                   same_site="lax", max_age=8 * 60 * 60, session_cookie="proofing_admin")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


class LoginBody(BaseModel):
    password: str = Field(max_length=1024)


class GalleryBody(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    selection_limit: int = Field(ge=1, le=10000)


class PublishBody(BaseModel):
    published: bool


class SelectionBody(BaseModel):
    selected: bool
    note: str = Field(default="", max_length=500)


def get_gallery(db, token: str, public: bool = True):
    gallery = db.execute("SELECT * FROM galleries WHERE token = ?", (token,)).fetchone()
    if gallery is None or (public and not gallery["published"]):
        raise HTTPException(404, "Galeri bulunamadı.")
    return gallery


def get_admin_gallery(db, gallery_id: int):
    gallery = db.execute("SELECT * FROM galleries WHERE id = ?", (gallery_id,)).fetchone()
    if gallery is None:
        raise HTTPException(404, "Galeri bulunamadı.")
    return gallery


def photo_list(db, gallery_id: int):
    return [dict(row) for row in db.execute(
        "SELECT id, filename, selected, note FROM photos WHERE gallery_id = ? ORDER BY id", (gallery_id,)
    )]


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/admin")


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    template = "admin_dashboard.html" if request.session.get("admin") else "admin_login.html"
    return templates.TemplateResponse(request=request, name=template)


@app.post("/api/login", dependencies=[Depends(check_origin)])
def admin_login(request: Request, body: LoginBody):
    login(request, body.password)
    return {"ok": True}


@app.post("/api/logout", dependencies=[Depends(check_origin), Depends(require_admin)])
def admin_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/admin/galleries", dependencies=[Depends(require_admin)])
def list_galleries():
    with connect() as db:
        rows = db.execute("""
            SELECT g.*, COUNT(p.id) AS photo_count,
                   COALESCE(SUM(p.selected), 0) AS selected_count
            FROM galleries g LEFT JOIN photos p ON p.gallery_id = g.id
            GROUP BY g.id ORDER BY g.id DESC
        """).fetchall()
        return [dict(row) for row in rows]


@app.post("/api/admin/galleries", dependencies=[Depends(check_origin), Depends(require_admin)])
def create_gallery(body: GalleryBody):
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Galeri adı boş olamaz.")
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO galleries (token, title, description, selection_limit) VALUES (?, ?, ?, ?)",
            (secrets.token_urlsafe(32), title, body.description.strip(), body.selection_limit),
        )
        return dict(get_admin_gallery(db, cursor.lastrowid))


@app.get("/api/admin/galleries/{gallery_id}", dependencies=[Depends(require_admin)])
def gallery_details(gallery_id: int):
    with connect() as db:
        return {"gallery": dict(get_admin_gallery(db, gallery_id)), "photos": photo_list(db, gallery_id)}


@app.patch("/api/admin/galleries/{gallery_id}", dependencies=[Depends(check_origin), Depends(require_admin)])
def publish_gallery(gallery_id: int, body: PublishBody):
    with connect() as db:
        get_admin_gallery(db, gallery_id)
        db.execute("UPDATE galleries SET published = ? WHERE id = ?", (body.published, gallery_id))
    return {"ok": True}


@app.post("/api/admin/galleries/{gallery_id}/photos", dependencies=[Depends(check_origin), Depends(require_admin)])
def upload_photo(gallery_id: int, file: UploadFile = File(...)):
    with connect() as db:
        gallery = get_admin_gallery(db, gallery_id)
        if gallery["submitted_at"]:
            raise HTTPException(409, "Gönderilmiş galeriye fotoğraf eklenemez.")
    filename, preview_name = make_preview(file)
    try:
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            gallery = get_admin_gallery(db, gallery_id)
            if gallery["submitted_at"]:
                raise HTTPException(409, "Gönderilmiş galeriye fotoğraf eklenemez.")
            db.execute("INSERT INTO photos (gallery_id, filename, preview_name) VALUES (?, ?, ?)",
                       (gallery_id, filename, preview_name))
    except Exception:
        (UPLOAD_DIR / preview_name).unlink(missing_ok=True)
        raise
    return {"ok": True}


@app.delete("/api/admin/galleries/{gallery_id}/photos/{photo_id}",
            dependencies=[Depends(check_origin), Depends(require_admin)])
def delete_photo(gallery_id: int, photo_id: int):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        gallery = get_admin_gallery(db, gallery_id)
        if gallery["submitted_at"]:
            raise HTTPException(409, "Gönderilmiş galeriden fotoğraf silinemez.")
        photo = db.execute("SELECT preview_name FROM photos WHERE gallery_id = ? AND id = ?",
                           (gallery_id, photo_id)).fetchone()
        if photo is None:
            raise HTTPException(404, "Fotoğraf bulunamadı.")
        db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    (UPLOAD_DIR / photo["preview_name"]).unlink(missing_ok=True)
    return {"ok": True}


def preview_response(db, gallery_id: int, photo_id: int):
    photo = db.execute("SELECT preview_name FROM photos WHERE id = ? AND gallery_id = ?",
                       (photo_id, gallery_id)).fetchone()
    if photo is None:
        raise HTTPException(404, "Fotoğraf bulunamadı.")
    path = UPLOAD_DIR / photo["preview_name"]
    if not path.is_file():
        raise HTTPException(404, "Önizleme bulunamadı.")
    return FileResponse(path, media_type="image/webp")


@app.get("/api/admin/galleries/{gallery_id}/photos/{photo_id}/preview", dependencies=[Depends(require_admin)])
def admin_preview(gallery_id: int, photo_id: int):
    with connect() as db:
        get_admin_gallery(db, gallery_id)
        return preview_response(db, gallery_id, photo_id)


@app.get("/galeri/{token}", response_class=HTMLResponse)
def client_page(request: Request, token: str):
    with connect() as db:
        get_gallery(db, token)
    return templates.TemplateResponse(request=request, name="client_gallery.html", context={"token": token})


@app.get("/api/galeri/{token}")
def client_gallery(token: str):
    with connect() as db:
        gallery = get_gallery(db, token)
        return {"gallery": {key: gallery[key] for key in ("title", "description", "selection_limit", "submitted_at")},
                "photos": photo_list(db, gallery["id"])}


@app.get("/api/galeri/{token}/photos/{photo_id}/preview")
def client_preview(token: str, photo_id: int):
    with connect() as db:
        gallery = get_gallery(db, token)
        return preview_response(db, gallery["id"], photo_id)


@app.put("/api/galeri/{token}/photos/{photo_id}", dependencies=[Depends(check_origin)])
def update_selection(token: str, photo_id: int, body: SelectionBody):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        gallery = get_gallery(db, token)
        if gallery["submitted_at"]:
            raise HTTPException(409, "Seçim zaten iletildi.")
        photo = db.execute("SELECT selected FROM photos WHERE id = ? AND gallery_id = ?",
                           (photo_id, gallery["id"])).fetchone()
        if photo is None:
            raise HTTPException(404, "Fotoğraf bulunamadı.")
        count = db.execute("SELECT COUNT(*) FROM photos WHERE gallery_id = ? AND selected = 1",
                           (gallery["id"],)).fetchone()[0]
        if body.selected and not photo["selected"] and count >= gallery["selection_limit"]:
            raise HTTPException(409, "Seçim sınırına ulaşıldı.")
        db.execute("UPDATE photos SET selected = ?, note = ? WHERE id = ?",
                   (body.selected, body.note.strip(), photo_id))
    return {"ok": True}


@app.post("/api/galeri/{token}/submit", dependencies=[Depends(check_origin)])
def submit_gallery(token: str):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        gallery = get_gallery(db, token)
        if gallery["submitted_at"]:
            raise HTTPException(409, "Seçim zaten iletildi.")
        count = db.execute("SELECT COUNT(*) FROM photos WHERE gallery_id = ? AND selected = 1",
                           (gallery["id"],)).fetchone()[0]
        if count == 0:
            raise HTTPException(400, "En az bir fotoğraf seçin.")
        db.execute("UPDATE galleries SET submitted_at = CURRENT_TIMESTAMP WHERE id = ?", (gallery["id"],))
    return {"ok": True}
