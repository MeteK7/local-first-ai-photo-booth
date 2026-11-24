from io import BytesIO

import pytest
from PIL import Image

from app.i18n import CATALOGS, PLACEHOLDER, artwork_font, camera_messages, phone_locale, translate
from app.motion_study import motion_preview
from app.multi_photo import MotionStudyLayout, TimeSculpturePlan, capture_directions


def test_catalogs_have_matching_keys_and_placeholders():
    english = CATALOGS["en"]
    turkish = CATALOGS["tr"]
    assert english.keys() == turkish.keys()
    for key, text in english.items():
        assert text and turkish[key]
        assert sorted(PLACEHOLDER.findall(text)) == sorted(PLACEHOLDER.findall(turkish[key])), key


@pytest.mark.parametrize(("requested", "expected"), [
    ("tr-TR,tr;q=0.9,en;q=0.5", "tr"),
    ("tr;q=0.5,en-US;q=0.8", "en"),
    ("de-DE,tr;q=0.8", "tr"),
    ("en;q=0,*;q=0.9", "tr"),
    ("*;q=0.9,tr;q=0", "en"),
    ("tr;q=bad,en;q=0.8", "en"),
    ("", "en"),
])
def test_phone_negotiates_supported_languages(requested, expected):
    assert phone_locale(requested) == expected


def test_cues_and_combined_camera_setup_notices_have_stable_keys():
    directions = capture_directions(TimeSculpturePlan(experience="time-sculpture"))
    assert directions.prompts == tuple(translate(key) for key in directions.prompt_keys)
    assert translate(directions.prompt_keys[0], "tr") == "Boş sahne · Kadrajdan çıkın."
    notices = camera_messages("Charge the camera battery. Extend the camera lens.")
    assert [notice.key for notice in notices] == ["messages.camera.battery", "messages.camera.lens"]


def test_turkish_artwork_font_and_motion_preview():
    font = artwork_font("tr", 54)
    missing = bytes(font.getmask("\U0010ffff"))
    assert all(bytes(font.getmask(letter)) != missing for letter in "İıŞşĞğÇçÖöÜü")
    english = motion_preview(MotionStudyLayout.MATCH_CUT, 4, "en")
    turkish = motion_preview(MotionStudyLayout.MATCH_CUT, 4, "tr")
    assert english != turkish
    with Image.open(BytesIO(english)) as first, Image.open(BytesIO(turkish)) as second:
        assert first.size == second.size == (720, 480)
    assert motion_preview(MotionStudyLayout.MATCH_CUT, 4, "en") == english
