import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.sandbox.cli import async_main
from src.sandbox.bootstrap import run_doctor, run_plan, run_apply, generate_bootstrap_plan


def mock_subprocess_run_ok(args, **kwargs):
    mock_res = MagicMock()
    mock_res.returncode = 0
    cmd = args[0]
    if cmd == "uv":
        mock_res.stdout = "uv 0.11.8"
    elif cmd == "docker" and args[1] == "--version":
        mock_res.stdout = "Docker version 24.0.7"
    elif cmd == "docker" and args[1] == "info":
        mock_res.stdout = "Docker Info"
    elif cmd == "supabase":
        mock_res.stdout = "2.101.0"
    elif cmd == "render" and args[1] == "--version":
        mock_res.stdout = "render v2.18.0"
    else:
        mock_res.stdout = "mocked ok"
    return mock_res


def mock_subprocess_run_fail(args, **kwargs):
    mock_res = MagicMock()
    cmd = args[0]
    if cmd == "supabase":
        mock_res.returncode = 1
        mock_res.stderr = "supabase not found"
        mock_res.stdout = ""
    elif cmd == "docker" and args[1] == "info":
        # CLI есть, но демон лежит
        mock_res.returncode = 1
        mock_res.stderr = "Cannot connect to the Docker daemon"
        mock_res.stdout = ""
    elif cmd == "docker" and args[1] == "--version":
        # Docker CLI нет совсем
        mock_res.returncode = 127
        mock_res.stderr = "docker command not found"
        mock_res.stdout = ""
    else:
        mock_res.returncode = 0
        mock_res.stdout = "mocked ok"
    return mock_res


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_doctor_ok(mock_run, capsys):
    """Проверяет успешное прохождение doctor через CLI."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Doctor ===" in captured.out
    assert "[OK]     python" in captured.out
    assert "[OK]     uv" in captured.out
    assert "[OK]     docker" in captured.out
    assert "[OK]     supabase" in captured.out
    assert "[OK]     render" in captured.out
    assert "Локальное окружение готово к установке." in captured.out


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_doctor_json_ok(mock_run, capsys):
    """Проверяет doctor --json в случае успеха."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["status"] == "success"
    assert data["checks"]["python"]["status"] == "OK"
    assert data["checks"]["docker"]["status"] == "OK"


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_fail)
async def test_cli_bootstrap_doctor_fail(mock_run, capsys):
    """Проверяет падение doctor при отсутствии supabase CLI."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Doctor ===" in captured.out
    assert "[FAIL]   supabase" in captured.out
    assert "Ошибка: Обнаружены критические проблемы в локальном окружении." in captured.out


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_plan(mock_run, capsys):
    """Проверяет генерацию плана через CLI."""
    with patch("sys.argv", ["cli.py", "bootstrap", "plan"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Plan (DRY-RUN) ===" in captured.out
    assert "Внимание: Это read-only симуляция. Никакие ресурсы в облаке не будут созданы." in captured.out
    assert "Supabase Project Name:      adr-bootstrap-db-" in captured.out
    assert "TELEGRAM_UPDATE_MODE" in captured.out
    assert "BOT_TOKEN" in captured.out
    # Проверяем, что вывод read-only и не содержит реальных секретных значений (только имена)
    assert "token" not in captured.out.lower() or "telegram bot token (запрашивается в install или через telegram_bot_token)" in captured.out.lower()
    # Проверим, что нет никаких реальных значений для BOT_TOKEN или других секретных переменных
    assert "BOT_TOKEN=" not in captured.out


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_plan_json(mock_run, capsys):
    """Проверяет plan --json."""
    with patch("sys.argv", ["cli.py", "bootstrap", "plan", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "adr-bootstrap-db-" in data["resources"]["supabase_project_name"]
    assert "TELEGRAM_UPDATE_MODE" in data["planned_env_vars"]
    assert "BOT_TOKEN" in data["planned_env_vars"]
    # Проверка на отсутствие секретных значений
    for var_name in data["planned_env_vars"]:
        assert var_name not in data or data[var_name] is None


def mock_subprocess_run_render_update_notice(args, **kwargs):
    mock_res = MagicMock()
    mock_res.returncode = 0
    cmd = args[0]
    if cmd == "uv":
        mock_res.stdout = "uv 0.11.8"
    elif cmd == "docker" and args[1] == "--version":
        mock_res.stdout = "Docker version 24.0.7"
    elif cmd == "docker" and args[1] == "info":
        mock_res.stdout = "Docker Info"
    elif cmd == "supabase":
        mock_res.stdout = "2.101.0"
    elif cmd == "render" and args[1] == "--version":
        mock_res.stdout = (
            "render v2.18.0\n"
            "A newer version of the Render CLI is available.\n"
            "Please run 'npm install -g @renderinc/cli' to update."
        )
    else:
        mock_res.stdout = "mocked ok"
    return mock_res


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_render_update_notice)
async def test_cli_bootstrap_doctor_render_with_update_notice(mock_run, capsys):
    """Проверяет, что doctor фильтрует update notice от render и оставляет только первую строку (версию)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["status"] == "success"
    assert data["checks"]["render"]["status"] == "OK"
    assert data["checks"]["render"]["message"] == "Render CLI доступен (render v2.18.0)"


