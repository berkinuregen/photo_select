import io
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from PIL import Image

temporary = tempfile.TemporaryDirectory()
os.environ["ADMIN_PASSWORD"] = "test-password-is-long"
os.environ["SECRET_KEY"] = "test-secret-key-is-at-least-thirty-two-characters"
os.environ["DATA_DIR"] = str(Path(temporary.name) / "data")
os.environ["UPLOAD_DIR"] = str(Path(temporary.name) / "uploads")
os.environ["COOKIE_SECURE"] = "false"

from fastapi.testclient import TestClient

from app.main import app
from app.database import connect
from app.images import cleanup_pending_previews
from app.images import make_preview

HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def image_bytes():
    buffer = io.BytesIO()
    with Image.new("RGB", (1600, 800), "red") as image:
        image.save(buffer, "JPEG")
    return buffer.getvalue()


class ProofingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()
        cls.assert_login = cls.client.post("/api/login", headers=HEADERS, json={"password": os.environ["ADMIN_PASSWORD"]})
        assert cls.assert_login.status_code == 200

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        temporary.cleanup()

    def create_gallery(self, limit=1):
        response = self.client.post("/api/admin/galleries", headers=HEADERS,
                                    json={"title": "Düğün", "description": "Merhaba", "selection_limit": limit})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def upload(self, gallery, filename="IMG_1024.JPG", content=None):
        response = self.client.post(f"/api/admin/galleries/{gallery['id']}/photos", headers=HEADERS,
                                    files={"file": (filename, image_bytes() if content is None else content, "image/jpeg")})
        return response

    def publish(self, gallery, published=True):
        return self.client.patch(f"/api/admin/galleries/{gallery['id']}", headers=HEADERS,
                                 json={"published": published})

    def test_gallery_lifecycle(self):
        gallery = self.create_gallery()
        token, gid = gallery["token"], gallery["id"]
        base = f"/api/galeri/{token}"
        self.assertEqual(self.client.get(base).status_code, 404)
        self.assertEqual(self.upload(gallery).status_code, 200)
        self.assertEqual(self.upload(gallery, "IMG_1055.JPG").status_code, 200)
        self.assertEqual(self.upload(gallery, "bad.jpg", b"not an image").status_code, 400)
        self.assertEqual(self.publish(gallery).status_code, 200)
        self.assertEqual(self.client.get(f"/galeri/{token}").status_code, 200)
        photos = self.client.get(base).json()["photos"]
        self.assertEqual(len(photos), 2)
        first, second = [p["id"] for p in photos]
        preview = self.client.get(f"{base}/photos/{first}/preview")
        self.assertEqual(preview.headers["content-type"], "image/webp")
        with Image.open(io.BytesIO(preview.content)) as image:
            self.assertEqual(image.size, (1200, 600))
        self.assertEqual(self.client.put(f"{base}/photos/{first}", json={"selected": True}).status_code, 403)
        self.assertEqual(self.client.put(f"{base}/photos/{first}", headers=HEADERS,
                                         json={"selected": True, "note": "Siyah-beyaz"}).status_code, 200)
        self.assertEqual(self.client.put(f"{base}/photos/{second}", headers=HEADERS,
                                         json={"selected": True}).status_code, 409)
        self.assertEqual(self.client.post(f"{base}/submit", headers=HEADERS).status_code, 200)
        self.assertEqual(self.client.put(f"{base}/photos/{first}", headers=HEADERS,
                                         json={"selected": False}).status_code, 409)
        self.assertEqual(self.client.delete(f"/api/admin/galleries/{gid}/photos/{first}", headers=HEADERS).status_code, 409)
        self.assertEqual(self.upload(gallery).status_code, 409)
        result = self.client.get(f"/api/admin/galleries/{gid}").json()
        self.assertEqual(result["photos"][0]["filename"], "IMG_1024.JPG")
        self.assertEqual(result["photos"][0]["note"], "Siyah-beyaz")
        self.assertTrue(result["gallery"]["submitted_at"])
        self.publish(gallery, False)
        self.assertEqual(self.client.get(base).status_code, 404)
        self.assertEqual(self.client.get(f"{base}/photos/{first}/preview").status_code, 404)

    def test_access_and_origin(self):
        gallery = self.create_gallery()
        with TestClient(app) as anonymous:
            self.assertEqual(anonymous.get("/api/admin/galleries").status_code, 401)
            self.assertEqual(anonymous.get(f"/api/admin/galleries/{gallery['id']}").status_code, 401)
            self.assertEqual(anonymous.post("/api/login", headers={**HEADERS, "Origin": "https://evil.example"},
                                            json={"password": os.environ["ADMIN_PASSWORD"]}).status_code, 403)
        self.assertEqual(self.client.get("/api/galeri/not-a-token").status_code, 404)

    def test_concurrent_selection_limit(self):
        gallery = self.create_gallery()
        self.upload(gallery, "one.jpg")
        self.upload(gallery, "two.jpg")
        self.publish(gallery)
        base = f"/api/galeri/{gallery['token']}"
        ids = [p["id"] for p in self.client.get(base).json()["photos"]]
        def select(photo_id):
            return self.client.put(f"{base}/photos/{photo_id}", headers=HEADERS, json={"selected": True}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(pool.map(select, ids))
        self.assertEqual(statuses, [200, 409])
        self.assertEqual(sum(p["selected"] for p in self.client.get(base).json()["photos"]), 1)

    def test_empty_submission_and_cross_gallery_photo(self):
        first, second = self.create_gallery(), self.create_gallery()
        self.upload(first)
        self.publish(first)
        self.publish(second)
        first_base = f"/api/galeri/{first['token']}"
        second_base = f"/api/galeri/{second['token']}"
        photo_id = self.client.get(first_base).json()["photos"][0]["id"]
        self.assertEqual(self.client.post(f"{second_base}/submit", headers=HEADERS).status_code, 400)
        self.assertEqual(self.client.get(f"{second_base}/photos/{photo_id}/preview").status_code, 404)
        self.assertEqual(self.client.put(f"{second_base}/photos/{photo_id}", headers=HEADERS,
                                         json={"selected": True}).status_code, 404)

    def test_delete_and_size_limit(self):
        gallery = self.create_gallery()
        self.assertEqual(self.upload(gallery, "large.jpg", b"x" * (30 * 1024 * 1024 + 1)).status_code, 413)
        self.assertEqual(self.upload(gallery, "picture.gif", image_bytes()).status_code, 400)
        self.assertEqual(self.upload(gallery).status_code, 200)
        gid = gallery["id"]
        photo = self.client.get(f"/api/admin/galleries/{gid}").json()["photos"][0]
        self.assertEqual(self.client.delete(f"/api/admin/galleries/{gid}/photos/{photo['id']}",
                                            headers=HEADERS).status_code, 200)
        self.assertEqual(self.client.get(f"/api/admin/galleries/{gid}/photos/{photo['id']}/preview").status_code, 404)
        self.assertEqual(self.client.get(f"/api/admin/galleries/{gid}").json()["photos"], [])

    def test_delete_submitted_gallery_and_previews(self):
        gallery = self.create_gallery()
        other = self.create_gallery()
        self.upload(gallery)
        self.upload(other, "other.jpg")
        self.publish(gallery)
        base = f"/api/galeri/{gallery['token']}"
        photo = self.client.get(base).json()["photos"][0]
        self.client.put(f"{base}/photos/{photo['id']}", headers=HEADERS,
                        json={"selected": True, "note": "Test"})
        self.client.post(f"{base}/submit", headers=HEADERS)
        with connect() as db:
            preview = db.execute("SELECT preview_name FROM photos WHERE id = ?", (photo["id"],)).fetchone()[0]
        preview_path = Path(os.environ["UPLOAD_DIR"]) / preview
        with TestClient(app) as anonymous:
            self.assertEqual(anonymous.delete(f"/api/admin/galleries/{gallery['id']}", headers=HEADERS).status_code, 401)
        self.assertEqual(self.client.delete(f"/api/admin/galleries/{gallery['id']}").status_code, 403)
        result = self.client.delete(f"/api/admin/galleries/{gallery['id']}", headers=HEADERS)
        self.assertEqual(result.json(), {"ok": True, "cleanup_pending": 0})
        self.assertFalse(preview_path.exists())
        self.assertEqual(self.client.get(base).status_code, 404)
        self.assertEqual(self.client.get(f"{base}/photos/{photo['id']}/preview").status_code, 404)
        self.assertEqual(self.client.get(f"/api/admin/galleries/{gallery['id']}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/admin/galleries/{gallery['id']}", headers=HEADERS).status_code, 404)
        self.assertEqual(len(self.client.get(f"/api/admin/galleries/{other['id']}").json()["photos"]), 1)

    def test_preview_cleanup_failure_is_reported_and_retried(self):
        gallery = self.create_gallery()
        self.upload(gallery)
        with patch("pathlib.Path.unlink", side_effect=PermissionError("test")):
            with self.assertLogs("app.images", level="ERROR"):
                result = self.client.delete(f"/api/admin/galleries/{gallery['id']}", headers=HEADERS)
        self.assertEqual(result.json()["cleanup_pending"], 1)
        with connect() as db:
            name = db.execute("SELECT preview_name FROM pending_preview_deletions").fetchone()[0]
        preview = Path(os.environ["UPLOAD_DIR"]) / name
        self.assertTrue(preview.exists())
        self.assertEqual(cleanup_pending_previews(), 0)
        self.assertFalse(preview.exists())

    def test_upload_does_not_enter_recreated_gallery(self):
        gallery = self.create_gallery()
        replacement = {}

        def delete_during_processing(file):
            preview = make_preview(file)
            self.client.delete(f"/api/admin/galleries/{gallery['id']}", headers=HEADERS)
            replacement.update(self.create_gallery())
            return preview

        with patch("app.main.make_preview", side_effect=delete_during_processing):
            response = self.upload(gallery)
        self.assertIn(response.status_code, (404, 409))
        self.assertEqual(self.client.get(f"/api/admin/galleries/{replacement['id']}").json()["photos"], [])


if __name__ == "__main__":
    unittest.main()
