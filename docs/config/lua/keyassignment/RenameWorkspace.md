# `RenameWorkspace`

{{since('nightly')}}

Prompts for a new name and renames a workspace.

`RenameWorkspace` accepts one optional parameter:

* `workspace` - the name of the workspace to rename. If omitted, the active
  workspace is renamed.

```lua
local wezterm = require 'wezterm'
local act = wezterm.action

config.keys = {
  -- Rename the active workspace
  {
    key = 'r',
    mods = 'CTRL|SHIFT',
    action = act.RenameWorkspace,
  },
  -- Rename a specific workspace
  {
    key = 'R',
    mods = 'CTRL|SHIFT',
    action = act.RenameWorkspace { workspace = 'default' },
  },
}
```
