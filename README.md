# Local Qwen agent toolkit

Configured model:

`hf.co/unsloth/Qwen3-Coder-Next-GGUF:UD-IQ1_M`

## Install

Make sure Ollama is running and verify the exact model name:

```bash
ollama list
ollama run 'hf.co/unsloth/Qwen3-Coder-Next-GGUF:UD-IQ1_M' 'Reply with OK'
```

Then, from this extracted directory:

```bash
chmod +x install.sh
./install.sh
source ~/.zshrc
```

Verify the installation:

```bash
qwen-agent --help
qwen-plan "Explain this file" README.md
```

## Installed locations

- Core program: `~/.local/share/qwen-agent/qwen-agent`
- Commands: `~/.local/bin/qwen-*`
- PATH line: `~/.zshrc`

## Examples

```bash
qwen-find "Where is retry behavior implemented?"

qwen-files "Explain responsibilities and risks" src/client.py src/retry.py

qwen-plan "Add validation for empty package names" src/config.py tests/test_config.py

qwen-review "Look for correctness regressions"

qwen-review-staged "Pre-commit correctness review"

qwen-review-branch "Review before opening an MR" --base main

qwen-test-plan "Tests for deterministic package sampling" src/sampling.py

qwen-write-tests "Add regression tests for duplicate IDs"   src/sampling.py tests/test_sampling.py

qwen-fix-test "Diagnose and propose a minimal fix"   --command 'pytest tests/test_sampling.py -x'   src/sampling.py tests/test_sampling.py

qwen-sql-review "Check correctness and performance" src/queries.py

git diff | qwen-second-opinion --stdin   "Challenge the design choices in this diff"

qwen-patch "Add validation for empty insight names"   src/config.py tests/test_config.py
```

## Codex and Claude Code

Append `instructions/AGENTS-snippet.md` to your repository's `AGENTS.md`.

Append `instructions/CLAUDE-snippet.md` to your repository's `CLAUDE.md`.

Restart existing Codex and Claude Code sessions after changing instruction files.

## Optional configuration

Add overrides to `~/.zshrc`:

```bash
export LOCAL_QWEN_MODEL='hf.co/unsloth/Qwen3-Coder-Next-GGUF:UD-IQ1_M'
export OLLAMA_HOST_URL='http://127.0.0.1:11434'
export LOCAL_QWEN_NUM_CTX='32768'
export LOCAL_QWEN_MAX_CHARS='120000'
```

The `UD-IQ1_M` quantization is extremely compressed. Use it for first-pass work
and independently verify its output.
