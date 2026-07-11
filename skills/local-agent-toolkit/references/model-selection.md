# Model Selection

Inspect the installed inventory first:

```bash
local-agent models --json
```

Then apply this policy:

1. Exclude models whose capabilities clearly make them unsuitable for coding.
2. Exclude models with insufficient context for the explicit supplied files.
3. Prefer smaller suitable models for discovery, file summaries, and simple diagnosis.
4. Prefer stronger coding models for plans, reviews, tests, patches, and second opinions.
5. Treat parameter count, artifact size, and quantization as rough resource signals only.
6. Pass the selected name explicitly with `--model`.
7. Do not hard-code model names or add ranking heuristics.

`size_bytes` is artifact size, not exact runtime memory use.
