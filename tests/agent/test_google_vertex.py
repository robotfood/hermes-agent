from agent.google_vertex import init_google_vertex, resolve_google_vertex_config


PROJECT_ENV_VARS = ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "GCLOUD_PROJECT")
LOCATION_ENV_VARS = ("GOOGLE_VERTEX_LOCATION", "GOOGLE_CLOUD_LOCATION", "VERTEX_LOCATION")


def _clear_vertex_env(monkeypatch):
    for name in PROJECT_ENV_VARS + LOCATION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_uses_config_project_over_env(monkeypatch):
    _clear_vertex_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "env-project")

    resolved = resolve_google_vertex_config({
        "provider": {"google-vertex": {"options": {"project": "cfg-project"}}}
    })

    assert resolved == {"project": "cfg-project", "location": "us-central1"}


def test_project_env_fallback_order(monkeypatch):
    _clear_vertex_env(monkeypatch)
    monkeypatch.setenv("GCP_PROJECT", "gcp-project")
    monkeypatch.setenv("GCLOUD_PROJECT", "gcloud-project")

    assert resolve_google_vertex_config({})["project"] == "gcp-project"

    monkeypatch.delenv("GCP_PROJECT")
    assert resolve_google_vertex_config({})["project"] == "gcloud-project"


def test_google_cloud_project_wins_when_config_missing(monkeypatch):
    _clear_vertex_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "cloud-project")
    monkeypatch.setenv("GCP_PROJECT", "gcp-project")

    assert resolve_google_vertex_config({})["project"] == "cloud-project"


def test_location_precedence_and_default(monkeypatch):
    _clear_vertex_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project")
    monkeypatch.setenv("GOOGLE_VERTEX_LOCATION", "us-east1")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-west4")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")

    assert resolve_google_vertex_config({})["location"] == "us-east1"
    assert resolve_google_vertex_config({
        "provider": {"google-vertex": {"options": {"location": "us-central1"}}}
    })["location"] == "us-central1"

    monkeypatch.delenv("GOOGLE_VERTEX_LOCATION")
    assert resolve_google_vertex_config({})["location"] == "europe-west4"

    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION")
    assert resolve_google_vertex_config({})["location"] == "asia-northeast1"

    monkeypatch.delenv("VERTEX_LOCATION")
    assert resolve_google_vertex_config({})["location"] == "us-central1"


def test_returns_none_when_no_project(monkeypatch):
    _clear_vertex_env(monkeypatch)

    assert resolve_google_vertex_config({}) is None


def test_supports_providers_config_shape(monkeypatch):
    _clear_vertex_env(monkeypatch)

    resolved = resolve_google_vertex_config({
        "providers": {"google-vertex": {"options": {"project": "cfg-project", "location": "global"}}}
    })

    assert resolved == {"project": "cfg-project", "location": "global"}


def test_init_google_vertex_validates_sdk_and_returns_config(monkeypatch):
    _clear_vertex_env(monkeypatch)

    resolved = init_google_vertex({
        "provider": {"google-vertex": {"options": {"project": "cfg-project", "location": "global"}}}
    })

    assert resolved == {"project": "cfg-project", "location": "global"}


def test_vertex_tools_use_json_schema_parameters():
    from agent.gemini_vertex_adapter import _function_declarations_for_genai

    payload = {
        "functionDeclarations": [
            {
                "name": "terminal",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cmd": {"type": "string"},
                        "timeout": {"type": "integer"},
                        "items": {"type": "array", "items": {"type": "boolean"}},
                    },
                },
            }
        ]
    }

    converted = _function_declarations_for_genai(payload)

    decl = converted["functionDeclarations"][0]
    params = decl["parametersJsonSchema"]
    assert "parameters" not in decl
    assert params["type"] == "object"
    assert params["properties"]["cmd"]["type"] == "string"
    assert params["properties"]["timeout"]["type"] == "integer"
    assert params["properties"]["items"]["type"] == "array"
    assert params["properties"]["items"]["items"]["type"] == "boolean"
