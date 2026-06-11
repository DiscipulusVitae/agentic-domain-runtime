"""Фаза Render для живого мастера установки."""
import json
import sys
import time
import urllib.request
import urllib.error

from ..env_checks import TTY_ERROR_MESSAGE
from ..render_url_readback import verify_render_service_url
from ..live_executor import (
    ask,
    ask_yes_no,
    run_cmd,
    run_interactive,
    check_cli_logged_in,
    step_pass,
    step_skip,
    step_fail,
    step_info,
    save_state,
    mask,
)

ADR_REPO_URL = "https://github.com/DiscipulusVitae/agentic-domain-runtime"
ADR_REPO_BRANCH = "main"


def _is_adr_health(body: dict) -> bool:
    """Проверяет, что /health ответ похож на ADR runtime, а не на placeholder."""
    if not isinstance(body, dict):
        return False
    required_keys = {"status", "runtime", "mode", "persistence", "database"}
    return required_keys.issubset(body.keys())


def _validate_adr_health(body: dict) -> dict:
    """Валидирует ADR /health ответ. Возвращает результат проверки."""
    result = {"valid": False, "reason": ""}
    if not _is_adr_health(body):
        result["reason"] = "Ответ не содержит ADR-специфичных полей (status, runtime, mode, persistence, database)"
        return result
    result["valid"] = True
    result["persistence"] = body.get("persistence", "?")
    result["status"] = body.get("status", "?")
    result["runtime"] = body.get("runtime", "?")
    result["mode"] = body.get("mode", "?")
    db = body.get("database", {})
    result["db_configured"] = db.get("configured", False)
    result["db_reachable"] = db.get("reachable", False)
    result["db_smoke"] = db.get("schema_smoke", "?")
    return result


def _validate_live_render_health(body: dict) -> dict:
    """Строгая валидация для live Render: требует Supabase persistence + DB reachable.

    В отличие от _validate_adr_health, которая принимает любой ADR-shaped JSON
    (включая memory mode), эта функция требует доказательства, что Render service
    действительно подключён к Supabase.
    """
    result = _validate_adr_health(body)
    if not result["valid"]:
        return result

    if result["persistence"] != "supabase":
        result["valid"] = False
        result["reason"] = f"persistence={result['persistence']} (ожидается supabase) — env vars не применились или runtime в memory mode"
        return result

    db = body.get("database", {})
    if not db.get("configured"):
        result["valid"] = False
        result["reason"] = "database.configured=false — Supabase env vars не настроены"
        return result

    if not db.get("reachable"):
        result["valid"] = False
        result["reason"] = "database.reachable=false — Supabase недоступен"
        return result

    if db.get("schema_smoke") != "ok":
        result["valid"] = False
        result["reason"] = f"database.schema_smoke={db.get('schema_smoke')} (ожидается ok) — smoke не прошёл"
        return result

    return result


