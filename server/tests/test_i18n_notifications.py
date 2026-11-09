"""Unit tests for multi-language notification rendering (plan section 21/B5:
Afaan Oromo, Amharic, English)."""

from app.services.notifications import render_template


def test_renders_in_each_supported_language():
    assert render_template("level_up", {"level": 5}, "en") == "You reached level 5!"
    assert "5" in render_template("level_up", {"level": 5}, "am")
    assert "5" in render_template("level_up", {"level": 5}, "om")


def test_unsupported_language_falls_back_to_english():
    assert render_template("level_up", {"level": 5}, "fr") == "You reached level 5!"


def test_unknown_notification_type_falls_back_to_its_own_name():
    assert render_template("totally_unknown_type", {}, "en") == "totally_unknown_type"


def test_missing_payload_key_falls_back_to_the_unformatted_template():
    # Shouldn't crash even if a caller forgets a placeholder's value.
    assert "{level}" in render_template("level_up", {}, "en")
