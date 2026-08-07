#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "ci" / "generate-workflows.py"
CREATE_RELEASE = ROOT / "ci" / "create-release.sh"

EXPECTED_WORKFLOWS = {
    "gen_centos9_tag.yml",
    "gen_debian12_tag.yml",
    "gen_fedora41_tag.yml",
    "gen_macos_tag.yml",
    "gen_ubuntu22.04_tag.yml",
    "gen_ubuntu24.04_tag.yml",
    "gen_ubuntu26.04_tag.yml",
    "gen_windows_tag.yml",
}


def workflow_entries(workflow_dir):
    return {path.name: path.read_bytes() for path in workflow_dir.iterdir()}


def generate_workflows():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        workflow_dir = root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        (workflow_dir / "pages.yml").write_bytes(b"name: stale\r\n")
        (workflow_dir / "stale.yaml").write_bytes(b"name: stale\n")
        subprocess.run(
            [sys.executable, str(GENERATOR)],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return workflow_entries(workflow_dir)


class GeneratedWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = generate_workflows()

    def test_generates_only_expected_tag_workflows(self):
        self.assertEqual(set(self.workflows), EXPECTED_WORKFLOWS)

    def test_release_contract(self):
        forbidden = (
            "pull_request:",
            "schedule:",
            "branches:",
            "github.repository ==",
            "pages: write",
            "id-token: write",
            "secrets.",
            "FURY_TOKEN",
            "GH_PAT",
            "MACOS_CERT",
            "MACOS_APPLEID",
            "gemfury",
            "homebrew",
            "winget",
            "flathub",
        )
        for name, content in self.workflows.items():
            with self.subTest(workflow=name):
                text = content.decode("utf-8")
                header, jobs = text.split("\njobs:\n", 1)
                build, upload = jobs.split("\n  upload:\n", 1)
                self.assertIn('      - "20*"', text)
                self.assertTrue(
                    header.endswith("\npermissions:\n  contents: read\n"), header
                )
                self.assertEqual(header.count("\nconcurrency:\n"), 1)
                self.assertIn(
                    "\nconcurrency:\n"
                    "  group: ${{ github.workflow }}-${{ github.ref }}\n"
                    "  cancel-in-progress: false\n",
                    header,
                )
                self.assertNotIn("\n    permissions:", build)
                self.assertEqual(upload.count("\n    permissions:\n"), 1)
                self.assertIn(
                    "\n    permissions:\n      contents: write\n", upload
                )
                self.assertIn("GITHUB_REF_NAME", text)
                self.assertIn("gh release upload --clobber", text)
                self.assertIn("*.sha256", text)
                for value in forbidden:
                    self.assertNotIn(value, text)

    def test_retains_current_artifact_patterns(self):
        patterns = {
            "gen_centos9_tag.yml": ("wezterm-*.rpm",),
            "gen_debian12_tag.yml": ("wezterm-*.deb", "wezterm-*.xz"),
            "gen_fedora41_tag.yml": ("wezterm-*.rpm",),
            "gen_macos_tag.yml": ("WezTerm-*.zip",),
            "gen_ubuntu22.04_tag.yml": ("wezterm-*.deb", "wezterm-*.xz"),
            "gen_ubuntu24.04_tag.yml": ("wezterm-*.deb", "wezterm-*.xz"),
            "gen_ubuntu26.04_tag.yml": (
                "wezterm-*.deb",
                "wezterm-*.xz",
                "*src.tar.gz",
                "*.AppImage",
            ),
            "gen_windows_tag.yml": ("WezTerm-*.zip", "WezTerm-*.exe"),
        }
        for name, expected in patterns.items():
            with self.subTest(workflow=name):
                text = self.workflows[name].decode("utf-8")
                for pattern in expected:
                    self.assertIn(pattern, text)


class CreateReleaseTests(unittest.TestCase):
    def run_script(self, view_status, *args, view_output=""):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            log = temp / "gh.log"
            gh = temp / "gh"
            gh.write_text(
                """#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1:3] == ["release", "view"]:
    sys.stdout.write(os.environ["GH_VIEW_OUTPUT"])
    raise SystemExit(int(os.environ["GH_VIEW_STATUS"]))
""",
                encoding="utf-8",
            )
            gh.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{temp}:{env['PATH']}",
                    "GH_LOG": str(log),
                    "GH_VIEW_OUTPUT": view_output,
                    "GH_VIEW_STATUS": str(view_status),
                }
            )
            result = subprocess.run(
                ["bash", str(CREATE_RELEASE), *args],
                env=env,
                capture_output=True,
                text=True,
            )
            calls = []
            if log.exists():
                calls = [json.loads(line) for line in log.read_text().splitlines()]
            return result, calls

    def test_reuses_existing_draft_release(self):
        result, calls = self.run_script(
            0, "20260807-test", view_output="true\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls,
            [
                [
                    "release",
                    "view",
                    "20260807-test",
                    "--json",
                    "isDraft",
                    "--jq",
                    ".isDraft",
                ]
            ],
        )

    def test_rejects_existing_published_release(self):
        result, calls = self.run_script(
            0, "20260807-test", view_output="false\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already published", result.stderr)
        self.assertEqual(
            calls,
            [
                [
                    "release",
                    "view",
                    "20260807-test",
                    "--json",
                    "isDraft",
                    "--jq",
                    ".isDraft",
                ]
            ],
        )

    def test_creates_empty_draft_for_missing_release(self):
        result, calls = self.run_script(1, "20260807-test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls,
            [
                [
                    "release",
                    "view",
                    "20260807-test",
                    "--json",
                    "isDraft",
                    "--jq",
                    ".isDraft",
                ],
                [
                    "release",
                    "create",
                    "20260807-test",
                    "--draft",
                    "--title",
                    "20260807-test",
                    "--notes",
                    "",
                ],
            ],
        )

    def test_rejects_a_missing_tag(self):
        result, calls = self.run_script(0)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])


