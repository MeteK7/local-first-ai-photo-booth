import os
from base64 import b64decode
from datetime import UTC, datetime, timedelta
from io import BytesIO
from ipaddress import IPv4Interface
from pathlib import Path
from secrets import token_urlsafe
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
from app.ai_photos import AIJob
from app.creative_renderers import CATALOG, render
from app.security import hash_password, token_digest

pytestmark = pytest.mark.postgres
BASE = "http://127.0.0.1:8000"
HEADERS = {"X-Booth-Request": "1", "Origin": BASE}


@pytest.fixture
def settings(tmp_path):
    if os.environ.get("PHOTOBOOTH_RUN_DB_TESTS") != "1":
        pytest.skip("Set PHOTOBOOTH_RUN_DB_TESTS=1 to opt into PostgreSQL tests.")
    cfg = Settings(db_name="photobooth_test", data_root=tmp_path, frontend_dir=tmp_path / "web",
                   camera_enabled=False, download_bind=None, printer_name=None)
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

    def spool(job, image, layout="Photo"):
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


def seed_original(app, settings, session_id, jpeg, width=60, height=40):
    photo = uuid4()
    save_original(settings.data_root, photo, jpeg)
    with app.state.db.begin() as db:
        db.add(OriginalPhoto(id=photo, session_id=UUID(session_id), request_id=uuid4(),
                             captured_at=datetime.now(UTC), byte_size=len(jpeg), width=width, height=height))
    return photo


PHOTOS = "/api/sessions/current/photos"
STUDIO = f"{PHOTOS}/creative"
PHONE_LINKS = f"{PHOTOS}/phone-links"
PRINT_JOBS = f"{PHOTOS}/print-jobs"


def sample_jpeg():
    with BytesIO() as output, Image.new("RGB", (60, 40), (225, 80, 50)) as image:
        image.paste((51, 76, 124), (15, 8, 40, 31))
        image.save(output, format="JPEG")
        return output.getvalue()


def sculpture_jpeg(slot):
    background = 185 if slot == 1 else 196
    with BytesIO() as output, Image.new("RGB", (300, 200), (background,) * 3) as image:
        if slot > 1:
            center = (slot - 2) * 100 + 50
            image.paste((53, 91, 134), (center - 18, 55, center + 18, 150))
        image.save(output, format="JPEG")
        return output.getvalue()


