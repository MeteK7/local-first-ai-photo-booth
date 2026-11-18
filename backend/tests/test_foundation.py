import os
from base64 import b64decode
from datetime import UTC, datetime, timedelta
from io import BytesIO
from ipaddress import IPv4Interface
from pathlib import Path
from secrets import token_urlsafe
from threading import Event
from time import monotonic, sleep
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from app.admin import AdminUser
from app.config import Settings
from app.db import make_engine
from app.downloads import DownloadLink, create_delivery_app
from app.main import create_app
from app.media import asset_path, save_jpeg, save_original
from app.photos import Filmstrip, OriginalPhoto
from app import printing
from app.ai_photos import AIJob, JobState, run_job
from app.image_provider import LocalPreviewProvider
from app.security import hash_password, token_digest

pytestmark = pytest.mark.postgres
BASE = "http://127.0.0.1:8000"
HEADERS = {"X-Booth-Request": "1", "Origin": BASE}


@pytest.fixture
def settings(tmp_path):
    if os.environ.get("PHOTOBOOTH_RUN_DB_TESTS") != "1":
        pytest.skip("Set PHOTOBOOTH_RUN_DB_TESTS=1 to opt into PostgreSQL tests.")
    cfg = Settings(db_name="photobooth_test", data_root=tmp_path, frontend_dir=tmp_path / "web",
                   camera_enabled=False, download_bind=None, printer_name=None, ai_mode="disabled")
    if cfg.db_host not in {"127.0.0.1", "localhost"}:
        pytest.fail("Database integration tests require loopback PostgreSQL.")
    engine = make_engine(cfg)
    try:
        with engine.connect() as conn:
            if conn.scalar(text("SELECT current_database()")) != "photobooth_test":
                pytest.fail("Database integration tests require photobooth_test.")
    finally:
        engine.dispose()
    ini = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    ini.attributes["booth_settings"] = cfg
    command.upgrade(ini, "head")
    return cfg


def test_session_survives_app_restart_and_isolated_browser_cannot_access_it(settings):
    with TestClient(create_app(settings), base_url=BASE) as first:
        assert first.get("/api/health/ready").json()["status"] == "ready"
        assert first.get("/api/camera/status").json()["state"] == "unavailable"
        assert first.post("/api/sessions").status_code == 403
        assert first.post("/api/sessions", headers={**HEADERS, "Origin": "https://elsewhere.invalid"}).status_code == 403
        created = first.post("/api/sessions", headers=HEADERS)
        assert created.status_code == 201
        session_id = created.json()["id"]
        token = first.cookies.get("booth_customer")
        assert first.post("/api/sessions", headers=HEADERS).json()["id"] == session_id
    with TestClient(create_app(settings), base_url=BASE) as restarted:
        assert restarted.get("/api/sessions/current").json() is None
        restarted.cookies.set("booth_customer", token, path="/api/sessions")
        assert restarted.get("/api/sessions/current").json()["id"] == session_id
        assert restarted.post("/api/sessions/current/finish", json={"state": "active"}, headers=HEADERS).status_code == 422
        result = restarted.post("/api/sessions/current/finish", json={"state": "completed"}, headers=HEADERS)
        assert result.json()["state"] == "completed"
        assert restarted.get("/api/sessions/current").json() is None


def test_admin_requires_login_and_logout_revokes_cookie(settings):
    app = create_app(settings)
    username = f"test-{uuid4()}"
    password = token_urlsafe(24)
    with app.state.db.begin() as db:
        db.add(AdminUser(username=username, password_hash=hash_password(password)))
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/api/admin/overview").status_code == 401
        login = client.post("/api/admin/login", json={"username": username, "password": password}, headers=HEADERS)
        assert login.status_code == 200
        token = client.cookies.get("booth_admin")
        assert client.get("/api/admin/overview").json()["username"] == username
        assert client.post("/api/admin/logout", headers=HEADERS).status_code == 204
        client.cookies.set("booth_admin", token, path="/api/admin")
        assert client.get("/api/admin/overview").status_code == 401