def run_render_phase(plan, state: dict) -> None:
    """Фаза Render: login, создание сервиса, env vars, деплой, /health."""
    service_id = state.get("render_service_id")
    service_url = state.get("render_service_url")

    # --- Авторизация ---
    if not check_cli_logged_in("render", ["whoami"]):
        print()
        print("  Render CLI не авторизован.")
        if ask_yes_no("  Запустить 'render login' в этом терминале?",
                       default=True):
            step_info("Запуск render login (откроется браузер)...")
            run_interactive(["render", "login"], timeout=300)

            if check_cli_logged_in("render", ["whoami"]):
                step_pass("Render CLI авторизован (через интерактивный login).")
            else:
                step_info("Интерактивный login не подтвердился — пробуем fallback.")
                _render_login_fallback(state)
                return
        else:
            _render_login_fallback(state)
            return
    else:
        step_pass("Render CLI авторизован.")

    # --- Workspace ---
    workspace_name = state.get("render_workspace")
    workspace_id = state.get("render_workspace_id")

    # Проверяем текущий workspace
    current = run_cmd(
        ["render", "workspace", "current", "--output", "json"], timeout=15
    )
    if current["ok"]:
        try:
            data = json.loads(current["stdout"])
            workspace_name = data.get("name", "")
            workspace_id = data.get("id", "")
        except json.JSONDecodeError:
            pass

    if workspace_id:
        state["render_workspace"] = workspace_name
        state["render_workspace_id"] = workspace_id
        step_info(f"Workspace: {workspace_name}")
        print()
        if not ask_yes_no("Это reviewer/disposable workspace?",
                          default=False):
            step_fail("Workspace не подтверждён как reviewer. Завершение.")
            print()
            print("Для live proof используйте reviewer/test аккаунт,")
            print("не personal/prod-associated. Создайте отдельный workspace")
            print("или переключитесь на существующий reviewer/test workspace.")
            print()
            print("  render login              # перелогиниться под reviewer аккаунт")
            print("  render workspace current   # проверить текущий workspace")
            sys.exit(1)
    else:
        step_info("Workspace не выбран — ищу доступные...")
        workspace_name, workspace_id = _select_render_workspace(state)
        if not workspace_id:
            step_fail("Workspace не выбран. Render фаза недоступна.")
            print("  Создайте workspace в Render Dashboard:")
            print("    https://dashboard.render.com/")
            print("  Или выполните вручную: render workspace set")
            print("  Затем перезапустите installer.")
            if not ask_yes_no("Пропустить Render?"):
                sys.exit(1)
            state["render_skipped"] = True
            save_state(state)
            return

    save_state(state)

    # --- Создание сервиса ---
    if not service_id:
        service_name = plan.render_web_service_name
        supabase_url = state.get("supabase_url", "")
        anon_key = state.get("supabase_anon_key", "")

        if not anon_key:
            print()
            step_skip("Без Supabase ключа создание Render-сервиса с DB-backed /health невозможно.")
            if not ask_yes_no("Пропустить Render?"):
                sys.exit(1)
            state["render_skipped"] = True
            save_state(state)
            return

        # Сначала проверяем, существует ли сервис
        list_result = run_cmd(["render", "services", "--output", "json"], timeout=15)
        if list_result["ok"]:
            try:
                services = json.loads(list_result["stdout"])
                if services:
                    for s in services:
                        svc = s.get("service", s)
                        if svc.get("name") == service_name:
                            service_id = svc.get("id", "")
                            state["render_service_id"] = service_id
                            state["render_service_source"] = "existing"
                            state["render_service_status"] = "service_existing"
                            service_url = verify_render_service_url(
                                state=state,
                                run_cmd=run_cmd,
                                step_info=step_info,
                                service_id=service_id,
                                service_name=service_name,
                            )
                            if service_url:
                                step_pass(f"Найден существующий сервис: {service_url}")
                            else:
                                step_info(f"Сервис найден, но URL pending: {mask(service_id)}")
                            break
            except json.JSONDecodeError:
                pass

        # Если не найден — создаём
        if not service_id:
            print()
            if not ask_yes_no(f"Создать Render сервис '{service_name}' (free tier, Docker runtime)?"):
                if not ask_yes_no("Пропустить Render?"):
                    sys.exit(1)
                state["render_skipped"] = True
                save_state(state)
                return

            step_info("Создание сервиса (занимает 30-60 секунд)...")
            create_args = [
                "render", "services", "create",
                "--name", service_name,
                "--type", "web_service",
                "--runtime", "docker",
                "--repo", ADR_REPO_URL,
                "--branch", ADR_REPO_BRANCH,
                "--plan", "free",
                "--region", "frankfurt",
                "--output", "json",
                "--confirm",
                "--env-var", "ADR_PERSISTENCE=supabase",
                "--env-var", f"SUPABASE_URL=https://{state['supabase_project_ref']}.supabase.co",
                "--env-var", f"SUPABASE_API_KEY_PUBLISHABLE={anon_key}",
            ]

            result = run_cmd(create_args, timeout=120)
            if result["ok"]:
                try:
                    data = json.loads(result["stdout"])
                    if isinstance(data, list):
                        svc = data[0].get("service", data[0])
                    else:
                        svc = data.get("service", data)
                    service_id = svc.get("id", "")
                    if service_id:
                        state["render_service_id"] = service_id
                        state["render_service_source"] = "created_fresh"
                        state["render_service_status"] = "service_created"
                        service_url = verify_render_service_url(
                            state=state,
                            run_cmd=run_cmd,
                            step_info=step_info,
                            service_id=service_id,
                            service_name=service_name,
                        )
                        if service_url:
                            step_pass(f"Сервис создан: {service_url}")
                        else:
                            step_info(f"Сервис создан, но URL pending: {mask(service_id)}")
                except json.JSONDecodeError:
                    step_fail(f"Не удалось разобрать ответ: {result['stdout'][:200]}")
                    if not ask_yes_no("Пропустить Render?"):
                        sys.exit(1)
                    state["render_skipped"] = True
                    save_state(state)
                    return
            else:
                combined = result["combined"].lower()
                if "already" in combined or "exist" in combined:
                    step_info(f"Сервис уже существует: {service_name}")
                    # Ещё раз ищем по имени
                    list_result2 = run_cmd(["render", "services", "--output", "json"], timeout=15)
                    if list_result2["ok"]:
                        try:
                            services = json.loads(list_result2["stdout"])
                            if services:
                                for s in services:
                                    svc = s.get("service", s)
                                    if svc.get("name") == service_name:
                                        service_id = svc.get("id", "")
                                        state["render_service_id"] = service_id
                                        state["render_service_source"] = "existing"
                                        state["render_service_status"] = "service_existing"
                                        service_url = verify_render_service_url(
                                            state=state,
                                            run_cmd=run_cmd,
                                            step_info=step_info,
                                            service_id=service_id,
                                            service_name=service_name,
                                        )
                                        if service_url:
                                            step_pass(f"Найден существующий сервис: {service_url}")
                                        else:
                                            step_info(f"Сервис найден, но URL pending: {mask(service_id)}")
                                        break
                        except json.JSONDecodeError:
                            pass

                if not service_id:
                    step_fail(f"Не удалось создать сервис: {result['combined']}")
                    if not ask_yes_no("Пропустить Render?"):
                        sys.exit(1)
                    state["render_skipped"] = True
                    save_state(state)
                    return
    else:
        if state.get("render_url_status") != "url_verified":
            service_url = verify_render_service_url(
                state=state,
                run_cmd=run_cmd,
                step_info=step_info,
                service_id=service_id,
                service_name=plan.render_web_service_name,
            )
        if not state.get("render_service_source"):
            state["render_service_source"] = "existing"
        if not state.get("render_service_status"):
            state["render_service_status"] = "service_existing"
        step_pass(f"Сервис: {service_url or mask(service_id)} (из сохранённого состояния)")

    save_state(state)

    # --- Ожидание деплоя + /health ---
    if service_url:
        print()
        step_info("Ожидание деплоя (может занять 2-5 минут)...")
        step_info(f"Проверьте статус: https://dashboard.render.com/web/{service_id}")

        health_url = f"{service_url}/health" if not service_url.endswith("/") else f"{service_url}health"

        for attempt in range(12):
            time.sleep(15)
            try:
                req = urllib.request.Request(health_url)
                resp = urllib.request.urlopen(req, timeout=10)
                body = json.loads(resp.read().decode())
                validation = _validate_live_render_health(body)
                if validation["valid"]:
                    step_pass(f"Деплой готов! /health: HTTP {resp.status}, Supabase-backed ADR validated")
                    step_info(f"  persistence: {validation['persistence']}, "
                              f"db.reachable: {validation['db_reachable']}, "
                              f"schema_smoke: {validation['db_smoke']}")
                    state["health_ok"] = True
                    break
                else:
                    step_fail(f"/health: {validation['reason']}")
                    state["health_ok"] = False
                    break
            except urllib.error.HTTPError as e:
                if e.code == 503:
                    step_info(f"Попытка {attempt + 1}/12: HTTP 503 (ещё деплоится)...")
                else:
                    step_info(f"Попытка {attempt + 1}/12: HTTP {e.code}")
            except Exception as e:
                step_info(f"Попытка {attempt + 1}/12: {e}")
        else:
            step_fail("Сервис не ответил за 3 минуты. Проверьте статус в Render Dashboard.")
    else:
        if state.get("render_url_status") != "url_pending":
            state["render_url_status"] = "url_missing_or_unverified"
        state["render_url_verified"] = False
        step_skip("URL сервиса не подтверждён Render API/read-back — пропускаем /health проверку.")
        print("  Safe next step: дождитесь URL в Render Dashboard и перезапустите installer.")
        print("  Telegram webhook phase по умолчанию заблокирована до url_verified.")

    # Очистка stale skip-флагов при успешном завершении фазы
    state.pop("render_skipped", None)
    save_state(state)


