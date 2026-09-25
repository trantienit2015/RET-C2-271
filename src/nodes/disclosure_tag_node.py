"""AgentCore Platform v1.0 - RET-C2-271 DisclosureTagNode (inner step 3)."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json
from src.services.service import build_disclosure_tag


class DisclosureTagNode(FunctionNode):
    """Deterministic AI-disclosure tag application per 消費者庁 framework.

    PB contract: disclosure_tag must be present and non-empty whenever AI-generated
    content is produced (captions present) - independent of caption wording.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        captions = from_json(state.get("captions"), {})
        is_ai_generated = bool(captions)

        tag = build_disclosure_tag(is_ai_generated)

        emit_trace_event(
            "disclosure_tag_applied",
            {"ai_generated": is_ai_generated, "correlation_id": state.get("correlation_id", "")},
            state,
        )
        return {"disclosure_tag": tag, "status": AgentStatus.SUCCESS.value}
