---
tags:
  - appearance
  - workspace
---
# `workspace_sidebar_width = 360`

{{since('nightly')}}

When [enable_workspace_sidebar](enable_workspace_sidebar.md) is `true`,
this option controls the width of the workspace sidebar.

This option accepts a plain number, measured in pixels, or a string value
with a unit suffix similar to [window_padding](window_padding.md):

* `"180px"` - the `px` suffix indicates pixels
* `"144pt"` - the `pt` suffix indicates points. There are `72` points in `1 inch`
* `"20cell"` - the `cell` suffix sizes the sidebar based on the width of a
  terminal cell, which in turn depends on the font size, font scaling and dpi
* `"20%"` - the `%` suffix sizes the sidebar as a percentage of the window width

The default is `360`, which is 360 pixels.

```lua
config.workspace_sidebar_width = 360
```
