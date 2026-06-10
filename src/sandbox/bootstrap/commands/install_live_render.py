"""Фаза Render для живого мастера установки."""
import json
import sys
import time
import urllib.request
import urllib.error

from ..live_executor import (
    ask,
    ask_yes_no,
    run_cmd,
    check_cli_logged_in,
    step_pass,
    step_skip,
    step_fail,
    step_info,
    save_state,
    mask,
)


def run_render_phase(plan, state: dict) -> None:
    """Фаза Render: login, создание сервиса, env vars, деплой, /health."""
    service_id = state.get("render_service_id")
    service_url = state.get("render_service_url")

    # --- Авторизация ---
    if not check_cli_logged_in("render", ["whoami"]):
        print()
        print("  Render CLI не авторизован.")
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
            return
    step_pass("Render CLI авторизован.")

    # --- Workspace ---
    whoami = run_cmd(["render", "whoami", "--output", "json"], timeout=15)
    if whoami["ok"]:
        try:
            data = json.loads(whoami["stdout"])
            state["render_workspace"] = data.get("workspace", {}).get("name", "неизвестно")
        except json.JSONDecodeError:
            pass
    step_info(f"Workspace: {state.get('render_workspace', 'неизвестно')}")

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

        print()
        if not ask_yes_no(f"Создать Render сервис '{service_name}' (free tier, Docker runtime)?"):
            if not ask_yes_no("Пропустить Render?"):
                sys.exit(1)
            state["render_skipped"] = True
            save_state(state)
            return

        step_info("Создание сервиса (занимает 30-60 секунд)...")
        create_args = [
            "render", "services", "create", service_name,
            "--type", "web_service",
            "--runtime", "docker",
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
                service_url = svc.get("url", "")
                if service_id:
                    state["render_service_id"] = service_id
                    state["render_service_url"] = service_url
                    step_pass(f"Сервис создан: {service_url or mask(service_id)}")
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
                list_result = run_cmd(["render", "services", "--output", "json"], timeout=15)
                if list_result["ok"]:
                    try:
                        services = json.loads(list_result["stdout"])
                        for s in services:
                            svc_inner = s.get("service", s)
                            if svc_inner.get("name") == service_name:
                                service_id = svc_inner.get("id", "")
                                service_url = svc_inner.get("url", "")
                                state["render_service_id"] = service_id
                                state["render_service_url"] = service_url
                                step_pass(f"Найден существующий сервис: {service_url}")
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
        step_pass(f"Сервис: {service_url or mask(service_id)} (из сохранённого состояния)")

    save_state(state)

    # --- Ожидание деплоя + /health ---
    if service_url:
        print()
        step_info("Ожидание деплоя (может занять 2-5 минут)...")
        step_info(f"Проверьте статус: https://dashboard.render.com/web/srv-{service_id}")

        health_url = f"{service_url}/health" if not service_url.endswith("/") else f"{service_url}health"

        for attempt in range(12):
            time.sleep(15)
            try:
                req = urllib.request.Request(health_url)
                resp = urllib.request.urlopen(req, timeout=10)
                body = json.loads(resp.read().decode())
                step_pass(f"Деплой готов! /health: HTTP {resp.status}")
                step_info(f"Ответ: {json.dumps(body, ensure_ascii=False)}")
                state["health_ok"] = True
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
        step_skip("URL сервиса неизвестен — пропускаем /health проверку.")

    save_state(state)
