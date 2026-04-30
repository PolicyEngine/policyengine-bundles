# PolicyEngine Bundles

> This repository is currently for testing the PolicyEngine bundle design. Its
> schemas, examples, and release contracts should not be treated as canonical
> production infrastructure until the team explicitly promotes them.

This repository is the immutable archive of PolicyEngine release bundles.

A bundle is the release contract that connects one human-facing
`policyengine` version to the exact component versions and data artifacts that
were certified together.

For example:

```text
policyengine==4.4.0
  vendors or references bundle==4.4.0

bundle==4.4.0
  pins policyengine==4.4.0
  pins policyengine-core==x.y.z
  pins policyengine-us==a.b.c
  pins policyengine-uk==d.e.f
  pins country data artifact releases
  pins dataset URIs and SHA256s
  carries validation results
  carries install locks or constraints by profile and Python version
```

Country packages and data packages continue to release independently. A bundle
selects already-published artifacts and certifies that they work together.

## Repository Layout

```text
schemas/
  bundle.schema.json
  country-bundle.schema.json
  validation-report.schema.json
examples/
  bundles/
    example/
      bundle.json
      countries/
        us.json
      validation-report.json
scripts/
  validate_schemas.py
```

Future bundle releases should live under:

```text
bundles/
  4.4.0/
    bundle.json
    countries/
      us.json
      uk.json
    locks/
      pylock.us.py313.toml
      pylock.uk.py313.toml
      pylock.all.py313.toml
    constraints/
      constraints-us-py313.txt
      constraints-uk-py313.txt
      constraints-all-py313.txt
    validation-report.json
```

## Profiles

Bundles support country-specific install profiles:

- `us`: `policyengine`, `policyengine-core`, `policyengine-us`, and certified US data artifacts.
- `uk`: `policyengine`, `policyengine-core`, `policyengine-uk`, and certified UK data artifacts.
- `all`: all country packages and certified data artifacts included in the release.

Python extras in `policyengine.py` should remain convenience install profiles:

```bash
pip install "policyengine[us]==4.4.0"
pip install "policyengine[uk]==4.4.0"
pip install "policyengine[us,uk]==4.4.0"
```

The bundle manifest is the canonical reproducibility record. Constraints and
lockfiles are the exact install mechanisms for users who need byte-for-byte
environment reproduction.

## Validation

Run local validation with:

```bash
python -m pip install jsonschema ruff
python scripts/validate_schemas.py
ruff format --check .
ruff check .
```

The validation script checks that:

- every schema is a valid JSON Schema document;
- every example bundle validates against `bundle.schema.json`;
- every example country bundle validates against `country-bundle.schema.json`;
- every example validation report validates against `validation-report.schema.json`.

## Release Contract

A bundle release should not be published unless:

- package versions and artifacts resolve from PyPI or their package registry;
- `policyengine-core` is exact-pinned;
- country model packages are exact-pinned;
- data artifact URIs are immutable/versioned;
- certified data artifacts include SHA256 hashes;
- country data release manifests are reachable;
- lock/constraints files solve for supported Python versions;
- integrated validation passes for each profile.
