"""
CLI harness для тестирования Butler классификатора и доменных потоков в песочнице.

Текущие правила работы CLI:
1. Одиночный позиционный аргумент текста по умолчанию запускает полный сквозной flow (--full по умолчанию).
   Пример:
     uv run python -m src.sandbox "Добавь рецепт борща"
     (Выполняется классификация, запуск доменного хендлера и эмуляция сохранения).

2. Для сценариев прогона по файлу (--scenario) по умолчанию выполняется только классификация.
   Для запуска сквозного flow по сценарию требуется явно передать флаг --full.
   Примеры:
     uv run python -m src.sandbox --scenario kitchen
     (Только классификация всех кейсов из сценария)
     
     uv run python -m src.sandbox --scenario kitchen --full
     (Классификация и полный сквозной flow для всех кейсов из сценария)

3. Если аргументы отсутствуют, CLI пытается читать из стандартного ввода (stdin) при условии,
   что stdin не является интерактивным терминалом (not sys.stdin.isatty()).
   Пример:
     echo "Добавь книгу Хроники Зеленого Архива, Виктор Классик" | uv run python -m src.sandbox
     (Будет прочитан текст из stdin и запущен полный сквозной flow)
     
   Если stdin является интерактивным терминалом (sys.stdin.isatty()), выводится help-сообщение.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from src.sandbox.fake_llm import FakeLLMClient
from src.sandbox.contracts import ButlerClassifierService

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def list_scenarios() -> None:
    """Выводит список доступных scenario файлов из директории fixtures."""
    if not FIXTURES_DIR.exists():
        print(f"Директория фикстур не найдена: {FIXTURES_DIR}")
        return

    files = list(FIXTURES_DIR.glob("*_scenarios.json"))
    if not files:
        print("Scenario файлы не найдены.")
        return

    print("Доступные сценарии:")
    for f in sorted(files):
        # Выводим имя без суффикса _scenarios.json для удобства запуска
        name = f.name.replace("_scenarios.json", "")
        print(f"  - {name} ({f.name})")


def find_scenario_file(scenario_name: str) -> Path | None:
    """Находит файл сценария по имени или пути."""
    # 1. Попробуем точное совпадение пути
    path = Path(scenario_name)
    if path.is_file():
        return path

    # 2. Попробуем в директории fixtures
    names_to_try = [
        scenario_name,
        f"{scenario_name}_scenarios.json",
        f"{scenario_name}.json",
    ]
    for name in names_to_try:
        p = FIXTURES_DIR / name
        if p.is_file():
            return p

    return None


async def run_single_text(text: str, full: bool = False) -> None:
    """Классифицирует одиночный текст. При full=True запускает сквозной SandboxHarness."""
    if full:
        from src.sandbox.harness import SandboxHarness
        harness = SandboxHarness()
        
        print("=== Sandbox Harness: Full Flow Run ===")
        print(f"Input text: '{text}'")
        print("-" * 60)
        
        result = await harness.run_flow(text)
        
        print(f"Trace:  {result['trace']}")
        print("Routing Decision:")
        print(f"  Domain:     {result['routing'].get('domain_id')}")
        print(f"  Agent:      {result['routing'].get('agent_id')}")
        print(f"  Confidence: {result['routing'].get('confidence'):.2f}")
        print(f"Success:      {result['success']}")
        
        if result.get("output"):
            print("\nGenerated Output/Responses:")
            print(result["output"])
        print("=" * 38)
    else:
        # Старое поведение (только классификация Butler)
        fake_client = FakeLLMClient(agent_id="core.butler")
        classifier = ButlerClassifierService(llm_client=fake_client)

        result = await classifier.classify(text, "text")

        print("=== Butler Routing Decision ===")
        print(f"Domain:     {result.domain}")
        print(f"Agent:      {result.agent}")
        print(f"Intent:     {result.decision.intent if result.decision else 'unknown'}")
        print(f"Confidence: {result.confidence:.2f}")
        print(f"Valid:      {result.is_valid}")
        print(f"Clarification needed: {result.needs_clarification}")


async def run_scenario(scenario_path: Path, full: bool = False) -> None:
    """Загружает сценарии из файла, прогоняет каждый и печатает таблицу результатов."""
    try:
        with open(scenario_path, "r", encoding="utf-8") as f:
            scenarios = json.load(f)
    except Exception as e:
        print(f"Ошибка чтения файла сценария: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(scenarios, list):
        print("Файл сценария должен содержать JSON массив.", file=sys.stderr)
        sys.exit(1)

    harness = None
    classifier = None
    if full:
        from src.sandbox.harness import SandboxHarness
        harness = SandboxHarness()
        print(f"Запуск сквозного сценария с SandboxHarness: {scenario_path.name}")
    else:
        fake_client = FakeLLMClient(agent_id="core.butler")
        classifier = ButlerClassifierService(llm_client=fake_client)
        print(f"Запуск сценария: {scenario_path.name}")
        
    print("-" * 140)
    if full:
        print(
            f"{'Input':<40} | {'Expected Domain':<15} | {'Actual Domain':<15} | {'Expected Agent':<18} | {'Actual Agent':<18} | {'Match?':<6} | {'Persisted?':<10}"
        )
    else:
        print(
            f"{'Input':<45} | {'Expected Domain':<15} | {'Actual Domain':<15} | {'Expected Agent':<18} | {'Actual Agent':<18} | {'Match?':<6}"
        )
    print("-" * 140)

    passed_count = 0
    for idx, item in enumerate(scenarios, 1):
        input_text = item.get("input", "")
        expected_domain = item.get("expected_domain")
        expected_agent = item.get("expected_agent")

        persisted_str = "N/A"
        if full and harness:
            res = await harness.run_flow(input_text)
            actual_domain = res["routing"].get("domain_id")
            actual_agent = res["routing"].get("agent_id")
            
            if res.get("stub"):
                persisted_str = "STUB"
            else:
                persisted_str = "YES" if res["success"] else "NO"
        else:
            result = await classifier.classify(input_text, "text")
            actual_domain = result.domain
            actual_agent = result.agent

        match = (actual_domain == expected_domain) and (actual_agent == expected_agent)
        match_str = "OK" if match else "FAIL"
        if match:
            passed_count += 1

        # Сокращаем длинный текст ввода для красивого отображения в таблице
        disp_input = input_text
        if len(disp_input) > 37:
            disp_input = disp_input[:34] + "..."

        if full:
            print(
                f"{disp_input:<40} | {str(expected_domain):<15} | {str(actual_domain):<15} | {str(expected_agent):<18} | {str(actual_agent):<18} | {match_str:<6} | {persisted_str:<10}"
            )
        else:
            print(
                f"{disp_input:<45} | {str(expected_domain):<15} | {str(actual_domain):<15} | {str(expected_agent):<18} | {str(actual_agent):<18} | {match_str:<6}"
            )

    print("-" * 140)
    print(f"Итог: {passed_count} из {len(scenarios)} пройдено.")


async def async_main() -> None:
    # Проверяем, если первая подкоманда - bootstrap
    if len(sys.argv) > 1 and sys.argv[1] == "bootstrap":
        bootstrap_parser = argparse.ArgumentParser(
            prog="uv run python -m src.sandbox bootstrap",
            description="Команды инициализации (bootstrap) для Runtime."
        )
        subparsers = bootstrap_parser.add_subparsers(dest="bootstrap_cmd", required=True)

        doctor_parser = subparsers.add_parser("doctor", help="Проверить локальные зависимости")
        doctor_parser.add_argument("--json", action="store_true", help="Вывод в формате JSON")

        plan_parser = subparsers.add_parser("plan", help="Сгенерировать план развертывания")
        plan_parser.add_argument("--json", action="store_true", help="Вывод в формате JSON")

        apply_parser = subparsers.add_parser("apply", help="Применить изменения развертывания")
        apply_parser.add_argument("--dry-run", action="store_true", help="Показать план без реальных изменений")
        apply_parser.add_argument("--json", action="store_true", help="Вывод в формате JSON")

        smoke_parser = subparsers.add_parser("smoke", help="Выполнить проверку работоспособности (smoke checks)")
        smoke_parser.add_argument("--dry-run", action="store_true", help="Показать план проверок без реальных вызовов")
        smoke_parser.add_argument("--json", action="store_true", help="Вывод в формате JSON")

        install_parser = subparsers.add_parser("install", help="Запустить мастер установки (install wizard)")
        install_parser.add_argument("--dry-run", action="store_true", help="Показать процесс установки без реальных изменений")
        install_parser.add_argument("--json", action="store_true", help="Вывод в формате JSON")

        checks_parser = subparsers.add_parser("checks", help="Выполнить read-only readiness проверки")
        checks_parser.add_argument("--read-only", action="store_true", help="Обязательный флаг для подтверждения read-only режима")
        checks_parser.add_argument("--json", action="store_true", help="Вывод в формате JSON")

        supabase_parser = subparsers.add_parser("supabase", help="Интегрировать local Supabase plan")
        supabase_parser.add_argument("--local", action="store_true", help="Запустить в локальном режиме")
        supabase_parser.add_argument("--dry-run", action="store_true", help="Показать план без реальных изменений")
        supabase_parser.add_argument("--json", action="store_true", help="Вывод в формате JSON")

        telegram_parser = subparsers.add_parser("telegram", help="Интегрировать Telegram/webhook план")
        telegram_parser.add_argument("--webhook", action="store_true", help="Подготовить конфигурацию вебхука")
        telegram_parser.add_argument("--dry-run", action="store_true", help="Показать план без реальных изменений")
        telegram_parser.add_argument("--json", action="store_true", help="Вывод в формате JSON")

        args = bootstrap_parser.parse_args(sys.argv[2:])

        from src.sandbox.bootstrap import run_doctor, run_plan, run_apply, run_smoke, run_install, run_checks, run_supabase_bootstrap, run_telegram_bootstrap
        if args.bootstrap_cmd == "doctor":
            sys.exit(run_doctor(json_mode=args.json))
        elif args.bootstrap_cmd == "plan":
            sys.exit(run_plan(json_mode=args.json))
        elif args.bootstrap_cmd == "apply":
            if not args.dry_run:
                bootstrap_parser.error("Команда apply требует указания флага --dry-run в текущей версии.")
            sys.exit(run_apply(dry_run=args.dry_run, json_mode=args.json))
        elif args.bootstrap_cmd == "smoke":
            if not args.dry_run:
                bootstrap_parser.error("Команда smoke требует указания флага --dry-run в текущей версии.")
            sys.exit(run_smoke(dry_run=args.dry_run, json_mode=args.json))
        elif args.bootstrap_cmd == "install":
            if not args.dry_run:
                bootstrap_parser.error("Команда install требует указания флага --dry-run в текущей версии.")
            sys.exit(run_install(dry_run=args.dry_run, json_mode=args.json))
        elif args.bootstrap_cmd == "checks":
            if not args.read_only:
                bootstrap_parser.error("Команда checks требует указания флага --read-only.")
            sys.exit(run_checks(json_mode=args.json))
        elif args.bootstrap_cmd == "supabase":
            if not args.local or not args.dry_run:
                bootstrap_parser.error("Команда supabase требует указания флагов --local и --dry-run в текущей версии.")
            sys.exit(run_supabase_bootstrap(local=args.local, dry_run=args.dry_run, json_mode=args.json))
        elif args.bootstrap_cmd == "telegram":
            if not args.webhook or not args.dry_run:
                bootstrap_parser.error("Команда telegram требует указания флагов --webhook и --dry-run в текущей версии.")
            sys.exit(run_telegram_bootstrap(webhook=args.webhook, dry_run=args.dry_run, json_mode=args.json))
        return



    parser = argparse.ArgumentParser(
        description=(
            "CLI harness для тестирования Butler классификатора и доменных потоков в песочнице.\n\n"
            "Правила запуска:\n"
            "  1. Одиночный текст (аргумент или stdin) -> полный сквозной flow (--full по умолчанию).\n"
            "  2. Запуск сценария (--scenario) -> только классификация по умолчанию (требуется явный флаг --full).\n"
            "  3. Без аргументов -> чтение из stdin (если не интерактивный терминал), иначе вывод этой справки."
        ),

        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="Текст запроса для классификации/запуска flow (если отсутствует и не указаны флаги сценариев, читается из stdin)",
    )
    parser.add_argument(
        "--scenario",
        help="Имя сценария в fixtures/ (например kitchen, books, health) или прямой путь к JSON-файлу сценария",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Вывести список доступных файлов сценариев в fixtures/",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Запустить полный flow через SandboxHarness с проверкой in-memory сохранения",
    )

    args = parser.parse_args()

    if args.list_scenarios:
        list_scenarios()
        return

    # Если передан сценарий
    if args.scenario:
        scenario_file = find_scenario_file(args.scenario)
        if not scenario_file:
            print(f"Сценарий не найден: {args.scenario}", file=sys.stderr)
            sys.exit(1)
        await run_scenario(scenario_file, full=args.full)
        return

    # Определяем текст для классификации
    text = args.text

    if text is None:
        if not sys.stdin.isatty():
            text = sys.stdin.read().strip()
        else:
            parser.print_help()
            sys.exit(1)

    if not text:
        print("Ошибка: Передан пустой текст запроса.", file=sys.stderr)
        sys.exit(1)

    # По умолчанию для одиночного текста (включая stdin) запускается полный сквозной flow
    run_full = True
    await run_single_text(text, full=run_full)


def main() -> None:
    # Проверяем, если первая подкоманда - runtime
    if len(sys.argv) > 1 and sys.argv[1] == "runtime":
        runtime_parser = argparse.ArgumentParser(
            prog="uv run python -m src.sandbox runtime",
            description="Команды рантайма (runtime) для Sandbox."
        )
        subparsers = runtime_parser.add_subparsers(dest="runtime_cmd", required=True)

        serve_parser = subparsers.add_parser("serve", help="Запустить HTTP сервер")
        serve_parser.add_argument("--host", default="127.0.0.1", help="Хост для запуска (default: 127.0.0.1)")
        serve_parser.add_argument("--port", type=int, default=8765, help="Порт для запуска (default: 8765)")

        smoke_parser = subparsers.add_parser("smoke", help="Выполнить smoke тест сервера")
        smoke_parser.add_argument("--url", default="http://127.0.0.1:8765", help="URL запущенного сервера")

        args = runtime_parser.parse_args(sys.argv[2:])

        if args.runtime_cmd == "serve":
            from src.sandbox.runtime import serve
            serve(host=args.host, port=args.port)
            sys.exit(0)
        elif args.runtime_cmd == "smoke":
            from src.sandbox.runtime import run_smoke_test
            success = run_smoke_test(args.url)
            sys.exit(0 if success else 1)
        return

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        sys.exit(130)


if __name__ == "__main__":
    main()
