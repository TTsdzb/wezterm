---
tags:
  - appearance
  - workspace
---
# `enable_workspace_sidebar = false`

{{since('nightly')}}

Controls whether a vertical workspace switcher sidebar is shown along the
left edge of the window.

When enabled, each row in the sidebar represents a workspace, with the
active workspace highlighted.  Clicking a row switches to that workspace,
and clicking the `+` button at the end of the list creates (and switches
to) a new workspace.  Right-clicking a row shows a menu with options to
switch to, rename, or close that workspace.  Scrolling the mouse wheel
over the sidebar switches between workspaces; see
[mouse_wheel_scrolls_workspaces](mouse_wheel_scrolls_workspaces.md) to
control that behavior.

The default is `false`; the sidebar is not shown.  It can also be toggled
at runtime for the current window using the
[ToggleWorkspaceSidebar](../keyassignment/ToggleWorkspaceSidebar.md) key
assignment.

```lua
config.enable_workspace_sidebar = true
```

The width of the sidebar is controlled by
[workspace_sidebar_width](workspace_sidebar_width.md).

When [use_fancy_tab_bar](use_fancy_tab_bar.md) is `true` (the default), the
sidebar spans the full height of the window and the tab bar is shifted to
the right of it.  When the retro tab bar is used instead (`use_fancy_tab_bar
= false`), the sidebar is rendered below the tab-bar strip.
