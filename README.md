# hermes-prune-tool-outputs

Model-initiated tool output pruning plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

The model calls the `prune_tool_outputs` tool when previous tool results are no longer needed. On the next API call, old tool outputs are replaced with compact 1-line summaries, keeping the context window lean.

## How it works

1. The model calls `prune_tool_outputs` (optionally with `keep_last_n_messages`, `keep_first_n_messages`, `exclude_tool_types`).
2. The handler validates the arguments and sets a thread-safe flag.
3. On the next API call, `llm_request` middleware replaces tool results outside the protected zone with 1-line summaries and clears the flag.
4. Middleware also appends a short, deterministic instruction to the system message telling the model when to prune.

## Installation

Clone and symlink the plugin into your Hermes home:

```bash
git clone https://github.com/In-line/hermes-prune-tool-outputs-plugin.git
cd hermes-prune-tool-outputs-plugin
./scripts/install.sh
```

The script honors `HERMES_HOME` and `HERMES_PROFILE` (installs into `~/.hermes/profiles/<name>/` when set) and refuses to overwrite unrelated existing paths.

Then enable the plugin and restart Hermes:

```bash
hermes plugins enable hermes-prune-tool-outputs
```

or add it manually to `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - hermes-prune-tool-outputs
```

Verify with `hermes plugins` — the plugin should be listed as enabled, and the `prune_tool_outputs` tool available in sessions.

## Tool parameters

| Parameter | Default | Description |
|---|---|---|
| `keep_last_n_messages` | 12 | Recent messages protected from pruning (min 2, max 500) |
| `keep_first_n_messages` | 0 | Messages from the start protected from pruning (max 100) |
| `exclude_tool_types` | — | Tool names whose results are never pruned |

## Configuration

| Env var | Default | Description |
|---|---|---|
| `PRUNE_TOOL_OUTPUTS_LOG_VERBOSE` | `false` | Log each prune with saved char counts at INFO level |

## Development

```bash
uv venv .venv && uv pip install --python .venv/bin/python pytest pre-commit
.venv/bin/python -m pytest          # unit + integration tests (tests/)
.venv/bin/pre-commit run --all-files  # lint + format (same checks CI runs)
```

## Releases

Tags (`v*`) trigger the [release workflow](.github/workflows/release.yml), which publishes a GitHub Release from curated notes in `.github/release-notes/<tag>.md`.

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE) or any later version (SPDX: `GPL-3.0-or-later`). All source files carry the standard GPL notice.
