---
tags:
  - spawn
  - workspace
---

# `prefer_to_spawn_new_workspace = false`

{{since('nightly')}}

If set to `true`, launching a new instance of `wezterm` will prefer to
create a new workspace in an already-running GUI instance. The workspace name
is based on [`default_workspace`](default_workspace.md) and made unique, such
as `default-2` or `default-3`.

When this option is `false`, launching another instance creates a new window
in the default workspace. The default value is `false`.

An explicit `--workspace` argument takes precedence over this option.
[`prefer_to_spawn_tabs`](prefer_to_spawn_tabs.md) also takes precedence when
an existing window can receive the new tab.
