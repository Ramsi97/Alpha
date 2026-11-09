"""Unit tests for the insecure-default-secret startup guard (plan section
18: "Secrets in environment or a secret manager; rotate if exposed")."""

import pytest

from app.core.config import settings
from app.main import _check_secrets


def test_insecure_default_in_development_just_warns(monkeypatch, caplog):
    monkeypatch.setattr(settings, "environment", "development")
    _check_secrets()  # must not raise


def test_insecure_default_in_production_refuses_to_start(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(RuntimeError, match="insecure default"):
        _check_secrets()


def test_real_secret_in_production_is_fine(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "jwt_secret", "a-real-randomly-generated-production-secret")
    _check_secrets()  # must not raise
