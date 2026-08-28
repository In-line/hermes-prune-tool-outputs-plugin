#!/usr/bin/env bash
set -euo pipefail

# Release checklist: create curated notes, then tag.
#   ./scripts/release.sh v1.0.0
#
# Requires gh (https://cli.github.com/) authenticated with repo push access.

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  echo "Usage: $0 <tag>   e.g. $0 v1.0.0" >&2
  exit 1
fi

NOTES_FILE=".github/release-notes/${TAG}.md"
if [[ ! -s "$NOTES_FILE" ]]; then
  echo "Missing curated release notes: $NOTES_FILE" >&2
  echo "Create it before tagging (the release workflow requires it)." >&2
  exit 1
fi

git tag "$TAG"
git push origin "$TAG"
echo "Tag $TAG pushed — the Release workflow will publish it."
