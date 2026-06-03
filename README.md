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
  carries install targets by profile and Python version
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
candidates/
  4.4.2-all.json
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
    install/
      us/
        py313/
          constraints.txt
          pylock.toml
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

The bundle manifest is the canonical reproducibility record. Install targets
point to the profile/Python-specific constraints and lockfile artifacts used to
recreate the certified package graph. They are not a byte-for-byte operating
system image or container substitute.

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

Bundle publication intentionally has one strict path: generate the bundle,
solve every supported Python version declared in the bundle metadata, then
validate the complete bundle. The CLI does not support partial profile or
partial Python-version release artifacts because those can silently create
stale or incomplete manifests.

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
Hugging Face reads use `HF_TOKEN`, `HUGGING_FACE_HUB_TOKEN`, or
`HUGGING_FACE_TOKEN` when set.

Runtime compatibility is certified by the bundle, not by mutating the data
release manifest. A country passes certification when the data release was built
with the same country and core package pins, when the selected country package
emits runtime metadata with the same `data_build_fingerprint` and the same core
pin, or when the candidate includes an explicit manual runtime certification:

```json
{
  "countries": {
    "us": {
      "model_package": "policyengine-us",
      "data_release_manifest_uri": "hf://model/policyengine/policyengine-us-data@1.73.0/release_manifest.json",
      "certification": {
        "basis": "manual_runtime_certification",
        "certified_by": "PolicyEngine",
        "reason": "Reviewed policyengine-us 1.715.2 against this data release."
      }
    }
  }
}
```

The `compatible_model_packages` and `compatible_core_packages` fields in data
release manifests are retained for readability and older producers, but they are
not the certification gate for bundle generation.

The canonical Hugging Face URI form is
`hf://{repo_type}/{org}/{repo}@{revision}/{path}`, for example
`hf://model/policyengine/policyengine-us-data@1.73.0/release_manifest.json`.
Legacy `hf://{org}/{repo}/{path}@{revision}` references are accepted for
historical bundle inputs and normalized by the shared reference parser.

Certified bundles should use immutable remote release manifest URIs. Local
`file://` release manifests are rejected by default because absolute filesystem
paths are not portable. Use `--testing-only` for local tests, or
`--embed-local-manifests` to copy local manifests into stable bundle paths under
`source-manifests/<country>/release_manifest.json`.
When a bundle embeds a local release manifest, that embedded file is the
authoritative source for validation. Runtime validation does not fall back to
the original local input path if the embedded copy is missing.
When a bundle records a release manifest URI, that URI is authoritative even if
a same-named file exists inside the bundle directory.

2. Generate install lockfiles and hash-pinned constraints:

```bash
python scripts/solve_lockfiles.py bundles/4.4.0
```

This writes profile/Python-specific artifacts under `install/`, then records
their relative paths back into `bundle.json` as profile `install_targets`.
The supported Python versions come exclusively from
`bundle.json` `metadata.python_versions`; there is no per-run Python-version
override.
Runtime validation requires every profile to contain exactly one install target
for each declared Python version, with no missing or undeclared targets.
Here, "lockfile" means an installation-resolution artifact, not a concurrency
lock. The bundle contract assumes the exact package graph works across supported
systems for a given Python version; validation records the platform it actually
ran on as evidence, not as part of bundle identity.

Each install target key must match its Python version:

```json
{
  "profiles": {
    "us": {
      "install_targets": {
        "py313": {
          "python_version": "3.13",
          "constraints": "install/us/py313/constraints.txt",
          "lockfile": "install/us/py313/pylock.toml",
          "resolver": "uv"
        }
      }
    }
  }
}
```

New bundles should use only `install_targets`. The older profile-level
`constraints` and `lockfiles` maps are intentionally not part of the current
schema because they make install resolution ambiguous.

3. Validate the complete bundle:

```bash
python scripts/validate_bundle.py bundles/4.4.0
```

Validation checks that certified data artifacts are reachable and match their
declared hashes, creates clean profile environments from the generated
constraints, verifies direct package versions, imports the profile packages, and
runs country household smoke checks where supported for every profile and every
declared install target. If `policyengine` is a pre-release bundle carrier and
is excluded from the runtime install, the smoke checks use the installed country
packages directly. The resulting
`validation-report.json` is part of the bundle contract.
Runtime validation records the current runner platform in check details, but
platform-specific lockfiles are intentionally out of scope for this contract.
For embedded release manifests, validation hashes the embedded file from the
bundle directory. Missing embedded manifests fail validation instead of falling
back to the original source URI recorded for provenance.

The validator defaults to full certification checks. Test fixtures or
historical demonstration bundles can opt into an explicitly partial report:

```bash
python scripts/validate_bundle.py \
  --skip-data-verification \
  --skip-runtime-validation \
  examples/bundles/example
```

Partial reports mark the skipped checks and set
`metadata.validation_scope` to `partial`. They are useful for schema fixtures,
but they are not evidence that a bundle is reproducible.

CI regenerates the current certified bundle from the committed candidate spec
and compares it with the checked-in bundle using normalized output. The
comparison ignores run-local evidence such as timestamps, temporary paths, and
resolver comments, but it still requires package/data metadata, lockfile
contents, and validation outcomes to match.

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
- profile install targets solve for supported Python versions;
- integrated validation passes for each profile.
