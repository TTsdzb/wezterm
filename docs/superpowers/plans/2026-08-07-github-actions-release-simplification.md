# GitHub Actions Release Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce GitHub Actions to eight tag-triggered platform builds that test and attach the existing artifact set to a draft Release in this fork without release secrets or external publication.

**Architecture:** Keep `ci/generate-workflows.py` as the single workflow source, but remove every mode except tagged releases. Each generated platform workflow builds and tests on its native target, transports packages through an Actions artifact, and independently uploads them to the same draft Release using the automatic GitHub token.

**Tech Stack:** Python 3 standard library and PyYAML when available, GitHub Actions YAML, Bash, GitHub CLI, Rust/Cargo, platform-native package tools.

## Global Constraints

- Trigger builds only for pushed tags matching `20*`.
- Retain CentOS 9, Fedora 41, Debian 12, Ubuntu 22.04, Ubuntu 24.04, Ubuntu 26.04, Windows, and macOS.
- Retain every current package attachment, source archive, and SHA256 file.
- Create or reuse a draft Release named after `GITHUB_REF_NAME`; never publish it automatically.
- Use no configured repository secret or personal access token; release commands use `${{ github.token }}`.
- Set the workflow default to `contents: read` for build jobs.
- Grant only `contents: write` to upload jobs.
- Do not publish to Gemfury, Homebrew/Linuxbrew, Winget, Flathub, Pages, or another repository.
- macOS uses the existing entitlements with ad-hoc signing only and performs no Developer ID signing or notarization.
- Do not create Git commits unless the user explicitly requests them; this repository rule overrides the plan skill's default commit checkpoints.

---

## File Structure

- `ci/generate-workflows.py`: defines the eight targets, tag-only build/upload jobs, artifact globs, token use, and generated YAML.
- `ci/test_release_workflows.py`: regression tests for generated workflow count, triggers, permissions, forbidden publication paths, artifact coverage, draft creation, packaging policy, and checked-in generated files.
- `ci/create-release.sh`: idempotently creates or reuses the draft Release for the supplied tag.
- `ci/deploy.sh`: retains platform packaging and replaces Apple release signing/notarization with ad-hoc signing.
- `ci/appimage.sh`: retains AppImage and PKGBUILD generation but stops generating an unused Linuxbrew formula.
- `.github/workflows/gen_*_tag.yml`: the eight generated and checked-in workflows; no other workflow files remain.
- `ci/make-flathub-pr.sh`, `ci/make-winget-pr.sh`: deleted because their external PR paths are removed.
- `ci/wezterm-homebrew-macos.rb.template`, `ci/wezterm-linuxbrew.rb.template`: deleted because no retained package step consumes them.

### Task 1: Make the Workflow Generator Tag-Only

**Files:**
- Create: `ci/test_release_workflows.py`
- Modify: `ci/generate-workflows.py:1-1170`

**Interfaces:**
- Consumes: Existing `Target.tag()`, `Target.asset_patterns()`, `Step` renderers, and the eight entries in `TARGETS`.
- Produces: `generate_actions()` that writes exactly eight `gen_<target>_tag.yml` files and `remove_actions()` that removes every old `.yml` workflow before generation.

- [ ] **Step 1: Add a failing generator contract test**

Create `ci/test_release_workflows.py` with the generator helper and initial tests:

```python
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
```

- [ ] **Step 2: Run the test and verify the old generator fails the contract**

Run: `python3 ci/test_release_workflows.py -v`

Expected: FAIL because the generator emits PR and continuous files, preserves the seeded `pages.yml`, injects release secrets, includes upstream-only publication steps, and does not use `GITHUB_REF_NAME`.

- [ ] **Step 3: Remove non-release generator state and methods**

In `ci/generate-workflows.py`:

- Remove the unused `sys` import, `GEMFURY_TARGET`, and all `TRIGGER_PATHS*` constants.
- Keep `APPIMAGE_TARGET = "ubuntu:26.04"`.
- Remove `continuous_only` and `is_tag` from `Target.__init__` and target construction.
- Change `package(self, trusted=False)` to `package(self)` and always return only the `ci/deploy.sh` packaging step plus AppImage/source steps.
- Remove `upload_artifact_nightly()`, `upload_asset_nightly()`, `create_flathub_pr()`, `create_winget_pr()`, `update_homebrew_tap()`, `pull_request()`, and `continuous()`.
- Remove the Gemfury branch from `upload_asset_tag()`.
- Remove Alpine public-key attachment behavior from `asset_patterns()` because Alpine is not a retained target and package signing is out of scope.

