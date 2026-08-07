# GitHub Actions Release Simplification Design

**Date:** 2026-08-07

## Goal

Reduce this fork's GitHub Actions automation to one responsibility: when a
`20*` tag is pushed, build and test the existing platform targets, package
runnable artifacts, and attach them to a draft GitHub Release in this fork.

The release pipeline must work with the repository-provided `GITHUB_TOKEN` and
must not require signing certificates, package-repository credentials, or a
personal access token.

## Scope

The retained release targets are:

- CentOS 9
- Fedora 41
- Debian 12
- Ubuntu 22.04
- Ubuntu 24.04
- Ubuntu 26.04
- Windows
- macOS, with Intel and ARM binaries combined into universal binaries

All current release attachment types remain in scope, including checksums and
the source archive produced by the Ubuntu 26.04/AppImage target.

The following automation is removed:

- Pull request and branch build workflows
- Scheduled and continuous/nightly workflows
- Formatting and component-specific check workflows
- GitHub Pages deployment
- Nix build and flake-update workflows
- Issue automation
- Gemfury uploads
- Homebrew and Linuxbrew tap updates
- Winget pull requests
- Flathub pull requests
- Apple Developer ID signing and notarization

## Workflow Architecture

`ci/generate-workflows.py` remains the source of truth. It will generate only
the eight `gen_*_tag.yml` files. All other files under `.github/workflows` will
be removed.

Each generated workflow has two jobs:

1. The platform-native build job checks out submodules, prepares dependencies,
   builds the release binaries, runs the existing full `cargo nextest` suite,
   packages the platform artifacts, and uploads an intermediate Actions
   artifact.
2. An Ubuntu upload job downloads that intermediate artifact, writes one
   `.sha256` file per release attachment, creates or reuses the draft Release
   for the pushed tag, and uploads the files with replacement enabled.

The upload job requests only `contents: write`. The current
`github.repository == 'wezterm/wezterm'` condition is removed so that the jobs
run in this fork. No repository name or external repository is hard-coded into
the retained release path.

## Artifact Behavior

Existing package formats and naming rules are retained:

- Windows publishes the ZIP archive and installer executable.
- macOS publishes the universal application ZIP.
- CentOS and Fedora publish RPM packages.
- Debian and Ubuntu publish DEB and TAR.XZ packages.
- Ubuntu 26.04 additionally publishes the AppImage and source archive.
- Every attachment receives a matching SHA256 file.

The Actions artifact is only an intermediate transport between jobs. The draft
GitHub Release is the durable output intended for users.

## macOS Packaging

The packaging script will no longer read Apple certificate, team, account, or
app-password secrets. Certificate import, temporary keychain management,
Developer ID signing, and `notarytool` submission are removed.

After assembling the application bundle, the workflow applies an ad-hoc
signature with `codesign --sign -`. This requires no identity or secret and
does not assert publisher trust, but keeps the universal application bundle in
a structurally runnable state. The existing non-secret macOS entitlements are
retained on the ad-hoc signature.

Because the package is not notarized, macOS Gatekeeper can still require users
to explicitly approve first launch or remove the downloaded file's quarantine
attribute. This is an accepted consequence of removing Apple release
credentials.

## Release Lifecycle

The pushed tag's actual name, exposed as `GITHUB_REF_NAME`, is the Release tag
and title. `ci/create-release.sh` will create an empty draft Release when none
exists and reuse an existing Release for the tag on reruns.

The eight workflows run independently. Their upload jobs can race while
creating the common draft Release, so creation remains wrapped in the existing
retry helper. A conflicting create is retried, observes the Release created by
another job, and then succeeds. Asset upload uses `gh release upload
--clobber`, making reruns idempotent.

The workflow does not automatically publish the draft. The repository owner
reviews the attachment set and publishes it manually.

## Removed Release Support Code

The workflow generator loses its continuous, pull-request, Gemfury, tap-update,
Winget, and Flathub branches. The `trusted` packaging mode and all release
secret injection are removed.

Helpers and templates used only by removed external publication paths are also
deleted. Package scripts stop generating Homebrew/Linuxbrew formulas that are
no longer consumed. Build and packaging logic required for the retained GitHub
Release attachments remains unchanged except for macOS ad-hoc signing.

## Failure Handling

A failed build, test, or package step prevents that platform's upload job from
running. Other platforms may still upload successful artifacts to the shared
draft. The incomplete draft makes missing platforms visible and remains safe
to repair by rerunning failed workflows before manual publication.

Release creation and upload failures fail only the affected upload job. Both
operations are retryable without changing asset names or creating another
Release.

## Security and Permissions

The retained workflows use no repository secrets. Release commands authenticate
through the automatic `${{ github.token }}` context. Their only write
permission is `contents: write` for draft Release creation and asset upload.
Build jobs use default read access and intermediate artifact APIs. No job checks
out, commits to, opens a pull request against, or uploads a package to another
repository or service.

## Verification

Implementation verification will include:

- Run `python3 ci/generate-workflows.py` and confirm it emits exactly eight tag
  workflow files.
- Parse every generated workflow as YAML.
- Confirm every workflow triggers only on pushed `20*` tags.
- Confirm upload jobs request only `contents: write` and have no upstream-only
  repository condition.
- Scan the generated workflows and CI scripts for removed secret names,
  external publication targets, Developer ID signing, and notarization.
- Run `bash -n` on each modified shell script.
- Review generated artifact globs to confirm all existing package, source, and
  checksum attachments remain represented.

Actual cross-platform compilation and package execution are verified by the
tag-triggered GitHub Actions jobs. Local verification will not claim to execute
Windows or macOS artifacts on Linux.

## Acceptance Criteria

- `.github/workflows` contains only the eight generated tag workflows.
- Pushing a matching tag starts all eight platform builds in the fork.
- Successful builds run tests and upload their current artifact set to one
  draft Release named after the pushed tag.
- The workflows reference no release secret other than the automatic
  `GITHUB_TOKEN` context, and require no configured repository secret.
- No retained workflow publishes docs or packages, updates another repository,
  or creates external pull requests.
- macOS packaging uses only ad-hoc signing and performs no notarization.
- Rerunning a workflow reuses the same draft Release and replaces matching
  assets rather than failing or creating duplicates.
