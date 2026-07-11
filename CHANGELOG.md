# Changelog

All notable changes to Local Agent Toolkit will be documented in this file.

The project follows semantic versioning. Because the project is still before version 1.0, minor releases may introduce breaking changes when necessary.

## [Unreleased]

## [0.1.0] - 2026-07-11

Initial public release of Local Agent Toolkit.

### Added

* Added the dependency-free `local-agent` Python CLI for delegating bounded coding tasks to models running through Ollama.
* Added task-specific commands for:

  * Repository and symbol discovery with `find`
  * Focused file analysis with `files`
  * Implementation planning with `plan`
  * Working-tree review with `review`
  * Staged-change review with `review-staged`
  * Branch review with `review-branch`
  * Test planning with `test-plan`
  * Test proposal generation with `write-tests`
  * Failure analysis with `diagnose`
  * Local test execution and diagnosis with `fix-test`
  * Change-impact analysis with `impact`
  * Adversarial review with `second-opinion`
  * Minimal patch proposals with `patch`
* Added `local-agent models` for listing models installed in Ollama.
* Added `local-agent models --json` for retrieving structured model metadata, including model size, family, parameter size, quantization, capabilities, and context length when available.
* Added interactive and noninteractive configuration through `local-agent configure`.
* Added support for configuring the model, Ollama host, context size, and maximum supplied-context size through command-line options, environment variables, or saved configuration.
* Added automatic repository context collection from Git-tracked files.
* Added explicit context manifests through `--show-context-files`.
* Added optional inclusion controls for untracked, ignored, sensitive, and outside-repository files.
* Added global delegation-instruction snippets for Codex and Claude Code.
* Added a managed installer with support for interactive and scripted installation.
* Added dry-run, repeat-install, uninstall, and configuration-purge workflows.
* Added release metadata validation for version tags.
* Added documentation for installation, configuration, commands, development, security reporting, support, and contributing.

### Safety

* Treats local-model output as untrusted advice that must be independently reviewed and verified.
* Instructs local models not to claim that commands or tests were executed unless output was supplied.
* Treats repository content, diffs, comments, filenames, and logs as untrusted data rather than executable instructions.
* Refuses to send repository content to a non-local Ollama host unless remote access is explicitly authorized.
* Requires a separate explicit override for insecure remote HTTP hosts.
* Rejects Ollama host URLs containing embedded credentials.
* Blocks common secret and credential files by default, including `.env` files, private keys, credential files, and SSH material.
* Skips symlinks, binary files, oversized files, and files exceeding configured context limits.
* Requires explicit authorization before reading files outside the current repository.
* Stores saved configuration using atomic writes and restrictive file permissions.
* Limits the maximum accepted Ollama response size.
* Refuses to replace an existing `local-agent` command unless it is owned by the toolkit installation.
* Preserves unrelated shell and agent-instruction content during installation and removal.
* Preserves user configuration during normal uninstall unless `--purge-config` is explicitly supplied.

### Testing and automation

* Added unit tests for configuration, model discovery, context collection, command execution, and installer behavior.
* Added regression coverage for:

  * Repository-boundary enforcement
  * Sensitive-file filtering
  * Ignored and untracked file handling
  * Symlink and binary-file rejection
  * Context-size and file-count limits
  * Remote-host authorization
  * Installer ownership checks
  * Repeat installation
  * Atomic upgrades
  * Safe uninstall behavior
  * Preservation of unrelated shell configuration
* Added Python test coverage on Ubuntu for Python 3.10, 3.11, and 3.13.
* Added release-critical Python and installer coverage on macOS.
* Added Ruff linting and formatting checks.
* Added ShellCheck and Bash syntax validation for the installer.
* Added CodeQL static analysis.
* Added full-history secret scanning with TruffleHog.
* Added installer smoke tests for Ubuntu and macOS.
* Added tag-time consistency checks ensuring release tags match the executable version and changelog entry.

### Known limitations

* Output quality depends on the selected local model, its quantization, context capacity, and the supplied repository context.
* Repository context may be truncated when it exceeds configured character or file-count limits.
* Installation and shell integration are currently designed primarily for macOS and zsh.
* The `fix-test` command executes the supplied shell command locally before sending its output to the model.
* Local-model suggestions are not automatically applied and must be reviewed, tested, and accepted by the parent agent or user.

[Unreleased]: https://github.com/tomerzipori/local-agent-toolkit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tomerzipori/local-agent-toolkit/releases/tag/v0.1.0
