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
  carries install lockfiles or constraints by profile and Python version
```

Country packages and data packages continue to release independently. A bundle
selects already-published artifacts and certifies that they work together.

## Repository Layout

```text
src/
  policyengine_bundles/
    bundle_validation.py
    generation.py
    lockfiles.py
    models.py
    validation.py
schemas/
  bundle.schema.json
  component-runtime-metadata.schema.json
  country-bundle.schema.json
  data-release-manifest.schema.json
  validation-report.schema.json
docs/
  component-metadata-contract.md
examples/
  bundles/
    example/
      bundle.json
      countries/
        us.json
      validation-report.json
scripts/
  generate_bundle.py
  generate_schemas.py
  solve_lockfiles.py
  validate_bundle.py
  validate_models.py
  validate_schemas.py
```

Schema files are generated from the Pydantic models in
`policyengine_bundles.models`; do not hand-edit them. Run
`python scripts/generate_schemas.py` after changing model contracts.

Bundle releases and historical seeds live under:

```text
bundles/
  4.4.0/
    bundle.json
    countries/
      us.json
      uk.json
    lockfiles/
      pylock.us.py313.toml
      pylock.uk.py313.toml
      pylock.all.py313.toml
    constraints/
      constraints-us-py313.txt
      constraints-uk-py313.txt
      constraints-all-py313.txt
    validation-report.json
```

The current `bundles/4.3.1/` directory is a historical seed derived from the
published `policyengine==4.3.1` wheel. Its `validation-report.json` is marked
`failed` on purpose because that release did not exact-pin `policyengine-core`
and the private UK data artifact checksum was not present in the bundled
manifest. This makes the current reproducibility gaps machine-readable instead
of hiding them.

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

## Demonstration: Historical 4.3.1 Seed

The `bundles/4.3.1/` directory demonstrates how the bundle system should work
once it is fully implemented, using the current published `policyengine==4.3.1`
wheel as source material.

Start from the human-facing version:

```bash
pip install "policyengine[us]==4.3.1"
```

The bundle record for that version is:

```text
bundles/4.3.1/bundle.json
```

That top-level manifest maps the `us`, `uk`, and `all` profiles to exact
country manifests:

```text
bundles/4.3.1/countries/us.json
bundles/4.3.1/countries/uk.json
```

For the US profile, the seed records:

| Component | Recorded value |
|---|---|
| `policyengine` | `4.3.1` |
| `policyengine-us` | `1.653.3` |
| `policyengine-core` | `>=3.25.0` |
| US data artifact | `hf://policyengine/policyengine-us-data/enhanced_cps_2024.h5@1.73.0` |
| US data SHA256 | `18cdc668d05311c32ae37364abcea89b0221c27154559667e951c7b19f5b5cbd` |

For the UK profile, the seed records:

| Component | Recorded value |
|---|---|
| `policyengine` | `4.3.1` |
| `policyengine-uk` | `2.88.0` |
| `policyengine-core` | `>=3.25.0` |
| UK data artifact | `hf://policyengine/policyengine-uk-data-private/enhanced_frs_2023_24.h5@1.40.4` |
| UK data SHA256 | not present in the source wheel manifest |

The validation report is intentionally not a success report:

```text
bundles/4.3.1/validation-report.json
```

It fails certification because:

- `policyengine-core` was not exact-pinned by `policyengine==4.3.1`.
- The private UK data artifact did not include a SHA256 in the bundled manifest.
- No lockfiles or constraints files were produced for the release.
- No bundle-level integration runtime was executed.

This is the expected behavior for a historical seed. The bundle can represent
what the old release knew, while making clear that the old release is not enough
for single-version reproducibility.

In a future fully certified bundle, the same flow should end with a passing
validation report:

```text
policyengine==4.4.0
  -> bundles/4.4.0/bundle.json
  -> profile us
  -> exact policyengine-core version
  -> exact policyengine-us version
  -> exact policyengine-us-data artifact URI and SHA256
  -> solved constraints or lockfile
  -> passing profile integration checks
```

Consumers such as `policyengine.py` or `policyengine-api-v2-alpha` should treat
the bundle as the release contract. Given one `policyengine` version, a consumer
can load the matching bundle, select a profile, resolve packages and datasets,
and reject failed or incomplete bundles unless the caller explicitly asks to run
with an uncertified historical seed.

## Authoring Flow

The current tooling demonstrates the intended bundle publication path without
adding extra release marker files. The official artifact is still the versioned
`bundle.json` plus its referenced country manifests, lockfiles, constraints, and
validation report.

1. Generate a bundle from an explicit candidate spec:

```bash
python scripts/generate_bundle.py \
  --input candidate-bundle.json \
  --output bundles/4.4.0
```

The candidate spec chooses the human-facing `policyengine` version, exact
package versions, supported Python versions, profiles, and country data release
manifest URIs. Data release manifests may be loaded from `file://` paths for
local testing or from `hf://...` references for Hugging Face artifacts. Private
Hugging Face reads use `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN` when set.

2. Generate install lockfiles and hash-pinned constraints:

```bash
python scripts/solve_lockfiles.py bundles/4.4.0
```

This writes profile/Python-specific artifacts under `lockfiles/` and
`constraints/`, then records their relative paths back into `bundle.json`.
Here, "lockfile" means an installation-resolution artifact, not a concurrency
lock. The default target platform is Linux; pass `--python-platform` only if the
bundle intentionally certifies another platform.

3. Validate the complete bundle:

```bash
python scripts/validate_bundle.py bundles/4.4.0
```

Validation checks that certified data artifacts are reachable and match their
declared hashes, creates clean profile environments from the generated
constraints, verifies direct package versions, imports the profile packages, and
runs country household smoke checks where supported. The resulting
`validation-report.json` is part of the bundle contract.

## Validation

Run local validation with:

```bash
python -m pip install -e ".[dev]"
python scripts/generate_schemas.py
pytest
python scripts/validate_schemas.py
python scripts/validate_models.py
ruff format --check .
ruff check .
```

The validation script checks that:

- every committed schema was generated from the current Pydantic models;
- every schema is a valid JSON Schema document;
- every example bundle validates against `bundle.schema.json`;
- every example country bundle validates against `country-bundle.schema.json`;
- every example validation report validates against `validation-report.schema.json`.

The model validation script checks that:

- every example and release bundle loads through the canonical Pydantic models;
- component runtime metadata payloads can be validated without component packages depending on this repository at runtime;
- core models can export JSON Schema for downstream documentation and contract checks.

## Release Contract

A bundle release should not be published unless:

- package versions and artifacts resolve from PyPI or their package registry;
- `policyengine-core` is exact-pinned;
- country model packages are exact-pinned;
- data artifact URIs are immutable/versioned;
- certified data artifacts include SHA256 hashes;
- country data release manifests are reachable;
- lockfile/constraints files solve for supported Python versions;
- integrated validation passes for each profile.
