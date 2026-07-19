# `CloseWorkspace`

{{since('nightly')}}

Closes a workspace, terminating all of its windows, tabs and panes.

`CloseWorkspace` accepts two optional parameters:

* `workspace` - the name of the workspace to close. If omitted, the active
  workspace is closed.
* `confirm` - whether to prompt for confirmation before closing. The default
  is `true`, which honors
  [window_close_confirmation](../config/window_close_confirmation.md). Set
  to `false` to close the workspace immediately without prompting.

```lua
local wezterm = require 'wezterm'
local act = wezterm.action

config.keys = {
  -- Close the active workspace, prompting for confirmation
  {
    key = 'q',
    mods = 'CTRL|SHIFT',
    action = act.CloseWorkspace,
  },
  -- Close a specific workspace without prompting
  {
    key = 'Q',
    mods = 'CTRL|SHIFT',
    action = act.CloseWorkspace { workspace = 'default', confirm = false },
  },
}
```