def _render_login_fallback(state: dict) -> None:
    """Fallback: вход вручную через новый терминал."""
    print()
    print("  Выполните в терминале:")
    print("    render login")
    print("  Откроется браузер для device-code авторизации.")
    print("  После завершения нажмите Enter.")
    print()
    ask("  Нажмите Enter когда будете готовы...")

    if not check_cli_logged_in("render", ["whoami"]):
        step_fail("Render всё ещё не авторизован.")
        if not ask_yes_no("Пропустить Render?"):
            sys.exit(1)
        state["render_skipped"] = True
        save_state(state)
    else:
        step_pass("Render CLI авторизован (через новый терминал).")


def _select_render_workspace(state: dict) -> tuple[str, str]:
    """Выбирает Render workspace: auto-pick если один, выбор если несколько.

    Использует render workspace current, затем интерактивный picker CLI.

    Returns:
        (workspace_name, workspace_id) — оба пустые если ничего не выбрано.
    """
    # Проверяем текущий workspace
    current = run_cmd(
        ["render", "workspace", "current", "--output", "json"], timeout=15
    )
    if current["ok"]:
        try:
            data = json.loads(current["stdout"])
            ws_name = data.get("name", "")
            ws_id = data.get("id", "")
            if ws_id:
                step_pass(f"Workspace: {ws_name}")
                return ws_name, ws_id
        except json.JSONDecodeError:
            pass

    # Workspace не выбран — интерактивный picker Render CLI
    print()
    step_info("Запуск интерактивного выбора workspace...")
    print("  Render CLI покажет список доступных workspace.")
    print("  Выберите workspace стрелками и нажмите Enter.")
    print()

    run_interactive(["render", "workspace", "set"], timeout=120)

    # Повторная проверка
    current = run_cmd(
        ["render", "workspace", "current", "--output", "json"], timeout=15
    )
    if current["ok"]:
        try:
            data = json.loads(current["stdout"])
            ws_name = data.get("name", "")
            ws_id = data.get("id", "")
            if ws_id:
                state["render_workspace"] = ws_name
                state["render_workspace_id"] = ws_id
                step_pass(f"Workspace выбран: {ws_name}")
                return ws_name, ws_id
        except json.JSONDecodeError:
            pass

    # Ничего не выбрано
    print()
    print("  Не удалось выбрать workspace.")
    print("  Выполните вручную: render workspace set")
    print("  Затем перезапустите installer.")
    return "", ""
