# Vertical Workspace Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, full-height vertical sidebar on the left of the WezTerm window that lists workspaces and lets the user click to switch, create (via a "+"), scroll between, and right-click for rename/close — complementing the existing horizontal tab bar.

**Architecture:** A native GUI element built on the same `box_model` element pipeline as the "fancy" tab bar. A logical `WorkspaceSidebarState` (pure, unit-tested) is rendered into a cached `ComputedElement`, painted over a reserved left strip. Horizontal space is reserved in `apply_dimensions` (mirroring how `tab_bar_height` is reserved on the vertical axis). Clicks/hover/scroll go through the existing `UIItem` hit-testing system; the "+" prompt and right-click menu are small `LineEditor`/menu overlays that dispatch native `KeyAssignment`s.

**Tech Stack:** Rust, WezTerm GUI (`wezterm-gui`), `config` crate (mlua-backed `FromDynamic`), `mux` crate, `termwiz` (overlays/line editor), euclid, the `box_model` micro-flexbox.

**Scope decisions (from the spec):**
- Enabled via `enable_workspace_sidebar` config + a `ToggleWorkspaceSidebar` key assignment. Off by default. No auto-hide.
- Entries show the workspace name only, with active highlight (hover styling via `hover_colors`).
- **Layout A** for the fancy tab bar (default): sidebar full height, tab bar shifted right. For the **retro** tab bar, the sidebar renders below the tab-bar strip (documented fallback — no retro-renderer changes).
- Actions: click-to-switch, scroll/relative-keys, "+" new-workspace prompt, right-click rename/close menu.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `config/src/config.rs` | Config schema | Add `enable_workspace_sidebar`, `workspace_sidebar_width`, `mouse_wheel_scrolls_workspaces` |
| `config/src/keyassignment.rs` | Key assignment enum | Add `ToggleWorkspaceSidebar`, `RenameWorkspace{..}`, `CloseWorkspace{..}` |
| `wezterm-gui/src/workspace_sidebar.rs` | **New.** Pure logical model + unit tests | Create |
| `wezterm-gui/src/termwindow/render/workspace_sidebar.rs` | **New.** Build/paint the element tree | Create |
| `wezterm-gui/src/overlay/workspace.rs` | **New.** Native "+" prompt + right-click action menu overlays | Create |
| `wezterm-gui/src/termwindow/mod.rs` | Window state, dispatch, rebuild, liveness | Add fields, `UIItemType` variant, assignment arms, `update_title` rebuild, notification handling, overlay launchers |
| `wezterm-gui/src/termwindow/resize.rs` | Reserve horizontal space | Add `left_sidebar_width()`, subtract in `apply_dimensions` |
| `wezterm-gui/src/termwindow/render/pane.rs` | Shift content origin | Offset `left_pixel_x` / `content_rect` / background x |
| `wezterm-gui/src/termwindow/render/fancy_tab_bar.rs` | Layout A tab-bar shift | Shift bounds + reduce widths |
| `wezterm-gui/src/termwindow/render/paint.rs` | Paint order | Insert `paint_workspace_sidebar` call |
| `wezterm-gui/src/termwindow/mouseevent.rs` | Hit-testing | Dispatch sidebar clicks/hover/scroll |
| `wezterm-gui/src/lib.rs` | Module registration | `mod workspace_sidebar;` |
| `wezterm-gui/src/overlay/mod.rs` | Module registration | `pub mod workspace;` |
| `wezterm-gui/src/termwindow/render/mod.rs` | Module registration | `mod workspace_sidebar;` |
| `docs/config/lua/config/*.md`, `docs/config/lua/keyassignment/*.md` | User docs | New pages |

**Build/verify commands used throughout:**
- Fast type-check a crate: `cargo check -p wezterm-gui` / `cargo check -p wezterm` (the `config` crate is pulled in transitively).
- Run a crate's tests: `cargo nextest run -p wezterm-gui` (or `cargo test -p wezterm-gui <name>` if nextest unavailable).
- Format gate (run before each commit): `cargo +nightly fmt`.
- Manual GUI run: `cargo run -p wezterm-gui -- --config-file ./test-conf.lua start --always-new-process`.

---

## Phase 1 — Config & key assignment plumbing

### Task 1: Add config options

**Files:**
- Modify: `config/src/config.rs` (near the tab-bar bools around line 482-493, and the `Dimension` fields)

- [ ] **Step 1: Add the three fields to `struct Config`**

In `config/src/config.rs`, immediately after the `mouse_wheel_scrolls_tabs` field (around line 486), add:

```rust
    /// When true, show a vertical workspace switcher sidebar on the left edge.
    #[dynamic(default)]
    pub enable_workspace_sidebar: bool,

    /// Width of the workspace sidebar.
    #[dynamic(try_from = "crate::units::PixelUnit", default = "default_workspace_sidebar_width")]
    pub workspace_sidebar_width: Dimension,

    /// When true, scrolling the mouse wheel over the workspace sidebar
    /// switches between workspaces.
    #[dynamic(default = "default_true")]
    pub mouse_wheel_scrolls_workspaces: bool,
```

- [ ] **Step 2: Add the default-width helper**

Near the other `Dimension` default helpers (the `default_one_cell` / `default_half_cell` block around line 1935-1941), add:

```rust
const fn default_workspace_sidebar_width() -> Dimension {
    Dimension::Pixels(180.)
}
```

- [ ] **Step 3: Type-check**

Run: `cargo check -p config`
Expected: PASS (no errors). If `Dimension` or `default_true` is not in scope, confirm the existing imports at `config/src/config.rs:20` (`use crate::units::Dimension;`) and `:25` cover them — they do.

- [ ] **Step 4: Commit**

```bash
cargo +nightly fmt
git add config/src/config.rs
git commit -m "config: add workspace_sidebar options"
```

---

### Task 2: Add `ToggleWorkspaceSidebar` key assignment + runtime state

**Files:**
- Modify: `config/src/keyassignment.rs` (the `KeyAssignment` enum, around line 610-614)
- Modify: `wezterm-gui/src/termwindow/mod.rs` (struct field ~393; init ~715; config-reload recompute ~1753; dispatch in `perform_key_assignment` ~2676)

- [ ] **Step 1: Add the enum variant**

In `config/src/keyassignment.rs`, inside `enum KeyAssignment` near `SwitchWorkspaceRelative(isize)` (line 614), add:

```rust
    ToggleWorkspaceSidebar,
```

- [ ] **Step 2: Add the runtime flag field to `TermWindow`**

In `wezterm-gui/src/termwindow/mod.rs`, next to `show_tab_bar: bool,` (line 393) add:

```rust
    show_workspace_sidebar: bool,
    workspace_sidebar: crate::workspace_sidebar::WorkspaceSidebarState,
    workspace_sidebar_computed: Option<box_model::ComputedElement>,
```

(These reference types created in Task 3 and Task 6; this task only compiles after Task 3 lands, so we finish wiring here but do the type-check at the end of Task 6. To keep this task self-contained and compiling, add the field but temporarily default the state — see Step 3.)

- [ ] **Step 3: Initialize the fields in the constructor**

In `mod.rs`, where `show_tab_bar,` and `tab_bar: TabBarState::default(),` are set (around lines 715-718), add alongside them:

```rust
            show_workspace_sidebar: config.enable_workspace_sidebar,
            workspace_sidebar: crate::workspace_sidebar::WorkspaceSidebarState::default(),
            workspace_sidebar_computed: None,
```

- [ ] **Step 4: Recompute the flag on config reload**

In `mod.rs`, right after the `self.show_tab_bar = ...` reload logic (around lines 1753-1755), add:

```rust
        self.show_workspace_sidebar = config.enable_workspace_sidebar;
```

(Place it after the existing `show_tab_bar` reassignment block so it runs on every reload.)

- [ ] **Step 5: Dispatch the toggle in `perform_key_assignment`**

In `mod.rs`, in the big `match assignment` inside `perform_key_assignment` (after the `ToggleFullScreen` arm around line 2678), add:

