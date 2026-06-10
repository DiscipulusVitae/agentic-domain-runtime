"""Фаза Supabase для живого мастера установки."""
import json
import sys

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
    get_supabase_api_keys,
)


def run_supabase_phase(plan, state: dict) -> None:
    """Фаза Supabase: login, org, проект, схема, ключи."""
    project_ref = state.get("supabase_project_ref")
    anon_key = state.get("supabase_anon_key")

    # --- Авторизация ---
    if not check_cli_logged_in("supabase", ["projects", "list", "--output", "json"]):
        print()
        print("  Supabase CLI не авторизован.")
        print("  Откройте НОВЫЙ терминал и выполните:")
        print("    supabase login")
        print("  После завершения вернитесь сюда и нажмите Enter.")
        print()
        ask("  Нажмите Enter когда будете готовы...")

        if not check_cli_logged_in("supabase", ["projects", "list", "--output", "json"]):
            step_fail("Supabase всё ещё не авторизован.")
            if not ask_yes_no("  Пропустить Supabase и продолжить без БД?"):
                sys.exit(1)
            state["supabase_skipped"] = True
            save_state(state)
            return
    step_pass("Supabase CLI авторизован.")

    # --- Организация ---
    if not state.get("supabase_org_id"):
        print()
        orgs = run_cmd(["supabase", "orgs", "list", "--output", "json"], timeout=15)
        org_list = []
        if orgs["ok"]:
            try:
                org_list = json.loads(orgs["stdout"])
            except json.JSONDecodeError:
                pass

        if not org_list:
            org_name = plan.supabase_organization
            step_info(f"Создание организации: {org_name}")
            create = run_cmd(["supabase", "orgs", "create", org_name], timeout=30)
            if not create["ok"]:
                combined = create["combined"].lower()
                if "already" in combined or "exist" in combined:
                    step_info(f"Организация уже существует: {org_name}")
                else:
                    step_fail(f"Не удалось создать организацию: {create['combined']}")
                    if not ask_yes_no("Пропустить Supabase?"):
                        sys.exit(1)
                    state["supabase_skipped"] = True
                    save_state(state)
                    return
            orgs = run_cmd(["supabase", "orgs", "list", "--output", "json"], timeout=15)
            if orgs["ok"]:
                org_list = json.loads(orgs["stdout"])

        if org_list:
            org = org_list[0]
            state["supabase_org_id"] = org.get("id", "")
            state["supabase_org_name"] = org.get("name", "")
            step_pass(f"Организация: {org.get('name', 'неизвестно')} ({mask(org.get('id', ''))})")
        else:
            state["supabase_org_id"] = ""
            step_skip("Не удалось определить организацию, будет использована default.")
    else:
        step_pass(f"Организация: {state.get('supabase_org_name', 'неизвестно')} (из сохранённого состояния)")

    save_state(state)

    # --- Создание проекта ---
    if not project_ref:
        print()
        project_name = plan.supabase_project_name
        org_id = state.get("supabase_org_id", "")

        if not ask_yes_no(f"Создать Supabase проект '{project_name}' в регионе eu-central-1?"):
            if not ask_yes_no("Пропустить Supabase?"):
                sys.exit(1)
            state["supabase_skipped"] = True
            save_state(state)
            return

        step_info("Создание проекта (это может занять минуту)...")
        create_args = ["supabase", "projects", "create", project_name,
                       "--region", "eu-central-1", "--output", "json"]
        if org_id:
            create_args += ["--org-id", org_id]

        result = run_cmd(create_args, timeout=120)
        if not result["ok"]:
            combined = result["combined"].lower()
            if "already" in combined or "exist" in combined:
                step_info(f"Проект уже существует: {project_name}")
                list_result = run_cmd(["supabase", "projects", "list", "--output", "json"], timeout=15)
                if list_result["ok"]:
                    try:
                        projects = json.loads(list_result["stdout"])
                        for p in projects:
                            if p.get("name") == project_name:
                                project_ref = p.get("id", "")
                                state["supabase_project_ref"] = project_ref
                                step_pass(f"Найден существующий проект: {mask(project_ref)}")
                                break
                    except json.JSONDecodeError:
                        pass
            if not project_ref:
                step_fail(f"Не удалось создать проект: {result['combined']}")
                if not ask_yes_no("Пропустить Supabase?"):
                    sys.exit(1)
                state["supabase_skipped"] = True
                save_state(state)
                return
        else:
            try:
                data = json.loads(result["stdout"])
                project_ref = data.get("id", "")
                if project_ref:
                    state["supabase_project_ref"] = project_ref
                    step_pass(f"Проект создан: {mask(project_ref)}")
            except json.JSONDecodeError:
                step_fail("Не удалось разобрать ответ создания проекта")
                if not ask_yes_no("Пропустить Supabase?"):
                    sys.exit(1)
                state["supabase_skipped"] = True
                save_state(state)
                return
    else:
        step_pass(f"Проект: {mask(project_ref)} (из сохранённого состояния)")

    save_state(state)

    # --- Link ---
    if not state.get("supabase_linked"):
        print()
        step_info("Привязка проекта (supabase link)...")
        link = run_cmd(["supabase", "link", "--project-ref", project_ref, "--yes"], timeout=60)
        if link["ok"]:
            state["supabase_linked"] = True
            step_pass("Проект привязан.")
        else:
            step_fail(f"Не удалось привязать проект: {link['combined']}")
            if not ask_yes_no("Продолжить без link?"):
                if not ask_yes_no("Пропустить Supabase?"):
                    sys.exit(1)
                state["supabase_skipped"] = True
                save_state(state)
                return
    else:
        step_pass("Проект привязан (из сохранённого состояния).")

    save_state(state)

    # --- DB Push ---
    if not state.get("supabase_db_pushed"):
        print()
        if not ask_yes_no("Применить схему БД (supabase db push)?"):
            step_skip("Применение схемы пропущено.")
        else:
            step_info("Применение миграций...")
            push = run_cmd(["supabase", "db", "push", "--yes"], timeout=120)
            if push["ok"]:
                state["supabase_db_pushed"] = True
                step_pass("Схема БД применена.")
            else:
                step_fail(f"Ошибка применения схемы: {push['combined']}")
                if not ask_yes_no("Продолжить без схемы?"):
                    if not ask_yes_no("Пропустить Supabase?"):
                        sys.exit(1)
                    state["supabase_skipped"] = True
                    save_state(state)
                    return
    else:
        step_pass("Схема уже применена (из сохранённого состояния).")

    save_state(state)

    # --- Config Push (PostgREST schemas) ---
    if not state.get("supabase_config_pushed") and not state.get("supabase_skipped"):
        print()
        if ask_yes_no("Экспонировать схемы в PostgREST (supabase config push)?"):
            step_info("Применение конфига...")
            config = run_cmd(["supabase", "config", "push", "--yes"], timeout=60)
            if config["ok"]:
                state["supabase_config_pushed"] = True
                step_pass("Схемы экспонированы в PostgREST.")
            else:
                step_info(f"Конфиг: {config['combined'][:120]}")
                state["supabase_config_pushed"] = True

    save_state(state)

    # --- Seed + Smoke ---
    if not state.get("supabase_seeded") and not state.get("supabase_skipped"):
        print()
        step_info("Наполнение тестовыми данными (seed.sql)...")
        seed = run_cmd(["supabase", "db", "query", "--linked", "--file", "supabase/seed.sql"],
                       timeout=30)
        if seed["ok"]:
            state["supabase_seeded"] = True
            step_pass("Seed применён.")
        else:
            step_info(f"Seed: {seed['combined'][:100]}")

        print()
        step_info("Проверка БД (smoke.sql)...")
        smoke = run_cmd(["supabase", "db", "query", "--linked", "--file", "supabase/smoke.sql"],
                        timeout=60)
        if smoke["ok"]:
            step_pass("Smoke.sql пройден.")
        else:
            step_fail(f"Smoke.sql: {smoke['combined'][:200]}")

    save_state(state)

    # --- API ключи ---
    if not anon_key and project_ref:
        print()
        step_info("Получение API ключа...")
        keys = get_supabase_api_keys(project_ref)
        anon_key = keys.get("anon_key", "")
        if anon_key:
            state["supabase_anon_key"] = anon_key
            state["supabase_url"] = keys.get("url", f"https://{project_ref}.supabase.co")
            step_pass(f"Anon ключ: {mask(anon_key)}")
        else:
            print()
            print("  Не удалось получить API ключ автоматически.")
            print(f"  Откройте Dashboard: https://supabase.com/dashboard/project/{project_ref}/settings/api")
            print("  Скопируйте 'anon public' ключ и вставьте сюда.")
            anon_key = ask("  Anon ключ: ").strip()
            if anon_key:
                state["supabase_anon_key"] = anon_key
                state["supabase_url"] = f"https://{project_ref}.supabase.co"
                step_pass(f"Anon ключ: {mask(anon_key)}")
            else:
                step_skip("Anon ключ не задан — /health проверка Render будет недоступна.")

    save_state(state)
