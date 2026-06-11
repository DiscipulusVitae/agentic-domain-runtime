import json
import socket
import threading
import urllib.request
import urllib.error
import pytest
import subprocess
import sys
from http.server import HTTPServer
from src.sandbox.runtime import SandboxRuntimeHTTPRequestHandler


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def server_url():
    host = "127.0.0.1"
    port = get_free_port()
    server = HTTPServer((host, port), SandboxRuntimeHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{host}:{port}"
    yield url
    server.shutdown()
    server.server_close()


def test_health_endpoint(server_url):
    """Test GET /health returns 200 OK and expected structure."""
    url = f"{server_url}/health"
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.getcode() == 200
        body = response.read().decode("utf-8")
        data = json.loads(body)
        assert data.get("status") == "ok"
        assert data.get("runtime") == "python-stdlib"
        assert data.get("mode") == "sandbox"
        assert data.get("llm_provider") == "fake"
        assert isinstance(data.get("enabled_domains"), list)
        assert "kitchen" in data.get("enabled_domains")
        assert isinstance(data.get("agent_ids"), list)
        assert "core.butler" in data.get("agent_ids")
        assert "kitchen.recorder" in data.get("agent_ids")
        # Assert default memory persistence fields
        assert data.get("persistence") == "memory"
        assert data.get("telegram_configured") == False
        assert data.get("database") == {
            "configured": False,
            "reachable": False,
            "schema_smoke": "skipped"
        }


def test_health_endpoint_supabase_missing_env(server_url, monkeypatch):
    """Test GET /health with Supabase persistence and missing required env variables."""
    monkeypatch.setenv("ADR_PERSISTENCE", "supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_API_KEY_PUBLISHABLE", raising=False)

    url = f"{server_url}/health"
    req = urllib.request.Request(url, method="GET")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=5)

    assert exc_info.value.code == 503
    body = exc_info.value.read().decode("utf-8")
    data = json.loads(body)
    assert data.get("status") == "error"
    assert data.get("persistence") == "supabase"
    assert data.get("database") == {
        "configured": False,
        "reachable": False,
        "schema_smoke": "failed"
    }