```rust
            ToggleWorkspaceSidebar => {
                self.show_workspace_sidebar = !self.show_workspace_sidebar;
                self.workspace_sidebar_computed.take();
                // Re-reserve/-release the left strip and recompute cols.
                let dims = self.dimensions;
                self.apply_dimensions(&dims, None);
                if let Some(window) = self.window.as_ref() {
                    window.invalidate();
                }
            }
```

- [ ] **Step 6: Verify `apply_dimensions` signature**

Run: `cargo check -p wezterm-gui 2>&1 | head -40`
Expected: This task references `apply_dimensions(&dims, None)` and the Task-3 type. Until Task 3 exists it will fail on the unresolved `workspace_sidebar` module — that is expected. Confirm the ONLY errors are (a) unresolved `crate::workspace_sidebar` and (b) any `apply_dimensions` arity mismatch. If `apply_dimensions` has a different signature, open `wezterm-gui/src/termwindow/resize.rs:131` and match it (it is `pub fn apply_dimensions(&mut self, dimensions: &Dimensions, scale_changed_cells: Option<RowsAndCols>, ...)`; pass `None` for the optional cells arg, and default any trailing args to match the existing internal callers just below the definition).

- [ ] **Step 7: Commit (after Task 3 makes it compile)**

Defer the commit for this task until Task 3 lands so the tree compiles. When green:

```bash
cargo +nightly fmt
git add config/src/keyassignment.rs wezterm-gui/src/termwindow/mod.rs
git commit -m "gui: add ToggleWorkspaceSidebar assignment and runtime flag"
```

---

## Phase 2 — Logical state model (TDD)

### Task 3: `WorkspaceSidebarState`

**Files:**
- Create: `wezterm-gui/src/workspace_sidebar.rs`
- Modify: `wezterm-gui/src/lib.rs` (add `mod workspace_sidebar;`)

- [ ] **Step 1: Register the module**

In `wezterm-gui/src/lib.rs`, add alongside the other `mod` declarations (near `mod tabbar;` if present, else with the other modules):

```rust
mod workspace_sidebar;
```

- [ ] **Step 2: Write the failing test**

Create `wezterm-gui/src/workspace_sidebar.rs`:

```rust
//! Logical model for the vertical workspace switcher sidebar.
//! This module is windowing-agnostic and unit-testable: it turns a list of
//! workspace names + the active name into an ordered list of entries that the
//! renderer (termwindow/render/workspace_sidebar.rs) draws.

/// Identifies a clickable region in the sidebar, carried in `UIItemType`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum WorkspaceSidebarItem {
    /// A workspace row; `index` matches the position in the built entry list's
    /// workspace entries (also the index into the sorted workspace list).
    Workspace { index: usize },
    /// The trailing "+" new-workspace button.
    NewButton,
}

#[derive(Clone, Debug, PartialEq)]
pub struct WorkspaceSidebarEntry {
    /// Display name (empty for the NewButton).
    pub name: String,
    /// Whether this entry is the active workspace.
    pub active: bool,
    pub item: WorkspaceSidebarItem,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct WorkspaceSidebarState {
    items: Vec<WorkspaceSidebarEntry>,
}

impl WorkspaceSidebarState {
    /// Build the sidebar model from the sorted workspace list and the active
    /// workspace name. A trailing NewButton entry is always appended.
    pub fn new(workspaces: &[String], active: &str) -> Self {
        let mut items = Vec::with_capacity(workspaces.len() + 1);
        for (index, name) in workspaces.iter().enumerate() {
            items.push(WorkspaceSidebarEntry {
                name: name.clone(),
                active: name == active,
                item: WorkspaceSidebarItem::Workspace { index },
            });
        }
        items.push(WorkspaceSidebarEntry {
            name: String::new(),
            active: false,
            item: WorkspaceSidebarItem::NewButton,
        });
        Self { items }
    }

    pub fn items(&self) -> &[WorkspaceSidebarEntry] {
        &self.items
    }

    /// The workspace name for a given `Workspace { index }`, if present.
    pub fn workspace_name(&self, index: usize) -> Option<&str> {
        self.items.iter().find_map(|e| match e.item {
            WorkspaceSidebarItem::Workspace { index: i } if i == index => Some(e.name.as_str()),
            _ => None,
        })
    }
}

#[cfg(test)]
mod test {
    use super::*;

    fn names(v: &[&str]) -> Vec<String> {
        v.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn builds_entries_in_order_with_active_and_new_button() {
        let ws = names(&["default", "project", "ssh"]);
        let state = WorkspaceSidebarState::new(&ws, "project");
        let items = state.items();

        // 3 workspaces + 1 new button
        assert_eq!(items.len(), 4);

        assert_eq!(items[0].name, "default");
        assert_eq!(items[0].active, false);
        assert_eq!(items[0].item, WorkspaceSidebarItem::Workspace { index: 0 });

        assert_eq!(items[1].name, "project");
        assert_eq!(items[1].active, true);
        assert_eq!(items[1].item, WorkspaceSidebarItem::Workspace { index: 1 });

        assert_eq!(items[2].name, "ssh");
        assert_eq!(items[2].active, false);

        assert_eq!(items[3].item, WorkspaceSidebarItem::NewButton);
        assert_eq!(items[3].active, false);
    }

    #[test]
    fn workspace_name_lookup() {
        let ws = names(&["a", "b"]);
        let state = WorkspaceSidebarState::new(&ws, "a");
        assert_eq!(state.workspace_name(1), Some("b"));
        assert_eq!(state.workspace_name(9), None);
    }

    #[test]
    fn empty_list_still_has_new_button() {
        let state = WorkspaceSidebarState::new(&[], "");
        assert_eq!(state.items().len(), 1);
        assert_eq!(state.items()[0].item, WorkspaceSidebarItem::NewButton);
    }
}
```

- [ ] **Step 3: Run the test to verify it passes**

