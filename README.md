![Cover Image](assets/cover.png)
# Local Agent toolkit

`local-agent` is a macOS-focused, dependency-free Python 3.10+ command for bounded
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

The installer manages its own binary at
`~/.local/share/local-agent-toolkit/bin/local-agent` and exposes
`~/.local/bin/local-agent` as a symlink to that managed path. Repeat installs
atomically replace only the managed binary when the public command is still
owned by this toolkit. If `~/.local/bin/local-agent` is a regular file, a
directory, or a symlink to something else, installation refuses to replace it
and asks you to move or remove it manually first.

The installer adds a removable, toolkit-managed PATH block to `.zshrc` only
when `~/.local/bin` is not already exported there elsewhere. In a terminal, the
installer prompts whether to install Codex instructions, Claude instructions,
both, or neither. Choose explicitly for scripts and CI:

```bash
./install.sh --instructions codex
./install.sh --instructions claude
./install.sh --instructions both
./install.sh --instructions none
./install.sh --dry-run --instructions both
```

Instructions are installed globally into `~/.codex/AGENTS.md` and/or
`~/.claude/CLAUDE.md`. The toolkit-managed marker block is replaced safely on
repeat installs while unrelated instructions are preserved. When the flag is
omitted in a noninteractive environment, instruction installation is skipped.
Restart existing Codex or Claude sessions after changing these files.

Dry runs inspect the current public command, managed install paths, `.zshrc`,
and instruction files, then print the changes that would be made without
writing files or invoking `local-agent configure`.

Uninstall with:

```bash
./install.sh --uninstall
./install.sh --uninstall --purge-config
```

Uninstall removes the public symlink only when it still resolves to the
toolkit-managed binary, then removes the managed installation directory, the
toolkit-managed PATH block, and the toolkit-managed instruction blocks. User
configuration at `~/.config/local-agent/config.json` is preserved unless
`--purge-config` is passed. Uninstall is still driven by the repository's
`install.sh`; a future `local-agent uninstall` command is not part of this
branch.

## Ollama models and settings

```bash
local-agent models
local-agent models --json
local-agent configure
local-agent files "Explain responsibilities and risks" src/client.py src/retry.py
```

Plain `models` prints the installed model names, one per line. `models --json`
combines Ollama's `/api/tags` and `/api/show` endpoints and reports a
versioned JSON document with `schema_version`, the host, the configured default
model, model sizes, family metadata, parameter sizes, quantization,
capabilities, and context lengths. Missing optional metadata is reported as
`null` or an empty list. Settings resolve in this order: command-line flag,
environment, then saved configuration.

```bash
export LOCAL_AGENT_MODEL='llama3.2:latest'
export LOCAL_AGENT_HOST='http://127.0.0.1:11434'
export LOCAL_AGENT_NUM_CTX='32768'
export LOCAL_AGENT_MAX_CHARS='120000'
```

If `LOCAL_AGENT_HOST` points to a non-local Ollama server, supplied source code
is sent to that server. Keep the host local when source privacy matters, or
pass `--allow-remote-host` explicitly when remote use is intentional. Remote
HTTP hosts additionally require `--allow-insecure-remote-host`. Hosts with
embedded credentials are rejected.

`local-agent configure` is interactive only when stdin and stdout are terminals.
Use `local-agent configure --show` to print the effective settings and their
source, or update settings noninteractively:

```bash
local-agent configure --model qwen-coder:latest
local-agent configure --host http://127.0.0.1:11434 --model qwen-coder:latest --num-ctx 32768 --max-chars 120000
```

Configuration is saved at `~/.config/local-agent/config.json` with schema
version `1`, atomic writes, and mode `0600`.

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
local-agent diagnose "Explain this CI failure" --stdin tests/test_sampling.py
local-agent fix-test "Diagnose and propose a minimal fix" --command 'pytest tests/test_sampling.py -x' src/sampling.py
local-agent impact "Assess the blast radius of changing retry behavior" src/retry.py tests/test_retry.py
git diff | local-agent second-opinion --stdin "Challenge the design choices in this diff"
local-agent patch "Add validation for empty insight names" src/config.py tests/test_config.py
```

`review-branch` detects the repository's remote default branch, then falls back
to `main` and `master`; `--base` is authoritative.

Context collection is now policy-driven:

- Explicit tracked files are included by default.
- Directories expand to Git-tracked files only by default.
- Explicit untracked files require `--include-untracked`.
- Ignored files require `--include-ignored`.
- Sensitive paths such as `.env`, private keys, `.ssh/*`, and
  `credentials.json` require `--allow-sensitive-files`.
- Files outside the current repository still require `--allow-outside-repo`.
- Symlinks, binary files, and oversized files are skipped with explicit reasons.
- `--max-file-bytes` defaults to `256000`.
- `--max-context-files` defaults to `200`.

Use `--show-context-files` to print the exact context-file manifest and exit
without contacting Ollama. Normal runs print a concise stderr summary of how
many files and characters are being sent, plus how many files were skipped.

Ignored files are not included automatically, even when explicitly named,
because `.gitignore` commonly covers build artifacts, local secrets, and other
non-reviewable workspace data.

`fix-test` deliberately executes the supplied local shell command. Its combined
output and exit status are included in the model context, and a nonzero command
status is returned after the model response.

`diagnose` inspects supplied failure output and file or stdin context without
executing a command. `impact` requires a Git repository and includes its file
map, targeted search results, and any staged or unstaged diff.

## Codex and Claude Code

Append `instructions/AGENTS-snippet.md` to `AGENTS.md` and
`instructions/CLAUDE-snippet.md` to `CLAUDE.md`. Restart existing sessions after
changing instruction files. The snippets require independent review and testing
of every model suggestion.

For scripted installation without instruction snippets:

```bash
./install.sh --instructions none
local-agent configure --model qwen-coder:latest --host http://127.0.0.1:11434
```

## Development

This project uses only the Python standard library:

```bash
python3 -m unittest discover -s tests -v
```

The repository intentionally has no license yet; choose one before making it
public.
