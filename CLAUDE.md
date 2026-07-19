# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

WezTerm is a GPU-accelerated cross-platform terminal emulator and multiplexer written in Rust. User-facing docs live at https://wezterm.org/ (sources under `docs/`).

## Build, test, and format

This is a Cargo workspace (`resolver = "2"`) with many member crates. Use `cargo check`/`cargo check -p <crate>` for fast iteration — it type-checks without codegen, much faster than a release build.

```console
cargo run                     # debug build + run the GUI (RUST_BACKTRACE=1 for backtraces)
cargo build -p wezterm-gui    # the actual GUI application
cargo build -p wezterm        # the `wezterm` CLI
cargo build -p wezterm-mux-server   # headless multiplexer server

make build                    # builds wezterm, wezterm-gui, wezterm-mux-server, strip-ansi-escapes
make check                    # cargo check across the key crates
make test                     # runs `cargo nextest run` (+ escape-parser as no_std)
cargo test --all              # full test suite (CI gate)
cargo nextest run -p <crate>  # run one crate's tests
```

- **Formatting is a CI gate and uses nightly:** `make fmt` (= `cargo +nightly fmt`). Config in `.rustfmt.toml` (edition 2018, `imports_granularity = "Module"`). Lua files are formatted with stylua (`ci/stylua.toml`).
- **Platform dependencies:** run `./get-deps` to install system libraries (fontconfig, freetype, harfbuzz, EGL/X11/Wayland, openssl, etc.). Add new OS-specific install steps there rather than to docs.
- **Docs:** `ci/build-docs.sh serve` builds and live-reloads the mkdocs site.

`wezterm-escape-parser`, `wezterm-cell`, and `wezterm-surface` are `no_std`-capable and checked/tested separately in the Makefile — keep them free of `std`-only dependencies.

## Running for manual testing

- `wezterm-gui start --always-new-process` avoids reusing a background process, so mux logs aren't hidden.
- `wezterm-gui --config-file ./test-conf.lua ...` runs against a throwaway config.
- `docs/` and `CONTRIBUTING.md` describe a NixOS VM workflow (`nix/`) for reproducing display-server bugs in a clean desktop.

## Architecture

The codebase is layered from a windowing-agnostic terminal core up to the GPU GUI. When adding a feature, work at the lowest layer that owns the concept.

**Terminal core (windowing-agnostic):**
- `termwiz/` — "Terminal Wizardry": the low-level toolkit. Escape-sequence parsing (paired with `wezterm-escape-parser`, `vtparse`), the cell/surface model, input events, color, and a small immediate-mode widget/line-editor framework. Reusable as a standalone crate.
- `term/` (crate `wezterm-term`) — the virtual terminal emulator: interprets escape sequences into screen state (`screen.rs`, `terminalstate/`). This is where xterm-compatible terminal behavior lives. Aim for compatibility with xterm's ctlseqs. Test helpers are in `term/src/test/`.
- `wezterm-cell`, `wezterm-surface`, `wezterm-char-props` — shared cell/grapheme/surface primitives.

**Multiplexer:**
- `mux/` — models panes, tabs, and windows and the **Domain** abstraction (`domain.rs`) that spawns/attaches panes. Domains include local PTYs (`localpane.rs`), SSH (`ssh.rs`), and tmux control mode (`tmux*.rs`). A `Pane` (`pane.rs`) is the core trait for anything that produces terminal output.
- Client/server: `codec/` defines the wire protocol; `wezterm-mux-server` + `wezterm-mux-server-impl` are the headless server; `wezterm-client` connects a GUI/CLI to a remote mux. `wezterm-uds` (unix domain sockets) and `wezterm-ssh` are transports.

**GUI:**
- `window/` — cross-platform window creation and GPU surface abstraction (Wayland, X11, macOS, Windows). OpenGL/WebGPU rendering entry points live here.
- `wezterm-gui/` — the GUI application. `termwindow/` is the central window controller (input in `keyevent.rs`/`mouseevent.rs`, overlays/modals, tab bar, panes). Rendering pipeline: `renderstate.rs`, `glyphcache.rs`, `shapecache.rs`, `quad.rs`, GLSL/WGSL shaders. `commands.rs`/`inputmap.rs` map key/mouse assignments to actions. Lua-facing GUI scripting is under `scripting/`.

**Configuration (Lua):**
- `config/` — the entire config schema (one file per area: `font.rs`, `keyassignment.rs`, `color.rs`, ...). Configuration is a Lua program evaluated via mlua at startup.
- `wezterm-dynamic/` — a serde-like framework converting between Rust config structs and dynamic JSON-ish `Value`s; config types derive `FromDynamic`/`ToDynamic`. Use this (not serde directly) for anything reachable from Lua config.
- `lua-api-crates/` — each subdirectory registers a slice of the `wezterm.*` Lua API (e.g. `window-funcs`, `mux`, `color-funcs`, `time-funcs`, `ssh-funcs`). Add new Lua-exposed functions in the matching crate here.

**Entry points:** `wezterm/` is the `wezterm` CLI (subcommands in `wezterm/src/cli/`); `wezterm-gui/src/main.rs` is the GUI binary; `wezterm-mux-server/` is the server binary. Supporting crates (`promise`, `filedescriptor`, `pty`, `async_ossl`, `frecency`, etc.) provide focused primitives used across the tree.

## Contributing conventions

- Add tests for terminal-behavior changes; `term/src/test/` has helpers for asserting screen contents.
- Add or update `docs/` when adding/changing user-visible behavior.
- Before submitting: `cargo test --all` and `cargo fmt --all` must pass (CI enforces both).
