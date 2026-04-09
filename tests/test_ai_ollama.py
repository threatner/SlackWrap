from __future__ import annotations
from unittest.mock import patch, MagicMock


def test_is_available_returns_false_when_not_running():
    from slackwrap.ai.ollama_client import OllamaClient
    with patch("slackwrap.ai.ollama_client.Client") as MockClient:
        MockClient.return_value.list.side_effect = Exception("Connection refused")
        client = OllamaClient()
        assert client.is_available() is False


def test_is_available_returns_true_when_running():
    from slackwrap.ai.ollama_client import OllamaClient
    with patch("slackwrap.ai.ollama_client.Client") as MockClient:
        MockClient.return_value.list.return_value = {"models": []}
        client = OllamaClient()
        assert client.is_available() is True


def test_chat_returns_response_text():
    from slackwrap.ai.ollama_client import OllamaClient
    with patch("slackwrap.ai.ollama_client.Client") as MockClient:
        mock_resp = MagicMock()
        mock_resp.message.content = "Hello!"
        MockClient.return_value.chat.return_value = mock_resp
        client = OllamaClient()
        assert client.chat(messages=[{"role": "user", "content": "hi"}]) == "Hello!"


def test_chat_json_returns_dict():
    from slackwrap.ai.ollama_client import OllamaClient
    with patch("slackwrap.ai.ollama_client.Client") as MockClient:
        mock_resp = MagicMock()
        mock_resp.message.content = '{"tone": "friendly", "confidence": 0.9}'
        MockClient.return_value.chat.return_value = mock_resp
        client = OllamaClient()
        result = client.chat_json(messages=[{"role": "user", "content": "analyze"}],
                                   schema={"type": "object", "properties": {"tone": {"type": "string"}}})
        assert result["tone"] == "friendly"


def test_embed_returns_vectors():
    from slackwrap.ai.ollama_client import OllamaClient
    with patch("slackwrap.ai.ollama_client.Client") as MockClient:
        MockClient.return_value.embed.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
        client = OllamaClient()
        vectors = client.embed(["hello"])
        assert len(vectors) == 1 and len(vectors[0]) == 3


def test_default_models():
    from slackwrap.ai.ollama_client import OllamaClient
    with patch("slackwrap.ai.ollama_client.Client"):
        client = OllamaClient()
        assert client.chat_model == "llama3.1:8b"
        assert client.embed_model == "nomic-embed-text"


def test_custom_models():
    from slackwrap.ai.ollama_client import OllamaClient
    with patch("slackwrap.ai.ollama_client.Client"):
        client = OllamaClient(chat_model="mistral", embed_model="mxbai-embed-large")
        assert client.chat_model == "mistral"
