import datetime
import json
import os
import sys
from pathlib import Path

def run_bootstrap_simulate(local: bool, fail_after_apply: bool, json_mode: bool) -> int:
    """Выполняет локальную синтетическую симуляцию цикла plan -> preflight -> apply -> verify -> rollback.

    Не взаимодействует с внешними API, БД или облачными провайдерами.
    """
    if not local:
        print("Ошибка: Локальная симуляция требует флага --local.", file=sys.stderr)
        return 1

    # 1. Plan Phase
    suffix = "sim123"
    sb_project = f"adr-sim-db-{suffix}"
    sb_org = "adr-sim-org"
    render_service = f"adr-sim-app-{suffix}"
    render_env = f"adr-sim-env-{suffix}"
    webhook_url = f"https://{render_service}.local/telegram-webhook"

    plan_details = {
        "supabase_project_name": sb_project,
        "supabase_organization": sb_org,
        "render_web_service_name": render_service,
        "render_environment_group": render_env,
        "webhook_target_url": webhook_url
    }

    steps_log = []

    steps_log.append({
        "phase": "plan",
        "status": "success",
        "message": "Локальный синтетический план успешно сгенерирован",
        "details": plan_details
    })

    # 2. Preflight Phase
    preflight_details = {
        "local_environment_checks": {
            "python_version_ok": True,
            "uv_available": True,
            "docker_available": True
        },
        "mock_endpoints_reachable": {
            "supabase_api": True,
            "render_api": True,
            "telegram_api": True
        }
    }
    steps_log.append({
        "phase": "preflight",
        "status": "success",
        "message": "Локальные preflight-проверки успешно завершены (имитация доступности API)",
        "details": preflight_details
    })

    # 3. Apply Phase
    state_path = Path(".bootstrap-state-sim.json")

    # Имитируем создание синтетических локальных ресурсов и запись их в файл состояния
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace("+00:00", "Z")
    sim_state = {
        "mode": "local-simulation",
        "status": "applying",
        "generated_at": timestamp,
        "resources": plan_details,
        "applied_steps": []
    }

    # Записываем промежуточное состояние (для демонстрации частичного apply)
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(sim_state, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        if json_mode:
            print(json.dumps({"error": f"Failed to initialize sim state: {str(e)}"}, indent=2), file=sys.stderr)
        else:
            print(f"Ошибка инициализации состояния симуляции: {e}", file=sys.stderr)
        return 1

    # Шаг Apply 1: Supabase
    sim_state["applied_steps"].append("supabase_sim_db_created")
    # Шаг Apply 2: Render
    sim_state["applied_steps"].append("render_sim_service_created")
    # Шаг Apply 3: Telegram
    sim_state["applied_steps"].append("telegram_sim_webhook_configured")

    sim_state["status"] = "applied"

    # Сохраняем финальное состояние apply
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(sim_state, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        if json_mode:
            print(json.dumps({"error": f"Failed to save applied sim state: {str(e)}"}, indent=2), file=sys.stderr)
        else:
            print(f"Ошибка сохранения состояния симуляции: {e}", file=sys.stderr)
        return 1

    steps_log.append({
        "phase": "apply",
        "status": "success",
        "message": "Синтетические локальные ресурсы успешно созданы (состояние записано в .bootstrap-state-sim.json)",
        "details": {
            "applied_steps": sim_state["applied_steps"],
            "state_file_written": True
        }
    })

    # 4. Verify Phase
    verify_success = not fail_after_apply
    verify_status = "success" if verify_success else "failed"
    verify_msg = (
        "Синтетические smoke-тесты успешно пройдены (локальный рантайм вернул HTTP 200 OK)"
        if verify_success else
        "Синтетический smoke-тест провален: Локальный синтетический сервис вернул HTTP 500 Internal Server Error (Симуляция ошибки)"
    )

    # Обновляем состояние в файле перед rollback
    sim_state["status"] = "verified" if verify_success else "failed"
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(sim_state, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except Exception:
        pass

    steps_log.append({
        "phase": "verify",
        "status": verify_status,
        "message": verify_msg,
        "details": {
            "local_health_check": "passed" if verify_success else "failed_http_500",
            "synthetic_telegram_webhook": "passed" if verify_success else "skipped"
        }
    })

    # 5. Rollback Phase
    # Читаем состояние из файла перед откатом, чтобы убедиться в консистентности
    rollback_steps = []
    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                loaded_state = json.load(f)

            # Revert steps in reverse order
            for step in reversed(loaded_state.get("applied_steps", [])):
                rollback_steps.append(f"reverted_{step}")

            # Удаляем файл состояния
            os.remove(state_path)
        except Exception as e:
            rollback_steps.append(f"rollback_failed: {str(e)}")

    steps_log.append({
        "phase": "rollback",
        "status": "success",
        "message": "Автоматический локальный откат успешно выполнен. Локальное состояние очищено.",
        "details": {
            "reverted_steps": rollback_steps,
            "state_file_removed": not state_path.exists()
        }
    })

    # Итоговый статус симуляции
    simulation_success = verify_success

    if json_mode:
        output = {
            "simulation": "local-only-synthetic",
            "fail_after_apply": fail_after_apply,
            "success": simulation_success,
            "steps": steps_log,
            "final_state": "ROLLED_BACK"
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Simulation (LOCAL-ONLY) ===")
        print("Режим: Локальная синтетическая симуляция цикла развертывания.")
        print("Внимание: Данная команда не производит никаких изменений во внешней инфраструктуре.")
        print()

        for idx, step in enumerate(steps_log, 1):
            phase_name = step["phase"].upper()
            status_str = f"[{step['status'].upper()}]"
            print(f"{idx}. Фаза {phase_name} {status_str}")
            print(f"   Сообщение: {step['message']}")
            if step["phase"] == "plan":
                for k, v in step["details"].items():
                    print(f"   - {k}: {v}")
            elif step["phase"] == "apply":
                print("   Примененные шаги:")
                for s in step["details"]["applied_steps"]:
                    print(f"   [x] {s}")
            elif step["phase"] == "rollback":
                print("   Откаченные шаги:")
                for s in step["details"]["reverted_steps"]:
                    print(f"   [x] {s}")
            print()

        print("-" * 50)
        if simulation_success:
            print("Симуляция завершена УСПЕШНО. Все фазы пройдены, ресурсы очищены.")
        else:
            print("Симуляция завершена со СБОЕМ на фазе верификации. Выполнен автоматический ОТКАТ.")
        print("=" * 45)

    return 0 if simulation_success else 1
