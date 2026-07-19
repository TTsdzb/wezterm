---
tags:
  - mouse
  - workspace
---
# `mouse_wheel_scrolls_workspaces`

{{since('nightly')}}

If `true`, the vertical mouse wheel will switch between workspaces when the
mouse cursor is over the [workspace sidebar](enable_workspace_sidebar.md).
This mirrors [mouse_wheel_scrolls_tabs](mouse_wheel_scrolls_tabs.md), which
controls the equivalent behavior for the tab bar.

The default is `true`. Set to `false` to disable this behavior.

```lua
config.mouse_wheel_scrolls_workspaces = true
```
