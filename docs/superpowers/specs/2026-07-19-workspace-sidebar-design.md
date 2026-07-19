# Vertical Workspace Switcher Sidebar — Design

**Date:** 2026-07-19
**Status:** Approved for planning

## Summary

Add a dedicated, full-height **vertical sidebar on the left edge** of the WezTerm
GUI window that lists all workspaces and lets the user switch between them by
clicking. This complements the existing **horizontal tab bar**, which continues
to switch tabs *within* the active workspace. The result is a two-axis layout:
workspaces down the left, tabs across the top.

The feature is **off by default** and enabled via config and/or a key
assignment. It is built as a native GUI element reusing the same `box_model`
rendering toolkit as the "fancy" tab bar, so it reserves real horizontal space
and keeps terminal geometry correct.

## Motivation

WezTerm already supports workspaces (a workspace is a name shared by a set of mux
windows), but the only ways to see or switch them are the launcher overlay
(`Ctrl+Shift+L`) and key assignments. There is no always-visible, at-a-glance
list. Users juggling several workspaces (e.g. one per project or per agent
session, as in cmux) benefit from a persistent switcher that mirrors how the tab
bar makes tabs visible and clickable.

## Decisions (locked during brainstorming)

- **Entry content:** just the workspace name plus an active/highlight indicator.
  No status lines, counts, or previews.
- **Visibility:** off by default. Toggled by a config flag and a key assignment.
  **No** auto-hide based on workspace count.
- **Layout:** the sidebar is **full window height** on the left; the top tab bar
  sits **only above the content area** (to the right of the sidebar). This is
  "Layout A" — the cmux-style corner arrangement.
- **Actions:** click to switch · scroll-wheel and existing relative keys to move
  between workspaces · a **"+"** button that prompts for a name and
  creates/switches · **right-click** opens an **action menu rendered as a
  terminal overlay** (reusing the existing overlay pattern, like the horizontal
  tab's right-click navigator) — **not** a GPU-drawn floating popup.
- **Position:** left only for the MVP (no left/right config — YAGNI).

## Approach

**Native integrated strip, drawn with the `box_model` element toolkit.**

This reuses the machinery the fancy tab bar already uses: build an `Element`
tree, compute it into a laid-out `ComputedElement`, render it to GPU quads, and
register `UIItem`s for hit-testing. Horizontal space is reserved in
`apply_dimensions` (mirroring how `tab_bar_height` is reserved on the vertical
axis) so pane content shifts right and terminal columns recompute correctly.
Live updates come from repainting on the existing workspace `MuxNotification`s.

### Alternatives rejected

- **Lua / status-text only:** WezTerm's Lua surface (`left_status`,
  `format-tab-title`, …) lives *inside* the top tab-bar row. Lua cannot reserve
  horizontal space or draw a full-height left strip, so it cannot produce
  Layout A.
- **Docked pane/overlay:** hijacking a real pane to sit on the left fights the
  mux tiling/tab model, complicates dimensions, and would capture keyboard
  focus. Far more friction than reusing the box-model UI layer.

## Components

### 1. Configuration (`config/`)

- `enable_workspace_sidebar: bool` — default `false` (`config/src/config.rs`).
- `workspace_sidebar_width: Dimension` — default equivalent to ~`180px`.
  Using `Dimension` lets users express cells/pixels/percent, consistent with
  `window_padding`.
- `mouse_wheel_scrolls_workspaces: bool` — default `false`. Mirrors the existing
  `mouse_wheel_scrolls_tabs`; gates scroll-to-switch over the strip.
- Colors: **no new required config.** Active/inactive entry colors derive from
  the existing `tab_bar` colors; the strip background derives from
  `window_frame`. A dedicated `colors.workspace_sidebar` override is a possible
  future addition (out of scope).
- New key assignment `ToggleWorkspaceSidebar` in
  `config/src/keyassignment.rs`. It flips a per-window runtime override of the
  config flag. No default keybinding; documented for users to bind.

### 2. State model + rendering

- **`wezterm-gui/src/workspace_sidebar.rs`** — `WorkspaceSidebarState`,
  analogous to `TabBarState`. Built from `Mux::iter_workspaces()` +
  `Mux::active_workspace()`. Holds an ordered `Vec<WorkspaceSidebarEntry>`
  (`name`, `active`, `hover`) plus a trailing `NewWorkspaceButton`. Pure logical
  model with no GPU types — unit-testable.
- **`wezterm-gui/src/termwindow/render/workspace_sidebar.rs`** —
  - `build_workspace_sidebar(&self, palette) -> ComputedElement`: builds a
    vertically-stacked `box_model::Element` tree (`DisplayType::Block` children)
    within a left-strip `LayoutContext`, styled from the derived palette, with
    hover colors per entry and a `+` poly button (modeled on the fancy tab bar's
    `PLUS_BUTTON`).
  - `paint_workspace_sidebar(&self, ...)`: renders the computed element via
    `render_element` and registers `UIItem`s from `computed.ui_items()`.
  - Cached on `TermWindow` as `Option<ComputedElement>`, invalidated on
    change/hover — same lifecycle as `fancy_tab_bar`.

