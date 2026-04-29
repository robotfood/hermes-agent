import pytest

from hermes_cli.auth import PROVIDER_REGISTRY, get_auth_status, resolve_provider
from hermes_cli.runtime_provider import resolve_runtime_provider


def test_google_vertex_registered():
    pconfig = PROVIDER_REGISTRY["google-vertex"]

    assert pconfig.name == "Google Vertex AI"
    assert pconfig.auth_type == "adc"
    assert pconfig.inference_base_url == "vertexai://google"


def test_google_vertex_aliases_resolve():
    assert resolve_provider("google-vertex") == "google-vertex"
    assert resolve_provider("vertex") == "google-vertex"
    assert resolve_provider("vertex-ai") == "google-vertex"


def test_runtime_uses_google_vertex_config(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.runtime_provider.load_config",
        lambda: {
            "provider": {
                "google-vertex": {
                    "options": {"project": "cfg-project", "location": "global"}
                }
            },
            "model": {"provider": "google-vertex", "default": "gemini-2.5-flash"},
        },
    )

    runtime = resolve_runtime_provider(requested="google-vertex")

    assert runtime["provider"] == "google-vertex"
    assert runtime["api_mode"] == "chat_completions"
    assert runtime["base_url"] == "vertexai://google"
    assert runtime["api_key"] == "google-adc"
    assert runtime["source"] == "google-adc"
    assert runtime["project"] == "cfg-project"
    assert runtime["location"] == "global"


def test_runtime_errors_when_explicit_google_vertex_has_no_project(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.runtime_provider.load_config",
        lambda: {"model": {"provider": "google-vertex", "default": "gemini-2.5-flash"}},
    )
    for name in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "GCLOUD_PROJECT"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(Exception, match="requires a project"):
        resolve_runtime_provider(requested="google-vertex")


def test_runtime_errors_when_explicit_vertex_alias_has_no_project(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.runtime_provider.load_config",
        lambda: {"model": {"provider": "vertex", "default": "gemini-2.5-flash"}},
    )
    for name in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "GCLOUD_PROJECT"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(Exception, match="requires a project"):
        resolve_runtime_provider(requested="vertex")


def test_auth_status_uses_vertex_config(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {
            "provider": {
                "google-vertex": {
                    "options": {"project": "cfg-project", "location": "global"}
                }
            }
        },
    )

    status = get_auth_status("google-vertex")

    assert status["logged_in"] is True
    assert status["auth_mode"] == "google-adc"
    assert status["project"] == "cfg-project"
    assert status["location"] == "global"
