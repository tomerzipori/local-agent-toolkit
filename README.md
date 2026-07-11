# Local Agent toolkit

`local-agent` is a macOS-focused, dependency-free Python 3 command for bounded
coding assistance through a model installed in Ollama. Model output is
untrusted advice: the parent agent must independently verify patches, commands,
paths, and all test claims.

## Install

```bash
chmod +x install.sh
./install.sh
source ~/.zshrc
local-agent --help
```

The installer copies only `bin/local-agent` to `~/.local/bin`, safely upgrades
that copy on repeat runs, adds `~/.local/bin` to `.zshrc`, and attempts
interactive configuration when run from a terminal. Uninstall with:

```bash
./install.sh --uninstall
```

Configuration is saved at `~/.config/local-agent/config.json` with restrictive
file permissions. The installer does not delete that configuration.

## Ollama models and settings

```bash
local-agent models
local-agent configure
local-agent files "Explain responsibilities and risks" src/client.py src/retry.py
```

`models` uses Ollama's local `/api/tags` endpoint, the same model names shown by
`ollama list`. Settings resolve in this order: command-line flag, environment,
then saved configuration.

```bash
export LOCAL_AGENT_MODEL='llama3.2:latest'
export LOCAL_AGENT_HOST='http://127.0.0.1:11434'
export LOCAL_AGENT_NUM_CTX='32768'
export LOCAL_AGENT_MAX_CHARS='120000'
```

If `LOCAL_AGENT_HOST` points to a non-local Ollama server, supplied source code
is sent to that server. Keep the host local when source privacy matters.

## Commands

```bash
local-agent find "Where is retry behavior implemented?"
local-agent files "Explain responsibilities and risks" src/client.py src/retry.py
local-agent plan "Add validation for empty package names" src/config.py tests/test_config.py
local-agent review "Look for correctness regressions"
local-agent review-staged "Pre-commit correctness review"
local-agent review-branch "Review before opening an MR" --base origin/main
local-agent test-plan "Tests for deterministic package sampling" src/sampling.py
local-agent write-tests "Add regression tests for duplicate IDs" src/sampling.py tests/test_sampling.py
local-agent fix-test "Diagnose and propose a minimal fix" --command 'pytest tests/test_sampling.py -x' src/sampling.py
git diff | local-agent second-opinion --stdin "Challenge the design choices in this diff"
local-agent patch "Add validation for empty insight names" src/config.py tests/test_config.py
```

`review-branch` detects the repository's remote default branch, then falls back
to `main` and `master`; `--base` is authoritative. File context is repository
bound by default, binary files and symlinks are skipped, and `--allow-outside-repo`
is an explicit escape hatch. Large context is truncated with an in-prompt notice.

`fix-test` deliberately executes the supplied local shell command. Its combined
output and exit status are included in the model context, and a nonzero command
status is returned after the model response.

## Codex and Claude Code

Append `instructions/AGENTS-snippet.md` to `AGENTS.md` and
`instructions/CLAUDE-snippet.md` to `CLAUDE.md`. Restart existing sessions after
changing instruction files. The snippets require independent review and testing
of every model suggestion.

## Development

This project uses only the Python standard library:

```bash
python3 -m unittest discover -s tests -v
```

The repository intentionally has no license yet; choose one before making it
public.
