"""AgentCore Platform v1.0 - RET-C2-271 InputValidateNode (outer pre_process slot).

Step 1: S-1 trust gate (VERIFIED_EXTERNAL) + S-2 deterministic credential/PII scan on
the content metadata (regex, NOT an LLM check). Parses the content item and serializes
it to validated_input (JSON string) so the inner domain workflow graph - which only
receives a string user_input plus InvocationContext - can reconstruct it.
"""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import to_json
from src.services.security import sanitize_query, scan_for_sensitive
from src.services.service import parse_content_item


class InputValidateNode(FunctionNode):
    """Validate + sanitize the content item and serialize for the inner graph."""

    # S-1: standard business operation - VERIFIED_EXTERNAL caller.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        user_input = state.get("user_input", "")

        # S-4: emit before validation so reject paths also trace.
        emit_trace_event(
            "content_received",
            {
                "input_chars": len(user_input) if isinstance(user_input, str) else 0,
                "correlation_id": state.get("correlation_id", ""),
            },
            state,
        )

        if not isinstance(user_input, str) or not user_input.strip():
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["InputValidateNode: content item is empty or invalid"],
            }

        # S-2: deterministic credential/PII scan before any parsing.
        violation = scan_for_sensitive(user_input)
        if violation:
            emit_trace_event("content_rejected", {"reason": "sensitive_data"}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"InputValidateNode: S-2 gate rejected input - {violation}"],
            }

        sanitized = sanitize_query(user_input.strip())
        content_item = parse_content_item(sanitized)
        if content_item is None:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["InputValidateNode: could not parse content item"],
            }

        return {
            "content_item": to_json(content_item),
            "target_platforms": to_json(content_item["target_platforms"]),
            "validated_input": json.dumps(content_item, ensure_ascii=False),
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-2 domain hook: re-verify no credential/PII slipped through at the gate boundary."""
        payload = state.get("validated_input") or state.get("user_input") or ""
        if isinstance(payload, str):
            violation = scan_for_sensitive(payload)
            if violation:
                return {"status": AgentStatus.ERROR.value, "error_log": [f"S-2 gate: {violation}"]}
        return state
