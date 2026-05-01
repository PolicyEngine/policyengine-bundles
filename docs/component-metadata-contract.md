# Component Metadata Contract

This repository owns the canonical PolicyEngine bundle schemas and typed models.
Component packages should not depend on `policyengine-bundles` at runtime.

Instead, component packages should expose small dependency-free metadata emitters
that return plain JSON-compatible dictionaries. The bundle generator imports or
reads those payloads and validates them against `policyengine_bundles` models.

## Runtime Component Metadata

Core and country packages should expose:

```python
def get_runtime_metadata() -> dict:
    return {
        "name": "policyengine-core",
        "version": "3.25.3",
        "git_sha": "abc123",
    }
```

Country packages may include the core version they were imported with:

```python
def get_runtime_metadata() -> dict:
    return {
        "name": "policyengine-us",
        "version": "1.667.1",
        "git_sha": "def456",
        "data_build_fingerprint": "sha256:...",
        "core": {
            "name": "policyengine-core",
            "version": "3.25.3",
            "resolution_status": "pinned",
        },
    }
```

## Dependency Boundary

Component repos may install `policyengine-bundles` in CI to validate these
payloads:

```python
from policyengine_bundles import load_component_metadata


def test_runtime_metadata_contract():
    load_component_metadata(get_runtime_metadata())
```

Production imports in `policyengine-core`, `policyengine-us`, `policyengine-uk`,
`policyengine-us-data`, and `policyengine-uk-data` should not require
`policyengine-bundles`.

## Bundle Ownership

The bundle generator is responsible for turning component metadata into a
certified bundle. Component packages describe themselves; `policyengine-bundles`
certifies the cross-package composition.