Replace the release commands returned by `upload_asset_tag()` with:

```python
return [
    ActionStep(
        "Download artifact",
        action="actions/download-artifact@v8",
        params={"name": self.name},
    ),
    checksum,
    RunStep(
        "Create draft release",
        'bash ci/retry.sh bash ci/create-release.sh "$GITHUB_REF_NAME"',
        env={"GH_TOKEN": "${{ github.token }}"},
    ),
    RunStep(
        "Upload to tagged release",
        f'bash ci/retry.sh gh release upload --clobber "$GITHUB_REF_NAME" {glob}',
        env={"GH_TOKEN": "${{ github.token }}"},
    ),
]
```

Reduce `tag()` to the retained build and GitHub Release path:

```python
def tag(self):
    steps = self.prep_environment()
    steps += self.build_all_release()
    steps += self.test_all()
    steps += self.package()
    steps += self.upload_artifact()

    uploader = Job(
        runs_on="ubuntu-latest",
        steps=self.checkout(submodules=False) + self.upload_asset_tag(),
    )

    return (
        Job(
            runs_on=self.os,
            container=self.container,
            steps=steps,
            env=self.env,
        ),
        uploader,
    )
```

- [ ] **Step 4: Replace generic multi-mode generation with tag-only generation**

Change `generate_actions()` to take no mode callbacks. For each deep-copied target, derive `name = f"{t.name}_tag"`, call `t.tag()`, and render this fixed trigger:

```yaml
on:
  push:
    tags:
      - "20*"

permissions:
  contents: read
```

Render the upload job without the upstream repository condition and with only:

```yaml
permissions:
  contents: write
```

Remove the Gemfury presence check. Retain the AppImage target sanity check.

Replace the bottom-level generation calls with:

```python
def remove_actions():
    for name in glob.glob(".github/workflows/*.yml"):
        os.remove(name)


remove_actions()
generate_actions()
```

- [ ] **Step 5: Run the generator tests**

Run: `python3 ci/test_release_workflows.py -v`

Expected: all three tests PASS. The command runs the generator only in a temporary directory, so checked-in workflow files are not changed yet.

### Task 2: Make Draft Release Creation Explicit and Idempotent

**Files:**
- Modify: `ci/test_release_workflows.py`
- Modify: `ci/create-release.sh:1-17`

**Interfaces:**
- Consumes: A tag argument supplied as `"$GITHUB_REF_NAME"` and `GH_TOKEN` supplied by each upload job.
- Produces: `ci/create-release.sh <tag>` that reuses an existing Release or creates an empty draft with the same tag and title.

- [ ] **Step 1: Add failing tests with a fake GitHub CLI**

Add these imports near the top of `ci/test_release_workflows.py`:

```python
import json
import os
```

Add this constant and test class before the `if __name__` block:

```python
CREATE_RELEASE = ROOT / "ci" / "create-release.sh"


class CreateReleaseTests(unittest.TestCase):
    def run_script(self, view_status, *args):
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

    def test_reuses_existing_release(self):
        result, calls = self.run_script(0, "20260807-test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["release", "view", "20260807-test"]])

    def test_creates_empty_draft_for_missing_release(self):
        result, calls = self.run_script(1, "20260807-test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls,
            [
                ["release", "view", "20260807-test"],
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
```

- [ ] **Step 2: Run the draft creation tests and verify they fail**

Run: `python3 ci/test_release_workflows.py CreateReleaseTests -v`

Expected: FAIL because the current script creates a pre-release with upstream documentation notes and accepts an empty tag.

- [ ] **Step 3: Replace the release creation script**

Replace `ci/create-release.sh` with:

```bash
#!/bin/bash
set -xe

name=${1:?release tag is required}

gh release view "$name" >/dev/null 2>&1 ||
  gh release create "$name" --draft --title "$name" --notes ""
```

- [ ] **Step 4: Run the focused and complete tests**

Run: `python3 ci/test_release_workflows.py CreateReleaseTests -v`

Expected: all three `CreateReleaseTests` PASS.

Run: `python3 ci/test_release_workflows.py -v`

Expected: all tests PASS.

### Task 3: Remove Trusted Publishing and Ad-Hoc Sign macOS

**Files:**
- Modify: `ci/test_release_workflows.py`
- Modify: `ci/deploy.sh:21-103`
- Modify: `ci/appimage.sh:44-48`
- Delete: `ci/make-flathub-pr.sh`
- Delete: `ci/make-winget-pr.sh`
- Delete: `ci/wezterm-homebrew-macos.rb.template`
- Delete: `ci/wezterm-linuxbrew.rb.template`

