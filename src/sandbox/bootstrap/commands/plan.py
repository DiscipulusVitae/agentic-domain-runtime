import json
from ..plan import generate_bootstrap_plan

def run_plan(json_mode: bool) -> int:
    """Выполняет сухой расчет плана развертывания (plan)."""
    plan = generate_bootstrap_plan()

    if json_mode:
        output = {
            "dry_run": True,
            "resources": {
                "supabase_project_name": plan.supabase_project_name,
                "supabase_organization": plan.supabase_organization,
                "render_web_service_name": plan.render_web_service_name,
                "render_environment_group": plan.render_environment_group
            },
            "required_auth": plan.required_auth,
            "planned_env_vars": plan.planned_env_vars,
            "update_modes": {
                "local": "polling",
                "cloud": "webhook",
                "webhook_target_url": plan.webhook_target_url
            }
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Plan (DRY-RUN) ===")
        print("Внимание: Это read-only симуляция. Никакие ресурсы в облаке не будут созданы.")
        print()
        print("1. Превью имен ресурсов:")
        print(f"   - Supabase Project Name:      {plan.supabase_project_name}")
        print(f"   - Supabase Database Org:      {plan.supabase_organization}")
        print(f"   - Render Web Service Name:    {plan.render_web_service_name}")
        print(f"   - Render Environment Group:   {plan.render_environment_group}")
        print()
        print("2. Чек-лист авторизации:")
        for auth in plan.required_auth:
            print(f"   [ ] {auth}")
        print()
        print("3. Планируемые переменные окружения (только имена):")
        for var in plan.planned_env_vars:
            print(f"   - {var}")
        print()
        print("4. Политика доставки обновлений (Webhook/Polling):")
        print("   - Локальная разработка: Polling (TELEGRAM_UPDATE_MODE=polling)")
        print("   - Облако (Render): Webhook (TELEGRAM_UPDATE_MODE=webhook)")
        print(f"     Адрес вебхука: {plan.webhook_target_url}")
        print("=" * 36)

    return 0
