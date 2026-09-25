"""AgentCore Platform v1.0 - RET-C2-271 OutputValidateNode (outer post_process slot).

Step 6: S-3 deterministic output gate. Strips any platform-credential pattern from the
upload package before it leaves the agent (drop/redact + log, no silent suppression),
and shapes the final formatted_output (compliance report + captions + disclosure tag +
upload package).
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import redact_credentials


class OutputValidateNode(FunctionNode):
    """S-3 output gate: credential redaction + final output assembly (outer post_process)."""

    # S-1: explicit by design, not inherited implicitly.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("status") == AgentStatus.ERROR.value:
            emit_trace_event(
                "output_validate_upstream_error",
                {"correlation_id": state.get("correlation_id", "")},
                state,
            )
            return {"status": AgentStatus.ERROR.value}

        compliance_report = from_json(state.get("compliance_report"), {})
        captions = from_json(state.get("captions"), {})
        disclosure_tag = state.get("disclosure_tag", "")
        upload_package = from_json(state.get("upload_package"), {})

        formatted = {
            "compliance_report": compliance_report,
            "captions": captions,
            "disclosure_tag": disclosure_tag,
            "upload_metadata_package": upload_package,
        }

        emit_trace_event(
            "output_validated",
            {
                "severity": compliance_report.get("severity", "none")
                if isinstance(compliance_report, dict)
                else "none",
                "has_disclosure_tag": bool(disclosure_tag),
                "correlation_id": state.get("correlation_id", ""),
            },
            state,
        )

        return {
            "formatted_output": formatted,
            "result": to_json(formatted),
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-3 domain hook: strip platform-credential patterns from the emitted result."""
        text = state.get("result") or ""
        if isinstance(text, str):
            redacted, was_redacted = redact_credentials(text)
            if was_redacted:
                emit_trace_event("output_gate_redacted", {"field": "result"}, state)
                new_state = dict(state)
                new_state["result"] = redacted
                return new_state
        return state