def test_photo_files_are_scoped_to_the_active_session(settings):
    app = create_app(settings)
    photo_id, capture_request = uuid4(), uuid4()
    photo_path = f"/api/sessions/current/photos/{photo_id}"
    jpeg_fixture = b"\xff\xd8fixture\xff\xd9"
    with TestClient(app, base_url=BASE) as owner, TestClient(app, base_url=BASE) as other:
        session_id = UUID(owner.post("/api/sessions", headers=HEADERS).json()["id"])
        other.post("/api/sessions", headers=HEADERS).raise_for_status()
        with app.state.db.begin() as db:
            db.add(OriginalPhoto(id=photo_id, session_id=session_id, request_id=capture_request,
                                 captured_at=datetime.now(UTC), byte_size=len(jpeg_fixture), width=1, height=1))
            save_original(settings.data_root, photo_id, jpeg_fixture)
        assert owner.get("/api/sessions/current/photos/latest").json()["id"] == str(photo_id)
        repeated = owner.post("/api/sessions/current/photos", json={"request_id": str(capture_request)},
                              headers=HEADERS)
        assert repeated.status_code == 200
        assert repeated.json()["id"] == str(photo_id)
        for action in ("preview", "download"):
            own_file = owner.get(f"{photo_path}/{action}")
            assert own_file.status_code == 200
            assert own_file.content == jpeg_fixture
            assert own_file.headers["cache-control"] == "no-store"
            assert other.get(f"{photo_path}/{action}").status_code == 404
        assert "attachment" in owner.get(f"{photo_path}/download").headers["content-disposition"]
        assert owner.get("/api/sessions/current/photos/live-view").status_code == 503
        owner.post("/api/sessions/current/finish", json={"state": "completed"}, headers=HEADERS).raise_for_status()
        assert owner.get(f"{photo_path}/download").status_code == 404
        assert asset_path(settings.data_root, "originals", photo_id).read_bytes() == jpeg_fixture


def test_filmstrip_resumes_and_composes_three_originals(settings):
    app, colors = create_app(settings), ((240, 0, 0), (0, 180, 0), (0, 0, 230))
    photos_url = "/api/sessions/current/photos"
    filmstrip_url = f"{photos_url}/filmstrip"
    originals = {}
    with TestClient(app, base_url=BASE) as owner, TestClient(app, base_url=BASE) as other:
        session = owner.post("/api/sessions", json={"experience": "filmstrip"}, headers=HEADERS).json()
        assert session["experience"] == "filmstrip"
        assert owner.post("/api/sessions", headers=HEADERS).json()["experience"] == "filmstrip"
        assert other.post("/api/sessions", headers=HEADERS).json()["experience"] == "single"
        assert owner.get(filmstrip_url).json() == {"captured": 0, "required": 3, "result": None}
        assert owner.post(filmstrip_url, headers=HEADERS).status_code == 409

        now = datetime.now(UTC)
        for index, color in enumerate(colors):
            photo_id = uuid4()
            with BytesIO() as stream, Image.new("RGB", (90, 60), color) as image:
                image.save(stream, format="JPEG")
                originals[photo_id] = stream.getvalue()
            save_original(settings.data_root, photo_id, originals[photo_id])
            with app.state.db.begin() as db:
                db.add(OriginalPhoto(id=photo_id, session_id=UUID(session["id"]), request_id=uuid4(),
                                     captured_at=now + timedelta(seconds=index), byte_size=len(originals[photo_id]),
                                     width=90, height=60))
            assert owner.get(filmstrip_url).json()["captured"] == index + 1

        extra_capture = owner.post(photos_url, json={"request_id": str(uuid4())}, headers=HEADERS)
        assert extra_capture.status_code == 409
        composition = owner.post(filmstrip_url, headers=HEADERS).raise_for_status().json()
        assert (composition["width"], composition["height"]) == (600, 1800)
        assert owner.get(filmstrip_url).json()["result"] == composition
        assert owner.post(filmstrip_url, headers=HEADERS).json() == composition
        file_url = f"{filmstrip_url}/{composition['id']}"
        preview = owner.get(f"{file_url}/preview").raise_for_status()
        download = owner.get(f"{file_url}/download").raise_for_status()
        assert download.content == preview.content
        assert 'filename="classic-filmstrip.jpg"' in download.headers["content-disposition"]
        assert other.get(f"{file_url}/download").status_code == 404
        with Image.open(BytesIO(download.content)) as strip:
            assert strip.size == (600, 1800)
            assert strip.info["dpi"] == (300, 300)
            for point, color in zip(((300, 310), (300, 900), (300, 1490)), colors, strict=True):
                assert max(abs(a - b) for a, b in zip(strip.getpixel(point), color, strict=True)) <= 3
        for photo_id, original in originals.items():
            assert asset_path(settings.data_root, "originals", photo_id).read_bytes() == original
        owner.post("/api/sessions/current/finish", json={"state": "completed"}, headers=HEADERS).raise_for_status()
        assert owner.get(f"{file_url}/preview").status_code == 404


