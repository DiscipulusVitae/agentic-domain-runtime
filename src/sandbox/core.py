from dataclasses import dataclass
from typing import Any


@dataclass
class FlowResult:
    routing: dict[str, Any]
    trace: str
    success: bool
    output: str
    display_name: str | None = None
    include_display_name: bool = True

    def to_dict(self) -> dict[str, Any]:
        res = {
            "routing": self.routing,
            "trace": self.trace,
            "success": self.success,
            "output": self.output,
        }
        if self.include_display_name:
            res["display_name"] = self.display_name
        return res


class TraceHelper:
    def __init__(self) -> None:
        self.steps: list[str] = []

    def add_routing(self, domain_id: str | None) -> None:
        if not domain_id:
            self.steps.append("[routing: ambiguous/clarification_needed]")
        else:
            self.steps.append(f"[routing: {domain_id}]")

    def add_flow_steps(
        self, extraction: bool, validation: bool, persistence: bool, records_count: int = 0
    ) -> None:
        self.steps.append(f"[extraction: {'success' if extraction else 'failed'}]")
        self.steps.append(f"[validation: {'success' if validation else 'failed'}]")
        if persistence:
            self.steps.append(f"[persistence: saved ({records_count} records)]")
        else:
            self.steps.append("[persistence: failed]")

    def build(self) -> str:
        return " -> ".join(self.steps)


class OutputBuilder:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add_header(self, process_text: str, agent_display_name: str) -> None:
        self.lines.append(process_text)
        self.lines.append("---")
        self.lines.append(f"[{agent_display_name}]")

    def add_line(self, line: str) -> None:
        self.lines.append(line)

    def build(self) -> str:
        return "\n".join(self.lines)