**Interfaces:**
- Consumes: Universal macOS application assembled in `$zipdir/WezTerm.app` and existing `ci/macos-entitlement.plist`.
- Produces: An ad-hoc-signed macOS ZIP with no certificate/notarization inputs; AppImage packaging without Linuxbrew output; no external publisher helpers.

- [ ] **Step 1: Add failing packaging policy tests**

Add before the `if __name__` block in `ci/test_release_workflows.py`:

```python
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
```

- [ ] **Step 2: Run the packaging policy tests and verify they fail**

Run: `python3 ci/test_release_workflows.py PackagingPolicyTests -v`

Expected: FAIL because `deploy.sh` contains certificate signing, keychain setup, notarization, and Homebrew generation; `appimage.sh` generates a Linuxbrew formula; and publisher helpers still exist.

- [ ] **Step 3: Replace Apple release signing with ad-hoc signing**

In the macOS branch of `ci/deploy.sh`, delete both `if [ -n "$MACOS_TEAM_ID" ]` blocks, including secret decoding, keychain management, Developer ID signing, and `notarytool` submission.

After the loop that copies or combines the four binaries, add:

```bash
    /usr/bin/codesign --force --deep --sign - \
      --entitlements ci/macos-entitlement.plist "$zipdir/WezTerm.app"
```

Keep ZIP creation immediately after this command. Remove the final SHA256 and `wezterm.rb` generation lines from the macOS branch; checksums are generated by the upload job.

- [ ] **Step 4: Remove unused external publication outputs**

Delete only the Linuxbrew formula generation line from `ci/appimage.sh`:

```bash
sed -e "s/@TAG@/$TAG_NAME/g" -e "s/@SHA256@/$SHA256/g" < ci/wezterm-linuxbrew.rb.template > wezterm-linuxbrew.rb
```

Retain the preceding PKGBUILD generation because this change does not alter the AppImage output path or the accepted release attachment set.

Delete the four external publication-only files listed in this task's file section. Retain `ci/macos-entitlement.plist` for ad-hoc signing.

- [ ] **Step 5: Run focused tests and shell syntax checks**

Run: `python3 ci/test_release_workflows.py PackagingPolicyTests -v`

Expected: all three `PackagingPolicyTests` PASS.

Run: `bash -n ci/deploy.sh ci/appimage.sh ci/create-release.sh`

Expected: exit status 0 with no output.

### Task 4: Regenerate and Check In Only the Eight Release Workflows

**Files:**
- Modify: `ci/test_release_workflows.py`
- Regenerate: `.github/workflows/gen_centos9_tag.yml`
- Regenerate: `.github/workflows/gen_debian12_tag.yml`
- Regenerate: `.github/workflows/gen_fedora41_tag.yml`
- Regenerate: `.github/workflows/gen_macos_tag.yml`
- Regenerate: `.github/workflows/gen_ubuntu22.04_tag.yml`
- Regenerate: `.github/workflows/gen_ubuntu24.04_tag.yml`
- Regenerate: `.github/workflows/gen_ubuntu26.04_tag.yml`
- Regenerate: `.github/workflows/gen_windows_tag.yml`
- Delete: `.github/workflows/fmt.yml`
- Delete: `.github/workflows/gen_centos9_continuous.yml`
- Delete: `.github/workflows/gen_centos9.yml`
- Delete: `.github/workflows/gen_debian12_continuous.yml`
- Delete: `.github/workflows/gen_debian12.yml`
- Delete: `.github/workflows/gen_fedora41_continuous.yml`
- Delete: `.github/workflows/gen_fedora41.yml`
- Delete: `.github/workflows/gen_macos_continuous.yml`
- Delete: `.github/workflows/gen_macos.yml`
- Delete: `.github/workflows/gen_ubuntu22.04_continuous.yml`
- Delete: `.github/workflows/gen_ubuntu22.04.yml`
- Delete: `.github/workflows/gen_ubuntu24.04_continuous.yml`
- Delete: `.github/workflows/gen_ubuntu24.04.yml`
- Delete: `.github/workflows/gen_ubuntu26.04_continuous.yml`
- Delete: `.github/workflows/gen_ubuntu26.04.yml`
- Delete: `.github/workflows/gen_windows_continuous.yml`
- Delete: `.github/workflows/gen_windows.yml`
- Delete: `.github/workflows/lock.yml`
- Delete: `.github/workflows/nix-build.yml`
- Delete: `.github/workflows/nix-continuous.yml`
- Delete: `.github/workflows/nix-update-flake.yml`
- Delete: `.github/workflows/no-response.yml`
- Delete: `.github/workflows/pages.yml`
- Delete: `.github/workflows/termwiz.yml`
- Delete: `.github/workflows/verify-pages.yml`
- Delete: `.github/workflows/wezterm_ssh.yml`