def test_phone_downloads_expire_and_only_serve_the_linked_result(settings):
    app = create_app(settings)
    interface = IPv4Interface("192.168.42.7/24")
    lan_base = f"http://{interface.ip}:8001"
    lan_app = create_delivery_app(settings.model_copy(update={"download_bind": interface}), app.state.db)
    local_links = "/api/sessions/current/photos/phone-links"
    now = datetime.now(UTC)
    with (
        TestClient(app, base_url=BASE) as original_owner,
        TestClient(app, base_url=BASE) as strip_owner,
        TestClient(lan_app, base_url=lan_base, client=("192.168.42.100", 50000)) as phone,
        TestClient(lan_app, base_url=lan_base, client=("192.168.43.100", 50000)) as external,
    ):
        original_session = original_owner.post("/api/sessions", headers=HEADERS).json()
        strip_session = strip_owner.post("/api/sessions", headers=HEADERS, json={"experience": "filmstrip"}).json()
        original_id, strip_id = uuid4(), uuid4()
        source, composition = b"original jpeg bytes", b"composed jpeg bytes"
        save_original(settings.data_root, original_id, source)
        save_jpeg(settings.data_root, "processed", strip_id, composition)
        with app.state.db.begin() as db:
            db.add_all([
                OriginalPhoto(id=original_id, session_id=UUID(original_session["id"]), request_id=uuid4(),
                              captured_at=now, byte_size=len(source), width=6, height=4),
                Filmstrip(id=strip_id, session_id=UUID(strip_session["id"]), created_at=now,
                          byte_size=len(composition), width=6, height=18),
            ])

        original_request = {"asset_id": str(original_id), "kind": "original"}
        strip_request = {"asset_id": str(strip_id), "kind": "filmstrip"}
        assert original_owner.post(local_links, json=original_request, headers=HEADERS).status_code == 503
        app.state.download_base = lan_base
        assert strip_owner.post(local_links, json=original_request, headers=HEADERS).status_code == 404
        assert original_owner.post(local_links, json=strip_request, headers=HEADERS).status_code == 404

        photo_link = original_owner.post(local_links, json=original_request, headers=HEADERS).raise_for_status().json()
        strip_link = strip_owner.post(local_links, json=strip_request, headers=HEADERS).raise_for_status().json()
        link_path = urlsplit(photo_link["url"]).path
        strip_path = urlsplit(strip_link["url"]).path
        assert photo_link["url"].startswith(f"{lan_base}/d/")
        assert link_path != strip_path
        image = photo_link["qr_image"]
        assert image.startswith("data:image/png;base64,")
        with Image.open(BytesIO(b64decode(image.split(",")[1]))) as png:
            assert png.format == "PNG" and png.width == png.height

        download = phone.get(link_path).raise_for_status()
        assert download.content == source
        assert download.headers["cache-control"] == "no-store"
        assert download.headers["referrer-policy"] == "no-referrer"
        assert 'filename="photo-booth.jpg"' in download.headers["content-disposition"]
        assert phone.head(link_path).status_code == 200
        assert phone.get(strip_path).content == composition
        assert external.get(link_path, headers={"X-Forwarded-For": "192.168.42.100"}).status_code == 404
        assert phone.get(link_path, headers={"Host": "elsewhere.invalid"}).status_code == 400
        for path in ("/", "/admin", "/api/admin/overview", local_links, "/openapi.json", "/d/" + "z" * 43):
            assert phone.get(path).status_code == 404
        assert phone.post(link_path).status_code == 405

        original_owner.post("/api/sessions/current/finish", json={"state": "completed"}, headers=HEADERS).raise_for_status()
        assert phone.get(link_path).content == source
        strip_owner.post("/api/sessions/current/finish", json={"state": "canceled"}, headers=HEADERS).raise_for_status()
        assert phone.get(strip_path).status_code == 404
        with app.state.db.begin() as db:
            token = link_path.removeprefix("/d/")
            assert db.get(DownloadLink, token) is None
            grant = db.get(DownloadLink, token_digest(token))
            assert grant.original_id == original_id and grant.filmstrip_id is None
            grant.expires_at = now - timedelta(seconds=1)
        assert phone.get(link_path).status_code == 404