class PackagingPolicyTests(unittest.TestCase):
    def test_macos_uses_only_adhoc_signing(self):
        text = (ROOT / "ci" / "deploy.sh").read_text(encoding="utf-8")
        self.assertRegex(text, r"codesign\s+--force\s+--deep\s+--sign\s+-")
        self.assertIn("--entitlements ci/macos-entitlement.plist", text)
        for value in (
            "MACOS_CERT",
            "MACOS_TEAM_ID",
            "MACOS_APPLEID",
            "MACOS_APP_PW",
            "notarytool",
            "build.keychain",
            "wezterm-homebrew-macos",
        ):
            self.assertNotIn(value, text)

    def test_appimage_does_not_generate_linuxbrew_formula(self):
        text = (ROOT / "ci" / "appimage.sh").read_text(encoding="utf-8")
        self.assertNotIn("wezterm-linuxbrew", text)

    def test_appimage_metadata_uses_workflow_repository(self):
        appimage = (ROOT / "ci" / "appimage.sh").read_text(encoding="utf-8")
        pkgbuild = (ROOT / "ci" / "PKGBUILD.template").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            ': "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"', appimage
        )
        self.assertIn(
            'IFS=/ read -r repository_owner repository_name repository_extra '
            '<<< "$GITHUB_REPOSITORY"',
            appimage,
        )
        self.assertIn(
            "gh-releases-zsync|$repository_owner|$repository_name|latest|",
            appimage,
        )
        self.assertEqual(pkgbuild.count("https://github.com/@GITHUB_REPOSITORY@"), 2)
        self.assertIn('s|@GITHUB_REPOSITORY@|$GITHUB_REPOSITORY|g', appimage)

        for value in ("wez|wezterm", "wez/wezterm", "wezterm/wezterm"):
            with self.subTest(value=value):
                self.assertNotIn(value, appimage)
                self.assertNotIn(value, pkgbuild)

    def test_external_publisher_helpers_are_removed(self):
        removed = (
            "ci/make-flathub-pr.sh",
            "ci/make-winget-pr.sh",
            "ci/wezterm-homebrew-macos.rb.template",
            "ci/wezterm-linuxbrew.rb.template",
        )
        for path in removed:
            with self.subTest(path=path):
                self.assertFalse((ROOT / path).exists())


class CheckedInWorkflowTests(unittest.TestCase):
    def test_checked_in_workflows_match_generator(self):
        workflow_dir = ROOT / ".github" / "workflows"
        self.assertEqual(workflow_entries(workflow_dir), generate_workflows())


if __name__ == "__main__":
    unittest.main()
