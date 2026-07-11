# Installer and configuration reference

This document contains lower-level installation and configuration behavior useful for troubleshooting, automation, and reviewing what `install.sh` is allowed to change.

For the normal setup path, start with the [README](../README.md#quick-start).

## Installer usage

```bash
./install.sh [--skills codex|claude|both|none] [--uninstall] [--purge-config] [--dry-run]
```

Examples:

```bash
./install.sh --skills codex
./install.sh --skills claude
./install.sh --skills both
./install.sh --skills none
./install.sh --dry-run --skills both
```

When run interactively without `--skills`, the installer asks whether to install the Codex skill, Claude Code skill, both, or neither. For scripts and CI, pass the desired value explicitly.

## Managed paths

The installer owns only paths that it creates and marks as belonging to this toolkit.

| Purpose | Path |
| --- | --- |
| Managed installation root | `~/.local/share/local-agent-toolkit` |
| Managed executable | `~/.local/share/local-agent-toolkit/bin/local-agent` |
| Public command symlink | `~/.local/bin/local-agent` |
| Installation state | `~/.local/share/local-agent-toolkit/install-state.json` |
| Saved user configuration | `~/.config/local-agent/config.json` |
| Model metadata cache | `~/.cache/local-agent/model-metadata-v1.json` |
| Installer lock | `~/.local/state/local-agent-toolkit/install.lock` |
| Codex personal skill | `~/.agents/skills/local-agent-toolkit` |
| Claude Code personal skill | `~/.claude/skills/local-agent-toolkit` |

`~/.local/share/local-agent-toolkit` is the authoritative marker for a managed installation.

## PATH behavior

The installer exposes the managed executable through `~/.local/bin/local-agent`.

If `~/.local/bin` is not already exported in `~/.zshrc`, the installer adds a removable marked block:

```bash
# BEGIN LOCAL-AGENT TOOLKIT PATH
export PATH="$HOME/.local/bin:$PATH"
# END LOCAL-AGENT TOOLKIT PATH
```

If the same PATH export already exists outside the toolkit markers, the installer leaves `.zshrc` unchanged.

The installer refuses to replace `~/.local/bin/local-agent` when it is a regular file, directory, or symlink to another target. Move or remove that path manually before installing.

## Reinstallation behavior

If the managed installation directory already exists, an interactive run asks for exact lowercase `yes` or `no` confirmation before removing and reinstalling it.

A noninteractive or CI rerun does not reinstall automatically. It exits successfully after explaining that confirmation requires an interactive terminal. This prevents scripts from silently replacing an existing installation.

## Personal skill installation

The canonical skill source is `skills/local-agent-toolkit`.

Replacement is ownership-protected. The installer refuses to replace unmanaged directories, symlinks, or destinations with missing or malformed ownership markers.

With `--skills both`, Codex is processed first and Claude Code second. If the first target succeeds and the second fails, the successful target remains installed and the overall command exits nonzero to report partial completion.

After a skill is installed successfully, the installer removes only the matching toolkit-managed legacy instruction block from `~/.codex/AGENTS.md` or `~/.claude/CLAUDE.md`. Unrelated content, line endings, and final-newline behavior are preserved.

Restart or refresh existing Codex and Claude Code sessions after installation. Filesystem installation does not itself prove that a running session discovered the skill.

## Deprecated `--instructions` alias

The old syntax remains temporarily available:

```bash
./install.sh --instructions codex
```

It selects the personal-skill installation flow and prints a deprecation warning. It does not reinstall the old global instruction block. New scripts should use `--skills`.

## Dry runs

```bash
./install.sh --dry-run --skills both
```

A dry run inspects the current public command, managed installation paths, `.zshrc`, canonical skill source, and exact skill destinations. It prints intended changes without writing files or invoking `local-agent configure`.

## Configuration

Saved configuration lives at `~/.config/local-agent/config.json`. The file uses schema version `1`, is written atomically, and has mode `0600`.

```bash
local-agent configure --show

local-agent configure \
  --model 'your-installed-model-name' \
  --host http://127.0.0.1:11434 \
  --num-ctx 32768 \
  --max-chars 120000
```

Settings resolve in this order:

1. command-line option;
2. environment variable;
3. saved configuration;
4. built-in default.

```bash
export LOCAL_AGENT_MODEL='your-installed-model-name'
export LOCAL_AGENT_HOST='http://127.0.0.1:11434'
export LOCAL_AGENT_NUM_CTX='32768'
export LOCAL_AGENT_MAX_CHARS='120000'
```

## Model inventory

List model names:

```bash
local-agent models
```

Inspect human-readable or structured details:

```bash
local-agent models --verbose
local-agent models --json
```

The versioned inventory includes installed model metadata, running state, system-memory information, memory estimates, performance timings, cache status, and warnings when available.

Static metadata is cached by model name and digest at `~/.cache/local-agent/model-metadata-v1.json`. Warm inventory and recommendation calls can reuse valid cached metadata rather than calling Ollama's `/api/show` for every installed model.

Optional metadata may be `null` or empty. Artifact size is not exact runtime RAM or VRAM use, and estimated memory for unloaded models remains an approximation.

## Model recommendation

Recommend an installed model for a specific command and planned context size:

```bash
local-agent recommend-model review --num-ctx 16384
local-agent recommend-model review --num-ctx 16384 --name-only
local-agent recommend-model review --num-ctx 16384 --json
```

Optional controls include:

```text
--quality fast|balanced|strong
--prefer-model <exact-installed-name>
--exclude-model <exact-installed-name>
--refresh
```

The command profile determines whether the ranking favors a lightweight suitable model, a balanced candidate, or the strongest safe candidate. Models are rejected when they are explicitly excluded, unsuitable for coding, unable to support the requested context, or classified as unsafe or unknown for memory fit.

Preferences influence ranking only among eligible models. They cannot bypass context or memory filters.

The recommender may inspect Ollama `/api/tags` and `/api/ps`, cached static metadata, `/api/show` when refresh or cache misses require it, and current system memory. It never loads, unloads, benchmarks, or runs inference with a model.

If no safe eligible model is found, `--name-only` produces no model name and the command exits nonzero. Reduce the requested context or supplied files and retry once; otherwise do not delegate locally.

## Recommender assumptions

The recommender is conservative and explainable, not a universal quality leaderboard.

- Runtime memory for unloaded models is estimated from artifact size, runtime overhead, and KV-cache requirements.
- Installed size is not exact runtime memory usage.
- Parameter count does not fully determine model quality.
- Mixture-of-experts total parameters can overstate active computation.
- Quantization is used conservatively as a tie-breaker rather than a universal quality score.
- A model classified as safe may still generate slowly.
- Unknown or incomplete metadata can cause conservative rejection.

Use JSON output to inspect candidates, rejected models, reason codes, assumptions, warnings, and estimated headroom.

## Remote Ollama hosts

The default host is `http://127.0.0.1:11434`.

When `LOCAL_AGENT_HOST` or `--host` points to a non-local server, supplied source context is sent to that server. Remote use requires `--allow-remote-host`; remote plain HTTP additionally requires `--allow-insecure-remote-host`.

Host URLs containing embedded credentials, query strings, fragments, or non-root paths are rejected. Keep the host local when source privacy matters.

## Uninstallation

Preserve saved model configuration:

```bash
./install.sh --uninstall
```

Remove the saved configuration too:

```bash
./install.sh --uninstall --purge-config
```

Uninstallation removes the public symlink only when it still resolves to the toolkit-managed executable, the managed installation directory, the toolkit-managed PATH block, matching legacy managed instruction blocks, and only owned skill directories at known destinations.

It never removes a parent skill directory or an unmarked destination. Uninstallation is driven by the repository's `install.sh`; there is currently no `local-agent uninstall` subcommand.

The model metadata cache is not part of the managed installation root and is not currently documented as being removed by `--uninstall` or `--purge-config`.

## Primary support boundary

The installer is designed primarily for macOS users running zsh. Ubuntu is exercised in CI, and parts of the CLI may work on other Unix-like systems, but Bash, Fish, Windows, and nonstandard shell setups may require manual executable installation and PATH configuration.