def test_print_job_retries_safe_failure_and_deduplicates(settings, monkeypatch):
    app = create_app(settings)
    endpoint = "/api/sessions/current/photos/print-jobs"
    asset = uuid4()
    result = {"asset_id": str(asset), "kind": "original"}
    queued_calls = []
    outcomes = iter([
        printing.SpoolResult(printing.PrintState.FAILED, "The printer is offline."),
        printing.SpoolResult(printing.PrintState.SUBMITTED, "Queued in Windows."),
        printing.SpoolResult(printing.PrintState.SENT, "Sent to the printer."),
    ])

    def spool(job, image):
        queued_calls.append((job.id, image))
        return next(outcomes)

    monkeypatch.setattr(printing, "windows_job", spool)
    monkeypatch.setattr(printing, "printer_configured", lambda config: bool(config.printer_name))
    with TestClient(app, base_url=BASE) as owner, TestClient(app, base_url=BASE) as other:
        session = owner.post("/api/sessions", headers=HEADERS).raise_for_status().json()
        other.post("/api/sessions", headers=HEADERS).raise_for_status()
        jpeg = b"test original"
        save_original(settings.data_root, asset, jpeg)
        with app.state.db.begin() as db:
            db.add(OriginalPhoto(id=asset, session_id=UUID(session["id"]), request_id=uuid4(),
                                 captured_at=datetime.now(UTC), byte_size=len(jpeg), width=6, height=4))
        assert owner.get(endpoint, params=result).json() is None
        assert owner.post(endpoint, json=result, headers=HEADERS).status_code == 503
        settings.printer_name = "Isolated test queue"
        assert other.get(endpoint, params=result).status_code == 404
        assert other.post(endpoint, json=result, headers=HEADERS).status_code == 404
        started = owner.post(endpoint, json=result, headers=HEADERS)
        assert started.status_code == 202 and started.json()["state"] == "queued"
        job_id = started.json()["id"]
        duplicate = owner.post(endpoint, json=result, headers=HEADERS)
        assert duplicate.status_code == 200 and duplicate.json()["id"] == job_id
        printing.process_print_queue(settings, app.state.db)
        failed = owner.get(endpoint, params=result).json()
        assert failed["state"] == "failed" and "offline" in failed["detail"]

        retry = owner.post(endpoint, json=result, headers=HEADERS)
        assert retry.status_code == 202 and retry.json()["id"] == job_id
        printing.process_print_queue(settings, app.state.db)
        assert owner.get(endpoint, params=result).json()["state"] == "submitted"
        printing.process_print_queue(settings, app.state.db)
        assert owner.post(endpoint, json=result, headers=HEADERS).json()["state"] == "sent"
        path = asset_path(settings.data_root, "originals", asset)
        assert queued_calls == [(UUID(job_id), path), (UUID(job_id), path), (UUID(job_id), None)]

        with app.state.db.begin() as db:
            job = db.get(printing.PrintJob, UUID(job_id))
            job.state = printing.PrintState.SUBMITTING
            job.updated_at = datetime.now(UTC) - timedelta(minutes=2)
        printing.process_print_queue(settings, app.state.db)
        assert owner.post(endpoint, json=result, headers=HEADERS).json()["state"] == "unknown"
        assert len(queued_calls) == 3