@pytest.mark.asyncio
async def test_cli_bootstrap_apply_dry_run(capsys):
    """Проверяет успешный запуск команды apply --dry-run и человекочитаемый вывод."""
    with patch("sys.argv", ["cli.py", "bootstrap", "apply", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out
    assert "=== ADR Bootstrap Apply (DRY-RUN) ===" in out
    assert "Внимание: Выполняется сухой запуск. Никаких изменений в реальной инфраструктуре не производится." in out
    assert "Настройка Supabase: проект и схема данных" in out
    assert "Настройка Render: веб-сервис и группа окружения" in out
    assert "Настройка Telegram: вебхук и команды бота" in out
    assert "Проверка работоспособности (Runtime Smoke Test)" in out
    assert "Локальное состояние (Local Ignored State File Policy)" in out
    assert "Политика отката изменений (Rollback/Cleanup Caveat)" in out
    assert "Для выполнения реального развертывания потребуется отдельное подтверждение" in out
    # Проверка отсутствия плейсхолдеров секретов
    assert ("TELEGRAM_" + "BOT_TOKEN=") not in out
    assert ("RENDER_" + "API_KEY=") not in out
    assert ("SUPABASE_" + "ACCESS_TOKEN=") not in out


@pytest.mark.asyncio
async def test_cli_bootstrap_apply_dry_run_json(capsys):
    """Проверяет успешный запуск команды apply --dry-run --json и JSON вывод."""
    with patch("sys.argv", ["cli.py", "bootstrap", "apply", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "Это сухой запуск (dry-run)" in data["message"]

    steps = {s["step_id"]: s for s in data["steps"]}
    assert len(steps) == 6
    for key in ["supabase", "render", "telegram", "smoke_test"]:
        assert key in steps
        assert steps[key]["status"] == "mutation_prevented"
        assert steps[key]["boundary"] == "future_live_mutation"
    for key in ["state_policy", "rollback_caveat"]:
        assert key in steps
        assert steps[key]["status"] == "skipped"
        assert steps[key]["boundary"] == "offline_dry_run"


@pytest.mark.asyncio
async def test_cli_bootstrap_apply_no_dry_run_fail(capsys):
    """Проверяет, что запуск без --dry-run падает с соответствующей ошибкой."""
    with patch("sys.argv", ["cli.py", "bootstrap", "apply"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code != 0

    captured = capsys.readouterr()
    assert "Команда apply требует указания флага --dry-run" in captured.err


@pytest.mark.asyncio
async def test_bootstrap_plan_apply_consistency(capsys):
    """Регрессионный тест для проверки согласованности plan и apply --dry-run."""
    # Получаем вывод для plan --json
    with patch("sys.argv", ["cli.py", "bootstrap", "plan", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    captured_plan = capsys.readouterr()
    plan_data = json.loads(captured_plan.out.strip())

    # Получаем вывод для apply --dry-run --json
    with patch("sys.argv", ["cli.py", "bootstrap", "apply", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    captured_apply = capsys.readouterr()
    apply_data = json.loads(captured_apply.out.strip())

    # Проверяем, что plan_data и apply_data корректные
    assert plan_data["dry_run"] is True
    assert apply_data["dry_run"] is True

    # 1. Проверяем, что resource names совпадают
    resources = plan_data["resources"]
    sb_project = resources["supabase_project_name"]
    sb_org = resources["supabase_organization"]
    render_service = resources["render_web_service_name"]
    render_env = resources["render_environment_group"]

    # Собираем все тексты из описаний и действий стадий
    all_stage_texts = []
    for step in apply_data["steps"]:
        all_stage_texts.append(step["name"])
        all_stage_texts.extend(step["details"].get("actions", []))
    all_stage_text = " ".join(all_stage_texts)

    # Имена ресурсов должны упоминаться в стадиях
    assert sb_project in all_stage_text
    assert sb_org in all_stage_text
    assert render_service in all_stage_text
    assert render_env in all_stage_text

    # 2. Проверяем, что webhook URL совпадает
    webhook_url = plan_data["update_modes"]["webhook_target_url"]
    assert webhook_url in all_stage_text

    # 3. Проверяем, что planned env var names совместимы со stage descriptions/actions
    for var in plan_data["planned_env_vars"]:
        # Проверяем, что ключевые переменные явно упомянуты в действиях стадий
        if var in ["DATABASE_URL", "BOT_TOKEN"]:
            assert var in all_stage_text


@pytest.mark.asyncio
async def test_cli_bootstrap_smoke_dry_run(capsys):
    """Проверяет успешный запуск команды smoke --dry-run и человекочитаемый вывод."""
    with patch("sys.argv", ["cli.py", "bootstrap", "smoke", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out
    assert "=== ADR Bootstrap Smoke (DRY-RUN) ===" in out
    assert "Внимание: Это read-only симуляция smoke-тестов. Никакие внешние запросы не выполнялись." in out
    assert "Проверка локального рантайма" in out
    assert "http://127.0.0.1:8765/health" in out
    assert "Проверка облачного рантайма" in out
    assert "https://adr-bootstrap-app-" in out
    assert "/health" in out
    assert "Синтетический запрос к Telegram вебхуку" in out
    assert "/telegram-webhook" in out
    assert "Контролируемый запрос с невалидной нагрузкой" in out
    assert "Final Status Classification" in out
    assert "SUCCESS" in out
    assert "DEGRADED_WEBHOOK" in out
    assert "FAILURE" in out
    assert "Никакие секреты не выводятся, реальные вызовы не производятся." in out

    # Проверка отсутствия плейсхолдеров секретов
    assert ("TELEGRAM_" + "BOT_TOKEN=") not in out
    assert ("RENDER_" + "API_KEY=") not in out
    assert ("SUPABASE_" + "ACCESS_TOKEN=") not in out


@pytest.mark.asyncio
async def test_cli_bootstrap_smoke_dry_run_json(capsys):
    """Проверяет успешный запуск команды smoke --dry-run --json и JSON вывод."""
    with patch("sys.argv", ["cli.py", "bootstrap", "smoke", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "Это сухой запуск smoke-тестов" in data["message"]

    steps = {s["step_id"]: s for s in data["steps"]}
    assert len(steps) == 4
    assert "local_runtime_health" in steps
    assert "cloud_runtime_health" in steps
    assert "synthetic_telegram_webhook" in steps
    assert "controlled_invalid_payload" in steps

    assert steps["local_runtime_health"]["details"]["expected_status"] == 200
    assert steps["local_runtime_health"]["boundary"] == "read_only_external_checks"
    assert steps["cloud_runtime_health"]["details"]["expected_status"] == 200
    assert steps["cloud_runtime_health"]["boundary"] == "read_only_external_checks"
    assert steps["synthetic_telegram_webhook"]["details"]["expected_status"] == 200
    assert steps["synthetic_telegram_webhook"]["boundary"] == "future_live_mutation"
    assert steps["controlled_invalid_payload"]["details"]["expected_status"] == 400
    assert steps["controlled_invalid_payload"]["boundary"] == "future_live_mutation"

    assert "success" in data["metadata"]["final_status_classification"]
    assert "degraded_webhook" in data["metadata"]["final_status_classification"]
    assert "failure" in data["metadata"]["final_status_classification"]


@pytest.mark.asyncio
async def test_cli_bootstrap_smoke_no_dry_run_fail(capsys):
    """Проверяет, что запуск bootstrap smoke без --dry-run падает с соответствующей ошибкой."""
    with patch("sys.argv", ["cli.py", "bootstrap", "smoke"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code != 0

    captured = capsys.readouterr()
    assert "Команда smoke требует указания флага --dry-run" in captured.err


@pytest.mark.asyncio
async def test_bootstrap_smoke_plan_consistency(capsys):
    """Проверяет согласованность plan и smoke --dry-run по вебхуку и cloud health."""
    # Получаем plan
    with patch("sys.argv", ["cli.py", "bootstrap", "plan", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    captured_plan = capsys.readouterr()
    plan_data = json.loads(captured_plan.out.strip())

    # Получаем smoke
    with patch("sys.argv", ["cli.py", "bootstrap", "smoke", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    captured_smoke = capsys.readouterr()
    smoke_data = json.loads(captured_smoke.out.strip())

    webhook_url = plan_data["update_modes"]["webhook_target_url"]
    expected_cloud_health = webhook_url.replace("/telegram-webhook", "/health")

    steps = {s["step_id"]: s for s in smoke_data["steps"]}

    assert steps["synthetic_telegram_webhook"]["details"]["target_url"] == webhook_url
    assert steps["controlled_invalid_payload"]["details"]["target_url"] == webhook_url
    assert steps["cloud_runtime_health"]["details"]["target_url"] == expected_cloud_health


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_install_dry_run(mock_run, capsys):
    """Проверяет успешный запуск install --dry-run и человекочитаемый вывод (все 10 шагов)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "install", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out

    assert "=== ADR Bootstrap Install Wizard (DRY-RUN) ===" in out
    assert "1. Подготовительный чек-лист (Upfront Checklist):" in out
    assert "2. Проверка локальных зависимостей (Doctor Prerequisites):" in out
    assert "3. Руководство по авторизации Supabase (Supabase Auth Guidance):" in out
    assert "4. Руководство по авторизации Render (Render Auth Guidance):" in out
    assert "5. Регистрация бота в Telegram (Telegram Bot Setup):" in out
    assert "6. Превью плана развертывания (Plan Preview):" in out
    assert "7. Граница явного подтверждения (Explicit Approval Boundary):" in out
    assert "8. Применение конфигурации (Apply Stage):" in out
    assert "9. Проверка работоспособности (Smoke Stage):" in out
    assert "10. Политика локального состояния (Local Ignored State Policy):" in out

    # Проверка отсутствия плейсхолдеров секретов
    assert ("TELEGRAM_" + "BOT_TOKEN=") not in out
    assert ("RENDER_" + "API_KEY=") not in out
    assert ("SUPABASE_" + "ACCESS_TOKEN=") not in out


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_install_dry_run_json(mock_run, capsys):
    """Проверяет успешный запуск install --dry-run --json и JSON вывод."""
    with patch("sys.argv", ["cli.py", "bootstrap", "install", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "Это сухой запуск мастера установки" in data["message"]

    steps = {s["step_id"]: s for s in data["steps"]}
    assert len(steps) == 10

    expected_steps = [
        "upfront_checklist",
        "doctor_prerequisites",
        "supabase_auth_guidance",
        "render_auth_guidance",
        "telegram_botfather_step",
        "plan_preview",
        "explicit_approval_boundary",
        "apply_stage",
        "smoke_stage",
        "local_ignored_state_policy"
    ]
    for step_name in expected_steps:
        assert step_name in steps
        if step_name in ["upfront_checklist", "doctor_prerequisites", "supabase_auth_guidance", "render_auth_guidance", "telegram_botfather_step", "plan_preview"]:
            assert steps[step_name]["status"] == "ready"
        elif step_name == "explicit_approval_boundary":
            assert steps[step_name]["status"] == "requires_approval"
            assert steps[step_name]["boundary"] == "human_approval_boundary"
        elif step_name in ["apply_stage", "smoke_stage"]:
            assert steps[step_name]["status"] == "mutation_prevented"
            assert steps[step_name]["boundary"] == "future_live_mutation"
        elif step_name == "local_ignored_state_policy":
            assert steps[step_name]["status"] == "skipped"
            assert steps[step_name]["boundary"] == "offline_dry_run"

    # Проверка отсутствия секретных значений
    assert "token" not in captured.out.lower() or "запрашивается в install или через telegram_bot_token" in captured.out.lower()


@pytest.mark.asyncio
async def test_cli_bootstrap_install_no_dry_run_blocked(capsys):
    """Проверяет, что запуск bootstrap install без --dry-run заблокирован."""
    with patch("sys.argv", ["cli.py", "bootstrap", "install"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code != 0

    captured = capsys.readouterr()
    assert "Команда install требует указания флага --dry-run" in captured.err


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_checks_ok(mock_run, capsys):
    """Проверяет успешный запуск команды checks --read-only и человекочитаемый вывод."""
    with patch("sys.argv", ["cli.py", "bootstrap", "checks", "--read-only"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out
    assert "=== ADR Bootstrap Checks (READ-ONLY) ===" in out
    assert "Внимание: Это read-only проверка готовности окружения. Никакие ресурсы не создаются." in out
    assert "Проверка наличия и версий CLI инструментов" in out
    assert "Наличие авторизации и переменных окружения" in out
    assert "Параметры планируемых целевых ресурсов" in out
    assert "Будущая проверка Supabase API" in out
    assert "Будущая проверка Render API" in out
    assert "Будущая проверка Telegram API" in out


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_checks_json(mock_run, capsys):
    """Проверяет запуск команды checks --read-only --json, структуру JSON и отсутствие изменений."""
    with patch("sys.argv", ["cli.py", "bootstrap", "checks", "--read-only", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "read_only" in data["metadata"]
    assert data["metadata"]["read_only"] is True

    steps = {s["step_id"]: s for s in data["steps"]}
    assert len(steps) == 6

    expected_steps = [
        "cli_tools",
        "auth_env_presence",
        "planned_targets",
        "future_supabase_api_check",
        "future_render_api_check",
        "future_telegram_api_check"
    ]
    for step_name in expected_steps:
        assert step_name in steps

    assert steps["cli_tools"]["status"] == "ready"
    assert steps["cli_tools"]["boundary"] == "read_only_external_checks"
    assert steps["auth_env_presence"]["status"] == "ready"
    assert steps["auth_env_presence"]["boundary"] == "offline_dry_run"
    assert steps["planned_targets"]["status"] == "ready"
    assert steps["planned_targets"]["boundary"] == "offline_dry_run"

    for step_name in ["future_supabase_api_check", "future_render_api_check", "future_telegram_api_check"]:
        assert steps[step_name]["status"] == "mutation_prevented"
        assert steps[step_name]["boundary"] == "future_live_mutation"


@pytest.mark.asyncio
async def test_cli_bootstrap_checks_blocked(capsys):
    """Проверяет, что запуск bootstrap checks без --read-only заблокирован."""
    with patch("sys.argv", ["cli.py", "bootstrap", "checks"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code != 0

    captured = capsys.readouterr()
    assert "Команда checks требует указания флага --read-only" in captured.err


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_checks_no_secrets(mock_run, capsys):
    """Проверяет, что секретные значения не выводятся в выводе checks."""
    # Установим фейковые переменные окружения
    with patch.dict("os.environ", {
        "SUPABASE_ACCESS_TOKEN": "secret_supabase_token_123",
        "RENDER_API_KEY": "secret_render_key_456",
        "TELEGRAM_BOT_TOKEN": "secret_bot_token_789",
        "DATABASE_URL": "postgresql://user:secret_password@host:5432/db"
    }):
        with patch("sys.argv", ["cli.py", "bootstrap", "checks", "--read-only"]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        out = captured.out
        # Убедимся, что сами секреты не выводятся
        assert "secret_supabase_token_123" not in out
        assert "secret_render_key_456" not in out
        assert "secret_bot_token_789" not in out
        assert "secret_password" not in out
        # Но наличие определяется корректно (present)
        assert "supabase_access_token_present : присутствует" in out
        assert "render_api_key_present        : присутствует" in out
        assert "telegram_bot_token_present    : присутствует" in out
        assert "database_url_present          : присутствует" in out
