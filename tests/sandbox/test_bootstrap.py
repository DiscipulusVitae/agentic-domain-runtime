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

    stages = {s["stage"]: s for s in data["stages"]}
    assert len(stages) == 6
    for key in ["supabase", "render", "telegram", "smoke_test", "state_policy", "rollback_caveat"]:
        assert key in stages
        assert stages[key]["status"] == "skipped"
        assert stages[key]["mutation_prevented"] is True


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
    for stage in apply_data["stages"]:
        all_stage_texts.append(stage["description"])
        all_stage_texts.extend(stage["actions"])
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
    assert "Локальный рантайм" in out
    assert "http://127.0.0.1:8765/health" in out
    assert "Облачный рантайм" in out
    assert "https://adr-bootstrap-app-" in out
    assert "/health" in out
    assert "Синтетический Telegram вебхук" in out
    assert "/telegram-webhook" in out
    assert "Контролируемый некорректный запрос" in out
    assert "Final Status Classification" in out
    assert "SUCCESS" in out
    assert "DEGRADED WEBHOOK" in out
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

    checks = {c["name"]: c for c in data["checks"]}
    assert len(checks) == 4
    assert "local_runtime_health" in checks
    assert "cloud_runtime_health" in checks
    assert "synthetic_telegram_webhook" in checks
    assert "controlled_invalid_payload" in checks

    assert checks["local_runtime_health"]["expected_status"] == 200
    assert checks["cloud_runtime_health"]["expected_status"] == 200
    assert checks["synthetic_telegram_webhook"]["expected_status"] == 200
    assert checks["controlled_invalid_payload"]["expected_status"] == 400

    assert "success" in data["final_status_classification"]
    assert "degraded_webhook" in data["final_status_classification"]
    assert "failure" in data["final_status_classification"]


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

    checks = {c["name"]: c for c in smoke_data["checks"]}

    assert checks["synthetic_telegram_webhook"]["target_url"] == webhook_url
    assert checks["controlled_invalid_payload"]["target_url"] == webhook_url
    assert checks["cloud_runtime_health"]["target_url"] == expected_cloud_health