def seed_effect_original(app, settings, session_id, jpeg, width=60, height=40):
    photo = uuid4()
    save_original(settings.data_root, photo, jpeg)
    with app.state.db.begin() as db:
        db.add(OriginalPhoto(id=photo, session_id=UUID(session_id), request_id=uuid4(),
                             captured_at=datetime.now(UTC), byte_size=len(jpeg), width=width, height=height))
    return photo


def test_effect_phone_link_only_serves_its_completed_result_until_expiry_or_cancel(settings):
    app = create_app(settings)
    provider = LocalPreviewProvider()
    interface = IPv4Interface("192.168.42.7/24")
    lan_base = f"http://{interface.ip}:8001"
    lan = create_delivery_app(settings.model_copy(update={"download_bind": interface}), app.state.db)
    effects = "/api/sessions/current/photos/ai"
    links = "/api/sessions/current/photos/phone-links"
    with BytesIO() as output, Image.new("RGB", (60, 40), (225, 80, 50)) as image:
        image.save(output, format="JPEG")
        original = output.getvalue()

    def queue_effect(kiosk):
        session = kiosk.post("/api/sessions", headers=HEADERS).raise_for_status().json()
        photo = seed_effect_original(app, settings, session["id"], original)
        job = kiosk.post(effects, headers=HEADERS, json={
            "asset_id": str(photo), "template_id": "cinematic-portrait", "consent": True,
        }).raise_for_status().json()
        return photo, {"asset_id": job["id"], "kind": "effect"}

    with (
        TestClient(app, base_url=BASE) as owner,
        TestClient(app, base_url=BASE) as other,
        TestClient(lan, base_url=lan_base, client=("192.168.42.100", 50000)) as phone,
        TestClient(lan, base_url=lan_base, client=("192.168.43.100", 50000)) as external,
    ):
        app.state.image_provider = provider
        app.state.download_base = lan_base
        photo, effect = queue_effect(owner)
        assert owner.post(links, json=effect, headers=HEADERS).status_code == 404
        run_job(settings, app.state.db, provider)
        _, other_effect = queue_effect(other)
        run_job(settings, app.state.db, provider)
        assert other.post(links, json=effect, headers=HEADERS).status_code == 404
        assert owner.post(links, json=other_effect, headers=HEADERS).status_code == 404

        processed = owner.get(f"{effects}/{effect['asset_id']}/download").raise_for_status().content
        grant = owner.post(links, json=effect, headers=HEADERS).raise_for_status().json()
        original_grant = owner.post(links, json={"asset_id": str(photo), "kind": "original"},
                                    headers=HEADERS).raise_for_status().json()
        path = urlsplit(grant["url"]).path
        assert path != urlsplit(original_grant["url"]).path
        response = phone.get(path).raise_for_status()
        assert response.content == processed and response.content != original
        assert 'filename="photo-booth-effect.jpg"' in response.headers["content-disposition"]
        assert phone.get(urlsplit(original_grant["url"]).path).content == original
        assert external.get(path).status_code == 404
        assert phone.get(f"{effects}/{effect['asset_id']}/download").status_code == 404

        owner.post("/api/sessions/current/finish", json={"state": "completed"}, headers=HEADERS).raise_for_status()
        assert phone.get(path).content == processed
        with app.state.db.begin() as db:
            stored = db.get(DownloadLink, token_digest(path.removeprefix("/d/")))
            assert stored.effect_id == UUID(effect["asset_id"])
            stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert phone.get(path).status_code == 404
        other_link = other.post(links, json=other_effect, headers=HEADERS).raise_for_status().json()
        other_path = urlsplit(other_link["url"]).path
        assert phone.get(other_path).status_code == 200
        other.post("/api/sessions/current/finish", json={"state": "canceled"}, headers=HEADERS).raise_for_status()
        assert phone.get(other_path).status_code == 404


