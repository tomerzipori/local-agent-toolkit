from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from tests.helpers import ROOT, LocalAgentTestCase


class InstallerTests(LocalAgentTestCase):
    def make_install_source(self, root: Path) -> Path:
        source = root / "toolkit"
        (source / "bin").mkdir(parents=True)
        (source / "instructions").mkdir(parents=True)
        shutil.copy2(ROOT / "install.sh", source / "install.sh")
        shutil.copy2(ROOT / "bin/local-agent", source / "bin/local-agent")
        shutil.copy2(
            ROOT / "instructions/AGENTS-snippet.md", source / "instructions/AGENTS-snippet.md"
        )
        shutil.copy2(
            ROOT / "instructions/CLAUDE-snippet.md", source / "instructions/CLAUDE-snippet.md"
        )
        return source

    def run_install(
        self, source: Path, home: Path, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "HOME": str(home)}
        return subprocess.run(
            ["bash", str(source / "install.sh"), *args],
            text=True,
            capture_output=True,
            env=env,
            check=check,
        )

    def test_clean_install_creates_managed_binary_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            result = self.run_install(source, home)

            managed = home / ".local/share/local-agent-toolkit/bin/local-agent"
            public = home / ".local/bin/local-agent"
            state = home / ".local/share/local-agent-toolkit/install-state.json"
            self.assertEqual(result.returncode, 0)
            self.assertTrue(managed.is_file())
            self.assertTrue(os.access(managed, os.X_OK))
            self.assertTrue(public.is_symlink())
            self.assertEqual(public.resolve(), managed.resolve())
            self.assertEqual(
                json.loads(state.read_text(encoding="utf-8")),
                {
                    "schema_version": 1,
                    "public_binary": "~/.local/bin/local-agent",
                    "managed_binary": "~/.local/share/local-agent-toolkit/bin/local-agent",
                    "installed_instructions": [],
                },
            )

    def test_repeat_install_updates_owned_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            self.run_install(source, home)
            managed = home / ".local/share/local-agent-toolkit/bin/local-agent"
            original = managed.read_text(encoding="utf-8")

            updated = original.replace('VERSION = "0.1.0"', 'VERSION = "0.1.1-dev"', 1)
            (source / "bin/local-agent").write_text(updated, encoding="utf-8")
            self.run_install(source, home)

            self.assertEqual(managed.read_text(encoding="utf-8"), updated)
            self.assertEqual((home / ".local/bin/local-agent").resolve(), managed.resolve())

    def test_install_refuses_existing_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            public = home / ".local/bin/local-agent"
            public.parent.mkdir(parents=True)
            public.write_text("foreign command\n", encoding="utf-8")

            result = self.run_install(source, home, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to replace existing path:", result.stderr)
            self.assertEqual(public.read_text(encoding="utf-8"), "foreign command\n")

    def test_install_refuses_foreign_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            public = home / ".local/bin/local-agent"
            public.parent.mkdir(parents=True)
            public.symlink_to(home / "other-tool")

            result = self.run_install(source, home, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to replace existing path:", result.stderr)
            self.assertTrue(public.is_symlink())
            self.assertEqual(public.readlink(), home / "other-tool")

    def test_install_refuses_existing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            public = home / ".local/bin/local-agent"
            public.mkdir(parents=True)

            result = self.run_install(source, home, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to replace existing path:", result.stderr)
            self.assertTrue(public.is_dir())

    def test_uninstall_removes_owned_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            self.run_install(source, home)
            self.run_install(source, home, "--uninstall")

            self.assertFalse((home / ".local/bin/local-agent").exists())
            self.assertFalse((home / ".local/share/local-agent-toolkit").exists())

    def test_uninstall_preserves_foreign_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            self.run_install(source, home)
            public = home / ".local/bin/local-agent"
            foreign_target = home / "foreign-local-agent"
            foreign_target.write_text("#!/bin/sh\n", encoding="utf-8")
            public.unlink()
            public.symlink_to(foreign_target)

            result = self.run_install(source, home, "--uninstall")
            self.assertIn("public command is no longer owned", result.stdout)
            self.assertTrue(public.is_symlink())
            self.assertEqual(public.resolve(), foreign_target.resolve())
            self.assertFalse((home / ".local/share/local-agent-toolkit").exists())

    def test_uninstall_removes_managed_path_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            self.run_install(source, home)
            zshrc = home / ".zshrc"
            self.assertIn("# BEGIN LOCAL-AGENT TOOLKIT PATH", zshrc.read_text(encoding="utf-8"))

            self.run_install(source, home, "--uninstall")
            self.assertNotIn("# BEGIN LOCAL-AGENT TOOLKIT PATH", zshrc.read_text(encoding="utf-8"))
            self.assertNotIn(
                'export PATH="$HOME/.local/bin:$PATH"', zshrc.read_text(encoding="utf-8")
            )

    def test_uninstall_preserves_unrelated_zshrc_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            zshrc = home / ".zshrc"
            zshrc.parent.mkdir(parents=True)
            zshrc.write_text('# keep me\nexport PATH="$HOME/bin:$PATH"\n', encoding="utf-8")

            self.run_install(source, home)
            self.run_install(source, home, "--uninstall")

            self.assertEqual(
                zshrc.read_text(encoding="utf-8"), '# keep me\nexport PATH="$HOME/bin:$PATH"\n'
            )

    def test_uninstall_preserves_config_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            config = home / ".config/local-agent/config.json"
            config.parent.mkdir(parents=True)
            config.write_text('{"model": "saved"}\n', encoding="utf-8")

            self.run_install(source, home)
            self.run_install(source, home, "--uninstall")

            self.assertEqual(config.read_text(encoding="utf-8"), '{"model": "saved"}\n')

    def test_uninstall_purge_config_removes_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            config = home / ".config/local-agent/config.json"
            config.parent.mkdir(parents=True)
            config.write_text('{"model": "saved"}\n', encoding="utf-8")

            self.run_install(source, home)
            self.run_install(source, home, "--uninstall", "--purge-config")

            self.assertFalse((home / ".config/local-agent").exists())

    def test_dry_run_makes_no_filesystem_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            result = self.run_install(source, home, "--dry-run", "--instructions", "both")

            self.assertEqual(result.returncode, 0)
            self.assertIn("Would create symlink", result.stdout)
            self.assertFalse((home / ".local").exists())
            self.assertFalse((home / ".zshrc").exists())
            self.assertFalse((home / ".codex").exists())
            self.assertFalse((home / ".claude").exists())

    def test_failed_upgrade_leaves_previous_binary_working(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            self.run_install(source, home)
            managed = home / ".local/share/local-agent-toolkit/bin/local-agent"
            public = home / ".local/bin/local-agent"
            previous = managed.read_text(encoding="utf-8")
            managed_dir = managed.parent
            managed_dir.chmod(0o500)
            try:
                result = self.run_install(source, home, check=False)
            finally:
                managed_dir.chmod(0o700)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(managed.read_text(encoding="utf-8"), previous)
            help_result = subprocess.run(
                [str(public), "--help"], text=True, capture_output=True, check=True
            )
            self.assertIn("usage:", help_result.stdout.lower())

    def test_instruction_install_remains_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            (home / ".codex").mkdir(parents=True)
            (home / ".claude").mkdir(parents=True)
            (home / ".codex/AGENTS.md").write_text(
                "Keep this Codex instruction.\n", encoding="utf-8"
            )
            (home / ".claude/CLAUDE.md").write_text(
                "Keep this Claude instruction.\n", encoding="utf-8"
            )

            self.run_install(source, home, "--instructions", "both")
            self.run_install(source, home, "--instructions", "both")

            codex = (home / ".codex/AGENTS.md").read_text(encoding="utf-8")
            claude = (home / ".claude/CLAUDE.md").read_text(encoding="utf-8")
            self.assertEqual(codex.count("<!-- BEGIN LOCAL-AGENT TOOLKIT -->"), 1)
            self.assertEqual(claude.count("<!-- BEGIN LOCAL-AGENT TOOLKIT -->"), 1)
            self.assertIn("Keep this Codex instruction.", codex)
            self.assertIn("Keep this Claude instruction.", claude)

    def test_purge_config_requires_uninstall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            result = self.run_install(source, home, "--purge-config", check=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn("--purge-config requires --uninstall", result.stderr)

    def test_existing_user_path_line_is_left_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            zshrc = home / ".zshrc"
            zshrc.parent.mkdir(parents=True)
            zshrc.write_text('export PATH="$HOME/.local/bin:$PATH"\n', encoding="utf-8")

            self.run_install(source, home)

            self.assertEqual(
                zshrc.read_text(encoding="utf-8"), 'export PATH="$HOME/.local/bin:$PATH"\n'
            )

    def test_installer_is_repeatable_and_uninstall_is_idempotent(self):
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "HOME": home}
            install = ROOT / "install.sh"
            first = subprocess.run(
                ["bash", str(install)], env=env, text=True, capture_output=True, check=True
            )
            second = subprocess.run(
                ["bash", str(install)], env=env, text=True, capture_output=True, check=True
            )
            target = Path(home) / ".local/bin/local-agent"
            self.assertTrue(target.is_file())
            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 0)
            zshrc = (Path(home) / ".zshrc").read_text(encoding="utf-8")
            self.assertEqual(zshrc.count('export PATH="$HOME/.local/bin:$PATH"'), 1)
            self.assertFalse((Path(home) / ".codex/AGENTS.md").exists())
            self.assertFalse((Path(home) / ".claude/CLAUDE.md").exists())
            subprocess.run(
                ["bash", str(install), "--uninstall"], env=env, check=True, capture_output=True
            )
            subprocess.run(
                ["bash", str(install), "--uninstall"], env=env, check=True, capture_output=True
            )
            self.assertFalse(target.exists())

    def test_installer_instruction_modes_repeat_and_uninstall(self):
        install = ROOT / "install.sh"
        for mode in ("codex", "claude", "both", "none"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as home:
                home_path = Path(home)
                env = {**os.environ, "HOME": home}
                (home_path / ".codex").mkdir()
                (home_path / ".claude").mkdir()
                (home_path / ".codex/AGENTS.md").write_text(
                    "Keep this Codex instruction.\n", encoding="utf-8"
                )
                (home_path / ".claude/CLAUDE.md").write_text(
                    "Keep this Claude instruction.\n", encoding="utf-8"
                )
                config = home_path / ".config/local-agent/config.json"
                config.parent.mkdir(parents=True)
                config.write_text('{"model": "saved"}\n', encoding="utf-8")

                subprocess.run(
                    ["bash", str(install), "--instructions", mode],
                    env=env,
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["bash", str(install), "--instructions", mode],
                    env=env,
                    check=True,
                    capture_output=True,
                )

                codex = (home_path / ".codex/AGENTS.md").read_text(encoding="utf-8")
                claude = (home_path / ".claude/CLAUDE.md").read_text(encoding="utf-8")
                self.assertEqual(
                    codex.count("<!-- BEGIN LOCAL-AGENT TOOLKIT -->"),
                    int(mode in {"codex", "both"}),
                )
                self.assertEqual(
                    claude.count("<!-- BEGIN LOCAL-AGENT TOOLKIT -->"),
                    int(mode in {"claude", "both"}),
                )
                self.assertIn("Keep this Codex instruction.", codex)
                self.assertIn("Keep this Claude instruction.", claude)

                subprocess.run(
                    ["bash", str(install), "--uninstall"], env=env, check=True, capture_output=True
                )
                subprocess.run(
                    ["bash", str(install), "--uninstall"], env=env, check=True, capture_output=True
                )
                self.assertFalse((home_path / ".local/bin/local-agent").exists())
                self.assertNotIn(
                    "<!-- BEGIN LOCAL-AGENT TOOLKIT -->",
                    (home_path / ".codex/AGENTS.md").read_text(encoding="utf-8"),
                )
                self.assertNotIn(
                    "<!-- BEGIN LOCAL-AGENT TOOLKIT -->",
                    (home_path / ".claude/CLAUDE.md").read_text(encoding="utf-8"),
                )
                self.assertEqual(config.read_text(encoding="utf-8"), '{"model": "saved"}\n')