@pytest.mark.parametrize(("experience", "options", "size", "print_layout", "pose_sequence"), [
    ("signature-strip", {"layout": "vertical", "count": 2}, (600, 1800), "Filmstrip", False),
    ("signature-strip", {"layout": "horizontal", "count": 4}, (1800, 600), "HorizontalStrip", False),
    ("signature-strip", {"layout": "grid", "count": 6}, (1800, 1200), "Photo", False),
    ("between-frames", {"count": 3, "guided": False}, (1800, 1200), "Photo", False),
    ("motion-study", {"count": 5}, (1800, 1200), "Photo", False),
    ("mini-scene", {"count": 4}, (1800, 1200), "Photo", False),
    pytest.param("time-sculpture", {"count": 4}, (1800, 1200), "Photo", True, id="sculpture-fallback"),
    pytest.param("time-sculpture", {"count": 4}, (1800, 1200), "Photo", False, id="sculpture-composite"),
])
def test_multi_photo_resumes_and_delivers_the_same_result(settings, monkeypatch, experience, options,
                                                         size, print_layout, pose_sequence):
    app = create_app(settings)
    interface = IPv4Interface("192.168.42.7/24")
    lan_base = f"http://{interface.ip}:8001"
    lan_app = create_delivery_app(settings.model_copy(update={"download_bind": interface}), app.state.db)
    submitted = []

    def print_image(job, image, profile):
        submitted.append((job.filmstrip_id, image.read_bytes(), profile))
        return printing.SpoolResult(printing.PrintState.SENT, "Sent to the printer.")

    monkeypatch.setattr(printing, "windows_job", print_image)
    monkeypatch.setattr(printing, "printer_configured", lambda config: bool(config.printer_name))
    with (
        TestClient(app, base_url=BASE) as owner,
        TestClient(app, base_url=BASE) as other,
        TestClient(lan_app, base_url=lan_base, client=("192.168.42.100", 50000)) as phone,
    ):
        selection = {"experience": experience, "version": 1, **options}
        count = selection["count"]
        body = {"experience": "filmstrip", "multi_photo_plan": selection}
        for changes in ({"count": 1}, {"count": 7}, {"layout": "album"}, {"version": 2}):
            revised = {**selection, **changes}
            assert owner.post("/api/sessions", json={**body, "multi_photo_plan": revised}, headers=HEADERS).status_code == 422
        assert owner.post("/api/sessions", json={**body, "experience": "single"}, headers=HEADERS).status_code == 422
        if experience == "time-sculpture":
            catalog_path = "/api/sessions/multi-photo-studio"
            assert "Time Sculpture" not in [mode["name"] for mode in owner.get(catalog_path).json()["creative"]]
            assert owner.post("/api/sessions", json=body, headers=HEADERS).status_code == 409
            settings.time_sculpture_enabled = True
            assert "Time Sculpture" in [mode["name"] for mode in owner.get(catalog_path).json()["creative"]]
        session = owner.post("/api/sessions", json=body, headers=HEADERS).raise_for_status().json()
        current = owner.get("/api/sessions/current").json()
        assert current["multi_photo_plan"] == selection
        if experience == "between-frames":
            assert current["studio_directions"]["prompts"] == []
        elif experience == "motion-study":
            prompts = current["studio_directions"]["prompts"]
            assert len(prompts) == count and prompts[-1] == "Hold your final pose."
        elif experience in {"mini-scene", "time-sculpture"}:
            assert current["studio_directions"]["manual_advance"] is True
        resumed = owner.post("/api/sessions", headers=HEADERS).raise_for_status().json()
        assert (resumed["id"], resumed["multi_photo_plan"]) == (session["id"], selection)
        other.post("/api/sessions", json=body, headers=HEADERS).raise_for_status()
        assert owner.post(PHOTOS, json={"request_id": str(uuid4()), "slot": 2}, headers=HEADERS).status_code == 409
        assert owner.post(PHOTOS, json={"request_id": str(uuid4()), "slot": 1}, headers=HEADERS).status_code == 503

        composite = experience == "time-sculpture" and not pose_sequence
        width, height = (300, 200) if composite else (60, 40)
        sources = [sculpture_jpeg(slot) for slot in range(1, count + 1)] if composite else [sample_jpeg()] * count
        ids, request_ids = [uuid4() for _ in range(count)], [uuid4() for _ in range(count)]
        for slot, (photo, request_id, jpeg) in enumerate(zip(ids, request_ids, sources, strict=True), 1):
            save_original(settings.data_root, photo, jpeg)
            with app.state.db.begin() as db:
                db.add(OriginalPhoto(id=photo, session_id=UUID(session["id"]), request_id=request_id, capture_slot=slot,
                                     captured_at=datetime.now(UTC), byte_size=len(jpeg), width=width, height=height))
            if slot == 1:
                progress = owner.get(f"{PHOTOS}/filmstrip").json()
                assert progress == {"captured": 1, "required": count, "result": None}
                token = owner.cookies.get("booth_customer")
                with TestClient(app, base_url=BASE) as reopened:
                    reopened.cookies.set("booth_customer", token, path="/api/sessions")
                    replay = reopened.post(PHOTOS, json={"request_id": str(uuid4()), "slot": 1}, headers=HEADERS)
                    assert replay.status_code == 200 and replay.json()["id"] == str(photo)
                conflict = owner.post(PHOTOS, json={"request_id": str(request_id), "slot": 2}, headers=HEADERS)
                assert conflict.status_code == 409

        assert owner.post(PHOTOS, json={"request_id": str(uuid4())}, headers=HEADERS).status_code == 409
        result = owner.post(f"{PHOTOS}/filmstrip", headers=HEADERS).raise_for_status().json()
        assert (result["width"], result["height"]) == size
        filename = experience
        if pose_sequence:
            assert "hard to distinguish" in result["fallback_reason"]
            filename = "time-sculpture-poses"
        else:
            assert "fallback_reason" not in result
        assert owner.post(f"{PHOTOS}/filmstrip", headers=HEADERS).json() == result
        result_path = f"{PHOTOS}/filmstrip/{result['id']}"
        preview = owner.get(f"{result_path}/preview").raise_for_status().content
        download = owner.get(f"{result_path}/download").raise_for_status()
        assert download.content == preview
        assert f'filename="{filename}.jpg"' in download.headers["content-disposition"]
        assert other.get(f"{result_path}/preview").status_code == 404

        app.state.download_base = lan_base
        settings.printer_name = "Isolated test queue"
        asset = {"asset_id": result["id"], "kind": "filmstrip"}
        assert other.post(PHONE_LINKS, json=asset, headers=HEADERS).status_code == 404
        assert other.post(PRINT_JOBS, json=asset, headers=HEADERS).status_code == 404
        grant = owner.post(PHONE_LINKS, json=asset, headers=HEADERS).raise_for_status().json()
        phone_download = phone.get(urlsplit(grant["url"]).path).raise_for_status()
        assert phone_download.content == preview
        assert phone_download.headers["content-disposition"] == download.headers["content-disposition"]
        owner.post(PRINT_JOBS, json=asset, headers=HEADERS).raise_for_status()
        printing.process_print_queue(settings, app.state.db)
        assert submitted == [(UUID(result["id"]), preview, print_layout)]
        assert all(asset_path(settings.data_root, "originals", photo).read_bytes() == jpeg
                   for photo, jpeg in zip(ids, sources, strict=True))


