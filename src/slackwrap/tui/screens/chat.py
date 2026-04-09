from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Input, Header, Footer, RichLog
from textual.worker import Worker, WorkerState


class ChatScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("  Chat with your data", id="chat-title")
        yield RichLog(id="chat-log", wrap=True, markup=True)
        yield Input(placeholder="Ask anything about your Slack history...", id="chat-input")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#chat-log", RichLog)
        engine = self.app.get_chat_engine()
        if engine is None:
            log.write("[dim]No data loaded. Please sync first, then reopen chat.[/dim]")
            return
        if not engine.ollama.is_available():
            log.write("[dim]Ollama is not available. Install: https://ollama.ai[/dim]")
            log.write("[dim]Start: ollama serve[/dim]")
            log.write("")
            log.write("[dim]Chat requires a running Ollama instance with a local model.[/dim]")
        else:
            log.write("[green]Ollama connected.[/green] Ask me anything about your Slack history!")
            log.write("")
        self.query_one("#chat-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        log = self.query_one("#chat-log", RichLog)
        log.write(f"[bold]You:[/bold] {query}")
        self.query_one("#chat-input", Input).value = ""

        engine = self.app.get_chat_engine()
        if engine is None:
            log.write("[dim]Chat engine not initialised. Sync data first.[/dim]")
            log.write("")
            return

        log.write("[dim]Thinking...[/dim]")
        self.run_worker(self._ask_worker(engine, query), name="chat_ask", exclusive=True)

    async def _ask_worker(self, engine, query: str) -> str:
        return engine.ask(query)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name != "chat_ask":
            return
        log = self.query_one("#chat-log", RichLog)
        if event.state == WorkerState.SUCCESS:
            response = event.worker.result
            log.write(f"[bold cyan]SlackWrap:[/bold cyan] {response}")
            log.write("")
        elif event.state == WorkerState.ERROR:
            log.write(f"[red]Error: {event.worker.error}[/red]")
            log.write("")