Run: `cargo nextest run -p wezterm-gui workspace_sidebar`
Expected: 3 tests PASS. (The logic and tests are written together; the "failing" state is only that the module didn't exist. If `cargo nextest` is unavailable, use `cargo test -p wezterm-gui workspace_sidebar`.)

- [ ] **Step 4: Type-check the whole crate (Task 2 wiring now resolves)**

Run: `cargo check -p wezterm-gui 2>&1 | head -40`
Expected: The `crate::workspace_sidebar` errors from Task 2 are gone. Remaining errors should only concern `workspace_sidebar_computed`'s use in Task 6 (it is only read there) — a bare `Option<ComputedElement>` field with no readers compiles fine, so the crate should now build. Fix any leftover import issues.

- [ ] **Step 5: Commit (folds in Task 2)**

```bash
cargo +nightly fmt
git add wezterm-gui/src/workspace_sidebar.rs wezterm-gui/src/lib.rs config/src/keyassignment.rs wezterm-gui/src/termwindow/mod.rs
git commit -m "gui: add WorkspaceSidebarState model and toggle wiring"
```

---

## Phase 3 — Reserve the left strip (geometry)

### Task 4: `left_sidebar_width()` + reserve width in `apply_dimensions`

**Files:**
- Modify: `wezterm-gui/src/termwindow/resize.rs` (add helper; edit both branches of `apply_dimensions`, lines ~166-288)

- [ ] **Step 1: Add the width helper**

In `wezterm-gui/src/termwindow/resize.rs`, add a method on `TermWindow` (place near the top of the `impl` that contains `apply_dimensions`, or just above `apply_dimensions`):

```rust
    /// Pixel width reserved on the left for the workspace sidebar (0 when hidden).
    pub fn left_sidebar_width(&self) -> f32 {
        if self.show_workspace_sidebar {
            let context = config::DimensionContext {
                dpi: self.dimensions.dpi as f32,
                pixel_max: self.dimensions.pixel_width as f32,
                pixel_cell: self.render_metrics.cell_size.width as f32,
            };
            self.config
                .workspace_sidebar_width
                .evaluate_as_pixels(context)
        } else {
            0.
        }
    }
```

(If `DimensionContext` is already imported in this file under a different path, reuse that import instead of the fully-qualified `config::DimensionContext`. The `Dimension`/`DimensionContext` types live in the `config` crate — `config/src/units.rs`.)

- [ ] **Step 2: Compute the reserved width once, next to `tab_bar_height`**

In `apply_dimensions`, right after the `tab_bar_height` block (resize.rs:166-170) and the `let border = self.get_os_border();` line (172), add:

```rust
        let sidebar_width = self.left_sidebar_width();
```

- [ ] **Step 3: Add it to the width budget (scale-changed branch)**

In the scale-changed branch, find `pixel_width` (resize.rs:209-211):

```rust
            let pixel_width = (cols * self.render_metrics.cell_size.width as usize)
                + (padding_left + padding_right)
                + (border.left + border.right).get() as usize;
```

Change it to:

```rust
            let pixel_width = (cols * self.render_metrics.cell_size.width as usize)
                + (padding_left + padding_right)
                + (border.left + border.right).get() as usize
                + sidebar_width as usize;
```

- [ ] **Step 4: Subtract it from available width (resize branch)**

In the resize branch, find `avail_width` (resize.rs:250-253):

```rust
            let avail_width = dimensions.pixel_width.saturating_sub(
                (padding_left + padding_right) as usize
                    + (border.left + border.right).get() as usize,
            );
```

Change it to:

```rust
            let avail_width = dimensions
                .pixel_width
                .saturating_sub(
                    (padding_left + padding_right) as usize
                        + (border.left + border.right).get() as usize,
                )
                .saturating_sub(sidebar_width as usize);
```

- [ ] **Step 5: Type-check**

Run: `cargo check -p wezterm-gui 2>&1 | head -40`
Expected: PASS. `sidebar_width` is used in both branches. If the scale-changed branch does not see `sidebar_width` (scope), move the `let sidebar_width = ...` binding to just before the branch split so both branches capture it.

- [ ] **Step 6: Add a geometry regression test**

Terminal `cols` are derived from window pixels. Add a focused test asserting the reserved width reduces `cols`. In `wezterm-gui/src/termwindow/resize.rs`, at the bottom, add:

```rust
#[cfg(test)]
mod sidebar_geometry_test {
    // Pure arithmetic mirror of the avail_width -> cols computation in
    // apply_dimensions, guarding the "reserve reduces cols" invariant.
    fn cols_for(pixel_width: usize, padding: usize, border: usize, sidebar: usize, cell_w: usize) -> usize {
        let avail = pixel_width
            .saturating_sub(padding + border)
            .saturating_sub(sidebar);
        avail / cell_w
    }

    #[test]
    fn sidebar_reserves_columns() {
        let base = cols_for(1000, 0, 0, 0, 10);
        let with_sidebar = cols_for(1000, 0, 0, 180, 10);
        assert_eq!(base, 100);
        assert_eq!(with_sidebar, 82);
        assert!(with_sidebar < base);
    }
}
```

- [ ] **Step 7: Run the test**

Run: `cargo nextest run -p wezterm-gui sidebar_reserves_columns`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cargo +nightly fmt
git add wezterm-gui/src/termwindow/resize.rs
git commit -m "gui: reserve left strip width for workspace sidebar"
```

---

### Task 5: Shift pane content & tab-bar origin (Layout A)

**Files:**
- Modify: `wezterm-gui/src/termwindow/render/pane.rs` (classic `left_pixel_x` ~340; box-model `content_rect`/background x ~606-651)
- Modify: `wezterm-gui/src/termwindow/render/fancy_tab_bar.rs` (bounds ~437-446; root `min_width` ~416; `max_tab_width` ~301)
- Modify: `wezterm-gui/src/termwindow/mod.rs` (tab-bar cell width in `update_title_impl` ~1992)

- [ ] **Step 1: Shift the classic pane content origin**

In `wezterm-gui/src/termwindow/render/pane.rs`, find `left_pixel_x` (pane.rs:340-342):

```rust
            let left_pixel_x = padding_left
                + border.left.get() as f32
                + (pos.left as f32 * self.render_metrics.cell_size.width as f32);
```

Change to:

```rust
            let left_pixel_x = self.left_sidebar_width()
                + padding_left
                + border.left.get() as f32
                + (pos.left as f32 * self.render_metrics.cell_size.width as f32);
```

- [ ] **Step 2: Shift the classic leftmost background edge**

In `paint_pane`, the background x for the leftmost pane (pane.rs:112-116) currently starts at `0.` when `pos.left == 0`:

```rust
            let (x, width_delta) = if pos.left == 0 {
                (
                    0.,
                    padding_left + border.left.get() as f32 + (cell_width / 2.0),
                )
            } else {
```

Change the `0.,` to `self.left_sidebar_width(),` so the pane background does not underlap the sidebar:

```rust
            let (x, width_delta) = if pos.left == 0 {
                (
                    self.left_sidebar_width(),
                    padding_left + border.left.get() as f32 + (cell_width / 2.0),
                )
            } else {
```

- [ ] **Step 3: Shift the box-model pane path**

In `build_pane` (pane.rs), apply the same two shifts:

- The `(x, width_delta)` for `pos.left == 0` (pane.rs:606-610): change `0.,` to `self.left_sidebar_width(),`.
- The `content_rect` x origin (pane.rs:649-651):

```rust
        let content_rect = euclid::rect(
            padding_left + border.left.get() as f32 - (cell_width / 2.0)
                + (pos.left as f32 * cell_width),
            top_pixel_y + (pos.top as f32 * cell_height) - (cell_height / 2.0),
            pos.width as f32 * cell_width,
            pos.height as f32 * cell_height,
        );
```

Change the first argument to add the sidebar width:

```rust
        let content_rect = euclid::rect(
            self.left_sidebar_width() + padding_left + border.left.get() as f32
                - (cell_width / 2.0)
                + (pos.left as f32 * cell_width),
            top_pixel_y + (pos.top as f32 * cell_height) - (cell_height / 2.0),
            pos.width as f32 * cell_width,
            pos.height as f32 * cell_height,
        );
```

- [ ] **Step 4: Reduce the tab-bar cell width (both renderers agree on width)**

In `wezterm-gui/src/termwindow/mod.rs`, in `update_title_impl` the first argument to `TabBarState::new` (mod.rs:1992) is the tab-bar width in cells:

```rust
        let new_tab_bar = TabBarState::new(
            self.dimensions.pixel_width / self.render_metrics.cell_size.width as usize,
```

Change it to subtract the reserved sidebar cells:

```rust
        let sidebar_width = self.left_sidebar_width() as usize;
        let new_tab_bar = TabBarState::new(
            (self.dimensions.pixel_width.saturating_sub(sidebar_width))
                / self.render_metrics.cell_size.width as usize,
```

- [ ] **Step 5: Shift the fancy tab bar to the right of the sidebar (Layout A)**

In `wezterm-gui/src/termwindow/render/fancy_tab_bar.rs`:

(a) `max_tab_width` (fancy_tab_bar.rs:301-303) uses `self.dimensions.pixel_width`. Reduce it. Just before that block add `let sidebar_width = self.left_sidebar_width();` and change:

```rust
    let max_tab_width = ((self.dimensions.pixel_width as f32 / num_tabs)
        - (1.5 * metrics.cell_size.width as f32))
    .max(0.);
```

to:

```rust
    let sidebar_width = self.left_sidebar_width();
    let max_tab_width = (((self.dimensions.pixel_width as f32 - sidebar_width) / num_tabs)
        - (1.5 * metrics.cell_size.width as f32))
    .max(0.);
```

(b) Root element `min_width` (fancy_tab_bar.rs:416):

```rust
        .min_width(Some(Dimension::Pixels(self.dimensions.pixel_width as f32)))
```

to:

```rust
        .min_width(Some(Dimension::Pixels(
            self.dimensions.pixel_width as f32 - sidebar_width,
        )))
```

(c) The compute `bounds` (fancy_tab_bar.rs:437-442):

```rust
        bounds: euclid::rect(
            border.left.get() as f32,
            0.,
            self.dimensions.pixel_width as f32 - (border.left + border.right).get() as f32,
            tab_bar_height,
        ),
```

to:

```rust
        bounds: euclid::rect(
            border.left.get() as f32 + sidebar_width,
            0.,
            self.dimensions.pixel_width as f32
                - (border.left + border.right).get() as f32
                - sidebar_width,
            tab_bar_height,
        ),
```

- [ ] **Step 6: Type-check**

Run: `cargo check -p wezterm-gui 2>&1 | head -40`
Expected: PASS. If `left_sidebar_width` is not resolvable from `fancy_tab_bar.rs`/`pane.rs`, confirm it is a `pub fn` on `TermWindow` (Task 4 Step 1) — all these files are methods on the same `TermWindow` via `impl crate::TermWindow` / `impl super::TermWindow`, so `self.left_sidebar_width()` resolves.

- [ ] **Step 7: Commit**

```bash
cargo +nightly fmt
git add wezterm-gui/src/termwindow/render/pane.rs wezterm-gui/src/termwindow/render/fancy_tab_bar.rs wezterm-gui/src/termwindow/mod.rs
git commit -m "gui: shift pane and fancy tab bar right of the sidebar strip"
```

Note: no visible sidebar yet (nothing paints it), but with `enable_workspace_sidebar=true` the terminal content and fancy tab bar now start ~180px in, leaving an empty reserved strip. This is a good manual checkpoint (run the app with the flag on).

---

## Phase 4 — Render the sidebar & keep it live

### Task 6: Build & paint the sidebar element tree

**Files:**
- Create: `wezterm-gui/src/termwindow/render/workspace_sidebar.rs`
- Modify: `wezterm-gui/src/termwindow/render/mod.rs` (add `mod workspace_sidebar;`)
- Modify: `wezterm-gui/src/termwindow/mod.rs` (add `UIItemType::WorkspaceSidebar`; rebuild state in `update_title_impl`)
- Modify: `wezterm-gui/src/termwindow/render/paint.rs` (paint call in `paint_pass`)

- [ ] **Step 1: Add the `UIItemType` variant**

In `wezterm-gui/src/termwindow/mod.rs`, in `enum UIItemType` (lines 154-162), add:

```rust
    WorkspaceSidebar(crate::workspace_sidebar::WorkspaceSidebarItem),
```

- [ ] **Step 2: Register the render submodule**

In `wezterm-gui/src/termwindow/render/mod.rs`, add with the other `mod` lines:

```rust
mod workspace_sidebar;
```

- [ ] **Step 3: Create the build/paint file**

Create `wezterm-gui/src/termwindow/render/workspace_sidebar.rs`:

```rust
use crate::customglyph::*;
use crate::termwindow::box_model::*;
use crate::termwindow::{UIItem, UIItemType};
use crate::utilsprites::RenderMetrics;
use crate::workspace_sidebar::WorkspaceSidebarItem;
use config::{Dimension, DimensionContext};
use window::color::LinearRgba;

/// "+" plus glyph for the new-workspace button (two outline strokes).
const PLUS_BUTTON: &[Poly] = &[
    Poly {
        path: &[
            PolyCommand::MoveTo(BlockCoord::Frac(1, 2), BlockCoord::Zero),
            PolyCommand::LineTo(BlockCoord::Frac(1, 2), BlockCoord::One),
        ],
        intensity: BlockAlpha::Full,
        style: PolyStyle::Outline,
    },
    Poly {
        path: &[
            PolyCommand::MoveTo(BlockCoord::Zero, BlockCoord::Frac(1, 2)),
            PolyCommand::LineTo(BlockCoord::One, BlockCoord::Frac(1, 2)),
        ],
        intensity: BlockAlpha::Full,
        style: PolyStyle::Outline,
    },
];

impl crate::TermWindow {
    pub fn invalidate_workspace_sidebar(&mut self) {
        self.workspace_sidebar_computed.take();
    }

    pub fn build_workspace_sidebar(&self) -> anyhow::Result<ComputedElement> {
        let font = self.fonts.title_font()?;
        let metrics = RenderMetrics::with_font_metrics(&font.metrics());
        let sidebar_width = self.left_sidebar_width();
        let border = self.get_os_border();

        // The fancy tab bar occupies the top strip to the RIGHT of the sidebar.
        // When the retro tab bar is in use we cannot shift it, so start the
        // sidebar below the tab-bar strip in that case (documented fallback).
        let top_inset = if self.show_tab_bar && !self.config.use_fancy_tab_bar {
            self.tab_bar_pixel_height().unwrap_or(0.)
        } else {
            0.
        };

        // Colors derived from the existing palette so we need no new config.
        let frame = &self.config.window_frame;
        let bg = if self.focused.is_some() {
            frame.active_titlebar_bg
        } else {
            frame.inactive_titlebar_bg
        }
        .to_linear();
        let fg = if self.focused.is_some() {
            frame.active_titlebar_fg
        } else {
            frame.inactive_titlebar_fg
        }
        .to_linear();

        let tab_bar_colors = self
            .config
            .resolved_palette
            .tab_bar
            .clone()
            .unwrap_or_default();
        let active_bg = tab_bar_colors.active_tab.bg_color.to_linear();
        let active_fg = tab_bar_colors.active_tab.fg_color.to_linear();
        let inactive_bg = bg;
        let inactive_fg = fg;
        let hover_bg = tab_bar_colors.inactive_tab_hover.bg_color.to_linear();
        let hover_fg = tab_bar_colors.inactive_tab_hover.fg_color.to_linear();

        let make_colors = |bg: LinearRgba, fg: LinearRgba| ElementColors {
            border: BorderColor::default(),
            bg: bg.into(),
            text: fg.into(),
        };

        let row_padding = BoxDimension {
            left: Dimension::Cells(0.5),
            right: Dimension::Cells(0.5),
            top: Dimension::Cells(0.25),
            bottom: Dimension::Cells(0.25),
        };

        let mut children = vec![];
        for entry in self.workspace_sidebar.items() {
            let element = match &entry.item {
                WorkspaceSidebarItem::Workspace { .. } => {
                    let (row_bg, row_fg) = if entry.active {
                        (active_bg, active_fg)
                    } else {
                        (inactive_bg, inactive_fg)
                    };
                    Element::new(&font, ElementContent::Text(entry.name.clone()))
                        .display(DisplayType::Block)
                        .item_type(UIItemType::WorkspaceSidebar(entry.item.clone()))
                        .padding(row_padding)
                        .min_width(Some(Dimension::Pixels(sidebar_width)))
                        .colors(make_colors(row_bg, row_fg))
                        .hover_colors(Some(make_colors(hover_bg, hover_fg)))
                }
                WorkspaceSidebarItem::NewButton => Element::new(
                    &font,
                    ElementContent::Poly {
                        line_width: metrics.underline_height.max(2),
                        poly: SizedPoly {
                            poly: PLUS_BUTTON,
                            width: Dimension::Pixels(metrics.cell_size.height as f32 / 2.),
                            height: Dimension::Pixels(metrics.cell_size.height as f32 / 2.),
                        },
                    },
                )
                .display(DisplayType::Block)
                .vertical_align(VerticalAlign::Middle)
                .item_type(UIItemType::WorkspaceSidebar(entry.item.clone()))
                .padding(row_padding)
                .min_width(Some(Dimension::Pixels(sidebar_width)))
                .colors(make_colors(inactive_bg, inactive_fg))
                .hover_colors(Some(make_colors(hover_bg, hover_fg))),
            };
            children.push(element);
        }

        let root = Element::new(&font, ElementContent::Children(children))
            .display(DisplayType::Block)
            .min_width(Some(Dimension::Pixels(sidebar_width)))
            .min_height(Some(Dimension::Pixels(
                self.dimensions.pixel_height as f32 - top_inset,
            )))
            .colors(make_colors(bg, fg));

        let computed = self.compute_element(
            &LayoutContext {
                height: DimensionContext {
                    dpi: self.dimensions.dpi as f32,
                    pixel_max: self.dimensions.pixel_height as f32,
                    pixel_cell: metrics.cell_size.height as f32,
                },
                width: DimensionContext {
                    dpi: self.dimensions.dpi as f32,
                    pixel_max: self.dimensions.pixel_width as f32,
                    pixel_cell: metrics.cell_size.width as f32,
                },
                bounds: euclid::rect(
                    border.left.get() as f32,
                    border.top.get() as f32 + top_inset,
                    sidebar_width,
                    self.dimensions.pixel_height as f32
                        - (border.top + border.bottom).get() as f32
                        - top_inset,
                ),
                metrics: &metrics,
                gl_state: self.render_state.as_ref().unwrap(),
                zindex: 10,
            },
            &root,
        )?;

        Ok(computed)
    }

    pub fn paint_workspace_sidebar(&self) -> anyhow::Result<Vec<UIItem>> {
        let computed = self
            .workspace_sidebar_computed
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("paint_workspace_sidebar called but cache is None"))?;
        let ui_items = computed.ui_items();
        let gl_state = self.render_state.as_ref().unwrap();
        self.render_element(computed, gl_state, None)?;
        Ok(ui_items)
    }
}
```

- [ ] **Step 4: Rebuild the state in `update_title_impl`**

In `wezterm-gui/src/termwindow/mod.rs`, at the end of `update_title_impl` (right after the `if new_tab_bar != self.tab_bar { ... }` block, around line 2012), add:

```rust
        let mux = Mux::get();
        let workspaces = mux.iter_workspaces();
        let active = mux.active_workspace();
        let new_sidebar =
            crate::workspace_sidebar::WorkspaceSidebarState::new(&workspaces, &active);
        if new_sidebar != self.workspace_sidebar {
            self.workspace_sidebar = new_sidebar;
            self.invalidate_workspace_sidebar();
            if let Some(window) = self.window.as_ref() {
                window.invalidate();
            }
        }
```

(`Mux` is already imported and used earlier in this function; reuse the existing `mux` binding at the top of `update_title_impl` instead of re-fetching if it is still in scope — if so, drop the `let mux = Mux::get();` line here.)

- [ ] **Step 5: Insert the paint call**

In `wezterm-gui/src/termwindow/render/paint.rs`, in `paint_pass`, right after the tab-bar block (paint.rs:271-273) and before `self.paint_window_borders(...)` (275):

```rust
        if self.show_workspace_sidebar {
            if self.workspace_sidebar_computed.is_none() {
                let sidebar = self.build_workspace_sidebar()?;
                self.workspace_sidebar_computed.replace(sidebar);
            }
            self.ui_items.append(&mut self.paint_workspace_sidebar()?);
        }
```

- [ ] **Step 6: Type-check**

Run: `cargo check -p wezterm-gui 2>&1 | head -60`
Expected: PASS. Likely fix-ups:
- Field/method names on `TabBarColors` (e.g. `active_tab`, `inactive_tab_hover`, `.bg_color`) — verify against `config/src/color.rs` (`struct TabBarColors`, `struct TabBarColor`). Adjust names to the actual fields if the check complains.
- `frame.active_titlebar_bg` etc. — verify field names on `config.window_frame` (`struct WindowFrameConfig` in `config/src/window.rs`). `.to_linear()` returns `LinearRgba`.
- `self.config.resolved_palette.tab_bar` type — confirm it is `Option<TabBarColors>`.
Resolve each by matching the real field name reported by the compiler.

- [ ] **Step 7: Manual verification**

Run: `cargo run -p wezterm-gui -- --config-file ./test-conf.lua start --always-new-process`
where `test-conf.lua` contains at least:

```lua
return {
  enable_workspace_sidebar = true,
  keys = {
    { key = 'w', mods = 'CTRL|SHIFT', action = wezterm.action.SwitchToWorkspace { name = 'second' } },
    { key = 's', mods = 'CTRL|SHIFT', action = wezterm.action.ToggleWorkspaceSidebar },
  },
}
```

Expected: a left strip shows `default` (highlighted) and a `+` row. Press `Ctrl+Shift+W` to create `second`; the sidebar should list `default`, `second`, `+`, with `second` highlighted. `Ctrl+Shift+S` hides/shows the strip and the content reflows.

- [ ] **Step 8: Commit**

```bash
cargo +nightly fmt
git add wezterm-gui/src/termwindow/render/workspace_sidebar.rs wezterm-gui/src/termwindow/render/mod.rs wezterm-gui/src/termwindow/mod.rs wezterm-gui/src/termwindow/render/paint.rs
git commit -m "gui: render the workspace sidebar strip"
```

---

### Task 7: Keep the sidebar live on workspace changes

**Files:**
- Modify: `wezterm-gui/src/termwindow/mod.rs` (window-side `MuxNotification` handler ~1315-1321; mux-side callback early-return ~1517-1533)

- [ ] **Step 1: Make the window react to workspace notifications**

In `wezterm-gui/src/termwindow/mod.rs`, the window-side handler currently no-ops these (mod.rs:1315-1321):

```rust
                MuxNotification::PaneAdded(_)
                | MuxNotification::WorkspaceRenamed { .. }
                | MuxNotification::PaneRemoved(_)
                | MuxNotification::WindowWorkspaceChanged(_)
                | MuxNotification::ActiveWorkspaceChanged(_)
                | MuxNotification::Empty
                | MuxNotification::WindowCreated(_) => {}
```

Split the workspace-related variants out to trigger a title/sidebar refresh:

```rust
                MuxNotification::WorkspaceRenamed { .. }
                | MuxNotification::WindowWorkspaceChanged(_)
                | MuxNotification::ActiveWorkspaceChanged(_)
                | MuxNotification::WindowCreated(_) => {
                    self.update_title();
                }
                MuxNotification::PaneAdded(_)
                | MuxNotification::PaneRemoved(_)
                | MuxNotification::Empty => {}
```

- [ ] **Step 2: Let those notifications reach the window**

In the mux-side `mux_pane_output_event_callback`, these variants `return true` early (mod.rs:1517-1533), so they never call `window.notify(...)`. Remove the three workspace variants (and `WindowCreated`) from that early-return arm so they fall through to `window.notify(TermWindowNotif::MuxNotification(n))` at the end of the function:

Before:

```rust
            | MuxNotification::AssignClipboard { .. }
            | MuxNotification::SaveToDownloads { .. }
            | MuxNotification::WindowCreated(_)
            | MuxNotification::ActiveWorkspaceChanged(_)
            | MuxNotification::WorkspaceRenamed { .. }
            | MuxNotification::Empty
            | MuxNotification::WindowWorkspaceChanged(_) => return true,
```

After:

```rust
            | MuxNotification::AssignClipboard { .. }
            | MuxNotification::SaveToDownloads { .. }
            | MuxNotification::Empty => return true,
```

(Leave `WindowCreated`, `ActiveWorkspaceChanged`, `WorkspaceRenamed`, `WindowWorkspaceChanged` to fall through to `window.notify`. Keep `Empty` in the early-return.)

- [ ] **Step 3: Type-check**

Run: `cargo check -p wezterm-gui 2>&1 | head -40`
Expected: PASS. Match arms must remain exhaustive; if the compiler reports a non-exhaustive or unreachable arm, adjust the grouping so every `MuxNotification` variant is still covered exactly once.

- [ ] **Step 4: Manual verification (liveness across windows)**

Run the app with two workspaces. Open a second GUI window (`Ctrl+Shift+N`) so both windows share the mux. Create a workspace in one; confirm the OTHER window's sidebar updates its list without needing focus/click. Confirm switching still works and there is no repaint storm (CPU stays idle when nothing changes).

- [ ] **Step 5: Commit**

```bash
cargo +nightly fmt
git add wezterm-gui/src/termwindow/mod.rs
git commit -m "gui: refresh workspace sidebar on mux workspace changes"
```

---

## Phase 5 — Mouse & scroll interaction

### Task 8: Click to switch, hover, scroll

**Files:**
- Modify: `wezterm-gui/src/termwindow/mouseevent.rs` (dispatch in `mouse_event_ui_item` ~357-386; new handler)

- [ ] **Step 1: Route the new UIItem type**

In `wezterm-gui/src/termwindow/mouseevent.rs`, in `mouse_event_ui_item` where it matches on `UIItemType` (around lines 357-386), add an arm alongside `UIItemType::TabBar(item) => ...`:

```rust
            UIItemType::WorkspaceSidebar(item) => {
                self.mouse_event_workspace_sidebar(item.clone(), &event, pane);
            }
```

(Match the surrounding arms' exact call shape — some pass `&event`, some `event.clone()`; mirror the `TabBar` arm in the same function.)

- [ ] **Step 2: Implement the handler**

Add this method in `mouseevent.rs` (near `mouse_event_tab_bar`):

```rust
    pub fn mouse_event_workspace_sidebar(
        &mut self,
        item: crate::workspace_sidebar::WorkspaceSidebarItem,
        event: &MouseEvent,
        pane: Arc<dyn Pane>,
    ) {
        use crate::workspace_sidebar::WorkspaceSidebarItem::*;
        use config::keyassignment::KeyAssignment;
        use window::{MouseButtons as WMB, MouseEventKind as WMEK, MousePress};

        match event.kind {
            WMEK::Press(MousePress::Left) => match item {
                Workspace { index } => {
                    if let Some(name) = self.workspace_sidebar.workspace_name(index) {
                        let name = name.to_string();
                        let _ = self.perform_key_assignment(
                            &pane,
                            &KeyAssignment::SwitchToWorkspace {
                                name: Some(name),
                                spawn: None,
                            },
                        );
                    }
                }
                NewButton => {
                    self.prompt_new_workspace();
                }
            },
            WMEK::Press(MousePress::Right) => {
                if let Workspace { index } = item {
                    if let Some(name) = self.workspace_sidebar.workspace_name(index) {
                        let name = name.to_string();
                        self.show_workspace_actions(name);
                    }
                }
            }
            WMEK::VertWheel(n) => {
                if self.config.mouse_wheel_scrolls_workspaces {
                    let _ = self.perform_key_assignment(
                        &pane,
                        &KeyAssignment::SwitchWorkspaceRelative(if n < 1 { 1 } else { -1 }),
                    );
                }
            }
            _ => {}
        }

        // Silence unused import warning if MouseButtons is not needed here.
        let _ = std::marker::PhantomData::<WMB>;
    }
```

(Hover styling needs no code here: `render_element` already swaps to `hover_colors` based on `self.current_mouse_event` vs the element bounds. `prompt_new_workspace` and `show_workspace_actions` are added in Phase 6/7 — this task will not fully compile until Task 10 provides at least `prompt_new_workspace`. To keep this task green on its own, temporarily stub the two calls with `// TODO` bodies is NOT allowed; instead land Task 8 together with Task 10/11 and commit once green. Reorder: implement Task 10's `prompt_new_workspace` and Task 11's `show_workspace_actions` method signatures first if executing strictly task-by-task.)

- [ ] **Step 3: Verify import/paths**

Run: `cargo check -p wezterm-gui 2>&1 | head -40`
Expected: Errors only for the not-yet-defined `prompt_new_workspace` / `show_workspace_actions`. Fix the mouse-event enum paths (`MouseEventKind`, `MousePress`, `VertWheel`) to match the exact names used by the existing `mouse_event_tab_bar` (copy its `use`/match style verbatim — it already handles `WMEK::Press`, `WMEK::VertWheel(n)`, `MousePress::Left/Right`).

- [ ] **Step 4: Commit (once Phase 6/7 land)**

```bash
cargo +nightly fmt
git add wezterm-gui/src/termwindow/mouseevent.rs
git commit -m "gui: handle workspace sidebar clicks, hover, and scroll"
```

---

## Phase 6 — "+" new-workspace prompt

### Task 9: Native name-prompt overlay

**Files:**
- Create: `wezterm-gui/src/overlay/workspace.rs`
- Modify: `wezterm-gui/src/overlay/mod.rs` (add `pub mod workspace;`)
- Modify: `wezterm-gui/src/termwindow/mod.rs` (add `prompt_new_workspace`)

- [ ] **Step 1: Register the overlay module**

In `wezterm-gui/src/overlay/mod.rs`, add:

```rust
pub mod workspace;
```

- [ ] **Step 2: Write the prompt overlay**

Create `wezterm-gui/src/overlay/workspace.rs`:

```rust
use crate::termwindow::TermWindowNotif;
use config::keyassignment::KeyAssignment;
use mux::pane::PaneId;
use termwiz::lineedit::{line_editor_terminal, LineEditor, NopLineEditorHost};
use termwiz::terminal::Terminal;
use wezterm_term::TermWizTerminal;

/// Reads a workspace name on the overlay thread, then dispatches
/// SwitchToWorkspace on the main thread. Empty input auto-generates a name.
pub fn prompt_workspace_name(
    mut term: TermWizTerminal,
    window: ::window::Window,
    pane_id: PaneId,
) -> anyhow::Result<()> {
    term.no_grab_mouse_in_raw_mode();
    term.render(&[termwiz::surface::Change::Text(
        "Enter a name for the new workspace (blank = auto):\r\n".to_string(),
    )])?;

    let mut host = NopLineEditorHost::default();
    let mut editor = LineEditor::new(&mut term);
    editor.set_prompt("workspace> ");
    let line = editor.read_line(&mut host)?;

    if let Some(text) = line {
        let name = text.trim().to_string();
        let assignment = KeyAssignment::SwitchToWorkspace {
            name: if name.is_empty() { None } else { Some(name) },
            spawn: None,
        };
        promise::spawn::spawn_into_main_thread(async move {
            window.notify(TermWindowNotif::PerformAssignment {
                pane_id,
                assignment,
                tx: None,
            });
            anyhow::Result::<()>::Ok(())
        })
        .detach();
    }

    Ok(())
}
```

- [ ] **Step 3: Add `prompt_new_workspace` to `TermWindow`**

In `wezterm-gui/src/termwindow/mod.rs`, near `show_prompt_input_line` (~2303), add:

```rust
    pub fn prompt_new_workspace(&mut self) {
        let mux = Mux::get();
        let tab = match mux.get_active_tab_for_window(self.mux_window_id) {
            Some(tab) => tab,
            None => return,
        };
        let pane = match self.get_active_pane_or_overlay() {
            Some(pane) => pane,
            None => return,
        };
        let window = self.window.clone().unwrap();
        let pane_id = pane.pane_id();

        let (overlay, future) = start_overlay(self, &tab, move |_tab_id, term| {
            crate::overlay::workspace::prompt_workspace_name(term, window, pane_id)
        });
        self.assign_overlay(tab.tab_id(), overlay);
        promise::spawn::spawn(future).detach();
    }
```

(Confirm `start_overlay` is already imported in `mod.rs` — the existing `show_prompt_input_line`/`show_input_selector` use it, so the import is present.)

- [ ] **Step 4: Type-check**

Run: `cargo check -p wezterm-gui 2>&1 | head -40`
Expected: PASS (the mouse handler's `prompt_new_workspace` call now resolves). Likely fix-ups:
- `NopLineEditorHost` / `LineEditor` / `line_editor_terminal` import paths — verify against how `wezterm-gui/src/overlay/prompt.rs` imports the termwiz line editor. If `NopLineEditorHost` does not exist, copy the minimal `PromptHost` from `overlay/prompt.rs` (it implements `LineEditorHost`) and use that.
- `editor.read_line(&mut host)` returns `anyhow::Result<Option<String>>`; adjust if the signature differs.
- `TermWindowNotif::PerformAssignment { pane_id, assignment, tx }` field names — verify against the enum definition (the launcher uses exactly this at `overlay/launcher.rs:481-485`).

- [ ] **Step 5: Manual verification**

Run the app with the sidebar on. Click the `+` row → the active pane shows the prompt overlay. Type `demo`, Enter → a `demo` workspace is created, switched to, and highlighted. Click `+` again, submit blank → an auto-named workspace appears.

- [ ] **Step 6: Commit**

```bash
cargo +nightly fmt
git add wezterm-gui/src/overlay/workspace.rs wezterm-gui/src/overlay/mod.rs wezterm-gui/src/termwindow/mod.rs
git commit -m "gui: add new-workspace prompt from the sidebar +"
```

---

## Phase 7 — Right-click actions: rename & close

### Task 10: `RenameWorkspace` / `CloseWorkspace` key assignments

**Files:**
- Modify: `config/src/keyassignment.rs` (enum, near `ToggleWorkspaceSidebar`)
- Modify: `wezterm-gui/src/termwindow/mod.rs` (dispatch arms; `rename_workspace_prompt`; close logic)
- Modify: `wezterm-gui/src/overlay/workspace.rs` (rename-prompt overlay)

- [ ] **Step 1: Add the enum variants**

In `config/src/keyassignment.rs`, next to `ToggleWorkspaceSidebar`, add:

```rust
    /// Prompt to rename the given workspace (None = active).
    RenameWorkspace {
        #[dynamic(default)]
        workspace: Option<String>,
    },
    /// Close (kill all windows in) the given workspace (None = active).
    CloseWorkspace {
        #[dynamic(default)]
        workspace: Option<String>,
    },
```

- [ ] **Step 2: Add a rename-prompt overlay function**

In `wezterm-gui/src/overlay/workspace.rs`, add:

```rust
/// Reads a new name for `old_name`, then renames the workspace on the main thread.
pub fn prompt_rename_workspace(
    mut term: TermWizTerminal,
    old_name: String,
) -> anyhow::Result<()> {
    term.no_grab_mouse_in_raw_mode();
    term.render(&[termwiz::surface::Change::Text(format!(
        "Rename workspace `{}` to:\r\n",
        old_name
    ))])?;

    let mut host = NopLineEditorHost::default();
    let mut editor = LineEditor::new(&mut term);
    editor.set_prompt("new name> ");
    let line = editor.read_line_with_optional_initial_value(&mut host, Some(&old_name))?;

    if let Some(text) = line {
        let new_name = text.trim().to_string();
        if !new_name.is_empty() && new_name != old_name {
            promise::spawn::spawn_into_main_thread(async move {
                let mux = mux::Mux::get();
                mux.rename_workspace(&old_name, &new_name);
                anyhow::Result::<()>::Ok(())
            })
            .detach();
        }
    }

    Ok(())
}
```

(If `read_line_with_optional_initial_value` is not on the chosen host/editor, fall back to `read_line` and skip the pre-fill.)

- [ ] **Step 3: Add dispatch + helpers in `mod.rs`**

In `perform_key_assignment` (`mod.rs`), add arms next to `ToggleWorkspaceSidebar`:

```rust
            RenameWorkspace { workspace } => {
                let mux = Mux::get();
                let name = workspace
                    .clone()
                    .unwrap_or_else(|| mux.active_workspace());
                self.rename_workspace_prompt(name);
            }
            CloseWorkspace { workspace } => {
                let mux = Mux::get();
                let name = workspace
                    .clone()
                    .unwrap_or_else(|| mux.active_workspace());
                for window_id in mux.iter_windows_in_workspace(&name) {
                    mux.kill_window(window_id);
                }
            }
```

And add the prompt launcher method near `prompt_new_workspace`:

```rust
    pub fn rename_workspace_prompt(&mut self, old_name: String) {
        let mux = Mux::get();
        let tab = match mux.get_active_tab_for_window(self.mux_window_id) {
            Some(tab) => tab,
            None => return,
        };
        let (overlay, future) = start_overlay(self, &tab, move |_tab_id, term| {
            crate::overlay::workspace::prompt_rename_workspace(term, old_name)
        });
        self.assign_overlay(tab.tab_id(), overlay);
        promise::spawn::spawn(future).detach();
    }
```

- [ ] **Step 4: Type-check**

Run: `cargo check -p wezterm-gui 2>&1 | head -40`
Expected: PASS. Verify `mux.kill_window(window_id)` and `mux.rename_workspace(&old, &new)` signatures (they are `pub fn kill_window(&self, WindowId)` at `mux/src/lib.rs:957` and `pub fn rename_workspace(&self, &str, &str)` at `mux/src/lib.rs:652`).

- [ ] **Step 5: Commit**

```bash
cargo +nightly fmt
git add config/src/keyassignment.rs wezterm-gui/src/overlay/workspace.rs wezterm-gui/src/termwindow/mod.rs
git commit -m "gui: add RenameWorkspace and CloseWorkspace assignments"
```

---

### Task 11: Right-click action menu overlay

**Files:**
- Modify: `wezterm-gui/src/overlay/workspace.rs` (menu overlay)
- Modify: `wezterm-gui/src/termwindow/mod.rs` (`show_workspace_actions`)

- [ ] **Step 1: Write the menu overlay**

The built-in `selector` overlay requires a Lua `EmitEvent` action, so implement a tiny native menu that dispatches real `KeyAssignment`s (the launcher's model). Append to `wezterm-gui/src/overlay/workspace.rs`:

```rust
use termwiz::input::{InputEvent, KeyCode, KeyEvent};
use termwiz::surface::Change;

/// A minimal right-click action menu for a workspace: Switch / Rename / Close.
/// Dispatches native KeyAssignments via the window (no Lua round-trip).
pub fn workspace_actions_menu(
    mut term: TermWizTerminal,
    window: ::window::Window,
    pane_id: PaneId,
    workspace: String,
) -> anyhow::Result<()> {
    let entries: Vec<(char, String, KeyAssignment)> = vec![
        (
            's',
            format!("Switch to `{}`", workspace),
            KeyAssignment::SwitchToWorkspace {
                name: Some(workspace.clone()),
                spawn: None,
            },
        ),
        (
            'r',
            format!("Rename `{}`", workspace),
            KeyAssignment::RenameWorkspace {
                workspace: Some(workspace.clone()),
            },
        ),
        (
            'x',
            format!("Close `{}`", workspace),
            KeyAssignment::CloseWorkspace {
                workspace: Some(workspace.clone()),
            },
        ),
    ];

    term.set_raw_mode()?;
    term.render(&[Change::Title(format!("Workspace: {}", workspace))])?;

    let mut text = format!("Actions for workspace `{}`:\r\n\r\n", workspace);
    for (key, label, _) in &entries {
        text.push_str(&format!("  [{}]  {}\r\n", key, label));
    }
    text.push_str("\r\n  [Esc] Cancel\r\n");
    term.render(&[Change::Text(text)])?;
    term.flush()?;

    loop {
        match term.poll_input(None) {
            Ok(Some(InputEvent::Key(KeyEvent { key, .. }))) => match key {
                KeyCode::Escape => break,
                KeyCode::Char(c) => {
                    if let Some((_, _, assignment)) =
                        entries.iter().find(|(k, _, _)| *k == c.to_ascii_lowercase())
                    {
                        let assignment = assignment.clone();
                        promise::spawn::spawn_into_main_thread(async move {
                            window.notify(TermWindowNotif::PerformAssignment {
                                pane_id,
                                assignment,
                                tx: None,
                            });
                            anyhow::Result::<()>::Ok(())
                        })
                        .detach();
                        break;
                    }
                }
                _ => {}
            },
            Ok(Some(_)) => {}
            Ok(None) => {}
            Err(_) => break,
        }
    }

    Ok(())
}
```

- [ ] **Step 2: Add `show_workspace_actions` to `TermWindow`**

In `mod.rs`, near `prompt_new_workspace`:

```rust
    pub fn show_workspace_actions(&mut self, workspace: String) {
        let mux = Mux::get();
        let tab = match mux.get_active_tab_for_window(self.mux_window_id) {
            Some(tab) => tab,
            None => return,
        };
        let pane = match self.get_active_pane_or_overlay() {
            Some(pane) => pane,
            None => return,
        };
        let window = self.window.clone().unwrap();
        let pane_id = pane.pane_id();

        let (overlay, future) = start_overlay(self, &tab, move |_tab_id, term| {
            crate::overlay::workspace::workspace_actions_menu(term, window, pane_id, workspace)
        });
        self.assign_overlay(tab.tab_id(), overlay);
        promise::spawn::spawn(future).detach();
    }
```

- [ ] **Step 3: Type-check**

Run: `cargo check -p wezterm-gui 2>&1 | head -40`
Expected: PASS — the Task 8 `show_workspace_actions` call now resolves. Likely fix-ups:
- `term.poll_input(None)` / `InputEvent` / `KeyEvent` / `KeyCode` — verify the `TermWizTerminal` input API against another overlay that reads keys (`overlay/selector.rs` `run_loop` uses `term.poll_input`). Match its exact pattern (it may return `InputEvent::Key(KeyEvent{ key: KeyCode::Char(c), .. })`).
- `term.flush()` / `term.set_raw_mode()` come from the `termwiz::terminal::Terminal` trait — ensure it is imported.

- [ ] **Step 4: Manual verification**

Right-click a workspace row → the menu overlay appears in the active pane. Press `r` → rename prompt; enter a new name → the sidebar row updates. Right-click another workspace, press `x` → that workspace's windows close and it disappears from the list. `Esc` cancels.

- [ ] **Step 5: Commit (folds in Task 8's mouse handler)**

```bash
cargo +nightly fmt
git add wezterm-gui/src/overlay/workspace.rs wezterm-gui/src/termwindow/mod.rs wezterm-gui/src/termwindow/mouseevent.rs
git commit -m "gui: right-click workspace actions menu (switch/rename/close)"
```

---

## Phase 8 — Documentation

### Task 12: User-facing docs

**Files:**
- Create: `docs/config/lua/config/enable_workspace_sidebar.md`
- Create: `docs/config/lua/config/workspace_sidebar_width.md`
- Create: `docs/config/lua/config/mouse_wheel_scrolls_workspaces.md`
- Create: `docs/config/lua/keyassignment/ToggleWorkspaceSidebar.md`
- Create: `docs/config/lua/keyassignment/RenameWorkspace.md`
- Create: `docs/config/lua/keyassignment/CloseWorkspace.md`

- [ ] **Step 1: Write the config docs**

Follow the style of an existing page (e.g. `docs/config/lua/config/enable_tab_bar.md`). Example for `enable_workspace_sidebar.md`:

```markdown
# `enable_workspace_sidebar = false`

{{since('nightly')}}

When set to `true`, WezTerm shows a vertical workspace switcher on the left
edge of the window. Each row is a workspace; the active workspace is
highlighted. Click a row to switch, click `+` to create a new workspace, and
right-click a row for rename/close actions.

The strip is off by default. Toggle it at runtime with the
[ToggleWorkspaceSidebar](../keyassignment/ToggleWorkspaceSidebar.md) key
assignment. Its width is controlled by
[workspace_sidebar_width](workspace_sidebar_width.md).

Note: full-height "Layout A" (the tab bar shifted to the right of the sidebar)
applies when [use_fancy_tab_bar](use_fancy_tab_bar.md) is `true` (the default).
With the retro tab bar the sidebar renders below the tab-bar strip.
```

Write analogous short pages for `workspace_sidebar_width` (default `180` pixels; accepts `"20cell"`, `"2in"`, etc. via the standard dimension syntax) and `mouse_wheel_scrolls_workspaces` (default `true`; scroll over the sidebar to change workspace).

- [ ] **Step 2: Write the key-assignment docs**

Follow `docs/config/lua/keyassignment/SwitchWorkspaceRelative.md`. Example for `ToggleWorkspaceSidebar.md`:

```markdown
# `ToggleWorkspaceSidebar`

{{since('nightly')}}

Shows or hides the [workspace sidebar](../config/enable_workspace_sidebar.md)
for the current window.

```lua
config.keys = {
  { key = 'w', mods = 'CTRL|SHIFT|ALT', action = wezterm.action.ToggleWorkspaceSidebar },
}
```
```

For `RenameWorkspace` and `CloseWorkspace`, document the optional `workspace`
arg (defaults to the active workspace), e.g.:

```markdown
# `RenameWorkspace`

{{since('nightly')}}

Prompts for a new name and renames a workspace. With no argument it renames the
active workspace.

```lua
action = wezterm.action.RenameWorkspace,
-- or target a specific workspace:
action = wezterm.action.RenameWorkspace { workspace = 'default' },
```
```

- [ ] **Step 3: Add a changelog entry**

Append to the "unreleased"/nightly section of `docs/changelog.md` following the existing bullet style:

```markdown
* New: vertical workspace sidebar (`enable_workspace_sidebar`,
  `ToggleWorkspaceSidebar`) — a left-edge switcher listing workspaces with
  click-to-switch, a `+` to create, scroll-to-switch, and right-click
  rename/close.
```

- [ ] **Step 4: Verify docs build (optional but recommended)**

Run: `ci/build-docs.sh serve` and confirm the new pages render and cross-links resolve. Stop the server when done.

- [ ] **Step 5: Commit**

```bash
git add docs/
git commit -m "docs: document workspace sidebar config and key assignments"
```

---

## Final verification

- [ ] `cargo +nightly fmt` — clean.
- [ ] `cargo test --all` — passes (CI gate).
- [ ] Manual end-to-end (`test-conf.lua` with `enable_workspace_sidebar = true`, fancy tab bar):
  - Sidebar lists workspaces; active highlighted; content + tab bar start right of the strip.
  - Click switches; `+` creates (named & auto); scroll changes workspace; right-click → switch/rename/close.
  - `ToggleWorkspaceSidebar` hides/shows and content reflows.
  - Second window reflects workspace list changes live.
  - With `use_fancy_tab_bar = false`, sidebar renders below the tab bar (fallback) without visual overlap.

---

## Self-Review

**Spec coverage:**
- Config flag / width / wheel option → Task 1. Toggle key assignment → Task 2. ✓
- Name-only entries + active highlight → Task 3 (model) + Task 6 (render). ✓
- Layout A + reserved strip geometry → Tasks 4–5; retro fallback → Task 6 Step 3. ✓
- Live updates → Task 7. ✓
- Click-to-switch / hover / scroll → Task 8. ✓
- "+" new workspace prompt → Task 9. ✓
- Right-click rename/close (terminal overlay, native) → Tasks 10–11. ✓
- Docs → Task 12. ✓
- Testing (unit model + geometry + manual) → Tasks 3, 4, and manual steps throughout. ✓

**Known cross-task ordering:** Task 8's mouse handler references `prompt_new_workspace` (Task 9) and `show_workspace_actions` (Task 11); commit Task 8 together with those (noted in Task 8 Step 2/4). When using subagent-driven execution, dispatch Tasks 9 and 11's method stubs before Task 8's commit, or land 8–11 as one reviewed unit.

**Placeholder scan:** No "TBD"/"handle appropriately". Every code step shows real code. Uncertain external signatures (`apply_dimensions`, termwiz `LineEditor`/input, `TabBarColors` field names) are handled by explicit "verify against <file>, adjust to the compiler-reported name" steps — legitimate verification, not deferred work.

**Type consistency:** `WorkspaceSidebarState` / `WorkspaceSidebarEntry` / `WorkspaceSidebarItem` names are consistent across Tasks 3, 6, 8. `left_sidebar_width()` defined in Task 4, used in Tasks 5–6. `UIItemType::WorkspaceSidebar` defined in Task 6, matched in Task 8. `prompt_new_workspace` / `show_workspace_actions` / `rename_workspace_prompt` names consistent across Tasks 8–11.
