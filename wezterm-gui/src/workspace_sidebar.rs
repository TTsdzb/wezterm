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
