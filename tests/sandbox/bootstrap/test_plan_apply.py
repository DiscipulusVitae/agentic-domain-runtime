import json
import sys
import pytest
from unittest.mock import MagicMock, patch

from src.sandbox.cli import async_main

@pytest.mark.asyncio
async def test_cli_bootstrap_plan(patch_subprocess_run_ok, capsys):
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
async def test_cli_bootstrap_plan_json(patch_subprocess_run_ok, capsys):
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
    assert "Настройка Render: веб-сервис и группа огружения" in out or "Настройка Render: веб-сервис и группа окружения" in out
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
async def test_cli_bootstrap_apply_preflight_ok(patch_subprocess_run_ok, capsys):
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
async def test_cli_bootstrap_apply_preflight_json_ok(patch_subprocess_run_ok, capsys):
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
async def test_cli_bootstrap_apply_preflight_optional_missing(patch_subprocess_run_fail, capsys):
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
async def test_cli_bootstrap_apply_preflight_critical_missing(patch_subprocess_run_critical_fail, capsys):
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
