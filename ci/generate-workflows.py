#!/usr/bin/env python3
import os
import glob
from copy import deepcopy

# The build from this target will be baked into the AppImage
APPIMAGE_TARGET = "ubuntu:26.04"


def yv(v, depth=0):
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "nil"

    if isinstance(v, str):
        if "\n" in v:
            indent = "  " * depth
            result = ""
            for l in v.splitlines():
                result = result + "\n" + (f"{indent}{l}" if l else "")
            return "|" + result
        # This is hideous
        if '"' in v:
            return "'" + v + "'"
        return '"' + v + '"'

    return v


class Step(object):
    def render(self, f, depth=0):
        raise NotImplementedError(repr(self))


class RunStep(Step):
    def __init__(self, name, run, shell="bash", env=None, condition=None):
        self.name = name
        self.run = run
        self.shell = shell
        self.env = env
        self.condition = condition

    def render(self, f, depth=0):
        indent = "  " * depth
        f.write(f"{indent}- name: {yv(self.name)}\n")
        if self.condition:
            f.write(f"{indent}  if: {self.condition}\n")
        if self.env:
            f.write(f"{indent}  env:\n")
            keys = list(self.env.keys())
            keys.sort()
            for k in keys:
                v = self.env[k]
                f.write(f"{indent}    {k}: {v}\n")
        if self.shell:
            f.write(f"{indent}  shell: {self.shell}\n")

        run = self.run

        f.write(f"{indent}  run: {yv(run, depth + 2)}\n")


class ActionStep(Step):
    def __init__(self, name, action, params=None, env=None, condition=None, id=None):
        self.name = name
        self.action = action
        self.params = params
        self.env = env
        self.condition = condition
        self.id = id

    def render(self, f, depth=0):
        indent = "  " * depth
        f.write(f"{indent}- name: {yv(self.name)}\n")
        f.write(f"{indent}  uses: {self.action}\n")
        if self.id:
            f.write(f"{indent}  id: {self.id}\n")
        if self.condition:
            f.write(f"{indent}  if: {self.condition}\n")
        if self.params:
            f.write(f"{indent}  with:\n")
            for k, v in self.params.items():
                f.write(f"{indent}    {k}: {yv(v, depth + 3)}\n")
        if self.env:
            f.write(f"{indent}  env:\n")
            for k, v in self.env.items():
                f.write(f"{indent}    {k}: {yv(v, depth + 3)}\n")


class CacheStep(ActionStep):
    def __init__(self, name, path, key, id=None):
        super().__init__(
            name, action="actions/cache@v4", params={"path": path, "key": key}, id=id
        )


class SccacheStep(ActionStep):
    def __init__(self, name):
        super().__init__(name, action="mozilla-actions/sccache-action@v0.0.9")


class CheckoutStep(ActionStep):
    def __init__(self, name="checkout repo", submodules=True, container=None):
        params = {}
        if submodules:
            params["submodules"] = "recursive"
        super().__init__(name, action=f"actions/checkout@v5", params=params)


class InstallCrateStep(ActionStep):
    def __init__(self, crate: str, key: str, version=None):
        params = {"crate": crate, "cache-key": key}
        if version is not None:
            params["version"] = version
        super().__init__(
            f"Install {crate} from Cargo",
            action="baptiste0928/cargo-install@v3",
            params=params,
        )


class Job(object):
    def __init__(self, runs_on, container=None, steps=None, env=None):
        self.runs_on = runs_on
        self.container = container
        self.steps = steps
        self.env = env

    def render(self, f, depth=0):
        f.write("\n    steps:\n")
        for s in self.steps:
            s.render(f, depth)