### 3. Geometry — the reserved left strip

Introduce a single horizontal inset, `left_sidebar_width` (0 when hidden),
threaded through the three places that currently assume content starts at
`padding_left`:

- **`termwindow/resize.rs::apply_dimensions`** — subtract `left_sidebar_width`
  from available width before computing terminal `cols`, and add it to the
  required-width budget. Mirrors the existing `tab_bar_height` handling on the
  vertical axis so columns and resize increments stay correct.
- **`termwindow/render/pane.rs`** — offset the pane content origin
  `left_pixel_x` by `left_sidebar_width` in both the classic and box-model pane
  paths.
- **Tab bar bounds** — shift the top tab bar's x-origin right and shrink its
  width by `left_sidebar_width`, so tabs sit only above the content area
  (the defining feature of Layout A). Applies to both the retro and fancy tab
  bar layout bounds.
- **Paint order (`termwindow/render/paint.rs`)** — add
  `paint_workspace_sidebar` to the paint sequence (after the tab bar, before
  window borders), drawing the full-height strip `[0, left_sidebar_width]`.

### 4. Mouse & keyboard interaction (`termwindow/mouseevent.rs`)

- New hit-test variant `UIItemType::WorkspaceSidebar(WorkspaceSidebarItem)`,
  where `WorkspaceSidebarItem` is `Workspace { index }` or `NewButton`.
  Dispatched from `mouse_event_ui_item` into a new
  `mouse_event_workspace_sidebar` handler (parallel to `mouse_event_tab_bar`).
  - **Left-click `Workspace`** → dispatch
    `SwitchToWorkspace { name: Some(name), spawn: None }` (the existing action
    that reconciles GUI windows and spawns if the workspace is empty).
  - **Left-click `NewButton`** → open the new-workspace prompt (§5).
  - **Right-click `Workspace`** → open the workspace actions overlay (§5).
  - **Hover enter/leave** → invalidate the cached element for hover styling.
- **Scroll:** `VertWheel` while hovering the strip → `SwitchWorkspaceRelative(±1)`,
  gated by `mouse_wheel_scrolls_workspaces`.
- **Keys:** no new bindings — existing `SwitchWorkspaceRelative` /
  `SwitchToWorkspace` assignments already move the active workspace, and the
  sidebar reflects it.

### 5. New-workspace prompt and right-click menu (terminal overlays)

- **New workspace ("+"):** open a single-line input overlay (the
  `PromptInputLine` / line-editor overlay machinery) to read a name; on submit,
  dispatch `SwitchToWorkspace { name: Some(entered), spawn: None }`. Empty input
  falls back to `Mux::generate_workspace_name()`.
- **Right-click actions:** open an `InputSelector`-style list overlay **in the
  terminal** (same family as the tab navigator) offering **Rename…**,
  **Close workspace**, **Switch here**. Rename chains into the input overlay then
  `Mux::rename_workspace(old, new)`; Close kills the windows returned by
  `Mux::iter_windows_in_workspace(name)`. No GPU-drawn popup.

### 6. Live updates (`termwindow/mod.rs`)

- Rebuild `WorkspaceSidebarState` in the same `update_title` path that rebuilds
  `TabBarState`.
- Repaint on the workspace `MuxNotification`s already whitelisted at
  `mod.rs:1316-1319` / `mod.rs:1524-1527`
  (`ActiveWorkspaceChanged`, `WindowWorkspaceChanged`, `WorkspaceRenamed`,
  `WindowCreated`, `WindowRemoved`). No new subscription required.

## Testing

- **Unit (`workspace_sidebar.rs`):** build state from a fake workspace list and
  assert ordering, active detection, presence of the `NewButton`, and hover
  flagging. Mirrors how `tabbar.rs` logic is exercised.
- **Geometry:** a focused test that `apply_dimensions` reduces terminal `cols`
  by the reserved width when the sidebar is enabled vs disabled.
- **Manual (per `CLAUDE.md`):**
  `wezterm-gui --config-file ./test-conf.lua start --always-new-process` with the
  flag enabled — create a couple of workspaces and verify switch/create/rename/
  close, and that pane content and the top tab bar shift right correctly. GPU
  rendering itself is not unit-testable, consistent with the rest of the GUI.

## Documentation

- Document `enable_workspace_sidebar`, `workspace_sidebar_width`,
  `mouse_wheel_scrolls_workspaces`, and the `ToggleWorkspaceSidebar` key
  assignment under `docs/` (config reference), per the repo convention that
  user-visible behavior ships with docs.

## Out of scope (future work)

- Right/configurable sidebar position.
- Per-entry status lines, counts, or previews.
- Dedicated `colors.workspace_sidebar` theming overrides.
- Drag-to-reorder workspaces.
