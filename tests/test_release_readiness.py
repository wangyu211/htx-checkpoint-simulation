from __future__ import annotations

import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.clean_clone_audit import (
    create_fresh_clone,
    forbidden_history_paths,
)
from tools.precheck import (
    _absolute_windows_path_hits,
    check_absolute_windows_paths,
    check_generator_determinism,
    check_portable_tracked_names,
    check_readme_command_contract,
    check_requirements_contract,
    tracked_files,
)


class PortablePathTests(unittest.TestCase):
    def test_rejects_case_reserved_and_unicode_collisions(self) -> None:
        errors = check_portable_tracked_names(
            {
                "docs/A.txt",
                "docs/a.TXT",
                "docs/con.md",
                "docs/\u00e9.md",
                "docs/e\u0301.md",
            }
        )
        joined = "\n".join(errors)
        self.assertIn("case-insensitive", joined)
        self.assertIn("Windows-reserved", joined)
        self.assertIn("Unicode normalization", joined)

    def test_detects_drive_file_uri_and_unc_but_not_urls_or_relative_paths(
        self,
    ) -> None:
        drive = "C:" + "\\Users\\owner\\private.csv"
        file_uri = "file:" + "///D:/private/output.csv"
        unc = "\\" * 2 + "server\\share\\private.csv"
        data = (
            f"{drive}\n{file_uri}\n{unc}\n"
            "https://example.test/path\n"
            ".\\relative\\path.csv\n"
            "$PWD\\relative\\path.csv\n"
        ).encode("utf-8")
        hits = "\n".join(_absolute_windows_path_hits(data))
        self.assertIn(drive, hits)
        self.assertIn(file_uri, hits)
        self.assertIn(unc, hits)
        self.assertNotIn("https://", hits)
        self.assertNotIn(".\\relative", hits)

    def test_scans_office_archive_members(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            deck = root / "slides" / "test.pptx"
            deck.parent.mkdir(parents=True)
            private_path = "E:" + "\\private\\source.mov"
            with zipfile.ZipFile(deck, "w") as archive:
                archive.writestr(
                    "ppt/slides/slide1.xml",
                    f"<text>{private_path}</text>",
                )
            errors, scanned = check_absolute_windows_paths(
                {"slides/test.pptx"},
                root=root,
            )
        self.assertEqual(scanned, 1)
        self.assertTrue(
            any("ppt/slides/slide1.xml" in error for error in errors),
            errors,
        )


class DocumentedCommandTests(unittest.TestCase):
    def test_current_readme_commands_resolve_to_tracked_sources(self) -> None:
        tracked = tracked_files()
        errors, checked = check_readme_command_contract(tracked)
        self.assertEqual(errors, [])
        self.assertGreaterEqual(checked, 15)

    def test_current_requirement_graph_is_exact_and_separates_opencv(
        self,
    ) -> None:
        errors, pins = check_requirements_contract(tracked_files())
        self.assertEqual(errors, [])
        self.assertGreaterEqual(pins, 10)


class GeneratorDeterminismTests(unittest.TestCase):
    GENERATOR = "scripts/generate_operational_anylogic.py"

    def _fixture(
        self,
        root: Path,
        *,
        generated: str,
        generator_body: str,
    ) -> set[str]:
        generator = root / self.GENERATOR
        generator.parent.mkdir(parents=True)
        generator.write_text(generator_body, encoding="utf-8")
        (root / "generated.txt").write_text(generated, encoding="utf-8")
        return {self.GENERATOR, "generated.txt"}

    def test_synchronized_generator_is_byte_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            tracked = self._fixture(
                root,
                generated="stable\n",
                generator_body=(
                    "from pathlib import Path\n"
                    "Path('generated.txt').write_text("
                    "'stable\\n', encoding='utf-8')\n"
                ),
            )
            errors, details = check_generator_determinism(
                tracked,
                root=root,
                generator_relative=self.GENERATOR,
            )
        self.assertEqual(errors, [])
        self.assertIs(details["source_synchronized"], True)
        self.assertIs(details["second_run_byte_identical"], True)

    def test_stale_generated_source_fails_first_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            tracked = self._fixture(
                root,
                generated="stale\n",
                generator_body=(
                    "from pathlib import Path\n"
                    "Path('generated.txt').write_text("
                    "'stable\\n', encoding='utf-8')\n"
                ),
            )
            errors, details = check_generator_determinism(
                tracked,
                root=root,
                generator_relative=self.GENERATOR,
            )
        self.assertTrue(any("not synchronized" in error for error in errors))
        self.assertIs(details["source_synchronized"], False)
        self.assertIs(details["second_run_byte_identical"], True)

    def test_nondeterministic_generator_fails_second_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            tracked = self._fixture(
                root,
                generated="initial\n",
                generator_body=(
                    "from pathlib import Path\n"
                    "from uuid import uuid4\n"
                    "Path('generated.txt').write_text("
                    "str(uuid4()), encoding='utf-8')\n"
                ),
            )
            errors, details = check_generator_determinism(
                tracked,
                root=root,
                generator_relative=self.GENERATOR,
            )
        self.assertTrue(any("not byte-idempotent" in error for error in errors))
        self.assertIs(details["second_run_byte_identical"], False)


class CleanCloneTests(unittest.TestCase):
    def _run_git(self, root: Path, *args: str) -> None:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fresh_clone_does_not_copy_ignored_worktree_assets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            source = base / "source"
            destination = base / "clone"
            source.mkdir()
            self._run_git(source, "init", "--quiet")
            (source / ".gitignore").write_text("_work/\n", encoding="utf-8")
            (source / "README.md").write_text("public\n", encoding="utf-8")
            private = source / "_work" / "private.mov"
            private.parent.mkdir()
            private.write_bytes(b"restricted")
            self._run_git(source, "add", ".gitignore", "README.md")
            self._run_git(
                source,
                "-c",
                "user.name=Release Test",
                "-c",
                "user.email=release@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "fixture",
            )
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=source,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout.strip()
            self.assertEqual(forbidden_history_paths(source), [])
            create_fresh_clone(source, destination, commit)
            self.assertTrue((destination / "README.md").is_file())
            self.assertFalse((destination / "_work").exists())

    def test_history_audit_detects_a_removed_restricted_video(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "source"
            source.mkdir()
            self._run_git(source, "init", "--quiet")
            video = source / "data" / "raw" / "restricted.mov"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"restricted")
            self._run_git(source, "add", "data/raw/restricted.mov")
            self._run_git(
                source,
                "-c",
                "user.name=Release Test",
                "-c",
                "user.email=release@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "restricted fixture",
            )
            video.unlink()
            self._run_git(source, "add", "-u")
            self._run_git(
                source,
                "-c",
                "user.name=Release Test",
                "-c",
                "user.email=release@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "remove fixture",
            )
            self.assertEqual(
                forbidden_history_paths(source),
                ["data/raw/restricted.mov"],
            )


if __name__ == "__main__":
    unittest.main()
