# policyengine-bundles

`policyengine-bundles` is an archival repository for historical compatibility
manifests for PolicyEngine package sets.

New PolicyEngine bundles are owned by `policyengine.py` and installed through
the `policyengine bundle install` command, for example
`uvx --from policyengine policyengine bundle install --venv .venv`. This
repository no longer publishes new bundle releases or opens consuming PRs into
`policyengine.py`.

A bundle answers one question:

> Which exact versions of PolicyEngine packages are asserted to work with which
> exact country data release manifests?

The repository does not build runtime environments, solve dependency locks,
import country packages, or run simulations. Runtime behavior belongs in the
package test suites and downstream deployment systems.

## Contract

Bundle schema v2 has two artifact types:

- **Candidate**: the source-of-truth input under `candidates/*.json` or
  `examples/candidates/*.json`.
- **Generated bundle**: the validated release payload generated from a candidate.

A candidate declares:

- `bundle_version`: the exact `policyengine` version bundled by `policyengine.py`.
- `packages`: exact component package versions, including `policyengine-core`.
- `countries`: each country model package and immutable data release manifest URI.

Generation resolves package pins from PyPI, loads each country data release
manifest, and writes a country compatibility assertion with:

- exact model package pin;
- exact core package pin;
- data package identity;
- release manifest URI;
- release manifest SHA-256;
- default dataset and artifact metadata from the data release manifest.

## Validation

Registry validation is intentionally light. It checks that:

- generated files satisfy the typed bundle directory contract;
- package pins are exact and include wheel hashes for runtime dependency pins;
- country package pins match the top-level package map;
- compatibility assertions match country manifests;
- release manifest URI and SHA are recorded consistently;
- each country has a default dataset present in its artifact map;
- certified or hash-pinned artifacts include SHA-256 metadata.

Validation does not download dataset artifacts or create Python environments.

## Historical Bundles

Schema v1 bundles under `bundles/` are read-only historical artifacts. The
tooling can load and check their internal metadata consistency, but it does not
generate new schema v1 bundles, re-run their runtime validation, package them as
active releases, or open `policyengine.py` consuming PRs for them.

## Historical Local Workflow

Install tooling:

```bash
python -m pip install --upgrade -e ".[dev]"
```

Generate a bundle from a candidate:

```bash
python scripts/generate_bundle.py \
  --input examples/candidates/example-us.json \
  --output .tmp/generated-bundles/4.14.0
```

Validate the generated bundle:

```bash
python scripts/validate_bundle.py .tmp/generated-bundles/4.14.0
```

Package release assets:

```bash
python scripts/package_bundle_release.py \
  .tmp/generated-bundles/4.14.0 \
  --output-dir .tmp/dist
```

Run repository checks:

```bash
python scripts/validate_schemas.py
python scripts/validate_models.py
pytest
ruff format --check .
ruff check .
```

## Publication

Publication is disabled. Historical scripts remain for inspection and
validation of existing manifests only. To update the current certified
PolicyEngine bundle, open a bundle metadata PR in `policyengine.py` with
`scripts/prepare_stack_update.py`.

## Schemas

Regenerate schemas after model changes:

```bash
python scripts/generate_schemas.py
```

Committed schemas are checked by CI with `scripts/validate_schemas.py`.
