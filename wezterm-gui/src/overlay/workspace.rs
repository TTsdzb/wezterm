use super::confirm::run_confirmation;
use crate::termwindow::{TermWindow, TermWindowNotif};
use config::keyassignment::KeyAssignment;
use mux::pane::PaneId;
use mux::tab::TabId;
use mux::termwiztermtab::TermWizTerminal;
use termwiz::input::{InputEvent, KeyCode, KeyEvent};
use termwiz::lineedit::*;
use termwiz::surface::Change;
use termwiz::terminal::Terminal;
use window::WindowOps;

struct WorkspaceHost {
    history: BasicHistory,
}

impl WorkspaceHost {
    fn new() -> Self {
        Self {
            history: BasicHistory::default(),
        }
    }
}

impl LineEditorHost for WorkspaceHost {
    fn history(&mut self) -> &mut dyn History {
        &mut self.history
    }

    fn resolve_action(
        &mut self,
        event: &InputEvent,
        editor: &mut LineEditor<'_>,
    ) -> Option<Action> {
        let (line, _cursor) = editor.get_line_and_cursor();
        if line.is_empty()
            && matches!(
                event,
                InputEvent::Key(KeyEvent {
                    key: KeyCode::Escape,
                    ..
                })
            )
        {
            Some(Action::Cancel)
        } else {
            None
        }
    }
}

/// Reads a workspace name on the overlay thread, then dispatches
/// SwitchToWorkspace on the main thread. Empty input auto-generates a name.
pub fn prompt_workspace_name(
    mut term: TermWizTerminal,
    window: ::window::Window,
    pane_id: PaneId,
) -> anyhow::Result<()> {
    term.no_grab_mouse_in_raw_mode();
    term.render(&[Change::Text(
        "Enter a name for the new workspace (blank = auto):\r\n".to_string(),
    )])?;

    let mut host = WorkspaceHost::new();
    let mut editor = LineEditor::new(&mut term);
    editor.set_prompt("workspace name> ");
    let line = editor.read_line(&mut host)?;

    if let Some(text) = line {
        let name = text.trim().to_string();
        let assignment = KeyAssignment::SwitchToWorkspace {
            name: if name.is_empty() { None } else { Some(name) },
            spawn: None,
        };
        window.notify(TermWindowNotif::PerformAssignment {
            pane_id,
            assignment,
            tx: None,
        });
    }
    Ok(())
}

/// Reads a new name for `old_name`, then renames the workspace on the main thread.
pub fn prompt_rename_workspace(mut term: TermWizTerminal, old_name: String) -> anyhow::Result<()> {
    term.no_grab_mouse_in_raw_mode();
    term.render(&[Change::Text(format!(
        "Rename workspace `{}` to:\r\n",
        old_name
    ))])?;

    let mut host = WorkspaceHost::new();
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

/// Prompts to confirm closing `workspace` (which contains `window_count`
/// windows), then kills all of its windows on the main thread if confirmed.
pub fn confirm_close_workspace(
    mut term: TermWizTerminal,
    window: ::window::Window,
    tab_id: TabId,
    workspace: String,
    window_count: usize,
) -> anyhow::Result<()> {
    if run_confirmation(
        &format!(
            "🛑 Really close workspace `{}` and its {} window(s)?",
            workspace, window_count
        ),
        &mut term,
    )? {
        promise::spawn::spawn_into_main_thread(async move {
            let mux = mux::Mux::get();
            for window_id in mux.iter_windows_in_workspace(&workspace) {
                mux.kill_window(window_id);
            }
            anyhow::Result::<()>::Ok(())
        })
        .detach();
    }
    TermWindow::schedule_cancel_overlay(window, tab_id, None);

    Ok(())
}
