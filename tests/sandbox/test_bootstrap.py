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
async def test_cli_bootstrap_doctor_optional_missing(mock_run, capsys):
    """Проверяет прохождение doctor при отсутствии опционального supabase CLI (неблокирующий FAIL)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Doctor ===" in captured.out
    assert "[FAIL]   supabase" in captured.out
    assert "Внимание: Отсутствуют некоторые опциональные инструменты" in captured.out
    assert "Подсказка: Установите Supabase CLI через npm" in captured.out


def mock_subprocess_run_critical_fail(args, **kwargs):
    mock_res = MagicMock()
    cmd = args[0]
    if cmd == "uv":
        mock_res.returncode = 127
        mock_res.stderr = "uv not found"
        mock_res.stdout = ""
    else:
        mock_res.returncode = 0
        mock_res.stdout = "mocked ok"
    return mock_res


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_critical_fail)
async def test_cli_bootstrap_doctor_critical_missing(mock_run, capsys):
    """Проверяет падение doctor при отсутствии критического uv."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Doctor ===" in captured.out
    assert "[FAIL]   uv" in captured.out
    assert "Ошибка: Обнаружены критические проблемы в локальном окружении" in captured.out


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_fail)
async def test_cli_bootstrap_doctor_json_optional_missing(mock_run, capsys):
    """Проверяет doctor --json в случае отсутствия опциональных утилит."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["status"] == "success"
    assert data["checks"]["supabase"]["status"] == "FAIL"
    assert "hint" in data["checks"]["supabase"]
    assert "action" in data["checks"]["supabase"]


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
    assert "Команда apply требует указания флага --dry-run или комбинации --preflight --read-only" in captured.err


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_apply_preflight_ok(mock_run, capsys):
    """Проверяет успешный запуск preflight --read-only и текстовый вывод."""
    with patch("sys.argv", ["cli.py", "bootstrap", "apply", "--preflight", "--read-only"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out
    assert "=== ADR Bootstrap Apply Preflight (READ-ONLY) ===" in out
    assert "Проверка наличия и версий CLI инструментов" in out
    assert "Наличие токенов авторизации" in out
    assert "Параметры планируемых целевых ресурсов" in out
    assert "Применение изменений в Supabase" in out
    assert "Применение изменений в Render" in out
    assert "GATE: Future live apply requires separate approval and is not implemented." in out

    # Проверка отсутствия секретов
    assert ("TELEGRAM_" + "BOT_TOKEN=") not in out
    assert ("RENDER_" + "API_KEY=") not in out
    assert ("SUPABASE_" + "ACCESS_TOKEN=") not in out


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_apply_preflight_json_ok(mock_run, capsys):
    """Проверяет успешный запуск preflight --read-only --json и JSON вывод."""
    with patch("sys.argv", ["cli.py", "bootstrap", "apply", "--preflight", "--read-only", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "preflight" in data["metadata"]
    assert data["metadata"]["preflight"] is True
    assert data["metadata"]["read_only"] is True
    assert data["metadata"]["explicit_next_gate"] == "future live apply requires separate approval and is not implemented"

    steps = {s["step_id"]: s for s in data["steps"]}
    assert "cli_tools" in steps
    assert "auth_presence" in steps
    assert "planned_targets" in steps
    assert "supabase_mutation" in steps
    assert steps["supabase_mutation"]["status"] == "requires_approval"


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_fail)
async def test_cli_bootstrap_apply_preflight_optional_missing(mock_run, capsys):
    """Проверяет успешный запуск preflight --read-only при отсутствии опционального supabase CLI (exit code 0)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "apply", "--preflight", "--read-only"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out
    assert "=== ADR Bootstrap Apply Preflight (READ-ONLY) ===" in out
    assert "Опциональные CLI инструменты отсутствуют" in out


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_critical_fail)
async def test_cli_bootstrap_apply_preflight_critical_missing(mock_run, capsys):
    """Проверяет падение preflight --read-only при отсутствии критического uv CLI (exit code 1)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "apply", "--preflight", "--read-only"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    out = captured.out
    assert "=== ADR Bootstrap Apply Preflight (READ-ONLY) ===" in out
    assert "Критические CLI инструменты" in out


@pytest.mark.asyncio
async def test_cli_bootstrap_apply_preflight_no_readonly_fail(capsys):
    """Проверяет, что запуск preflight без --read-only падает с ошибкой."""
    with patch("sys.argv", ["cli.py", "bootstrap", "apply", "--preflight"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code != 0

    captured = capsys.readouterr()
    assert "Команда apply с флагом --preflight требует обязательного указания флага --read-only" in captured.err



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


@pytest.mark.asyncio
async def test_cli_bootstrap_supabase_local_dry_run(capsys):
    """Проверяет успешный текстовый вывод команды bootstrap supabase --local --dry-run."""
    with patch("sys.argv", ["cli.py", "bootstrap", "supabase", "--local", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out
    assert "=== ADR Bootstrap Supabase Local Plan (DRY-RUN) ===" in out
    assert "Внимание: Это сухой запуск локального плана Supabase" in out
    assert "[OK] supabase/config.toml" in out
    assert "supabase start" in out
    assert "supabase stop" in out
    assert "disk-safe note" in out


@pytest.mark.asyncio
async def test_cli_bootstrap_supabase_local_dry_run_json(capsys):
    """Проверяет успешный JSON вывод команды bootstrap supabase --local --dry-run --json."""
    with patch("sys.argv", ["cli.py", "bootstrap", "supabase", "--local", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "Это сухой запуск локального плана Supabase" in data["message"]

    steps = {s["step_id"]: s for s in data["steps"]}
    assert "supabase_assets_check" in steps
    assert "supabase_command_plan" in steps
    assert steps["supabase_assets_check"]["status"] == "ready"
    assert steps["supabase_command_plan"]["status"] == "ready"
    assert steps["supabase_assets_check"]["details"]["assets"]["config"]["exists"] is True


@pytest.mark.asyncio
async def test_cli_bootstrap_supabase_missing_flags_blocked(capsys):
    """Проверяет, что запуск без необходимых флагов блокируется."""
    for args in [
        ["cli.py", "bootstrap", "supabase"],
        ["cli.py", "bootstrap", "supabase", "--local"],
        ["cli.py", "bootstrap", "supabase", "--dry-run"],
    ]:
        with patch("sys.argv", args):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code != 0

        captured = capsys.readouterr()
        assert "Команда supabase требует указания флагов --local и --dry-run" in captured.err


@pytest.mark.asyncio
@patch("subprocess.run")
async def test_cli_bootstrap_supabase_no_subprocess(mock_run, capsys):
    """Проверяет, что команда не выполняет системные вызовы (subprocess)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "supabase", "--local", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    assert mock_run.call_count == 0