class Target(object):
    def __init__(
        self,
        name=None,
        os="ubuntu-latest",
        container=None,
        bootstrap_git=False,
        rust_target=None,
    ):
        if not name:
            if container:
                name = container
            else:
                name = os
        self.name = name.replace(":", "")
        self.os = os
        self.container = container
        self.bootstrap_git = bootstrap_git
        self.rust_target = rust_target
        self.app_image = container == APPIMAGE_TARGET
        self.env = {}

    def render_env(self, f, depth=0):
        self.global_env()
        if self.env:
            indent = "    "
            f.write(f"{indent}env:\n")
            for k, v in self.env.items():
                f.write(f"{indent}  {k}: {yv(v, depth + 3)}\n")

    def uses_yum(self):
        if "fedora" in self.name:
            return True
        if "centos" in self.name:
            return True
        return False

    def uses_apt(self):
        if "ubuntu" in self.name:
            return True
        if "debian" in self.name:
            return True
        return False

    def uses_apk(self):
        if "alpine" in self.name:
            return True
        return False

    def uses_zypper(self):
        if "suse" in self.name:
            return True
        return False

    def needs_sudo(self):
        if not self.container and self.uses_apt():
            return True
        return False

    def install_system_package(self, name):
        installer = None
        if self.uses_yum():
            installer = "yum"
        elif self.uses_apt():
            installer = "apt-get"
        elif self.uses_apk():
            installer = "apk"
        elif self.uses_zypper():
            installer = "zypper"
        else:
            return []
        if self.needs_sudo():
            installer = f"sudo -n {installer}"
        if self.uses_apk():
            return [RunStep(f"Install {name}", f"{installer} add {name}")]
        else:
            return [RunStep(f"Install {name}", f"{installer} install -y {name}")]

    def install_curl(self):
        if (
            self.uses_yum()
            or self.uses_apk()
            or self.uses_zypper()
            or (self.uses_apt() and self.container)
        ):
            if "centos:stream9" in self.container:
                return self.install_system_package("curl-minimal")
            else:
                return self.install_system_package("curl")
        return []

    def install_openssh_server(self):
        steps = []
        if (
            self.uses_yum()
            or self.uses_zypper()
            or (self.uses_apt() and self.container)
        ):
            steps += [
                RunStep("Ensure /run/sshd exists", "mkdir -p /run/sshd")
            ] + self.install_system_package("openssh-server")
        if self.uses_apk():
            steps += self.install_system_package("openssh")
        return steps

    def install_newer_compiler(self):
        steps = []
        if self.name == "centos7":
            steps.append(
                RunStep(
                    "Install SCL",
                    "yum install -y centos-release-scl-rh",
                )
            )
            steps.append(
                RunStep(
                    "Update compiler",
                    "yum install -y devtoolset-9-gcc devtoolset-9-gcc-c++",
                )
            )
        return steps

    def install_git(self):
        steps = []
        if self.bootstrap_git:
            GIT_VERS = "2.26.2"
            steps.append(
                CacheStep(
                    "Cache Git installation",
                    path="/usr/local/git",
                    key=f"{self.name}-git-{GIT_VERS}",
                )
            )

            pre_reqs = ""
            if self.uses_yum():
                pre_reqs = "yum install -y wget curl-devel expat-devel gettext-devel openssl-devel zlib-devel gcc perl-ExtUtils-MakeMaker make"
            elif self.uses_apt():
                pre_reqs = "apt-get install -y wget libcurl4-openssl-dev libexpat-dev gettext libssl-dev libz-dev gcc libextutils-autoinstall-perl make"
            elif self.uses_zypper():
                pre_reqs = "zypper install -y wget libcurl-devel libexpat-devel gettext-tools libopenssl-devel zlib-devel gcc perl-ExtUtils-MakeMaker make"

            steps.append(
                RunStep(
                    name="Install Git from source",
                    shell="bash",
                    run=f"""{pre_reqs}
if test ! -x /usr/local/git/bin/git ; then
    cd /tmp
    wget https://github.com/git/git/archive/v{GIT_VERS}.tar.gz
    tar xzf v{GIT_VERS}.tar.gz
    cd git-{GIT_VERS}
    make prefix=/usr/local/git install
fi
ln -s /usr/local/git/bin/git /usr/local/bin/git""",
                )
            )

        else:
            if "tumbleweed" in self.name:
                # git-core requires /usr/bin/which and that gets satisfied
                # by busybox-which by default, which blocks installing
                # rpmbuild, which depends on the which rpm directly,
                # but that is blocked by the conflicting busybox-which rpm.
                # So we explicitly install which here now
                steps += self.install_system_package("which")

            steps += self.install_system_package("git")

        return steps

    def install_rust(self, cache=True, toolchain="stable"):
        salt = "2"
        key_prefix = f"{self.name}-{self.rust_target}-{salt}-${{{{ runner.os }}}}"
        params = dict()
        if self.rust_target:
            params["target"] = self.rust_target
        steps = []
        # Manually setup rust toolchain in CentOS7 curl is too old for the action
        if "centos7" in self.name:
            steps += [
                RunStep(
                    name="Install Rustup",
                    run="""
if ! command -v rustup &>/dev/null; then
  curl --proto '=https' --tlsv1.2 --retry 10 -fsSL "https://sh.rustup.rs" | sh -s -- --default-toolchain none -y
  echo "${CARGO_HOME:-$HOME/.cargo}/bin" >> $GITHUB_PATH
fi
""",
                ),
                RunStep(
                    name="Setup Toolchain",
                    run=f"""
rustup toolchain install {toolchain} --profile minimal --no-self-update
rustup default {toolchain}
""",
                ),
            ]
        elif "macos" in self.name:
            steps += [
                RunStep(
                    name="Install Rust (ARM)",
                    run="rustup target add aarch64-apple-darwin",
                ),
                RunStep(
                    name="Install Rust (Intel)",
                    run="rustup target add x86_64-apple-darwin",
                )
            ]
        else:
            steps += [
                ActionStep(
                    name="Install Rust",
                    action=f"dtolnay/rust-toolchain@{toolchain}",
                    params=params,
                ),
            ]
        if cache:
            steps += [
                SccacheStep(name="Compile with sccache"),
                # Cache vendored dependencies
                CacheStep(
                    name="Cache Rust Dependencies",
                    path="vendor\n.cargo/config",
                    key="cargo-deps-${{ hashFiles('**/Cargo.lock') }}",
                    id="cache-cargo-vendor",
                ),
                # Vendor dependencies
                RunStep(
                    name="Vendor dependencies",
                    condition="steps.cache-cargo-vendor.outputs.cache-hit != 'true'",
                    run="cargo vendor --locked --versioned-dirs >> .cargo/config",
                ),
            ]
        return steps

    def install_system_deps(self):
        if "win" in self.name:
            return []
        sudo = "sudo -n " if self.needs_sudo() else ""
        return [
            RunStep(
                name="Install System Deps",
                run=f"{sudo}env CI=yes PATH=$PATH ./get-deps",
            )
        ]

    def fixup_windows_path(self, cmd):
        if "win" in self.name:
            return "PATH C:\\Strawberry\\perl\\bin;%PATH%\n" + cmd
        return cmd

    def build_all_release(self):
        bin_crates = [
            "wezterm",
            "wezterm-gui",
            "wezterm-mux-server",
            "strip-ansi-escapes",
        ]
        steps = []
        for bin in bin_crates:
            if "win" in self.name:
                steps += [
                    RunStep(
                        name=f"Build {bin} (Release mode)",
                        shell="cmd",
                        run=self.fixup_windows_path(f"cargo build -p {bin} --release"),
                    )
                ]
            elif "macos" in self.name:
                steps += [
                    RunStep(
                        name=f"Build {bin} (Release mode Intel)",
                        run=f"cargo build --target x86_64-apple-darwin -p {bin} --release",
                    ),
                    RunStep(
                        name=f"Build {bin} (Release mode ARM)",
                        run=f"cargo build --target aarch64-apple-darwin -p {bin} --release",
                    ),
                ]
            else:
                if self.name == "centos7":
                    enable = "source /opt/rh/devtoolset-9/enable && "
                else:
                    enable = ""
                steps += [
                    RunStep(
                        name=f"Build {bin} (Release mode)",
                        run=enable + f"cargo build -p {bin} --release",
                    )
                ]
        return steps

    def test_all(self):
        run = "cargo nextest run --all --no-fail-fast"
        if "macos" in self.name:
            run += " --target=x86_64-apple-darwin"
        if self.name == "centos7":
            run = "source /opt/rh/devtoolset-9/enable\n" + run
        return [
            # Install cargo-nextest
            InstallCrateStep("cargo-nextest", key=self.name),
            # Run tests
            RunStep(name="Test", run=self.fixup_windows_path(run), shell="cmd")
            if "win" in self.name
            else RunStep(name="Test", run=run),
        ]

    def package(self):
        steps = [RunStep("Package", "bash ci/deploy.sh")]
        if self.app_image:
            # AppImage needs fuse and the file command
            steps += self.install_system_package("libfuse2")
            steps += self.install_system_package("file")
            steps.append(RunStep("Source Tarball", "bash ci/source-archive.sh"))
            steps.append(RunStep("Build AppImage", "bash ci/appimage.sh"))
        return steps

    def upload_artifact(self):
        steps = []

        if self.uses_yum():
            steps.append(
                RunStep(
                    "Move RPM",
                    f"mv ~/rpmbuild/RPMS/*/*.rpm .",
                )
            )
        elif self.uses_apk():
            steps += [
                # Add the distro name/version into the filename
                RunStep(
                    "Rename APKs",
                    f"mv ~/packages/wezterm/x86_64/*.apk $(echo ~/packages/wezterm/x86_64/*.apk | sed -e 's/wezterm-/wezterm-{self.name}-/')",
                ),
                # Move it to the repo dir
                RunStep(
                    "Move APKs",
                    f"mv ~/packages/wezterm/x86_64/*.apk .",
                ),
                # Move and rename the keys
                RunStep(
                    "Move APK keys",
                    f"mv ~/.abuild/*.pub wezterm-{self.name}.pub",
                ),
            ]
        elif self.uses_zypper():
            steps.append(
                RunStep(
                    "Move RPM",
                    f"mv /usr/src/packages/RPMS/*/*.rpm .",
                )
            )

        patterns = self.asset_patterns()
        glob = " ".join(patterns)
        paths = "\n".join(patterns)

        return steps + [
            ActionStep(
                "Upload artifact",
                action="actions/upload-artifact@v7",
                params={"name": self.name, "path": paths},
            ),
        ]

    def asset_patterns(self):
        patterns = []
        if self.uses_yum() or self.uses_zypper():
            patterns += ["wezterm-*.rpm"]
        elif "win" in self.name:
            patterns += ["WezTerm-*.zip", "WezTerm-*.exe"]
        elif "mac" in self.name:
            patterns += ["WezTerm-*.zip"]
        elif ("ubuntu" in self.name) or ("debian" in self.name):
            patterns += ["wezterm-*.deb", "wezterm-*.xz"]
        elif "alpine" in self.name:
            patterns += ["wezterm-*.apk"]

        if self.app_image:
            patterns.append("*src.tar.gz")
            patterns.append("*.AppImage")
            #patterns.append("*.zsync") broken upstream: <https://github.com/linuxdeploy/linuxdeploy/issues/309>
        return patterns

    def upload_asset_tag(self):
        patterns = self.asset_patterns()
        checksum = RunStep(
            "Checksum",
            f"for f in {' '.join(patterns)} ; do sha256sum $f > $f.sha256 ; done",
        )

        patterns.append("*.sha256")
        glob = " ".join(patterns)

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

    def global_env(self):
        self.env["CARGO_INCREMENTAL"] = "0"
        self.env["SCCACHE_GHA_ENABLED"] = "true"
        self.env["RUSTC_WRAPPER"] = "sccache"
        if "macos" in self.name:
            self.env["MACOSX_DEPLOYMENT_TARGET"] = "10.12"
        if "alpine" in self.name:
            self.env["RUSTFLAGS"] = "-C target-feature=-crt-static"
        if "win" in self.name:
            self.env["RUSTUP_WINDOWS_PATH_ADD_BIN"] = "1"
        return

    def prep_environment(self, cache=True):
        steps = []
        sudo = "sudo -n " if self.needs_sudo() else ""
        if self.uses_apt():
            if self.container:
                steps += [
                    RunStep(
                        "set APT to non-interactive",
                        "echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections",
                    ),
                ]
            steps += [
                RunStep("Update APT", f"{sudo}apt update"),
            ]

        if self.uses_zypper():
            if self.container:
                steps += [
                    RunStep(
                        "Seed GITHUB_PATH to work around possible @action/core bug",
                        f'echo "$PATH:/bin:/usr/bin" >> $GITHUB_PATH',
                    ),
                    RunStep(
                        "Install util-linux",
                        "zypper install -y util-linux",
                    ),
                ]
        if self.container:
            if ("fedora" in self.container) or (
                ("centos" in self.container) and ("centos7" not in self.container)
            ):
                steps += [
                    RunStep(
                        "Install config manager",
                        "dnf install -y 'dnf-command(config-manager)'",
                    ),
                ]
            if "centos:stream8" in self.container:
                steps += [
                    RunStep(
                        "Enable PowerTools",
                        "dnf config-manager --set-enabled powertools",
                    ),
                ]
            if "centos:stream9" in self.container:
                steps += [
                    # This holds the xcb bits
                    RunStep(
                        "Enable CRB repo for X bits",
                        "dnf config-manager --set-enabled crb",
                    ),
                ]
            if "alpine" in self.container:
                steps += [
                    RunStep(
                        "Upgrade system",
                        "apk upgrade --update-cache",
                        shell="sh",
                    ),
                    RunStep(
                        "Install CI dependencies",
                        "apk add nodejs zstd wget bash coreutils tar findutils",
                        shell="sh",
                    ),
                    RunStep(
                        "Allow root login",
                        "sed 's/root:!/root:*/g' -i /etc/shadow",
                    ),
                ]
            if "opensuse" in self.container:
                steps += [
                    # This holds the xcb bits
                    RunStep(
                        "Install tar",
                        "zypper install -yl tar gzip",
                    ),
                ]

        steps += self.install_newer_compiler()
        steps += self.install_git()
        steps += self.install_curl()

        if self.uses_apt():
            if self.container:
                steps += [
                    RunStep("Update APT", f"{sudo}apt update"),
                ]

        steps += self.install_openssh_server()
        steps += self.checkout()
        # We should be able to cache mac builds now?
        steps += self.install_rust()  # cache="mac" not in self.name)
        steps += self.install_system_deps()
        return steps

    def checkout(self, submodules=True):
        steps = []
        if self.container:
            steps += [
                RunStep(
                    "Workaround git permissions issue",
                    "git config --global --add safe.directory /__w/wezterm/wezterm",
                )
            ]
        steps += [CheckoutStep(submodules=submodules, container=self.container)]
        return steps

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