def test_print_effect_uses_completed_jpeg_and_a_separate_job_from_original(settings, monkeypatch):
    app = create_app(settings)
    provider = LocalPreviewProvider()
    endpoint = "/api/sessions/current/photos/print-jobs"
    queued_calls = []

    def spool(job, image):
        queued_calls.append((str(job.id), image, image.read_bytes()))
        return printing.SpoolResult(printing.PrintState.SENT, "Sent to the printer.")

    monkeypatch.setattr(printing, "windows_job", spool)
    with BytesIO() as output, Image.new("RGB", (60, 40), (225, 80, 50)) as image:
        image.save(output, format="JPEG")
        original = output.getvalue()
    with TestClient(app, base_url=BASE) as owner, TestClient(app, base_url=BASE) as other:
        session = owner.post("/api/sessions", headers=HEADERS).raise_for_status().json()
        other.post("/api/sessions", headers=HEADERS).raise_for_status()
        photo = seed_effect_original(app, settings, session["id"], original)
        app.state.image_provider = provider
        settings.printer_name = "Isolated test queue"
        monkeypatch.setattr(printing, "printer_configured", lambda config: bool(config.printer_name))
        effects = "/api/sessions/current/photos/ai"
        requested = owner.post(effects, headers=HEADERS, json={
            "asset_id": str(photo), "template_id": "cinematic-portrait", "consent": True,
        }).raise_for_status().json()
        effect_id = requested["id"]
        effect_asset = {"asset_id": effect_id, "kind": "effect"}
        original_asset = {"asset_id": str(photo), "kind": "original"}
        assert owner.get(endpoint, params=effect_asset).status_code == 404
        assert owner.post(endpoint, json=effect_asset, headers=HEADERS).status_code == 404

        run_job(settings, app.state.db, provider)
        effect = owner.get(f"{effects}/{effect_id}/download").raise_for_status().content
        assert effect != original
        assert other.get(endpoint, params=effect_asset).status_code == 404
        assert other.post(endpoint, json=effect_asset, headers=HEADERS).status_code == 404
        assert owner.get(endpoint, params=effect_asset).json() is None
        queued_effect = owner.post(endpoint, json=effect_asset, headers=HEADERS)
        assert queued_effect.status_code == 202
        effect_print_id = queued_effect.json()["id"]
        duplicate = owner.post(endpoint, json=effect_asset, headers=HEADERS)
        assert duplicate.status_code == 200 and duplicate.json()["id"] == effect_print_id
        printing.process_print_queue(settings, app.state.db)
        assert queued_calls == [(effect_print_id, asset_path(settings.data_root, "ai-generated", UUID(effect_id)), effect)]
        assert owner.get(endpoint, params=effect_asset).json()["state"] == "sent"
        assert owner.get(endpoint, params=original_asset).json() is None

        queued_original = owner.post(endpoint, json=original_asset, headers=HEADERS)
        assert queued_original.status_code == 202 and queued_original.json()["id"] != effect_print_id
        printing.process_print_queue(settings, app.state.db)
        assert queued_calls[1] == (queued_original.json()["id"], asset_path(settings.data_root, "originals", photo), original)


