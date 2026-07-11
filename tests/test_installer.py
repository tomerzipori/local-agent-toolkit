from __future__ import annotations

import json
import os
import pty
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from tests.helpers import ROOT, LocalAgentTestCase


class InstallerTests(LocalAgentTestCase):
    def make_install_source(self, root: Path) -> Path:
        source = root / "toolkit"
        source.mkdir()
        shutil.copy2(ROOT / "install.sh", source / "install.sh")
        shutil.copytree(ROOT / "bin", source / "bin", copy_function=shutil.copy2)
        shutil.copytree(ROOT / "instructions", source / "instructions", copy_function=shutil.copy2)
        shutil.copytree(ROOT / "scripts", source / "scripts", copy_function=shutil.copy2)
        shutil.copytree(ROOT / "skills", source / "skills", copy_function=shutil.copy2)
        return source

    def run_install(
        self,
        source: Path,
        home: Path,
        *args: str,
        check: bool = True,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "HOME": str(home)}
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["bash", str(source / "install.sh"), *args],
            text=True,
            capture_output=True,
            env=env,
            check=check,
        )

    def run_install_pty(
        self,
        source: Path,
        home: Path,
        *args: str,
        user_input: str,
        check: bool = True,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "HOME": str(home), "LOCAL_AGENT_HOST": "http://127.0.0.1:9"}
        if extra_env:
            env.update(extra_env)
        master_fd, slave_fd = pty.openpty()
        try:
            process = subprocess.Popen(
                ["bash", str(source / "install.sh"), *args],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                text=False,
            )
        finally:
            os.close(slave_fd)

        os.write(master_fd, user_input.encode("utf-8"))
        output = bytearray()
        try:
            while True:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
        finally:
            os.close(master_fd)

        returncode = process.wait()
        completed = subprocess.CompletedProcess(
            args=["bash", str(source / "install.sh"), *args],
            returncode=returncode,
            stdout=output.decode("utf-8", errors="replace"),
            stderr="",
        )
        if check and returncode != 0:
            raise subprocess.CalledProcessError(
                returncode,
                completed.args,
                output=completed.stdout,
                stderr=completed.stderr,
            )
        return completed

    @staticmethod
    def managed_root(home: Path) -> Path:
        return home / ".local/share/local-agent-toolkit"

    @staticmethod
    def managed_binary(home: Path) -> Path:
        return home / ".local/share/local-agent-toolkit/bin/local-agent"

    @staticmethod
    def public_binary(home: Path) -> Path:
        return home / ".local/bin/local-agent"

    @staticmethod
    def state_file(home: Path) -> Path:
        return home / ".local/share/local-agent-toolkit/install-state.json"

    @staticmethod
    def codex_skill(home: Path) -> Path:
        return home / ".agents/skills/local-agent-toolkit"

    @staticmethod
    def claude_skill(home: Path) -> Path:
        return home / ".claude/skills/local-agent-toolkit"

    @staticmethod
    def skill_marker(skill_dir: Path) -> dict[str, object]:
        return json.loads((skill_dir / ".local-agent-toolkit.json").read_text(encoding="utf-8"))

    @staticmethod
    def read_state(home: Path) -> dict[str, object]:
        return json.loads(InstallerTests.state_file(home).read_text(encoding="utf-8"))

    @staticmethod
    def legacy_block() -> str:
        return (
            "<!-- BEGIN LOCAL-AGENT TOOLKIT -->\nlegacy snippet\n<!-- END LOCAL-AGENT TOOLKIT -->\n"
        )

    def test_skill_source_validator_and_check_environment_help(self):
        validate = subprocess.run(
            ["python3", str(ROOT / "scripts/validate_skill.py")],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("valid:", validate.stdout)

        help_output = subprocess.run(
            [
                "python3",
                str(ROOT / "skills/local-agent-toolkit/scripts/check_environment.py"),
                "--help",
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("Check local-agent skill prerequisites", help_output.stdout)

    def test_clean_binary_only_install_writes_schema_two_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            result = self.run_install(source, home, "--skills", "none")

            managed = self.managed_binary(home)
            public = self.public_binary(home)
            self.assertEqual(result.returncode, 0)
            self.assertTrue(managed.is_file())
            self.assertTrue(os.access(managed, os.X_OK))
            self.assertTrue(public.is_symlink())
            self.assertEqual(public.resolve(), managed.resolve())
            self.assertEqual(
                self.read_state(home),
                {
                    "schema_version": 2,
                    "public_binary": "~/.local/bin/local-agent",
                    "managed_binary": "~/.local/share/local-agent-toolkit/bin/local-agent",
                    "installed_skills": {"codex": None, "claude": None},
                    "legacy_instruction_migration": {
                        "codex": "not_requested",
                        "claude": "not_requested",
                    },
                },
            )

    def test_install_codex_skill_copies_expected_tree_and_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            self.run_install(source, home, "--skills", "codex")

            skill_dir = self.codex_skill(home)
            self.assertTrue((skill_dir / "SKILL.md").is_file())
            self.assertTrue((skill_dir / "agents/openai.yaml").is_file())
            self.assertTrue((skill_dir / "references/commands.md").is_file())
            check_script = skill_dir / "scripts/check_environment.py"
            self.assertTrue(check_script.is_file())
            self.assertEqual(
                self.skill_marker(skill_dir),
                {
                    "schema_version": 1,
                    "manager": "local-agent-toolkit",
                    "skill": "local-agent-toolkit",
                },
            )
            self.assertTrue(check_script.stat().st_mode & stat.S_IRUSR)
            self.assertEqual(
                self.read_state(home)["installed_skills"],
                {"codex": "~/.agents/skills/local-agent-toolkit", "claude": None},
            )

    def test_both_install_removes_matching_legacy_blocks_and_preserves_unrelated_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            codex_global = home / ".codex/AGENTS.md"
            claude_global = home / ".claude/CLAUDE.md"
            codex_global.parent.mkdir(parents=True)
            claude_global.parent.mkdir(parents=True)
            codex_global.write_text(
                "keep codex\n\n" + self.legacy_block() + "after codex\n", encoding="utf-8"
            )
            claude_global.write_text(
                "keep claude\n\n" + self.legacy_block() + "after claude\n", encoding="utf-8"
            )

            result = self.run_install(source, home, "--skills", "both")

            self.assertEqual(result.returncode, 0)
            self.assertNotIn("BEGIN LOCAL-AGENT TOOLKIT", codex_global.read_text(encoding="utf-8"))
            self.assertNotIn("BEGIN LOCAL-AGENT TOOLKIT", claude_global.read_text(encoding="utf-8"))
            self.assertIn("keep codex", codex_global.read_text(encoding="utf-8"))
            self.assertIn("after codex", codex_global.read_text(encoding="utf-8"))
            self.assertEqual(
                self.read_state(home)["legacy_instruction_migration"],
                {"codex": "removed", "claude": "removed"},
            )

    def test_skills_none_leaves_existing_skills_and_legacy_blocks_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            existing_skill = self.codex_skill(home)
            existing_skill.mkdir(parents=True)
            (existing_skill / "keep.txt").write_text("existing\n", encoding="utf-8")
            codex_global = home / ".codex/AGENTS.md"
            codex_global.parent.mkdir(parents=True)
            codex_global.write_text("before\n" + self.legacy_block(), encoding="utf-8")

            self.run_install(source, home, "--skills", "none")

            self.assertTrue((existing_skill / "keep.txt").is_file())
            self.assertIn("BEGIN LOCAL-AGENT TOOLKIT", codex_global.read_text(encoding="utf-8"))

    def test_deprecated_instructions_alias_warns_and_installs_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            result = self.run_install(source, home, "--instructions", "claude")

            self.assertEqual(result.returncode, 0)
            self.assertIn("deprecated", result.stderr)
            self.assertTrue((self.claude_skill(home) / "SKILL.md").is_file())

    def test_repeat_install_requires_confirmed_yes_and_preserves_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            config = home / ".config/local-agent/config.json"
            config.parent.mkdir(parents=True)
            config.write_text('{"model": "saved"}\n', encoding="utf-8")

            self.run_install(source, home, "--skills", "codex")
            managed = self.managed_binary(home)
            original = managed.read_text(encoding="utf-8")
            updated = original.replace('VERSION = "0.1.0"', 'VERSION = "0.1.1-dev"', 1)
            (source / "bin/local-agent").write_text(updated, encoding="utf-8")

            result = self.run_install_pty(
                source,
                home,
                "--skills",
                "codex",
                user_input="yes\n",
            )

            self.assertIn("Type yes to reinstall or no to cancel:", result.stdout)
            self.assertEqual(managed.read_text(encoding="utf-8"), updated)
            self.assertEqual(config.read_text(encoding="utf-8"), '{"model": "saved"}\n')
            self.assertTrue((self.codex_skill(home) / "SKILL.md").is_file())

    def test_repeat_install_noninteractive_leaves_install_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            self.run_install(source, home, "--skills", "none")
            managed = self.managed_binary(home)
            original = managed.read_text(encoding="utf-8")
            updated = original.replace('VERSION = "0.1.0"', 'VERSION = "0.1.1-dev"', 1)
            (source / "bin/local-agent").write_text(updated, encoding="utf-8")

            result = self.run_install(source, home, "--skills", "none")

            self.assertEqual(result.returncode, 0)
            self.assertIn("reinstall confirmation requires an interactive terminal", result.stdout)
            self.assertEqual(managed.read_text(encoding="utf-8"), original)

    def test_invalid_selector_combinations_exit_with_status_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            cases = [
                ("--skills", "codex", "--instructions", "claude"),
                ("--skills", "codex", "--skills", "claude"),
                ("--instructions", "codex", "--instructions", "claude"),
                ("--uninstall", "--skills", "none"),
            ]
            for args in cases:
                with self.subTest(args=args):
                    result = self.run_install(source, home, *args, check=False)
                    self.assertEqual(result.returncode, 2)

    def test_invalid_skill_source_prevents_every_target_from_changing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            os.unlink(source / "skills/local-agent-toolkit/references/model-selection.md")

            result = self.run_install(source, home, "--skills", "both", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.codex_skill(home).exists())
            self.assertFalse(self.claude_skill(home).exists())
            self.assertFalse(self.managed_root(home).exists())

    def test_source_update_replaces_content_and_removes_stale_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            self.run_install(source, home, "--skills", "codex")
            installed = self.codex_skill(home)
            stale = installed / "stale.txt"
            stale.write_text("stale\n", encoding="utf-8")
            skill_md = source / "skills/local-agent-toolkit/SKILL.md"
            skill_md.write_text(
                skill_md.read_text(encoding="utf-8").replace("first pass", "initial pass"),
                encoding="utf-8",
            )

            self.run_install_pty(source, home, "--skills", "codex", user_input="yes\n")

            self.assertFalse(stale.exists())
            self.assertIn("initial pass", (installed / "SKILL.md").read_text(encoding="utf-8"))

    def test_unmanaged_malformed_and_symlink_collisions_fail_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            cases = []

            unmanaged = self.codex_skill(home)
            unmanaged.mkdir(parents=True)
            (unmanaged / "foreign.txt").write_text("foreign\n", encoding="utf-8")
            cases.append(("unmanaged", home))

            malformed_home = root / "malformed-home"
            malformed = self.codex_skill(malformed_home)
            malformed.mkdir(parents=True)
            (malformed / ".local-agent-toolkit.json").write_text("{bad json\n", encoding="utf-8")
            cases.append(("malformed", malformed_home))

            symlink_home = root / "symlink-home"
            symlink_target = root / "symlink-target"
            symlink_target.mkdir()
            self.codex_skill(symlink_home).parent.mkdir(parents=True)
            self.codex_skill(symlink_home).symlink_to(symlink_target)
            cases.append(("symlink", symlink_home))

            for label, case_home in cases:
                with self.subTest(label=label):
                    result = self.run_install(source, case_home, "--skills", "codex", check=False)
                    self.assertNotEqual(result.returncode, 0)

    def test_both_with_codex_failure_leaves_claude_installable_and_exit_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            codex_collision = self.codex_skill(home)
            codex_collision.mkdir(parents=True)
            (codex_collision / "foreign.txt").write_text("foreign\n", encoding="utf-8")
            codex_global = home / ".codex/AGENTS.md"
            claude_global = home / ".claude/CLAUDE.md"
            codex_global.parent.mkdir(parents=True)
            claude_global.parent.mkdir(parents=True)
            codex_global.write_text("before\n" + self.legacy_block(), encoding="utf-8")
            claude_global.write_text("before\n" + self.legacy_block(), encoding="utf-8")

            result = self.run_install(source, home, "--skills", "both", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((self.claude_skill(home) / "SKILL.md").is_file())
            self.assertIn("BEGIN LOCAL-AGENT TOOLKIT", codex_global.read_text(encoding="utf-8"))
            self.assertNotIn("BEGIN LOCAL-AGENT TOOLKIT", claude_global.read_text(encoding="utf-8"))
            self.assertEqual(
                self.read_state(home)["legacy_instruction_migration"],
                {"codex": "failed", "claude": "removed"},
            )

    def test_both_with_claude_failure_leaves_codex_installable_and_exit_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            claude_collision = self.claude_skill(home)
            claude_collision.mkdir(parents=True)
            (claude_collision / "foreign.txt").write_text("foreign\n", encoding="utf-8")

            result = self.run_install(source, home, "--skills", "both", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((self.codex_skill(home) / "SKILL.md").is_file())
            self.assertFalse((self.claude_skill(home) / "SKILL.md").exists())

    def test_staged_promotion_rollback_restores_existing_managed_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            self.run_install(source, home, "--skills", "codex")
            original = (self.codex_skill(home) / "SKILL.md").read_text(encoding="utf-8")
            updated = original.replace("repository exploration", "repo exploration", 1)
            (source / "skills/local-agent-toolkit/SKILL.md").write_text(updated, encoding="utf-8")

            result = self.run_install_pty(
                source,
                home,
                "--skills",
                "codex",
                user_input="yes\n",
                check=False,
                extra_env={"LOCAL_AGENT_TOOLKIT_TEST_PROMOTE_FAILURE": "1"},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(
                (self.codex_skill(home) / "SKILL.md").read_text(encoding="utf-8"), original
            )

    def test_dry_run_install_and_uninstall_are_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"

            install_result = self.run_install(source, home, "--dry-run", "--skills", "both")
            self.assertEqual(install_result.returncode, 0)
            self.assertFalse(self.managed_root(home).exists())
            self.assertFalse(self.codex_skill(home).exists())
            self.assertFalse(self.claude_skill(home).exists())

            uninstall_result = self.run_install(source, home, "--dry-run", "--uninstall")
            self.assertEqual(uninstall_result.returncode, 0)
            self.assertFalse(self.managed_root(home).exists())

    def test_uninstall_removes_only_owned_skills_and_preserves_config_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            config = home / ".config/local-agent/config.json"
            config.parent.mkdir(parents=True)
            config.write_text('{"model":"saved"}\n', encoding="utf-8")
            foreign = self.claude_skill(home)
            foreign.mkdir(parents=True)
            (foreign / "foreign.txt").write_text("keep\n", encoding="utf-8")

            self.run_install(source, home, "--skills", "codex")
            result = self.run_install(source, home, "--uninstall")

            self.assertEqual(result.returncode, 0)
            self.assertFalse(self.codex_skill(home).exists())
            self.assertTrue((foreign / "foreign.txt").is_file())
            self.assertEqual(config.read_text(encoding="utf-8"), '{"model":"saved"}\n')

    def test_uninstall_with_purge_config_removes_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            config = home / ".config/local-agent/config.json"
            config.parent.mkdir(parents=True)
            config.write_text('{"model":"saved"}\n', encoding="utf-8")

            self.run_install(source, home, "--skills", "none")
            self.run_install(source, home, "--uninstall", "--purge-config")

            self.assertFalse(config.exists())

    def test_missing_or_schema_one_state_is_reconstructed_from_owned_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            owned = self.codex_skill(home)
            owned.mkdir(parents=True)
            shutil.copytree(
                source / "skills/local-agent-toolkit",
                owned,
                dirs_exist_ok=True,
                copy_function=shutil.copy2,
            )
            (owned / ".local-agent-toolkit.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "manager": "local-agent-toolkit",
                        "skill": "local-agent-toolkit",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            self.state_file(home).parent.mkdir(parents=True, exist_ok=True)
            self.state_file(home).write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "public_binary": "~/.local/bin/local-agent",
                        "managed_binary": "~/.local/share/local-agent-toolkit/bin/local-agent",
                        "installed_instructions": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            self.run_install(source, home, "--skills", "none")

            self.assertEqual(
                self.read_state(home)["installed_skills"],
                {"codex": "~/.agents/skills/local-agent-toolkit", "claude": None},
            )

    def test_legacy_block_removal_preserves_crlf_and_final_newline_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_install_source(root)
            home = root / "home"
            target = home / ".codex/AGENTS.md"
            target.parent.mkdir(parents=True)
            target.write_bytes(
                b"keep\r\n"
                b"<!-- BEGIN LOCAL-AGENT TOOLKIT -->\r\n"
                b"legacy\r\n"
                b"<!-- END LOCAL-AGENT TOOLKIT -->\r\n"
                b"after"
            )

            self.run_install(source, home, "--skills", "codex")

            self.assertEqual(target.read_bytes(), b"keep\r\nafter")
