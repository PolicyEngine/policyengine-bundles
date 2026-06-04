#!/usr/bin/env bash
set -euo pipefail

: "${BUNDLE_VERSION:?}"
: "${POLICYENGINE_PY_REPO:?}"
: "${POLICYENGINE_PY_BASE_BRANCH:?}"

cd policyengine.py
branch="automation/policyengine-bundle-$BUNDLE_VERSION"
git config user.name "policyengine-bundles[bot]"
git config user.email "policyengine-bundles[bot]@users.noreply.github.com"
git switch -c "$branch"

python scripts/import_policyengine_bundle.py \
  "$BUNDLE_VERSION" \
  --dist-dir ../.tmp/dist

if [ -z "$(git status --porcelain)" ]; then
  echo "No policyengine.py changes produced."
  exit 0
fi

git add .
git commit -m "Vend PolicyEngine bundle $BUNDLE_VERSION"
git push --force-with-lease origin "$branch"
existing_pr="$(gh pr list \
  --repo "$POLICYENGINE_PY_REPO" \
  --head "$branch" \
  --state open \
  --json number \
  --jq '.[0].number // empty')"

if [ -n "$existing_pr" ]; then
  gh pr edit "$existing_pr" \
    --repo "$POLICYENGINE_PY_REPO" \
    --base "$POLICYENGINE_PY_BASE_BRANCH" \
    --title "Vend PolicyEngine bundle $BUNDLE_VERSION" \
    --body "Updates policyengine.py to vend PolicyEngine bundle $BUNDLE_VERSION from PolicyEngine/policyengine-bundles."
else
  gh pr create \
    --repo "$POLICYENGINE_PY_REPO" \
    --base "$POLICYENGINE_PY_BASE_BRANCH" \
    --head "$branch" \
    --title "Vend PolicyEngine bundle $BUNDLE_VERSION" \
    --body "Updates policyengine.py to vend PolicyEngine bundle $BUNDLE_VERSION from PolicyEngine/policyengine-bundles."
fi
