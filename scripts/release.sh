#!/usr/bin/env bash
# hermes-prune-tool-outputs: model-initiated tool output pruning for Hermes Agent.
# Copyright (C) 2026  Alik Aslanyan <inline0@pm.me>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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