def test_photo_effect_async_consent_and_result_isolation(settings):
    started, release = Event(), Event()
    uploads = []

    class ConsentProbe(LocalPreviewProvider):
        key = "consent-probe"
        label = "Consent test"
        sends_photo = True
        privacy_url = None

        def transform(self, jpeg, prompt):
            uploads.append((jpeg, prompt))
            started.set()
            if not release.wait(5):
                raise TimeoutError
            return super().transform(jpeg, prompt)

    app = create_app(settings, image_provider=ConsentProbe())
    endpoint = "/api/sessions/current/photos/ai"
    with BytesIO() as output, Image.new("RGB", (60, 40), (225, 80, 50)) as image:
        exif = image.getexif()
        exif[274] = 6
        exif[270] = "private descriptor"
        image.save(output, format="JPEG", exif=exif)
        original = output.getvalue()
    with TestClient(app, base_url=BASE) as owner, TestClient(app, base_url=BASE) as other:
        session = owner.post("/api/sessions", headers=HEADERS).raise_for_status().json()
        other.post("/api/sessions", headers=HEADERS).raise_for_status()
        photo = seed_effect_original(app, settings, session["id"], original)
        params = {"asset_id": str(photo)}
        args = {**params, "template_id": "cinematic-portrait"}
        assert owner.get(endpoint, params=params).json()["provider"]["sends_photo"] is True
        assert owner.post(endpoint, json={**args, "consent": False}, headers=HEADERS).status_code == 422
        assert owner.post(endpoint, json={**args, "consent": 1}, headers=HEADERS).status_code == 422
        assert other.post(endpoint, json={**args, "consent": True}, headers=HEADERS).status_code == 404
        assert not uploads
        queued = owner.post(endpoint, json={**args, "consent": True}, headers=HEADERS)
        assert queued.status_code == 202
        job = queued.json()
        try:
            assert started.wait(4)
            assert owner.get(endpoint, params=params).json()["templates"][0]["job"]["state"] == "processing"
            assert owner.get(f"{endpoint}/{job['id']}/preview").status_code == 404
        finally:
            release.set()
        deadline = monotonic() + 5
        while monotonic() < deadline:
            result = owner.get(endpoint, params=params).json()["templates"][0]["job"]
            if result["state"] == "completed":
                break
            sleep(.05)
        assert result["state"] == "completed"
        assert owner.post(endpoint, json={**args, "consent": True}, headers=HEADERS).json()["id"] == job["id"]
        assert len(uploads) == 1
        with Image.open(BytesIO(uploads[0][0])) as cleaned:
            assert cleaned.size == (40, 60)
            assert len(cleaned.getexif()) == 0
        assert "cool shadows" in uploads[0][1]
        preview = owner.get(f"{endpoint}/{job['id']}/preview").raise_for_status()
        download = owner.get(f"{endpoint}/{job['id']}/download").raise_for_status()
        assert preview.content == download.content
        assert other.get(f"{endpoint}/{job['id']}/download").status_code == 404
        assert asset_path(settings.data_root, "originals", photo).read_bytes() == original
        with app.state.db() as db:
            stored = db.get(AIJob, UUID(job["id"]))
            assert stored.sends_photo and stored.consented_at and stored.original_id == photo


def test_disabled_effects_and_local_failure_preserve_the_original(settings):
    app = create_app(settings)
    endpoint = "/api/sessions/current/photos/ai"
    original = b"unreadable test input"
    with TestClient(app, base_url=BASE) as owner:
        session = owner.post("/api/sessions", headers=HEADERS).raise_for_status().json()
        photo = seed_effect_original(app, settings, session["id"], original)
        params = {"asset_id": str(photo)}
        args = {**params, "template_id": "cinematic-portrait", "consent": True}
        assert owner.get(endpoint, params=params).json() == {"provider": None, "templates": []}
        assert owner.post(endpoint, json=args, headers=HEADERS).status_code == 503
        provider = LocalPreviewProvider()
        app.state.image_provider = provider
        response = owner.post(endpoint, json=args, headers=HEADERS).raise_for_status().json()
        run_job(settings, app.state.db, provider)
        job = owner.get(endpoint, params=params).json()["templates"][0]["job"]
        assert job["state"] == "failed"
        assert owner.get(f"/api/sessions/current/photos/{photo}/download").content == original
        retry = owner.post(endpoint, json=args, headers=HEADERS).raise_for_status().json()
        assert retry["id"] == response["id"] and retry["state"] == "queued"
        owner.post("/api/sessions/current/finish", json={"state": "canceled"}, headers=HEADERS).raise_for_status()
        run_job(settings, app.state.db, provider)
        with app.state.db() as db:
            assert db.get(AIJob, UUID(response["id"])).state == JobState.CANCELED
