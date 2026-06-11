"""Render cleanup helpers: API key resolution, service delete, read-back verification."""
import json
import os
import time
import urllib.request
import urllib.error

from ..live_executor import step_info

RENDER_API = "https://api.render.com/v1"

# Render-specific статусы — детализируют результат удаления Render сервиса
STATUS_RENDER_DELETE_VERIFIED = "render_delete_verified"
STATUS_RENDER_DELETE_FAILED = "render_delete_failed"
STATUS_RENDER_DELETE_PENDING = "render_delete_pending_verification"
STATUS_RENDER_MANUAL_REQUIRED = "render_manual_required"


def _resolve_render_api_key() -> tuple[str | None, str]:
    """Возвращает (api_key, source_description).

    Приоритет источников:
      1. RENDER_API_KEY из переменной окружения — trusted explicit source.
      2. Cleanroom CLI config — ~/.render/cli.yaml в scoped HOME, verified.
      3. Host CLI config — только НЕ в reviewer proof mode.

    В reviewer proof mode:
      - Cleanroom config (HOME != real user home) → accepted.
      - Host config (HOME == real user home) → blocked.
    """
    env_key = os.environ.get("RENDER_API_KEY")
    if env_key:
        return env_key.strip(), "env:RENDER_API_KEY"

    reviewer_proof = (
        os.environ.get("ADR_REVIEWER_PROOF", "").lower() in ("1", "true", "yes")
    )

    current_home = os.path.expanduser("~")
    try:
        import pwd
        real_home = pwd.getpwuid(os.getuid()).pw_dir
    except Exception:
        real_home = current_home
    is_cleanroom = (current_home != real_home)

    yaml_file = os.path.expanduser("~/.render/cli.yaml")
    try:
        with open(yaml_file) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("key:"):
                    key = stripped[4:].strip().strip('"').strip("'")
                    if reviewer_proof:
                        if is_cleanroom:
                            step_info("Render API key из cleanroom CLI config — accepted.")
                            return key, "cleanroom:cli.yaml"
                        else:
                            step_info("Render API key обнаружен в host config, но reviewer proof mode — пропущен.")
                            return None, "host_config_blocked_reviewer_proof"
                    return key, "host:cli.yaml"
    except OSError:
        pass

    for path_desc in [
        ("~/.render/api-key", os.path.expanduser("~/.render/api-key")),
        ("~/.config/render/auth.json", os.path.expanduser("~/.config/render/auth.json")),
    ]:
        desc, full_path = path_desc
        try:
            with open(full_path) as f:
                content = f.read().strip()
                if content:
                    if reviewer_proof:
                        if is_cleanroom:
                            step_info(f"Render API key из cleanroom {desc} — accepted.")
                            return content, f"cleanroom:{desc}"
                        else:
                            step_info(f"Render API key обнаружен в {desc}, но reviewer proof mode — пропущен.")
                            continue
                    return content, f"host:{desc}"
        except OSError:
            pass

    return None, "absent"


def _delete_render_service(service_id: str) -> str:
    """Удаляет Render сервис через REST API (Render CLI v2.20+ не имеет 'services delete').

    Returns один из render-специфичных статусов.
    """
    api_key, source = _resolve_render_api_key()

    if not api_key:
        if source == "absent":
            step_info("RENDER_API_KEY не задан, host config не найден.")
            step_info(
                "Сгенерируйте Personal Access Token в Render Dashboard: "
                "Account Settings → API Keys → Create API Key."
            )
        else:
            step_info(f"Render API key недоступен (source: {source}).")
        step_info(f"Ручное удаление: https://dashboard.render.com/web/{service_id}/settings")
        return STATUS_RENDER_MANUAL_REQUIRED

    try:
        req = urllib.request.Request(
            f"{RENDER_API}/services/{service_id}",
            method="DELETE",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp = urllib.request.urlopen(req, timeout=15)
        if resp.status not in (200, 204):
            step_info(f"REST API DELETE: HTTP {resp.status}")
            return STATUS_RENDER_DELETE_FAILED
    except urllib.error.HTTPError as e:
        if e.code == 404:
            step_info("REST API DELETE: HTTP 404 (Уже удалён)")
        else:
            step_info(f"REST API DELETE: HTTP {e.code}")
            return STATUS_RENDER_DELETE_FAILED
    except Exception as e:
        step_info(f"REST API DELETE: {e}")
        return STATUS_RENDER_DELETE_FAILED

    if not _verify_render_service_absent(service_id):
        step_info("Render сервис не подтверждён как удалённый — read-back verification failed.")
        return STATUS_RENDER_DELETE_PENDING

    step_info(f"Render сервис удалён через REST API (key source: {source}).")
    return STATUS_RENDER_DELETE_VERIFIED


def _verify_render_service_absent(service_id: str, attempts: int = 3, delay: float = 2.0) -> bool:
    """Read-back verification that Render service is absent/deleted."""
    api_key, _ = _resolve_render_api_key()
    if not api_key:
        step_info("Render verification skipped: API key not available.")
        return False

    for attempt in range(attempts):
        try:
            req = urllib.request.Request(
                f"{RENDER_API}/services/{service_id}",
                method="GET",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp = urllib.request.urlopen(req, timeout=15)
            if resp.status == 404:
                return True
            if resp.status in (200, 202):
                if attempt < attempts - 1:
                    time.sleep(delay)
                continue
            return False
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return True
            if e.code in (409, 429, 500, 502, 503, 504) and attempt < attempts - 1:
                time.sleep(delay)
                continue
            step_info(f"Render verification: HTTP {e.code}")
            return False
        except Exception as e:
            if attempt < attempts - 1:
                time.sleep(delay)
                continue
            step_info(f"Render verification: {e}")
            return False

    return False
