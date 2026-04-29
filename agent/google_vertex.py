"""Google Vertex AI provider configuration and ADC initialization."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def _google_vertex_options(config: Dict[str, Any]) -> Dict[str, Any]:
    provider_cfg = config.get("provider")
    if isinstance(provider_cfg, dict):
        vertex_cfg = provider_cfg.get("google-vertex")
        if isinstance(vertex_cfg, dict):
            options = vertex_cfg.get("options")
            if isinstance(options, dict):
                return options

    providers_cfg = config.get("providers")
    if isinstance(providers_cfg, dict):
        vertex_cfg = providers_cfg.get("google-vertex")
        if isinstance(vertex_cfg, dict):
            options = vertex_cfg.get("options")
            if isinstance(options, dict):
                return options

    return {}


def resolve_google_vertex_config(config: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Resolve Vertex project/location from config and environment.

    Returns ``None`` when no project is configured, which means the provider is
    disabled for auto-detection.
    """

    options = _google_vertex_options(config or {})

    project = (
        str(options.get("project") or "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        or os.getenv("GCP_PROJECT", "").strip()
        or os.getenv("GCLOUD_PROJECT", "").strip()
    )

    if not project:
        return None

    location = (
        str(options.get("location") or "").strip()
        or os.getenv("GOOGLE_VERTEX_LOCATION", "").strip()
        or os.getenv("GOOGLE_CLOUD_LOCATION", "").strip()
        or os.getenv("VERTEX_LOCATION", "").strip()
        or "us-central1"
    )

    return {
        "project": project,
        "location": location,
    }


def init_google_vertex(config: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Initialize the native Vertex AI SDK using ADC, if configured."""

    vertex_config = resolve_google_vertex_config(config)
    if not vertex_config:
        return None

    try:
        from google import genai  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Google Vertex AI support requires google-genai. "
            "Install it with `pip install google-genai`."
        ) from exc
    return vertex_config