@pytest.mark.asyncio
async def test_cli_bootstrap_supabase_missing_file_failure(capsys):
    """Проверяет, что при отсутствии файлов возвращается код 1 и в выводе есть FAIL."""
    with patch("pathlib.Path.is_file", return_value=False):
        with patch("sys.argv", ["cli.py", "bootstrap", "supabase", "--local", "--dry-run"]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out


@pytest.mark.asyncio
async def test_cli_bootstrap_supabase_missing_file_failure_json(capsys):
    """Проверяет, что в JSON при отсутствии файлов статус шага 'blocked' и возвращается код 1."""
    with patch("pathlib.Path.is_file", return_value=False):
        with patch("sys.argv", ["cli.py", "bootstrap", "supabase", "--local", "--dry-run", "--json"]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["steps"][0]["status"] == "blocked"


@pytest.mark.asyncio
async def test_cli_bootstrap_telegram_dry_run(capsys):
    """Проверяет успешный текстовый вывод команды bootstrap telegram --webhook --dry-run."""
    with patch("sys.argv", ["cli.py", "bootstrap", "telegram", "--webhook", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out
    assert "=== ADR Bootstrap Telegram Webhook Readiness (DRY-RUN) ===" in out
    assert "Внимание: Это сухой запуск (dry-run) настройки Telegram вебхука" in out
    assert "Ручная настройка бота через @BotFather (guidance only)" in out
    assert "Token Handoff Policy" in out
    assert "Планируемый URL для вебхука Telegram" in out
    assert "Планируемые действия с Telegram API" in out
    assert "Связь готовности с проверками smoke" in out


@pytest.mark.asyncio
async def test_cli_bootstrap_telegram_dry_run_json(capsys):
    """Проверяет успешный JSON вывод команды bootstrap telegram --webhook --dry-run --json."""
    with patch("sys.argv", ["cli.py", "bootstrap", "telegram", "--webhook", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "Это сухой запуск (dry-run) настройки Telegram вебхука" in data["message"]

    steps = {s["step_id"]: s for s in data["steps"]}
    assert "telegram_botfather_guidance" in steps
    assert "token_handoff_policy" in steps
    assert "planned_webhook_url" in steps
    assert "future_telegram_api_actions" in steps
    assert "smoke_readiness_relation" in steps

    assert steps["telegram_botfather_guidance"]["status"] == "requires_approval"
    assert steps["token_handoff_policy"]["status"] == "ready"
    assert steps["planned_webhook_url"]["status"] == "ready"
    assert steps["future_telegram_api_actions"]["status"] == "mutation_prevented"
    assert steps["smoke_readiness_relation"]["status"] == "ready"


@pytest.mark.asyncio
async def test_cli_bootstrap_telegram_missing_flags_blocked(capsys):
    """Проверяет, что запуск команды telegram без необходимых флагов блокируется."""
    for args in [
        ["cli.py", "bootstrap", "telegram"],
        ["cli.py", "bootstrap", "telegram", "--webhook"],
        ["cli.py", "bootstrap", "telegram", "--dry-run"],
    ]:
        with patch("sys.argv", args):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code != 0

        captured = capsys.readouterr()
        assert "Команда telegram требует указания флагов --webhook и --dry-run" in captured.err


@pytest.mark.asyncio
@patch("subprocess.run")
async def test_cli_bootstrap_telegram_no_subprocess(mock_run, capsys):
    """Проверяет, что команда telegram не выполняет системные вызовы (subprocess)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "telegram", "--webhook", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    assert mock_run.call_count == 0


@pytest.mark.asyncio
async def test_cli_bootstrap_telegram_no_token_leak(capsys):
    """Проверяет, что в выводе команды telegram нет значений токенов, даже если они заданы."""
    custom_env = {
        "TELEGRAM_BOT_TOKEN": "leak_secret_tg_token_987",
        "BOT_TOKEN": "leak_secret_bot_token_654"
    }
    with patch.dict("os.environ", custom_env):
        with patch("sys.argv", ["cli.py", "bootstrap", "telegram", "--webhook", "--dry-run"]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        out = captured.out
        assert "leak_secret_tg_token_987" not in out
        assert "leak_secret_bot_token_654" not in out

        # Также проверим для JSON вывода
        with patch("sys.argv", ["cli.py", "bootstrap", "telegram", "--webhook", "--dry-run", "--json"]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 0

        captured_json = capsys.readouterr()
        assert "leak_secret_tg_token_987" not in captured_json.out
        assert "leak_secret_bot_token_654" not in captured_json.out


@pytest.mark.asyncio
async def test_cli_bootstrap_state_lifecycle(tmp_path, capsys):
    """Тестирует жизненный цикл команды bootstrap state: dry-run, init, overwrite block, show, и отсутствие секретов."""
    state_file = tmp_path / ".bootstrap-state.json"

    # 1. dry-run не создает файл
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--dry-run", "--path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    assert not state_file.exists()

    # 2. init создает файл
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    assert state_file.exists()

    # Проверим структуру созданного файла
    with open(state_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["schema_version"] == "1.0.0"
    assert data["status"] == "initialized"
    assert "generated_at" in data
    assert "resources" in data
    assert "supabase_project_name" in data["resources"]
    assert "applied_steps" in data
    assert "steps_skeleton" in data

    # 3. init без флага --overwrite выдает ошибку при существующем НЕПУСТОМ файле
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1

    # 3b. init без флага --overwrite успешно выполняется на пустом существующем файле
    empty_state_file = tmp_path / "empty-state.json"
    empty_state_file.write_text("", encoding="utf-8")
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--path", str(empty_state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    assert empty_state_file.exists()

    # 3c. init без флага --overwrite успешно выполняется на файле, содержащем только whitespace
    whitespace_state_file = tmp_path / "whitespace-state.json"
    whitespace_state_file.write_text("   \n  \t ", encoding="utf-8")
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--path", str(whitespace_state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    assert whitespace_state_file.exists()

    # 4. init с флагом --overwrite работает на существующем НЕПУСТОМ файле
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--overwrite", "--path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    # 5. show выводит человекочитаемый отчет
    capsys.readouterr()  # Сбросить кэш вывода
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--show", "--path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "=== ADR Bootstrap State Show ===" in captured.out
    assert "Supabase Project:" in captured.out
    assert "Скелет шагов:" in captured.out

    # 6. show с флагом --json выводит JSON
    capsys.readouterr()
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--show", "--json", "--path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    captured = capsys.readouterr()
    show_data = json.loads(captured.out.strip())
    assert show_data["schema_version"] == "1.0.0"
    assert show_data["status"] == "initialized"

    # 7. Секретные переменные окружения не записываются в файл и не считываются
    with patch.dict("os.environ", {
        "TELEGRAM_BOT_TOKEN": "secret-bot-token-12345",
        "SUPABASE_ACCESS_TOKEN": "secret-sb-token-abcde",
        "RENDER_API_KEY": "secret-render-key-xyz"
    }):
        secret_state_file = tmp_path / ".bootstrap-state-secret.json"
        with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--path", str(secret_state_file)]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 0

        # Проверим, что секреты не записались в файл
        with open(secret_state_file, "r", encoding="utf-8") as f:
            secret_content = f.read()
        assert "secret-bot-token-12345" not in secret_content
        assert "secret-sb-token-abcde" not in secret_content
        assert "secret-render-key-xyz" not in secret_content

        # Проверим, что секреты не выводятся в show
        capsys.readouterr()
        with patch("sys.argv", ["cli.py", "bootstrap", "state", "--show", "--json", "--path", str(secret_state_file)]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 0
        captured_show = capsys.readouterr()
        assert "secret-bot-token-12345" not in captured_show.out
        assert "secret-sb-token-abcde" not in captured_show.out
        assert "secret-render-key-xyz" not in captured_show.out

    # 8. Попытка вызвать show на несуществующем файле завершается с ошибкой
    non_existent_file = tmp_path / "does-not-exist.json"
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--show", "--path", str(non_existent_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1


def test_gitignore_contains_bootstrap_state():
    """Проверяет, что .bootstrap-state.json добавлен в .gitignore."""
    gitignore_path = Path(__file__).parent.parent.parent / ".gitignore"
    assert gitignore_path.exists(), "Файл .gitignore не найден"
    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert ".bootstrap-state.json" in content, ".bootstrap-state.json не найден в .gitignore"


@pytest.mark.asyncio
async def test_cli_bootstrap_simulate_no_local():
    """Проверяет, что simulate без --local завершается с ошибкой (код 2 из argparse)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "simulate"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 2


@pytest.mark.asyncio
async def test_cli_bootstrap_simulate_happy_path(capsys):
    """Проверяет успешный happy path симуляции (human-readable)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "simulate", "--local"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Simulation (LOCAL-ONLY) ===" in captured.out
    assert "PLAN [SUCCESS]" in captured.out
    assert "PREFLIGHT [SUCCESS]" in captured.out
    assert "APPLY [SUCCESS]" in captured.out
    assert "VERIFY [SUCCESS]" in captured.out
    assert "ROLLBACK [SUCCESS]" in captured.out
    assert "Симуляция завершена УСПЕШНО" in captured.out

    # Проверим, что временный файл состояния симуляции был корректно удален
    assert not Path(".bootstrap-state-sim.json").exists()


@pytest.mark.asyncio
async def test_cli_bootstrap_simulate_happy_path_json(capsys):
    """Проверяет успешный happy path симуляции в формате JSON."""
    with patch("sys.argv", ["cli.py", "bootstrap", "simulate", "--local", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["simulation"] == "local-only-synthetic"
    assert data["fail_after_apply"] is False
    assert data["success"] is True
    assert data["final_state"] == "ROLLED_BACK"

    # Проверяем фазы
    phases = [step["phase"] for step in data["steps"]]
    assert phases == ["plan", "preflight", "apply", "verify", "rollback"]

    # Все фазы должны быть success
    for step in data["steps"]:
        assert step["status"] == "success"

    assert not Path(".bootstrap-state-sim.json").exists()


@pytest.mark.asyncio
async def test_cli_bootstrap_simulate_fail_path_json(capsys):
    """Проверяет сбой верификации и автоматический откат в формате JSON."""
    with patch("sys.argv", ["cli.py", "bootstrap", "simulate", "--local", "--fail-after-apply", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["simulation"] == "local-only-synthetic"
    assert data["fail_after_apply"] is True
    assert data["success"] is False
    assert data["final_state"] == "ROLLED_BACK"

    # Verify фаза должна быть failed, а apply и rollback - success
    steps = {step["phase"]: step for step in data["steps"]}
    assert steps["apply"]["status"] == "success"
    assert steps["verify"]["status"] == "failed"
    assert steps["rollback"]["status"] == "success"

    assert not Path(".bootstrap-state-sim.json").exists()


def test_gitignore_contains_bootstrap_state_sim():
    """Проверяет, что .bootstrap-state-sim.json добавлен в .gitignore."""
    gitignore_path = Path(__file__).parent.parent.parent / ".gitignore"
    assert gitignore_path.exists()
    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert ".bootstrap-state-sim.json" in content, ".bootstrap-state-sim.json не найден в .gitignore"


@pytest.mark.asyncio
async def test_cli_bootstrap_cleanup_no_flags_blocked():
    """Проверяет, что cleanup без --preview или --local блокируется (код 2)."""
    for args in [
        ["cli.py", "bootstrap", "cleanup"],
        ["cli.py", "bootstrap", "cleanup", "--preview"],
        ["cli.py", "bootstrap", "cleanup", "--local"],
    ]:
        with patch("sys.argv", args):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 2


@pytest.mark.asyncio
async def test_cli_bootstrap_cleanup_no_state_preview(capsys):
    """Проверяет no-state preview (без файла состояния, человекочитаемый вывод)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "cleanup", "--preview", "--local"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Rollback/Cleanup Preview ===" in captured.out
    assert "Источник состояния:  deterministic_plan" in captured.out
    assert "SKIPPED/NOT-CREATED" in captured.out
    assert "Созданные ресурсы отсутствуют, локальное состояние не требует изменений." in captured.out
    assert "локальное превью" in captured.out


@pytest.mark.asyncio
async def test_cli_bootstrap_cleanup_existing_state_preview(tmp_path, capsys):
    """Проверяет existing-state preview с файлом состояния."""
    state_file = tmp_path / "test-state.json"
    state_data = {
        "schema_version": "1.0.0",
        "status": "applied",
        "resources": {
            "supabase_project_name": "test-sb-project",
            "supabase_organization": "test-sb-org",
            "render_web_service_name": "test-render-service",
            "render_environment_group": "test-render-env",
            "webhook_target_url": "https://test-render-service.local/webhook"
        },
        "applied_steps": ["supabase_sim_db_created", "render_sim_service_created"]
    }
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state_data, f)

    with patch("sys.argv", ["cli.py", "bootstrap", "cleanup", "--preview", "--local", "--state-path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Rollback/Cleanup Preview ===" in captured.out
    assert f"Источник состояния:  state_file: {state_file.name}" in captured.out
    assert "supabase_project_name: test-sb-project (Статус: created)" in captured.out
    assert "render_web_service_name: test-render-service (Статус: created)" in captured.out
    assert "webhook_target_url: https://test-render-service.local/webhook (Статус: planned_not_created)" in captured.out

    assert "[MANUAL/FUTURE-LIVE] Удаление веб-сервиса Render" in captured.out
    assert "[MANUAL/FUTURE-LIVE] Удаление проекта Supabase" in captured.out
    assert "[AUTOMATIC/LOCAL] Удаление локального файла состояния" in captured.out


@pytest.mark.asyncio
async def test_cli_bootstrap_cleanup_json_shape(tmp_path, capsys):
    """Проверяет структуру JSON-вывода."""
    state_file = tmp_path / "test-state.json"
    state_data = {
        "schema_version": "1.0.0",
        "status": "initialized",
        "resources": {
            "supabase_project_name": "test-sb-proj",
            "supabase_organization": "test-sb-org",
            "render_web_service_name": "test-render-srv",
            "render_environment_group": "test-render-env",
            "webhook_target_url": "https://test-render-srv.local/webhook"
        },
        "applied_steps": []
    }
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state_data, f)

    with patch("sys.argv", ["cli.py", "bootstrap", "cleanup", "--preview", "--local", "--state-path", str(state_file), "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())

    assert data["source"] == f"state_file: {state_file.name}"
    assert data["state_path"] == state_file.name
    assert "supabase_project_name" in data["synthetic_resources"]
    assert data["synthetic_resources"]["supabase_project_name"]["value"] == "test-sb-proj"
    assert data["synthetic_resources"]["supabase_project_name"]["status"] == "planned_not_created"

    assert len(data["cleanup_steps"]) == 4
    step_ids = [step["step_id"] for step in data["cleanup_steps"]]
    assert step_ids == ["telegram", "render", "supabase", "state_file"]

    assert data["cleanup_steps"][0]["type"] == "skipped/not-created"
    assert data["cleanup_steps"][3]["type"] == "automatic/local"

    assert data["live_mutations_present"] is False
    assert "Внимание" in data["warning"]


@pytest.mark.asyncio
async def test_cli_bootstrap_cleanup_no_secrets_or_path_leak(tmp_path, capsys):
    """Проверяет отсутствие утечек абсолютных путей или секретов в выводе."""
    secret_token = "SUPABASE_" + "ACCESS_TOKEN" + "=" + "secret12345"
    state_file = tmp_path / "test-state.json"
    state_data = {
        "schema_version": "1.0.0",
        "status": "applied",
        "resources": {
            "supabase_project_name": "sb-proj",
            "supabase_organization": "sb-org",
            "render_web_service_name": "render-srv",
            "render_environment_group": "render-env",
            "webhook_target_url": "https://render-srv.local/webhook"
        },
        "applied_steps": []
    }
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state_data, f)

    with patch("sys.argv", ["cli.py", "bootstrap", "cleanup", "--preview", "--local", "--state-path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()

    assert str(tmp_path) not in captured.out
    assert secret_token not in captured.out
    assert "SUPABASE_" + "ACCESS_TOKEN" not in captured.out


@pytest.mark.asyncio
async def test_cli_bootstrap_operator_render_dry_run(capsys):
    """Проверяет Render operator cleanroom plan без login/API/mutation."""
    with patch("sys.argv", ["cli.py", "bootstrap", "operator", "--render", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out

    assert "=== ADR Operator Cleanroom Plan (RENDER / DRY-RUN) ===" in out
    assert "No login, external API call, or cloud mutation is executed." in out
    assert "Runtime image remains application-only" in out
    assert "Start clean operator/deployer shell" in out
    assert "Render CLI presence" in out
    assert "Render login and account confirmation" in out
    assert "Future Phase 1 Render /health smoke" in out
    assert "render whoami" in out
    assert "GATE: future Render mutation requires clean account confirmation and separate explicit GO." in out

    assert "TELEGRAM_" + "BOT_TOKEN=" not in out
    assert "RENDER_" + "API_KEY=" not in out
    assert "SUPABASE_" + "ACCESS_TOKEN=" not in out


@pytest.mark.asyncio
async def test_cli_bootstrap_operator_render_dry_run_json(capsys):
    """Проверяет JSON-вывод Render operator cleanroom plan."""
    with patch("sys.argv", ["cli.py", "bootstrap", "operator", "--render", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())

    assert data["dry_run"] is True
    assert data["metadata"]["target"] == "render"
    assert data["metadata"]["live_mutation_executed"] is False

    steps = {step["step_id"]: step for step in data["steps"]}
    assert steps["separate_runtime_image"]["boundary"] == "offline_dry_run"
    assert steps["operator_cleanroom_start"]["boundary"] == "offline_dry_run"
    assert steps["render_cli_presence"]["boundary"] == "read_only_external_checks"
    assert steps["render_login_identity_gate"]["boundary"] == "human_approval_boundary"
    assert steps["render_login_identity_gate"]["status"] == "requires_approval"
    assert steps["phase1_render_smoke_gate"]["boundary"] == "future_live_mutation"
    assert steps["phase1_render_smoke_gate"]["status"] == "requires_approval"


@pytest.mark.asyncio
async def test_cli_bootstrap_operator_requires_flags(capsys):
    """Проверяет, что operator без обязательных флагов заблокирован."""
    with patch("sys.argv", ["cli.py", "bootstrap", "operator", "--render"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code != 0

    captured = capsys.readouterr()
    assert "Команда operator требует указания флагов --render и --dry-run" in captured.err