def test_health_endpoint_supabase_success(server_url, monkeypatch):
    """Test GET /health in Supabase mode with mocked successful PostgREST query."""
    monkeypatch.setenv("ADR_PERSISTENCE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "http://mock-supabase.example.com")
    monkeypatch.setenv("SUPABASE_API_KEY_PUBLISHABLE", "mock-anon-key")

    from unittest.mock import patch, MagicMock
    original_urlopen = urllib.request.urlopen

    def side_effect(req, *args, **kwargs):
        url_str = req.full_url if isinstance(req, urllib.request.Request) else req
        if "mock-supabase.example.com" in url_str:
            mock_response = MagicMock()
            mock_response.getcode.return_value = 200
            mock_response.read.return_value = b'[]'
            mock_response.__enter__.return_value = mock_response
            return mock_response
        return original_urlopen(req, *args, **kwargs)

    with patch("urllib.request.urlopen", side_effect=side_effect) as mock_urlopen:
        url = f"{server_url}/health"
        with urllib.request.urlopen(url, timeout=5) as response:
            assert response.getcode() == 200
            body = response.read().decode("utf-8")
            data = json.loads(body)
            assert data.get("status") == "ok"
            assert data.get("persistence") == "supabase"
            assert data.get("database") == {
                "configured": True,
                "reachable": True,
                "schema_smoke": "ok"
            }

        # Verify the mock was called with the right headers
        called_args = [call[0][0] for call in mock_urlopen.call_args_list]
        supabase_calls = [r for r in called_args if isinstance(r, urllib.request.Request) and "mock-supabase.example.com" in r.full_url]
        assert len(supabase_calls) == 1
        req = supabase_calls[0]
        assert req.get_header("Apikey") == "mock-anon-key"
        assert req.get_header("Authorization") == "Bearer mock-anon-key"
        assert req.get_header("Accept-profile") == "core"


def test_health_endpoint_supabase_network_failure(server_url, monkeypatch):
    """Test GET /health in Supabase mode with mocked network/connection failure."""
    monkeypatch.setenv("ADR_PERSISTENCE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "http://mock-supabase.example.com")
    monkeypatch.setenv("SUPABASE_API_KEY_PUBLISHABLE", "mock-anon-key")

    from unittest.mock import patch
    original_urlopen = urllib.request.urlopen

    def side_effect(req, *args, **kwargs):
        url_str = req.full_url if isinstance(req, urllib.request.Request) else req
        if "mock-supabase.example.com" in url_str:
            raise urllib.error.URLError("Connection refused")
        return original_urlopen(req, *args, **kwargs)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        url = f"{server_url}/health"
        req = urllib.request.Request(url, method="GET")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)

        assert exc_info.value.code == 503
        body = exc_info.value.read().decode("utf-8")
        data = json.loads(body)
        assert data.get("status") == "error"
        assert data.get("persistence") == "supabase"
        assert data.get("database") == {
            "configured": True,
            "reachable": False,
            "schema_smoke": "failed"
        }


def test_health_endpoint_supabase_api_http_error(server_url, monkeypatch):
    """Test GET /health in Supabase mode with mocked API/HTTP error response."""
    monkeypatch.setenv("ADR_PERSISTENCE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "http://mock-supabase.example.com")
    monkeypatch.setenv("SUPABASE_API_KEY_PUBLISHABLE", "mock-anon-key")

    from unittest.mock import patch, MagicMock
    original_urlopen = urllib.request.urlopen

    def side_effect(req, *args, **kwargs):
        url_str = req.full_url if isinstance(req, urllib.request.Request) else req
        if "mock-supabase.example.com" in url_str:
            fp = MagicMock()
            fp.read.return_value = b"Not Found"
            raise urllib.error.HTTPError(
                url=url_str,
                code=404,
                msg="Not Found",
                hdrs={},
                fp=fp
            )
        return original_urlopen(req, *args, **kwargs)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        url = f"{server_url}/health"
        req = urllib.request.Request(url, method="GET")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)

        assert exc_info.value.code == 503
        body = exc_info.value.read().decode("utf-8")
        data = json.loads(body)
        assert data.get("status") == "error"
        assert data.get("persistence") == "supabase"
        assert data.get("database") == {
            "configured": True,
            "reachable": True,
            "schema_smoke": "failed"
        }


def test_webhook_telegram_success(server_url):
    """Test POST /webhook/telegram with valid payload returns 200 OK and routing result."""
    url = f"{server_url}/webhook/telegram"
    payload = {
        "update_id": 4242,
        "message": {
            "message_id": 1,
            "text": "Добавь рецепт борща"
        }
    }
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.getcode() == 200
        body = response.read().decode("utf-8")
        data = json.loads(body)
        assert "routing" in data
        assert "trace" in data
        assert "success" in data
        assert "output" in data
        assert data["success"] is True
        assert data["routing"]["domain_id"] == "kitchen"


def test_webhook_telegram_invalid_payload(server_url):
    """Test POST /webhook/telegram with invalid payloads returns 400 Bad Request."""
    url = f"{server_url}/webhook/telegram"

    # Test case 1: Invalid JSON format
    req = urllib.request.Request(
        url,
        data=b"invalid-raw-json",
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=5)
    assert exc_info.value.code == 400
    body = exc_info.value.read().decode("utf-8")
    data = json.loads(body)
    assert "error" in data

    # Test case 2: Empty message field
    payload_no_msg = {
        "update_id": 4242
    }
    req_data = json.dumps(payload_no_msg).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=5)
    assert exc_info.value.code == 400
    body = exc_info.value.read().decode("utf-8")
    data = json.loads(body)
    assert "error" in data
    assert "message" in data["error"]

    # Test case 3: Missing message.text field
    payload_no_text = {
        "update_id": 4242,
        "message": {
            "message_id": 1
        }
    }
    req_data = json.dumps(payload_no_text).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=5)
    assert exc_info.value.code == 400
    body = exc_info.value.read().decode("utf-8")
    data = json.loads(body)
    assert "error" in data
    assert "message.text" in data["error"]


