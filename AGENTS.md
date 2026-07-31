# AGENTS.md

This file is the Codex-facing working guide for this WezTerm fork. The older
Claude Code guide is in `CLAUDE.md`; keep both in sync when changing broad
maintenance conventions.

## Project

WezTerm is a GPU-accelerated terminal emulator and multiplexer written in Rust.
This fork adds a native left-side workspace sidebar for viewing, creating, and
switching workspaces.

User-facing docs live under `docs/`. Historical implementation notes for the
sidebar are under:

- `docs/superpowers/specs/2026-07-19-workspace-sidebar-design.md`
- `docs/superpowers/plans/2026-07-19-workspace-sidebar.md`

## Build, Test, Format

Use narrow Cargo commands while iterating.

```console
cargo check -p config
cargo check -p wezterm-gui
cargo test -p wezterm-gui workspace_sidebar
cargo nextest run -p wezterm-gui
cargo test --all
cargo +nightly fmt
```

`make check`, `make test`, and `make fmt` are the broader project gates. Rust
formatting uses nightly rustfmt; Lua formatting uses `stylua` via
`ci/stylua.toml`.

For manual GUI testing, prefer:

```console
cargo run -p wezterm-gui -- --config-file ./test-conf.lua start --always-new-process
```

## Architecture Map

- `termwiz/`, `term/`, `wezterm-cell/`, `wezterm-surface/`: terminal parsing,
  cells, surfaces, and reusable terminal primitives.
- `mux/`: panes, tabs, windows, workspaces, domains, and workspace notifications.
- `config/`: Lua-facing config schema and key assignments. Use
  `wezterm-dynamic` patterns for config-exposed types.
- `lua-api-crates/`: Lua API registration by feature area.
- `window/`: cross-platform window and GPU surface abstraction.
- `wezterm-gui/`: GUI application, including `termwindow/` input, overlays,
  tab bar, pane layout, and rendering.

When changing behavior, work at the lowest layer that owns the concept, and
update user docs for any user-visible config or action changes.

## Workspace Sidebar Fork Notes

The sidebar is optional and off by default. Its main user-facing surface is:

- `config.enable_workspace_sidebar`
- `config.workspace_sidebar_width`
- `config.mouse_wheel_scrolls_workspaces`
- `wezterm.action.ToggleWorkspaceSidebar`
- `wezterm.action.RenameWorkspace`
- `wezterm.action.CloseWorkspace`

Docs exist under:

- `docs/config/lua/config/enable_workspace_sidebar.md`
- `docs/config/lua/config/workspace_sidebar_width.md`
- `docs/config/lua/config/mouse_wheel_scrolls_workspaces.md`
- `docs/config/lua/keyassignment/ToggleWorkspaceSidebar.md`
- `docs/config/lua/keyassignment/RenameWorkspace.md`
- `docs/config/lua/keyassignment/CloseWorkspace.md`

Core implementation files:

- `config/src/config.rs`: sidebar config fields and defaults.
- `config/src/keyassignment.rs`: sidebar-related key assignments.
- `wezterm-gui/src/workspace_sidebar.rs`: pure logical sidebar model with unit
  tests.
- `wezterm-gui/src/termwindow/render/workspace_sidebar.rs`: box-model sidebar
  construction, GPU paint, and `UIItem` registration.
- `wezterm-gui/src/termwindow/resize.rs`: reserves the left strip and adjusts
  terminal geometry.
- `wezterm-gui/src/termwindow/render/pane.rs`: shifts pane content to the right
  when the sidebar is visible.
- `wezterm-gui/src/termwindow/render/fancy_tab_bar.rs`: shifts the fancy tab bar
  so it starts to the right of the sidebar.
- `wezterm-gui/src/termwindow/render/paint.rs`: paints the sidebar and appends
  sidebar hit-test items.
- `wezterm-gui/src/termwindow/mouseevent.rs`: click, right-click, and wheel
  dispatch for sidebar items.
- `wezterm-gui/src/overlay/workspace.rs`: prompt/menu overlays for create,
  rename, and close.
- `wezterm-gui/src/commands.rs`: command palette metadata.

Current design constraints:

- The sidebar is full-height on the left for the fancy tab bar layout.
- With the retro tab bar at the top, the sidebar starts below the retro tab bar
  because the retro renderer is not shifted.
- Workspace rows show only names plus active/hover styling.
- Colors derive from existing tab-bar and window-frame colors; there is no
  dedicated `colors.workspace_sidebar` config yet.
- The "+" button prompts for a workspace name; blank input uses generated names.
- Right-click actions are terminal overlays, not GPU popups.
- Scrolling over the sidebar switches workspaces only when
  `mouse_wheel_scrolls_workspaces` is enabled.

## Maintenance Rules

- Do not hand-roll separate rendering infrastructure for the sidebar. It should
  continue to use the existing `box_model` element pipeline and `UIItem`
  hit-testing.
- Keep terminal geometry correct: any visible sidebar width must be reserved in
  resize calculations and reflected in pane and tab-bar bounds.
- Invalidate cached sidebar layout when workspace state, config, dimensions, or
  font shape generation changes.
- Preserve the existing workspace notification/reconciliation flow in
  `wezterm-gui/src/frontend.rs` and `wezterm-gui/src/termwindow/mod.rs`.
- Add focused tests for logical model changes. GPU rendering is mainly verified
  manually, consistent with the rest of the GUI.
- Keep user docs updated with any change to config keys, defaults, key
  assignments, or sidebar behavior.

