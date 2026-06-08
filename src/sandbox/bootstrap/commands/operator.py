import json
import sys
from ..models import (
    OfflineDryRunStep,
    ReadOnlyExternalCheckStep,
    HumanApprovalBoundaryStep,
    FutureLiveMutationStep,
    BootstrapState,
)

def run_operator_cleanroom(render: bool, dry_run: bool, json_mode: bool) -> int:
    """Shows the clean operator/deployer path for future live gates.

    This command intentionally performs no login, API request, or cloud mutation.
    """
    if not render or not dry_run:
        print("Ошибка: Команда operator требует указания флагов --render и --dry-run.", file=sys.stderr)
        return 1

    steps = [
        OfflineDryRunStep(
            step_id="separate_runtime_image",
            name="Runtime image remains application-only",
            status="ready",
            message="Runtime Docker image serves the app and must not contain deployment credentials or cloud CLI state.",
            details={
                "runtime_command": "docker build -t agentic-domain-runtime-reviewer .",
                "forbidden_in_runtime": [
                    "Render credentials",
                    "Supabase credentials",
                    "Telegram tokens",
                    "host HOME mount",
                ],
            },
        ),
        OfflineDryRunStep(
            step_id="operator_cleanroom_start",
            name="Start clean operator/deployer shell",
            status="ready",
            message="Operator shell must start without host HOME, host CLI config, or previous service sessions.",
            details={
                "forbidden_mounts": [
                    "$HOME",
                    "~/.config/render",
                    "~/.config/supabase",
                    "~/.gitconfig",
                    "SSH keys",
                ],
                "allowed_inputs": [
                    "public repository URL",
                    "non-secret service name",
                    "human-entered Render login flow",
                ],
            },
        ),
        ReadOnlyExternalCheckStep(
            step_id="render_cli_presence",
            name="Render CLI presence",
            status="ready",
            message="Install or verify Render CLI inside the clean operator environment before login.",
            details={
                "check_command": "render --version || render help",
                "install_hint": "Install Render CLI inside the operator environment, not in the runtime image.",
            },
        ),
        HumanApprovalBoundaryStep(
            step_id="render_login_identity_gate",
            name="Render login and account confirmation",
            status="requires_approval",
            message="Run render login inside cleanroom, then render whoami, then human confirms the intended reviewer account.",
            details={
                "commands": [
                    "render login",
                    "render whoami",
                ],
                "abort_if": [
                    "already logged in before intentional login",
                    "account is not the intended reviewer account",
                    "account identity is unclear",
                    "billing/card prompt appears",
                ],
            },
        ),
        FutureLiveMutationStep(
            step_id="phase1_render_smoke_gate",
            name="Future Phase 1 Render /health smoke",
            status="requires_approval",
            message="Only after account confirmation may a separate explicit GO create a temporary Render service.",
            details={
                "required_go": "GO Phase 1: Render minimal HTTPS runtime smoke from clean reviewer account",
                "cleanup": "delete temporary Render Web Service after smoke",
            },
        ),
    ]

    state = BootstrapState(
        dry_run=True,
        message="Operator/deployer cleanroom plan for Render live gates. No login, external API call, or mutation was executed.",
        steps=steps,
        metadata={
            "target": "render",
            "live_mutation_executed": False,
            "next_gate": "explicit human GO after clean account confirmation",
        },
    )

    if json_mode:
        print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=== ADR Operator Cleanroom Plan (RENDER / DRY-RUN) ===")
        print("No login, external API call, or cloud mutation is executed.")
        print()
        for idx, step in enumerate(state.steps, 1):
            print(f"{idx}. {step.name} [{step.status.upper()}] (Boundary: {step.boundary})")
            print(f"   {step.message}")
            if step.details:
                for key, value in step.details.items():
                    if isinstance(value, list):
                        print(f"   - {key}:")
                        for item in value:
                            print(f"     * {item}")
                    else:
                        print(f"   - {key}: {value}")
            print()
        print("GATE: future Render mutation requires clean account confirmation and separate explicit GO.")
        print("=" * 56)

    return 0
