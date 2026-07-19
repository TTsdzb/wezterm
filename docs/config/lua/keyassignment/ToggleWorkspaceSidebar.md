# `ToggleWorkspaceSidebar`

{{since('nightly')}}

Shows or hides the [workspace sidebar](../config/enable_workspace_sidebar.md)
for the current window.

```lua
local wezterm = require 'wezterm'
local act = wezterm.action

config.keys = {
  { key = 'b', mods = 'CTRL|SHIFT', action = act.ToggleWorkspaceSidebar },
}
```
