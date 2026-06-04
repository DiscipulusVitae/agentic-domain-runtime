import json
import socket
import threading
import urllib.request
import urllib.error
import pytest
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


def test_cli_runtime_serve_subprocess():
    """Regression test: Start runtime serve in a subprocess and send a Telegram webhook request."""
    import shutil
    import subprocess
    import sys
    import time

    port = get_free_port()
    uv_path = shutil.which("uv")
    if uv_path:
        cmd = [uv_path, "run", "python", "-m", "src.sandbox", "runtime", "serve", "--host", "127.0.0.1", "--port", str(port)]
    else:
        cmd = [sys.executable, "-m", "src.sandbox", "runtime", "serve", "--host", "127.0.0.1", "--port", str(port)]

    # Start the server as a subprocess
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    try:
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

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
