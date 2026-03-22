from __future__ import annotations

import argparse
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Input, RichLog

from mtls_demo.protocol import EnqueueCommandRequest
from mtls_demo.state import StateStore


class ServerTUI(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        height: 1fr;
    }

    #agents {
        width: 2fr;
    }

    #controls {
        width: 1fr;
        padding: 1 2;
    }

    #commands {
        height: 14;
    }

    #command_output {
        height: 12;
    }

    Input, Button {
        margin-bottom: 1;
    }

    RichLog {
        border: solid $accent;
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, db_path: str, stale_after_seconds: int) -> None:
        super().__init__()
        self.store = StateStore(db_path)
        self.stale_after_seconds = stale_after_seconds

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            yield DataTable(id="agents")
            with Vertical(id="controls"):
                yield Input(placeholder="Agent ID", id="agent_id")
                yield Input(placeholder="Command", id="command")
                yield Input(value="60", placeholder="Timeout seconds", id="timeout_seconds")
                yield Button("Enqueue command", id="enqueue", variant="primary")
                yield RichLog(id="events", wrap=True)
        yield DataTable(id="commands")
        yield RichLog(id="command_output", wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.store.init_db()
        self._configure_tables()
        self.refresh_data()
        self.set_interval(2.0, self.refresh_data)
        self._log("TUI ready")

    def _configure_tables(self) -> None:
        agents_table = self.query_one("#agents", DataTable)
        agents_table.cursor_type = "row"
        commands_table = self.query_one("#commands", DataTable)
        commands_table.cursor_type = "row"

    def action_refresh(self) -> None:
        self.refresh_data()
        self._log("Refreshed data")

    def refresh_data(self) -> None:
        pruned = self.store.prune_stale_agents(self.stale_after_seconds)
        for agent_id in pruned:
            self._log(f"Removed stale agent {agent_id}")

        agents_table = self.query_one("#agents", DataTable)
        agents_table.clear(columns=True)
        agents_table.add_columns("Agent ID", "Display Name", "Status", "Last Seen", "Capabilities")
        for agent in self.store.list_agents():
            capabilities = ", ".join(agent.capabilities) if agent.capabilities else "-"
            agents_table.add_row(
                agent.agent_id,
                agent.display_name or "-",
                agent.status,
                agent.last_seen,
                capabilities,
                key=agent.agent_id,
            )

        commands_table = self.query_one("#commands", DataTable)
        commands_table.clear(columns=True)
        commands_table.add_columns("Command ID", "Agent ID", "Status", "Exit", "Command")
        for command in self.store.list_commands(limit=20):
            commands_table.add_row(
                command.command_id[:8],
                command.agent_id,
                command.status,
                "-" if command.exit_code is None else str(command.exit_code),
                command.command,
                key=command.command_id,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is None:
            return
        if event.data_table.id == "agents":
            agent_id = str(event.row_key.value)
            self.query_one("#agent_id", Input).value = agent_id
            self._log(f"Selected agent {agent_id}")
            return
        if event.data_table.id == "commands":
            command_id = str(event.row_key.value)
            command = self.store.get_command(command_id)
            if command is None:
                return
            output = self.query_one("#command_output", RichLog)
            output.clear()
            output.write(f"Command: {command.command}")
            output.write(f"Status: {command.status}")
            output.write(f"Exit code: {'-' if command.exit_code is None else command.exit_code}")
            output.write("")
            output.write("STDOUT:")
            output.write(command.stdout or "<empty>")
            output.write("")
            output.write("STDERR:")
            output.write(command.stderr or "<empty>")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "enqueue":
            return
        agent_id = self.query_one("#agent_id", Input).value.strip()
        command = self.query_one("#command", Input).value.strip()
        timeout_text = self.query_one("#timeout_seconds", Input).value.strip() or "60"

        if not agent_id or not command:
            self._log("Agent ID and command are required")
            return
        if self.store.get_agent(agent_id) is None:
            self._log(f"Unknown agent {agent_id}")
            return
        try:
            timeout_seconds = int(timeout_text)
        except ValueError:
            self._log("Timeout must be an integer")
            return

        queued = self.store.enqueue_command(
            EnqueueCommandRequest(
                agent_id=agent_id,
                command=command,
                requested_by="tui",
                timeout_seconds=timeout_seconds,
            )
        )
        self.query_one("#command", Input).value = ""
        self._log(f"Queued {queued.command_id[:8]} for {agent_id}")
        self.refresh_data()

    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.query_one("#events", RichLog).write(f"[{stamp}] {message}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the server-side TUI")
    parser.add_argument("--db-path", default="demo.sqlite3")
    parser.add_argument("--stale-after-seconds", type=int, default=60)
    args = parser.parse_args()
    ServerTUI(args.db_path, args.stale_after_seconds).run()


if __name__ == "__main__":
    main()
