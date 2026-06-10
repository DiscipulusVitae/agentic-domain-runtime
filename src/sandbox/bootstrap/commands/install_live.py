"""Мастер установки ADR — живой guided wizard (installer v1).

Запуск: uv run python -m src.sandbox bootstrap install --yes

Ведёт пользователя пошагово: doctor → plan → Supabase → Render → smoke → summary.
Сохраняет состояние в .bootstrap-state.json для восстановления после сбоев.
"""

import json
import sys
import time
import urllib.request
import urllib.error

from ..env_checks import check_python, check_uv, check_docker, check_supabase, check_render
from ..plan import generate_bootstrap_plan

from ..live_executor import (
    ask,
    ask_yes_no,
    run_cmd,
    step_header,
    step_pass,
    step_skip,
    step_fail,
    step_info,
    save_state,
    load_state,
    mask,
)

from .install_live_supabase import run_supabase_phase
from .install_live_render import run_render_phase

TOTAL_STEPS = 6


def run_install_live(json_mode: bool = False) -> int:
    """Запускает живой мастер установки ADR."""
    state = load_state()
    plan = generate_bootstrap_plan()

    print("=" * 60)
    print("  ADR Bootstrap — Мастер установки v1")
    print("=" * 60)
    print()
    print("Этот мастер проведёт вас через развёртывание ADR в облаке.")
    print("Что будет создано (disposable, free tier):")
    print(f"  - Supabase проект: {plan.supabase_project_name}")
    print(f"  - Render сервис:   {plan.render_web_service_name}")
    print()
    print("Что потребуется:")
    print("  - Supabase аккаунт (reviewer/test, не production)")
    print("  - Render аккаунт (reviewer/test, не production)")
    print("  - Supabase CLI + Render CLI (проверим далее)")
    print()
    print("Мутирующие операции запрашивают явное подтверждение (y/N).")
    print("Состояние сохраняется в .bootstrap-state.json после каждого шага.")
    print()

    if not ask_yes_no("Начать установку?", default=True):
        print("Установка отменена.")
        return 0

    # Step 1: Doctor / Preflight
    step_header(1, TOTAL_STEPS, "Проверка окружения (doctor)")

    checks = {
        "python": check_python(),
        "uv": check_uv(),
        "docker": check_docker(),
        "supabase": check_supabase(),
        "render": check_render(),
    }

    critical_fail = False
    for name, info in checks.items():
        marker = "[OK]" if info["status"] == "OK" else "[WARN]" if info["status"] == "WARN" else "[FAIL]"
        print(f"  {marker:6} {name:<12} {info['message']}")
        if info["status"] == "FAIL":
            if name in ("python", "uv"):
                critical_fail = True
            if "hint" in info:
                print(f"           {info['hint']}")
            if info.get("action"):
                print(f"           Команда: {info['action']}")

    if critical_fail:
        print()
        print("Критические ошибки: python или uv недоступны.")
        print("Установите Python 3.13+ и uv, затем перезапустите мастер.")
        return 1

    state["step1_doctor"] = {"checks": {k: v["status"] for k, v in checks.items()}}
    save_state(state)
    step_pass("Окружение готово.")

    # Step 2: Plan & Confirmation
    step_header(2, TOTAL_STEPS, "План развёртывания")

    print(f"  Supabase проект:     {plan.supabase_project_name}")
    print(f"  Supabase организация: {plan.supabase_organization}")
    print(f"  Render сервис:       {plan.render_web_service_name}")
    print(f"  Регион:              eu-central-1 (Frankfurt)")
    print(f"  План Render:         free (Docker runtime)")
    print()
    print("Этапы:")
    print("  1. Supabase: логин → создание проекта → схема БД → smoke.sql")
    print("  2. Render:   логин → создание сервиса → env vars → /health проверка")
    print("  3. Сводка и инструкции по очистке")
    print()

    if not ask_yes_no("Продолжить с этим планом?", default=True):
        print("Установка отменена.")
        return 0

    state["step2_plan"] = {"approved": True, "supabase_project": plan.supabase_project_name,
                           "render_service": plan.render_web_service_name}
    save_state(state)
    step_pass("План подтверждён.")

    # Step 3: Supabase Setup
    step_header(3, TOTAL_STEPS, "Supabase: настройка")
    run_supabase_phase(plan, state)

    # Step 4: Render Setup
    step_header(4, TOTAL_STEPS, "Render: настройка")
    run_render_phase(plan, state)

    # Step 5: Smoke Tests
    step_header(5, TOTAL_STEPS, "Проверка работоспособности")
    _run_smoke_phase(plan, state)

    # Step 6: Summary & Cleanup
    step_header(6, TOTAL_STEPS, "Сводка и очистка")
    _print_summary(plan, state)

    return 0


def _run_smoke_phase(plan, state: dict) -> None:
    """Фаза проверки работоспособности."""
    service_url = state.get("render_service_url")
    if not service_url or state.get("render_skipped"):
        step_skip("Render не настроен — проверки пропущены.")
        return

    health_url = f"{service_url}/health" if not service_url.endswith("/") else f"{service_url}health"

    try:
        req = urllib.request.Request(health_url)
        resp = urllib.request.urlopen(req, timeout=10)
        body = json.loads(resp.read().decode())
        step_pass(f"/health: HTTP {resp.status}")
        print(f"  status:      {body.get('status')}")
        print(f"  persistence: {body.get('persistence')}")
        db = body.get("database", {})
        print(f"  db.configured: {db.get('configured')}")
        print(f"  db.reachable:  {db.get('reachable')}")
        print(f"  db.schema_smoke: {db.get('schema_smoke')}")
    except Exception as e:
        step_fail(f"/health: {e}")


def _print_summary(plan, state: dict) -> None:
    """Выводит сводку и инструкции по очистке."""
    print()

    if state.get("supabase_skipped"):
        print("  Supabase: пропущен.")
    elif state.get("supabase_project_ref"):
        print(f"  Supabase проект:   {mask(state['supabase_project_ref'])}")
        print(f"  Supabase URL:      https://{state['supabase_project_ref']}.supabase.co")
    else:
        print("  Supabase: не создан.")

    if state.get("render_skipped"):
        print("  Render: пропущен.")
    elif state.get("render_service_id"):
        print(f"  Render сервис:     {mask(state['render_service_id'])}")
        print(f"  Render URL:        {state.get('render_service_url', 'неизвестен')}")
    else:
        print("  Render: не создан.")

    if state.get("health_ok"):
        print("  /health:           OK")

    print()
    print("--- Инструкции по очистке ---")
    print()

    if state.get("render_service_id"):
        sid = state['render_service_id']
        print(f"  # Удалить Render сервис:")
        print(f"  # Dashboard: https://dashboard.render.com/web/srv-{sid}/settings")
        print(f"  # REST API:  curl -X DELETE https://api.render.com/v1/services/{sid}")
        print()

    if state.get("supabase_project_ref"):
        ref = state["supabase_project_ref"]
        print(f"  # Удалить Supabase проект:")
        print(f"  supabase projects delete {ref} --yes")
        print()

    print("  # Удалить локальный файл состояния:")
    print("  rm .bootstrap-state.json")
    print()

    state["completed"] = True
    save_state(state)
    print("=" * 60)
    print("  Установка завершена.")
    print(f"  Состояние сохранено в .bootstrap-state.json")
    print("=" * 60)