**Interfaces:**
- Consumes: The deterministic `generate_actions()` and `remove_actions()` implemented in Task 1.
- Produces: A checked-in `.github/workflows` directory byte-for-byte equal to a fresh generator run.

- [ ] **Step 1: Add a failing checked-in output test**

Add before the `if __name__` block in `ci/test_release_workflows.py`:

```python
class CheckedInWorkflowTests(unittest.TestCase):
    def test_checked_in_workflows_match_generator(self):
        workflow_dir = ROOT / ".github" / "workflows"
        checked_in = {
            path.name: path.read_text(encoding="utf-8")
            for path in workflow_dir.glob("*.yml")
        }
        self.assertEqual(checked_in, generate_workflows())
```

- [ ] **Step 2: Run the checked-in output test and verify it fails**

Run: `python3 ci/test_release_workflows.py CheckedInWorkflowTests -v`

Expected: FAIL because the repository still contains old PR, continuous, Pages, Nix, and maintenance workflows, and the tag workflows still contain the old release path.

- [ ] **Step 3: Regenerate workflows from the repository root**

Run: `python3 ci/generate-workflows.py`

Expected: the command deletes every existing `.github/workflows/*.yml` and writes exactly the eight `gen_*_tag.yml` files listed above.

- [ ] **Step 4: Run the checked-in output and full regression tests**

Run: `python3 ci/test_release_workflows.py CheckedInWorkflowTests -v`

Expected: PASS.

Run: `python3 ci/test_release_workflows.py -v`

Expected: all tests PASS.

### Task 5: Validate the Complete Release Pipeline Definition

**Files:**
- Verify: `ci/generate-workflows.py`
- Verify: `ci/test_release_workflows.py`
- Verify: `ci/create-release.sh`
- Verify: `ci/deploy.sh`
- Verify: `ci/appimage.sh`
- Verify: `.github/workflows/*.yml`

**Interfaces:**
- Consumes: All outputs from Tasks 1-4.
- Produces: Evidence that generated YAML is valid, scripts parse, no removed publication credential/path remains, and checked-in workflows are deterministic.

- [ ] **Step 1: Parse every generated workflow as YAML**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
import yaml

paths = sorted(Path(".github/workflows").glob("*.yml"))
assert len(paths) == 8, [str(path) for path in paths]
for path in paths:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data and "jobs" in data, path
print("parsed", len(paths), "release workflows")
PY
```

Expected: `parsed 8 release workflows`.

- [ ] **Step 2: Run all persistent release workflow tests**

Run: `python3 ci/test_release_workflows.py -v`

Expected: all tests PASS.

- [ ] **Step 3: Check modified shell syntax**

Run: `bash -n ci/deploy.sh ci/appimage.sh ci/create-release.sh ci/retry.sh`

Expected: exit status 0 with no output.

- [ ] **Step 4: Scan for forbidden release paths and credentials**

Run:

```bash
rg -n 'secrets\.|GH_PAT|FURY_TOKEN|MACOS_(CERT|TEAM_ID|APPLEID|APP_PW)|notarytool|gemfury|wez/homebrew|winget-pkgs|flathub/|github\.repository ==|pages: write|id-token: write' \
  .github/workflows ci/generate-workflows.py ci/deploy.sh ci/appimage.sh
```

Expected: no output and exit status 1, indicating no match.

- [ ] **Step 5: Confirm ad-hoc signing is the sole macOS signing command**

Run: `rg -n 'codesign' ci/deploy.sh`

Expected: exactly one match, the `codesign --force --deep --sign -` command with the existing entitlement file on its continuation line.

- [ ] **Step 6: Check patch integrity and inspect the final file set**

Run: `git diff --check`

Expected: exit status 0 with no output.

Run: `git status --short`

Expected: only the design/plan, generator/test/scripts, deleted publication helpers/templates, eight regenerated tag workflows, and deleted non-tag workflows described by this plan are changed.

## Execution Note

Linux-local checks validate generation, YAML structure, shell syntax, permissions,
artifact globs, and release semantics. The first pushed test tag is the real
cross-platform integration test for Windows, macOS, and distribution-native
packages. Keep its Release as a draft until all eight workflows have completed
and the attachment set has been reviewed.
