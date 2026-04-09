from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Input, Header, Footer, RichLog


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
        log.write("[dim]Chat requires Ollama to be running locally.[/dim]")
        log.write("[dim]Install: https://ollama.ai  |  Start: ollama serve[/dim]")
        log.write("")
        log.write("[dim]This feature will be available in a future update (Plan 5).[/dim]")
        self.query_one("#chat-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        log = self.query_one("#chat-log", RichLog)
        log.write(f"[bold]You:[/bold] {query}")
        log.write("[dim]Chat not yet connected. Ollama integration coming in Plan 5.[/dim]")
        log.write("")
        self.query_one("#chat-input", Input).value = ""