def wait_for_result(kiosk, asset, treatment, state):
    deadline = monotonic() + 15
    while monotonic() < deadline:
        options = kiosk.get(STUDIO, params={"asset_id": str(asset)}).raise_for_status().json()
        result = next(option["result"] for option in options if option["id"] == treatment)
        if result and result["state"] == state:
            return result
        if result and result["state"] in {"failed", "canceled"}:
            pytest.fail(result["detail"])
        sleep(.05)
    pytest.fail(f"Timed out waiting for {treatment} to be {state}.")


def test_creative_results_are_local_and_deliver_the_selected_jpeg(settings, monkeypatch):
    app = create_app(settings)
    interface = IPv4Interface("192.168.42.7/24")
    lan_base = f"http://{interface.ip}:8001"
    lan = create_delivery_app(settings.model_copy(update={"download_bind": interface}), app.state.db)
    spool_calls = []

    def spool(job, image, layout="Photo"):
        spool_calls.append((str(job.creative_id), image.read_bytes()))
        return printing.SpoolResult(printing.PrintState.SENT, "Sent to the printer.")

    monkeypatch.setattr(printing, "windows_job", spool)
    monkeypatch.setattr(printing, "printer_configured", lambda config: bool(config.printer_name))
    original = sample_jpeg()
    with (
        TestClient(app, base_url=BASE) as owner,
        TestClient(app, base_url=BASE) as other,
        TestClient(lan, base_url=lan_base, client=("192.168.42.100", 50000)) as phone,
        TestClient(lan, base_url=lan_base, client=("192.168.43.100", 50000)) as external,
    ):
        session = owner.post("/api/sessions", headers=HEADERS).raise_for_status().json()
        other.post("/api/sessions", headers=HEADERS).raise_for_status()
        source = seed_original(app, settings, session["id"], original)
        app.state.download_base = lan_base
        settings.printer_name = "Isolated test queue"
        options = owner.get(STUDIO, params={"asset_id": source}).raise_for_status().json()
        assert [option["id"] for option in options] == list(CATALOG)
        assert all(option["result"] is None for option in options)
        assert other.get(STUDIO, params={"asset_id": source}).status_code == 404
        assert owner.post(f"{PHOTOS}/ai", json={}, headers=HEADERS).status_code == 404

        ids = []
        outputs = []
        for treatment in CATALOG:
            args = {"asset_id": str(source), "treatment": treatment}
            assert other.post(STUDIO, json=args, headers=HEADERS).status_code == 404
            queued = owner.post(STUDIO, json=args, headers=HEADERS)
            assert queued.status_code == 202 and queued.json()["state"] == "queued"
            result = wait_for_result(owner, source, treatment, "completed")
            assert result["id"] == queued.json()["id"] and result["kind"] == "creative"
            duplicate = owner.post(STUDIO, json=args, headers=HEADERS)
            assert duplicate.status_code == 200 and duplicate.json() == result
            ids.append(result["id"])
            jpeg = owner.get(f"{STUDIO}/{result['id']}/preview").raise_for_status().content
            assert owner.get(f"{STUDIO}/{result['id']}/download").raise_for_status().content == jpeg
            assert other.get(f"{STUDIO}/{result['id']}/download").status_code == 404
            outputs.append(jpeg)
        assert len(set(ids)) == len(set(outputs)) == 4
        assert asset_path(settings.data_root, "originals", source).read_bytes() == original

        selected = {"asset_id": ids[1], "kind": "creative"}
        assert other.post(PHONE_LINKS, json=selected, headers=HEADERS).status_code == 404
        assert other.post(PRINT_JOBS, json=selected, headers=HEADERS).status_code == 404
        grant = owner.post(PHONE_LINKS, json=selected, headers=HEADERS).raise_for_status().json()
        path = urlsplit(grant["url"]).path
        assert phone.get(path).raise_for_status().content == outputs[1]
        assert external.get(path).status_code == 404
        assert phone.get(STUDIO, params={"asset_id": source}).status_code == 404
        submitted = owner.post(PRINT_JOBS, json=selected, headers=HEADERS).raise_for_status().json()
        printing.process_print_queue(settings, app.state.db)
        assert spool_calls == [(ids[1], outputs[1])]
        assert owner.get(PRINT_JOBS, params=selected).json()["id"] == submitted["id"]
        assert owner.get(PRINT_JOBS, params={"asset_id": ids[0], "kind": "creative"}).json() is None

        owner.post("/api/sessions/current/finish", json={"state": "completed"}, headers=HEADERS).raise_for_status()
        assert phone.get(path).content == outputs[1]
        with app.state.db.begin() as db:
            link = db.get(DownloadLink, token_digest(path.removeprefix("/d/")))
            assert link.creative_id == UUID(ids[1])
            link.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert phone.get(path).status_code == 404


