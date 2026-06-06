import json
import logging
import asyncio
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from src.sandbox.harness import SandboxHarness
from src.sandbox.config import SandboxConfig
from src.sandbox.agent_registry import AGENT_REGISTRY

logger = logging.getLogger("sandbox.runtime")

# Singleton harness instance to preserve state across requests
_harness_instance = SandboxHarness()


class SandboxRuntimeHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Redirect server logs to the standard logging library
        logger.info("%s - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            cfg = SandboxConfig()
            response = {
                "status": "ok",
                "runtime": "python-stdlib",
                "mode": "sandbox",
                "llm_provider": cfg.llm_provider,
                "enabled_domains": cfg.enabled_domains,
                "agent_ids": list(AGENT_REGISTRY.keys())
            }
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        elif self.path == "/debug/storage":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "status": "ok",
                "description": "Sandbox-only in-memory storage observer",
                "counts": {
                    "kitchen": len(_harness_instance.kitchen_db),
                    "books": len(_harness_instance.books_db),
                    "medical": len(_harness_instance.medical_db)
                },
                "recent_items": {
                    "kitchen": [r.title for r in _harness_instance.kitchen_db],
                    "books": [b.title for b in _harness_instance.books_db],
                    "medical": [e.metric_type for e in _harness_instance.medical_db]
                }
            }
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"error": "Not Found"}
            self.wfile.write(json.dumps(response).encode("utf-8"))

    def do_POST(self):
        if self.path == "/webhook/telegram":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_error_response(400, "Empty payload")
                return

            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                self._send_error_response(400, "Invalid JSON payload")
                return

            if not isinstance(payload, dict):
                self._send_error_response(400, "Payload must be a JSON object")
                return

            message = payload.get("message")
            if not message or not isinstance(message, dict):
                self._send_error_response(400, "Missing or invalid 'message' field")
                return

            text = message.get("text")
            if text is None:
                self._send_error_response(400, "Missing 'message.text' field")
                return

            try:
                # Run the async SandboxHarness flow
                result = asyncio.run(_harness_instance.run_flow(text))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                logger.exception("Error running harness flow")
                self._send_error_response(500, f"Internal server error: {str(e)}")
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"error": "Not Found"}
            self.wfile.write(json.dumps(response).encode("utf-8"))

    def _send_error_response(self, status_code: int, message: str):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {"error": message}
        self.wfile.write(json.dumps(response).encode("utf-8"))


def serve(host: str, port: int):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    server_address = (host, port)
    httpd = HTTPServer(server_address, SandboxRuntimeHTTPRequestHandler)
    logger.info(f"Starting sandbox runtime HTTP server on {host}:{port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server is shutting down...")
    finally:
        httpd.server_close()
        logger.info("Server stopped.")