TARGETS = [
    Target(container="ubuntu:22.04"),
    Target(container="ubuntu:24.04"),
    Target(container="ubuntu:26.04"),
    Target(container="debian:12"),
    Target(name="centos9", container="quay.io/centos/centos:stream9"),
    Target(name="macos", os="macos-latest"),
    # https://fedoraproject.org/wiki/End_of_life?rd=LifeCycle/EOL
    Target(container="fedora:41"),
    # Target(container="alpine:3.15"),

    Target(name="windows", os="windows-2025", rust_target="x86_64-pc-windows-msvc"),
]


def generate_actions():
    have_appimage = False
    for t in TARGETS:
        t = deepcopy(t)

        if t.app_image:
            have_appimage = True

        name = f"{t.name}_tag"
        print(name)
        job, uploader = t.tag()

        file_name = f".github/workflows/gen_{name}.yml"
        if job.container:
            if t.app_image:
                container = f"container:\n      image: {yv(job.container)}\n      options: --privileged"
            else:
                container = f"container: {yv(job.container)}"

        else:
            container = ""

        with open(file_name, "w") as f:
            f.write(
                f"""name: {name}

on:
  push:
    tags:
      - "20*"

concurrency:
  group: ${{{{ github.workflow }}}}-${{{{ github.ref }}}}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  build:
    runs-on: {yv(job.runs_on)}
    {container}
"""
            )

            t.render_env(f)

            job.render(f, 3)

            # We upload using a native runner as github API access
            # inside a container is really unreliable and can result
            # in broken releases that can't automatically be repaired
            # <https://github.com/cli/cli/issues/4863>
            if uploader:
                f.write(
                    """
  upload:
    runs-on: ubuntu-latest
    needs: build
    permissions:
      contents: write
"""
                )
                uploader.render(f, 3)

        # Sanity check the yaml, if pyyaml is available
        try:
            import yaml

            with open(file_name) as f:
                yaml.safe_load(f)
        except ImportError:
            pass
    if not have_appimage:
        raise NotImplementedError("no appimage target is present")


def remove_actions():
    for pattern in ("*.yml", "*.yaml"):
        for name in glob.glob(f".github/workflows/{pattern}"):
            os.remove(name)


remove_actions()
generate_actions()
