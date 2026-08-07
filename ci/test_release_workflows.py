#!/usr/bin/env python3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "ci" / "generate-workflows.py"

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


def generate_workflows():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        workflow_dir = root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        (workflow_dir / "pages.yml").write_text("name: stale\n", encoding="utf-8")
        subprocess.run(
            [sys.executable, str(GENERATOR)],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return {
            path.name: path.read_text(encoding="utf-8")
            for path in workflow_dir.glob("*.yml")
        }


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
        for name, text in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertIn('      - "20*"', text)
                self.assertIn("contents: read", text)
                self.assertIn("contents: write", text)
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
                for pattern in expected:
                    self.assertIn(pattern, self.workflows[name])


if __name__ == "__main__":
    unittest.main()