def test_creative_failure_can_retry_and_filmstrip_cannot_request_treatments(settings):
    app = create_app(settings)
    with TestClient(app, base_url=BASE) as single, TestClient(app, base_url=BASE) as strip:
        session = single.post("/api/sessions", headers=HEADERS).raise_for_status().json()
        strip_session = strip.post("/api/sessions", json={"experience": "filmstrip"},
                                  headers=HEADERS).raise_for_status().json()
        original = b"Unreadable fixture"
        asset = seed_original(app, settings, session["id"], original)
        strip_asset = seed_original(app, settings, strip_session["id"], sample_jpeg())
        assert strip.post(STUDIO, json={"asset_id": str(strip_asset), "treatment": "classic-filter"},
                          headers=HEADERS).status_code == 404
        args = {"asset_id": str(asset), "treatment": "classic-filter"}
        queued = single.post(STUDIO, json=args, headers=HEADERS).raise_for_status().json()
        assert wait_for_result(single, asset, "classic-filter", "failed")["id"] == queued["id"]
        assert single.get(f"{PHOTOS}/{asset}/download").content == original
        assert single.get(f"{STUDIO}/{queued['id']}/preview").status_code == 404
        save_original(settings.data_root, asset, sample_jpeg())
        retry = single.post(STUDIO, json=args, headers=HEADERS)
        assert retry.status_code == 202 and retry.json()["id"] == queued["id"]
        assert wait_for_result(single, asset, "classic-filter", "completed")["id"] == queued["id"]


def test_studio_reuses_saved_classic_and_preserves_legacy_links_and_prints(settings):
    app = create_app(settings)
    interface = IPv4Interface("192.168.42.7/24")
    lan_base = f"http://{interface.ip}:8001"
    lan = create_delivery_app(settings.model_copy(update={"download_bind": interface}), app.state.db)
    extra = token_urlsafe(32)
    with TestClient(app, base_url=BASE) as owner, \
            TestClient(lan, base_url=lan_base, client=("192.168.42.100", 50000)) as phone:
        session = owner.post("/api/sessions", headers=HEADERS).raise_for_status().json()
        original = sample_jpeg()
        asset = seed_original(app, settings, session["id"], original)
        legacy = uuid4()
        saved = render("classic-filter", 1, original, asset)
        now = datetime.now(UTC)
        save_jpeg(settings.data_root, "ai-generated", legacy, saved)
        with app.state.db.begin() as db:
            db.add(AIJob(id=legacy, original_id=asset, template_id="cinematic-portrait", provider="local-preview",
                         prompt="Local preview", sends_photo=False, consented_at=now, state="completed",
                         detail="Ready", updated_at=now, width=60, height=40, byte_size=len(saved)))
            db.flush()
            db.add(DownloadLink(digest=token_digest(extra), effect_id=legacy, expires_at=now + timedelta(minutes=3)))
            db.add(printing.PrintJob(id=uuid4(), effect_id=legacy, printer="Epson", state="sent",
                                     detail="Printed", created_at=now, updated_at=now))
        options = owner.get(STUDIO, params={"asset_id": str(asset)}).raise_for_status().json()
        result = next(option["result"] for option in options if option["id"] == "classic-filter")
        assert result["id"] == str(legacy) and result["kind"] == "effect"
        response = owner.post(STUDIO, json={"asset_id": str(asset), "treatment": "classic-filter"}, headers=HEADERS)
        assert response.status_code == 200 and response.json() == result
        assert owner.get(f"{PHOTOS}/ai/{legacy}/download").raise_for_status().content == saved
        assert owner.get(PRINT_JOBS, params={"asset_id": str(legacy), "kind": "effect"}).json()["state"] == "sent"
        assert phone.get(f"/d/{extra}").raise_for_status().content == saved
        owner.post("/api/sessions/current/finish", json={"state": "canceled"}, headers=HEADERS).raise_for_status()
        assert phone.get(f"/d/{extra}").status_code == 404
