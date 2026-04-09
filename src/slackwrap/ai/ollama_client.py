from __future__ import annotations
import json
from ollama import Client


class OllamaClient:
    def __init__(self, host: str = "http://localhost:11434",
                 chat_model: str = "llama3.1:8b", embed_model: str = "nomic-embed-text"):
        self.host = host
        self.chat_model = chat_model
        self.embed_model = embed_model
        self._client = Client(host=host)

    def is_available(self) -> bool:
        try:
            self._client.list()
            return True
        except Exception:
            return False

    def chat(self, messages: list[dict], model: str | None = None, temperature: float = 0.7) -> str:
        response = self._client.chat(model=model or self.chat_model, messages=messages,
                                      options={"temperature": temperature})
        return response.message.content

    def chat_json(self, messages: list[dict], schema: dict,
                  model: str | None = None, temperature: float = 0.0) -> dict:
        response = self._client.chat(model=model or self.chat_model, messages=messages,
                                      format=schema, options={"temperature": temperature})
        return json.loads(response.message.content)

    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        response = self._client.embed(model=model or self.embed_model, input=texts)
        return response["embeddings"]

    def embed_single(self, text: str, model: str | None = None) -> list[float]:
        return self.embed([text], model=model)[0]