@pytest.fixture
def runtime_subprocess():
    procs = []

    def _run(cmd, **kwargs):
        # On Linux, configure PDEATHSIG to kill the subprocess if the parent pytest process terminates.
        if sys.platform.startswith("linux"):
            def set_pdeathsig():
                try:
                    import ctypes
                    libc = ctypes.CDLL("libc.so.6")
                    # PR_SET_PDEATHSIG = 1, SIGTERM = 15
                    libc.prctl(1, 15, 0, 0, 0)
                except Exception:
                    pass
            kwargs.setdefault("preexec_fn", set_pdeathsig)

        proc = subprocess.Popen(cmd, **kwargs)
        procs.append(proc)
        return proc

    yield _run

    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def test_cli_runtime_serve_subprocess(runtime_subprocess):
    """Regression test: Start runtime serve in a subprocess and send a Telegram webhook request."""
    import time

    port = get_free_port()
    # Always run sys.executable directly to avoid intermediate uv wrapper process
    # which can result in orphaned runtime processes when terminated.
    cmd = [sys.executable, "-m", "src.sandbox", "runtime", "serve", "--host", "127.0.0.1", "--port", str(port)]

    # Start the server as a subprocess via the cleanup-guaranteed fixture
    proc = runtime_subprocess(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for the /health endpoint to become available
    health_url = f"http://127.0.0.1:{port}/health"
    start_time = time.time()
    connected = False
    while time.time() - start_time < 5.0:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            raise RuntimeError(
                f"Subprocess terminated early with code {proc.returncode}.\n"
                f"STDOUT: {stdout.decode()}\n"
                f"STDERR: {stderr.decode()}"
            )
        try:
            with urllib.request.urlopen(health_url, timeout=0.5) as response:
                if response.getcode() == 200:
                    connected = True
                    break
        except Exception:
            time.sleep(0.1)

    if not connected:
        raise RuntimeError("Timeout waiting for the server to start")

    # Send a valid Telegram webhook request
    webhook_url = f"http://127.0.0.1:{port}/webhook/telegram"
    payload = {
        "update_id": 5555,
        "message": {
            "message_id": 1,
            "text": "Добавь рецепт борща"
        }
    }
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.getcode() == 200
        body = response.read().decode("utf-8")
        data = json.loads(body)
        assert "routing" in data
        assert data["routing"]["agent_id"] == "kitchen.recorder"


def test_debug_storage_endpoint(server_url):
    """Test GET /debug/storage returns counts and recent items correctly and safely."""
    # 1. Fetch initial state
    url = f"{server_url}/debug/storage"
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.getcode() == 200
        body = response.read().decode("utf-8")
        data = json.loads(body)

        # Verify public-safe response shape
        assert data.get("status") == "ok"
        assert data.get("description") == "Sandbox-only in-memory storage observer"
        assert "counts" in data
        assert "recent_items" in data
        assert "kitchen" in data["counts"]
        assert "books" in data["counts"]
        assert "medical" in data["counts"]
        assert isinstance(data["recent_items"]["kitchen"], list)

        # Ensure we don't leak credentials, env or secrets
        body_lower = body.lower()
        assert "token" not in body_lower
        assert "key" not in body_lower
        assert "secret" not in body_lower
        assert "password" not in body_lower

    initial_kitchen_count = data["counts"]["kitchen"]

    # 2. Send a valid payload that increments the count
    webhook_url = f"{server_url}/webhook/telegram"
    valid_payload = {
        "update_id": 1234,
        "message": {
            "message_id": 1,
            "text": "Добавь рецепт борща"
        }
    }
    req_data = json.dumps(valid_payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.getcode() == 200

    # 3. Verify count incremented
    with urllib.request.urlopen(url, timeout=5) as response:
        body = response.read().decode("utf-8")
        data = json.loads(body)
        after_valid_kitchen_count = data["counts"]["kitchen"]
        assert after_valid_kitchen_count == initial_kitchen_count + 1
        assert "борщ" in "".join(data["recent_items"]["kitchen"]).lower()

    # 4. Send an invalid payload (expect 400)
    invalid_payload = {
        "update_id": 5678,
        "message": {
            "message_id": 2
            # Missing text
        }
    }
    req_data = json.dumps(invalid_payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=5)
    assert exc_info.value.code == 400

    # 5. Verify count did NOT increment
    with urllib.request.urlopen(url, timeout=5) as response:
        body = response.read().decode("utf-8")
        data = json.loads(body)
        after_invalid_kitchen_count = data["counts"]["kitchen"]
        assert after_invalid_kitchen_count == after_valid_kitchen_count


def test_webhook_start_command_no_chat_id(server_url):
    """POST /webhook/telegram with /start without chat.id — returns welcome, send deferred."""
    url = f"{server_url}/webhook/telegram"
    payload = {
        "update_id": 99,
        "message": {"message_id": 99, "text": "/start"}
    }
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.getcode() == 200
        body = response.read().decode("utf-8")
        data = json.loads(body)
        assert data["success"] is True
        assert "send: no_chat_id" in data["trace"]


def test_webhook_start_command_with_chat_id(server_url):
    """POST /webhook/telegram with /start + chat.id — sendMessage called, sends skipped (no token)."""
    url = f"{server_url}/webhook/telegram"
    payload = {
        "update_id": 100,
        "message": {
            "message_id": 100,
            "text": "/start",
            "chat": {"id": 999888}
        }
    }
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.getcode() == 200
        body = response.read().decode("utf-8")
        data = json.loads(body)
        assert data["success"] is True
        assert "send: send_skipped_no_token" in data["trace"]


def test_webhook_unknown_command(server_url):
    """POST /webhook/telegram with unknown /command returns helpful message, HTTP 200."""
    url = f"{server_url}/webhook/telegram"
    payload = {
        "update_id": 2,
        "message": {"message_id": 2, "text": "/help"}
    }
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.getcode() == 200
        body = response.read().decode("utf-8")
        data = json.loads(body)
        assert data["success"] is False
        assert data["routing"]["intent"] == "unknown_command"
        assert "/start" in data["output"]


def test_webhook_text_path_not_broken(server_url):
    """Обычный text path не сломан после добавления /start handler."""
    url = f"{server_url}/webhook/telegram"
    payload = {
        "update_id": 3,
        "message": {"message_id": 3, "text": "Добавь книгу Оруэлл 1984"}
    }
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.getcode() == 200
        body = response.read().decode("utf-8")
        data = json.loads(body)
        assert data["success"] is True
        assert data["routing"]["domain_id"] == "books"


def test_webhook_invalid_payload_still_400(server_url):
    """Invalid payload всё ещё возвращает 400 после добавления /start handler."""
    url = f"{server_url}/webhook/telegram"
    payload_no_text = {
        "update_id": 4,
        "message": {"message_id": 4}
    }
    req_data = json.dumps(payload_no_text).encode("utf-8")
    req = urllib.request.Request(
        url, data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=5)
    assert exc_info.value.code == 400
    body = exc_info.value.read().decode("utf-8")
    data = json.loads(body)
    assert "message.text" in data["error"]


class TestWebhookSecretValidation:
    """T307.2: X-Telegram-Bot-Api-Secret-Token validation."""

    WEBHOOK_PATH = "/webhook/telegram"

    def _post_webhook(self, server_url, payload, headers=None):
        url = f"{server_url}{self.WEBHOOK_PATH}"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, headers=headers or {})
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.getcode(), resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def _valid_start_payload(self, chat_id=1):
        return {
            "update_id": 1,
            "message": {"message_id": 1, "text": "/start", "chat": {"id": chat_id}},
        }

    def test_no_secret_accepted(self, server_url, monkeypatch):
        """Без WEBHOOK_SECRET — webhook принимается без заголовка."""
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        code, body = self._post_webhook(server_url, self._valid_start_payload())
        assert code == 200

    def test_correct_secret_accepted(self, server_url, monkeypatch):
        """Правильный секрет в заголовке — webhook принимается."""
        monkeypatch.setenv("WEBHOOK_SECRET", "expected-secret")
        code, body = self._post_webhook(
            server_url, self._valid_start_payload(),
            headers={"X-Telegram-Bot-Api-Secret-Token": "expected-secret"},
        )
        assert code == 200

    def test_missing_header_rejected(self, server_url, monkeypatch):
        """Секрет настроен, заголовок отсутствует — 401."""
        monkeypatch.setenv("WEBHOOK_SECRET", "expected-secret")
        code, body = self._post_webhook(server_url, self._valid_start_payload())
        assert code == 401
        assert "Missing secret" in body

    def test_wrong_secret_rejected(self, server_url, monkeypatch):
        """Неправильный секрет в заголовке — 401."""
        monkeypatch.setenv("WEBHOOK_SECRET", "expected-secret")
        code, body = self._post_webhook(
            server_url, self._valid_start_payload(),
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
        assert code == 401
        assert "Invalid secret" in body

    def test_secret_not_in_response_body(self, server_url, monkeypatch, capsys):
        """Секрет не появляется в ответе."""
        monkeypatch.setenv("WEBHOOK_SECRET", "my-secret-xyz")
        _, body = self._post_webhook(
            server_url, self._valid_start_payload(),
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
        assert "my-secret-xyz" not in body

    def test_no_secret_mode_explicit_setting(self, server_url, monkeypatch):
        """WEBHOOK_SECRET='' эквивалентно unset — no validation."""
        monkeypatch.setenv("WEBHOOK_SECRET", "")
        code, body = self._post_webhook(server_url, self._valid_start_payload())
        assert code == 200


class TestTelegramSendReply:
    """T318: _try_send_telegram_message вызывается для видимого Telegram reply."""

    WEBHOOK_PATH = "/webhook/telegram"

    def _post_webhook(self, server_url, payload, headers=None):
        url = f"{server_url}{self.WEBHOOK_PATH}"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, headers=headers or {})
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.getcode(), resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_send_reply_called_for_text(self, server_url, monkeypatch):
        """Текстовое сообщение с chat.id → _try_send_telegram_message вызывается."""
        calls = []
        monkeypatch.setattr(
            "src.sandbox.runtime._try_send_telegram_message",
            lambda chat_id, text: calls.append((chat_id, text)) or "send_mocked",
        )
        payload = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "text": "Добавь рецепт борща",
                "chat": {"id": 12345},
            },
        }
        code, body = self._post_webhook(server_url, payload)
        assert code == 200
        assert len(calls) == 1
        assert calls[0][0] == 12345
        assert "ADR Sandbox" in calls[0][1]

    def test_send_reply_called_for_unknown_command(self, server_url, monkeypatch):
        """Неизвестная команда → _try_send_telegram_message вызывается с helpful text."""
        calls = []
        monkeypatch.setattr(
            "src.sandbox.runtime._try_send_telegram_message",
            lambda chat_id, text: calls.append((chat_id, text)) or "send_mocked",
        )
        payload = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "text": "/unknown_cmd",
                "chat": {"id": 12345},
            },
        }
        code, body = self._post_webhook(server_url, payload)
        assert code == 200
        assert len(calls) == 1
        assert calls[0][0] == 12345
        assert "Неизвестная команда" in calls[0][1]

    def test_send_reply_called_for_start(self, server_url, monkeypatch):
        """/start с chat.id → _try_send_telegram_message вызывается с welcome text."""
        calls = []
        monkeypatch.setattr(
            "src.sandbox.runtime._try_send_telegram_message",
            lambda chat_id, text: calls.append((chat_id, text)) or "send_mocked",
        )
        payload = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "text": "/start",
                "chat": {"id": 12345},
            },
        }
        code, body = self._post_webhook(server_url, payload)
        assert code == 200
        assert len(calls) == 1
        assert calls[0][0] == 12345
        assert "sandbox" in calls[0][1].lower()

    def test_no_chat_id_skips_send(self, server_url, monkeypatch):
        """Сообщение без chat.id → _try_send_telegram_message не вызывается."""
        calls = []
        monkeypatch.setattr(
            "src.sandbox.runtime._try_send_telegram_message",
            lambda chat_id, text: calls.append((chat_id, text)) or "send_mocked",
        )
        payload = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "text": "Привет",
            },
        }
        code, body = self._post_webhook(server_url, payload)
        assert code == 200
        data = json.loads(body)
        assert "[send: no_chat_id]" in data.get("trace", "")

    def test_telegram_configured_in_health(self, server_url, monkeypatch):
        """Health endpoint отображает telegram_configured."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
        url = f"{server_url}/health"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        assert data["telegram_configured"] is True

    def test_unknown_command_trace_includes_send_status(self, server_url, monkeypatch):
        """Trace неизвестной команды содержит [send: send_mocked]."""
        monkeypatch.setattr(
            "src.sandbox.runtime._try_send_telegram_message",
            lambda chat_id, text: "send_mocked",
        )
        payload = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "text": "/foo",
                "chat": {"id": 1},
            },
        }
        code, body = self._post_webhook(server_url, payload)
        data = json.loads(body)
        assert "[send: send_mocked]" in data.get("trace", "")

    def test_text_path_trace_includes_send_status(self, server_url, monkeypatch):
        """Trace текстового пути содержит [send: send_mocked]."""
        monkeypatch.setattr(
            "src.sandbox.runtime._try_send_telegram_message",
            lambda chat_id, text: "send_mocked",
        )
        payload = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "text": "Добавь рецепт борща",
                "chat": {"id": 1},
            },
        }
        code, body = self._post_webhook(server_url, payload)
        data = json.loads(body)
        assert "[send: send_mocked]" in data.get("trace", "")
