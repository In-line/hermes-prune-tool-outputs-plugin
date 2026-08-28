#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

HERMES_HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"
if [[ -n "${HERMES_PROFILE:-}" ]]; then
  TARGET_ROOT="$HERMES_HOME_DIR/profiles/${HERMES_PROFILE}"
else
  TARGET_ROOT="$HERMES_HOME_DIR"
fi

PLUGIN_TARGET="$TARGET_ROOT/plugins/hermes-prune-tool-outputs"

preflight_target() {
  local target="$1"
  local expected="$2"

  if [[ -L "$target" ]]; then
    local current_target
    current_target="$(readlink "$target")"
    if [[ "$current_target" != "$expected" ]]; then
      echo "Refusing to replace existing symlink: $target -> $current_target" >&2
      echo "Remove it manually or point it at this checkout before rerunning install.sh." >&2
      exit 1
    fi
  elif [[ -e "$target" ]]; then
    if [[ -d "$target" ]]; then
      local physical_target
      physical_target="$(cd "$target" && pwd -P)"
      if [[ "$physical_target" == "$expected" ]]; then
        return
      fi
    fi
    echo "Refusing to replace existing path: $target" >&2
    echo "Move it aside or remove it manually before rerunning install.sh." >&2
    exit 1
  fi
}

preflight_target "$PLUGIN_TARGET" "$REPO_ROOT"

mkdir -p "$(dirname "$PLUGIN_TARGET")"

if [[ ! -e "$PLUGIN_TARGET" && ! -L "$PLUGIN_TARGET" ]]; then
  ln -s "$REPO_ROOT" "$PLUGIN_TARGET"
fi

cat <<EOF
Installed hermes-prune-tool-outputs at:
  $PLUGIN_TARGET

Enable it:

  hermes plugins enable hermes-prune-tool-outputs

or add to ~/.hermes/config.yaml:

  plugins:
    enabled:
      - hermes-prune-tool-outputs

Verification:
  1. Restart Hermes.
  2. Run: hermes plugins
  3. Confirm hermes-prune-tool-outputs is listed as enabled.
  4. In a session, confirm the prune_tool_outputs tool is available.
EOF
