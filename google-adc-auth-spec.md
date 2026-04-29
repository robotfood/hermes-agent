# Google Vertex AI Auth Port Spec

Implement Google Vertex AI support using Google Cloud Application Default Credentials (ADC), matching opencode's behavior for native Vertex/Gemini usage.

## Goal

Add a Google Vertex AI provider that authenticates through ADC, so local users can run:

```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=your-project-id
export VERTEX_LOCATION=us-central1
```

and the app can call Vertex Gemini models without manually managing API keys.

## Provider ID

Use:

```txt
google-vertex
```

## Configuration Inputs

Resolve project ID in this precedence order:

```txt
provider.google-vertex.options.project
GOOGLE_CLOUD_PROJECT
GCP_PROJECT
GCLOUD_PROJECT
```

Resolve location in this precedence order:

```txt
provider.google-vertex.options.location
GOOGLE_VERTEX_LOCATION
GOOGLE_CLOUD_LOCATION
VERTEX_LOCATION
us-central1
```

The provider should only be enabled/autoloaded when `project` is present.

## Credential Sources

Use Google ADC. Support these without custom app-specific logic:

```txt
gcloud auth application-default login
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
GCE/GKE/Cloud Run attached service account
Workload Identity / metadata server
```

Do not require a Google API key for Vertex.

## Native Python Implementation

Use the native Vertex AI Python SDK.

Dependencies:

```bash
pip install google-cloud-aiplatform
```

Provider initialization:

```python
import os
import vertexai


def resolve_google_vertex_config(config: dict):
    options = (
        config
        .get("provider", {})
        .get("google-vertex", {})
        .get("options", {})
    )

    project = (
        options.get("project")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT")
        or os.getenv("GCLOUD_PROJECT")
    )

    location = (
        options.get("location")
        or os.getenv("GOOGLE_VERTEX_LOCATION")
        or os.getenv("GOOGLE_CLOUD_LOCATION")
        or os.getenv("VERTEX_LOCATION")
        or "us-central1"
    )

    if not project:
        return None

    return {
        "project": project,
        "location": location,
    }


def init_google_vertex(config: dict):
    vertex_config = resolve_google_vertex_config(config)
    if not vertex_config:
        return None

    vertexai.init(
        project=vertex_config["project"],
        location=vertex_config["location"],
    )

    return vertex_config
```

Example model call:

```python
from vertexai.generative_models import GenerativeModel


def generate_with_vertex(model_id: str, prompt: str):
    model = GenerativeModel(model_id)
    response = model.generate_content(prompt)
    return response.text
```

## Expected Usage

Config file:

```json
{
  "provider": {
    "google-vertex": {
      "options": {
        "project": "my-gcp-project",
        "location": "us-central1"
      }
    }
  }
}
```

Or env-only:

```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=my-gcp-project
export VERTEX_LOCATION=us-central1
```

Then:

```python
init_google_vertex(config)
text = generate_with_vertex("gemini-2.5-flash", "Say hello")
```

## Behavior Requirements

1. If no project is found, do not enable the provider.
2. If project exists but ADC is missing or invalid, surface the Google SDK auth error directly.
3. Default location must be `us-central1`.
4. API keys must not be required for `google-vertex`.
5. Do not manually refresh tokens when using native Vertex SDK; let Google SDK handle ADC.
6. Keep config/env resolution separate from model invocation so it can be tested independently.

## Test Cases

Cover:

```txt
uses config project over env project
uses GOOGLE_CLOUD_PROJECT when config project is missing
falls back through GCP_PROJECT and GCLOUD_PROJECT
uses config location over env location
falls back through GOOGLE_VERTEX_LOCATION, GOOGLE_CLOUD_LOCATION, VERTEX_LOCATION
defaults location to us-central1
returns disabled/None when no project is configured
initializes vertexai with resolved project/location
```

## Optional: OpenAI-Compatible Vertex Path

Only implement this if the target repo needs Vertex MaaS/OpenAI-compatible endpoints. Native Gemini does not need it.

For OpenAI-compatible Vertex, build:

```python
endpoint = (
    "aiplatform.googleapis.com"
    if location == "global"
    else f"{location}-aiplatform.googleapis.com"
)

base_url = (
    f"https://{endpoint}/v1/projects/{project}"
    f"/locations/{location}/endpoints/openapi"
)
```

Then use ADC to fetch a bearer token via `google-auth`, and refresh it before requests. This is separate from native Vertex/Gemini SDK usage.
