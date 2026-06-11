"""Render service URL read-back helpers."""
import json
import time


RENDER_URL_POLL_ATTEMPTS = 8
RENDER_URL_POLL_INTERVAL_SECONDS = 15


def service_payload(item: dict) -> dict:
    """Возвращает payload сервиса из Render CLI/API формы."""
    if not isinstance(item, dict):
        return {}
    service = item.get("service", item)
    return service if isinstance(service, dict) else {}


def service_url(service: dict) -> str:
    """Извлекает URL только из фактического Render read-back payload."""
    url = service.get("url")
    if not url and "serviceDetails" in service:
        url = service.get("serviceDetails", {}).get("url")
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if not url.startswith(("https://", "http://")):
        return ""
    return url.rstrip("/")


def mark_render_url_pending(state: dict, reason: str) -> None:
    """Фиксирует pending/missing URL без синтетического fallback."""
    state.pop("render_service_url", None)
    state["render_url_verified"] = False
    state["render_url_status"] = "url_pending"
    state["render_url_pending_reason"] = reason
    state["health_ok"] = False


def read_render_service(run_cmd, service_id: str, service_name: str) -> dict:
    """Читает сервис из Render CLI list output без live-мутаций."""
    result = run_cmd(["render", "services", "--output", "json"], timeout=15)
    if not result["ok"]:
        return {}

    try:
        services = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {}

    if not isinstance(services, list):
        return {}

    for item in services:
        service = service_payload(item)
        if service.get("id") == service_id or service.get("name") == service_name:
            return service
    return {}


def verify_render_service_url(
    *,
    state: dict,
    run_cmd,
    step_info,
    service_id: str,
    service_name: str,
    attempts: int = RENDER_URL_POLL_ATTEMPTS,
    interval_seconds: int = RENDER_URL_POLL_INTERVAL_SECONDS,
) -> str:
    """Bounded read-back: получает реальный URL сервиса из Render API/CLI."""
    for attempt in range(attempts):
        service = read_render_service(run_cmd, service_id, service_name)
        url = service_url(service)
        if url:
            state["render_service_url"] = url
            state["render_url_verified"] = True
            state["render_url_status"] = "url_verified"
            state.pop("render_url_pending_reason", None)
            return url

        if attempt + 1 < attempts:
            step_info(
                f"Render URL ещё не доступен через API/read-back "
                f"({attempt + 1}/{attempts})."
            )
            time.sleep(interval_seconds)

    mark_render_url_pending(
        state,
        "Render API/read-back не вернул service.url за отведённое число попыток.",
    )
    return ""
