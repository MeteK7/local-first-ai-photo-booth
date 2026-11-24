from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.creative import router
from app.creative_renderers import CATALOG

FRAMES = [key for key, item in CATALOG.items() if item.category != "treatment"]


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("frame", FRAMES)
def test_frame_samples_are_available_without_a_customer_photo_and_keep_the_print_ratio(client, frame):
    recipe = CATALOG[frame]
    response = client.get(f"{router.prefix}/frames/{frame}/preview?version={recipe.version}")
    assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
    with Image.open(BytesIO(response.content)) as preview:
        assert preview.mode == "RGB" and max(preview.size) == 360
        assert not preview.getexif()
        width, height = recipe.frame_size
        assert abs(preview.width / preview.height - width / height) < .005
        assert (preview.width < preview.height) == (height > width)


@pytest.mark.parametrize("path", [
    "unknown/preview", "classic-filter/preview", "hazar-station-portrait/preview?version=999",
])
def test_frame_samples_reject_unknown_frames_effects_and_old_versions(client, path):
    assert client.get(f"{router.prefix}/frames/{path}").status_code == 404
