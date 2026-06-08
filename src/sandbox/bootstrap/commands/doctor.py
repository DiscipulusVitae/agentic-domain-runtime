import json
from ..env_checks import (
    check_python,
    check_uv,
    check_docker,
    check_supabase,
    check_render,
)

def run_doctor(json_mode: bool) -> int:
    """Выполняет проверку локальных зависимостей (doctor)."""
    checks = {}

    checks["python"] = check_python()
    checks["uv"] = check_uv()
    checks["docker"] = check_docker()
    checks["supabase"] = check_supabase()
    checks["render"] = check_render()

    has_critical_fail = any(checks[name]["status"] == "FAIL" for name in ("python", "uv"))
    has_optional_fail = any(checks[name]["status"] == "FAIL" for name in ("docker", "supabase", "render"))

    if json_mode:
        output = {
            "status": "failed" if has_critical_fail else "success",
            "checks": checks
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Doctor ===")
        print("Проверка локального окружения:")
        for name, info in checks.items():
            status_str = f"[{info['status']}]"
            print(f"  {status_str:<8} {name:<10}: {info['message']}")
            if info["status"] == "FAIL" and "hint" in info:
                print(f"           Подсказка: {info['hint']}")
                if info.get("action"):
                    print(f"           Команда:   {info['action']}")
        print("=" * 28)

        if has_critical_fail:
            print("\nОшибка: Обнаружены критические проблемы в локальном окружении (отсутствует Python >= 3.13 или uv).")
            print("Без них невозможно запустить локальный offline sandbox.")
        elif has_optional_fail:
            print("\nВнимание: Отсутствуют некоторые опциональные инструменты (Docker, Supabase CLI, Render CLI).")
            print("Базовый offline-путь доступен, но эти инструменты потребуются для локального запуска Supabase или деплоя.")
        else:
            print("\nЛокальное окружение готово к установке.")

    return 1 if has_critical_fail else 0
