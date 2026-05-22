from __future__ import annotations

from pathlib import Path

from policyengine_bundles.validation import load_bundle_directory


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_410_bundle_declares_longterm_profile_without_partial_claim() -> None:
    bundle = load_bundle_directory(REPO_ROOT / "bundles" / "4.10.0")

    profile = bundle.manifest.profiles["us-longterm-crfb"]
    assert profile.countries == ["us"]
    assert profile.packages == [
        "policyengine",
        "policyengine-core",
        "policyengine-us",
    ]

    country = bundle.countries["us"]
    for year in (2026, 2050, 2100):
        artifact = country.datasets[f"long_term_cps_{year}"]
        assert artifact.status == "hash_pinned"
        assert artifact.sha256 is not None
        assert artifact.metadata_sha256 is not None


def test_410_validation_report_keeps_longterm_certification_skipped() -> None:
    bundle = load_bundle_directory(REPO_ROOT / "bundles" / "4.10.0")

    checks = [
        check
        for check in bundle.validation_report.checks
        if check.name == "longterm_partial_certification"
    ]
    assert len(checks) == 1
    assert checks[0].status == "skipped"
    assert checks[0].profile == "us-longterm-crfb"
    assert checks[0].details["representative_years"] == [2026, 2050, 2100]
