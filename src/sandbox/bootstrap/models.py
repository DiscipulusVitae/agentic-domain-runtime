class BootstrapStep:
    """Базовый класс для шагов процесса инициализации (bootstrap)."""
    boundary: str = ""

    def __init__(self, step_id: str, name: str, status: str, message: str, details: dict = None):
        self.step_id = step_id
        self.name = name
        # status: ready, blocked, skipped, requires_approval, mutation_prevented
        self.status = status
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "status": self.status,
            "boundary": self.boundary,
            "message": self.message,
            "details": self.details,
        }


class OfflineDryRunStep(BootstrapStep):
    """Шаг, выполняемый полностью локально без внешних запросов."""
    boundary: str = "offline_dry_run"


class ReadOnlyExternalCheckStep(BootstrapStep):
    """Шаг, выполняющий внешние read-only проверки (например, проверка прав CLI или доступности API)."""
    boundary: str = "read_only_external_checks"


class FutureLiveMutationStep(BootstrapStep):
    """Шаг, выполняющий мутирующие действия в облаке (создание ресурсов, вебхуков)."""
    boundary: str = "future_live_mutation"


class HumanApprovalBoundaryStep(BootstrapStep):
    """Шаг, требующий явного подтверждения человека (human approval)."""
    boundary: str = "human_approval_boundary"


class BootstrapState:
    """Единая модель состояния процесса инициализации (bootstrap state)."""
    def __init__(self, dry_run: bool, message: str, steps: list[BootstrapStep], metadata: dict = None):
        self.dry_run = dry_run
        self.message = message
        self.steps = steps
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "message": self.message,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": self.metadata,
        }


class BootstrapPlanModel:
    """Модель планирования развертывания (bootstrap plan)."""
    def __init__(
        self,
        suffix: str,
        supabase_project_name: str,
        supabase_organization: str,
        render_web_service_name: str,
        render_environment_group: str,
        webhook_target_url: str,
        required_auth: list[str],
        planned_env_vars: list[str],
        stages: list[dict],
    ):
        self.suffix = suffix
        self.supabase_project_name = supabase_project_name
        self.supabase_organization = supabase_organization
        self.render_web_service_name = render_web_service_name
        self.render_environment_group = render_environment_group
        self.webhook_target_url = webhook_target_url
        self.required_auth = required_auth
        self.planned_env_vars = planned_env_vars
        self.stages = stages