def run_smoke_test(base_url: str) -> bool:
    print(f"=== Sandbox Runtime Smoke Test (Target: {base_url}) ===")

    # 1. Test GET /health
    health_url = f"{base_url}/health"
    print(f"Testing GET {health_url}...")
    try:
        with urllib.request.urlopen(health_url, timeout=5) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8")
            print(f"Response code: {status_code}")
            print(f"Response body: {body}")
            if status_code != 200:
                print("FAIL: Expected status code 200")
                return False
            data = json.loads(body)
            if not all(k in data for k in ("status", "runtime", "mode")):
                print("FAIL: Missing required fields in /health response")
                return False
            print("GET /health: OK")
    except Exception as e:
        print(f"FAIL: GET /health failed: {e}")
        return False

    # 2. Test GET /debug/storage (initial counts)
    debug_storage_url = f"{base_url}/debug/storage"
    print(f"\nTesting GET {debug_storage_url} (initial counts)...")
    try:
        with urllib.request.urlopen(debug_storage_url, timeout=5) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8")
            print(f"Response code: {status_code}")
            print(f"Response body: {body}")
            if status_code != 200:
                print("FAIL: Expected status code 200")
                return False
            initial_data = json.loads(body)
            if "counts" not in initial_data or "kitchen" not in initial_data["counts"]:
                print("FAIL: Unexpected response structure for /debug/storage")
                return False
            initial_kitchen_count = initial_data["counts"]["kitchen"]
            print(f"Initial kitchen count: {initial_kitchen_count}")
    except Exception as e:
        print(f"FAIL: GET /debug/storage failed: {e}")
        return False

    # 3. Test POST /webhook/telegram (valid payload)
    webhook_url = f"{base_url}/webhook/telegram"
    print(f"\nTesting POST {webhook_url} (valid payload)...")
    valid_payload = {
        "update_id": 9999,
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
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8")
            print(f"Response code: {status_code}")
            print(f"Response body: {body}")
            if status_code != 200:
                print("FAIL: Expected status code 200")
                return False
            data = json.loads(body)
            if not data.get("success") or "routing" not in data or "trace" not in data:
                print("FAIL: Response payload structure is unexpected")
                return False
            print("POST /webhook/telegram (valid): OK")
    except Exception as e:
        print(f"FAIL: POST /webhook/telegram (valid) failed: {e}")
        return False

    # 4. Test GET /debug/storage (after valid payload - count should increment)
    print(f"\nTesting GET {debug_storage_url} (after valid payload)...")
    try:
        with urllib.request.urlopen(debug_storage_url, timeout=5) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8")
            print(f"Response code: {status_code}")
            print(f"Response body: {body}")
            if status_code != 200:
                print("FAIL: Expected status code 200")
                return False
            after_valid_data = json.loads(body)
            after_kitchen_count = after_valid_data["counts"]["kitchen"]
            print(f"Kitchen count after valid payload: {after_kitchen_count}")
            if after_kitchen_count != initial_kitchen_count + 1:
                print(f"FAIL: Kitchen count did not increment. Expected {initial_kitchen_count + 1}, got {after_kitchen_count}")
                return False
            print("Storage count increment: OK")
    except Exception as e:
        print(f"FAIL: GET /debug/storage after valid payload failed: {e}")
        return False

    # 5. Test POST /webhook/telegram (invalid payload - expected 400)
    print(f"\nTesting POST {webhook_url} (invalid payload)...")
    invalid_payload = {
        "update_id": 9999,
        "message": {
            "message_id": 1
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
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            status_code = response.getcode()
            print(f"Response code: {status_code} (Expected 400)")
            print("FAIL: Expected status code 400, but got 200")
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"Response code: {e.code} (Expected 400)")
        print(f"Response body: {body}")
        if e.code != 400:
            print(f"FAIL: Expected status code 400, but got {e.code}")
            return False
        try:
            data = json.loads(body)
            if "error" not in data:
                print("FAIL: Missing 'error' key in 400 response")
                return False
        except Exception:
            print("FAIL: Error response body is not valid JSON")
            return False
        print("POST /webhook/telegram (invalid): OK")
    except Exception as e:
        print(f"FAIL: Unexpected error during invalid payload test: {e}")
        return False

    # 6. Test GET /debug/storage (after invalid payload - count should remain the same)
    print(f"\nTesting GET {debug_storage_url} (after invalid payload)...")
    try:
        with urllib.request.urlopen(debug_storage_url, timeout=5) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8")
            print(f"Response code: {status_code}")
            print(f"Response body: {body}")
            if status_code != 200:
                print("FAIL: Expected status code 200")
                return False
            after_invalid_data = json.loads(body)
            after_invalid_kitchen_count = after_invalid_data["counts"]["kitchen"]
            print(f"Kitchen count after invalid payload: {after_invalid_kitchen_count}")
            if after_invalid_kitchen_count != after_kitchen_count:
                print(f"FAIL: Kitchen count changed after invalid payload. Expected {after_kitchen_count}, got {after_invalid_kitchen_count}")
                return False
            print("Invalid payload does not increment count: OK")
    except Exception as e:
        print(f"FAIL: GET /debug/storage after invalid payload failed: {e}")
        return False

    print("\nALL SMOKE TESTS PASSED")
    return True
