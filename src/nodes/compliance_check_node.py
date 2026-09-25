"""AgentCore Platform v1.0 - RET-C2-271 ComplianceCheckNode (inner step 1)."""

import json
import logging
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import to_json
from src.services.service import build_compliance_report, flag_prohibited_claims, lookup_compliance_rules

_logger = logging.getLogger("ret_c2_271.compliance_check")


class ComplianceCheckNode(FunctionNode):
    """Evaluate content against 景品表示法 / 消費者庁 AI-disclosure rules.

    LLM-essential (grounded): whether a claim is misleading in regulatory context is an
    LLM judgment grounded in the retrieved rules. The LLM is injected via graph config;
    when absent OR when a call fails, a deterministic screen keeps the pipeline runnable
    (no hard LLM dependency, no silent swallow - failures logged with correlation_id).
    Output is ADVISORY - it never asserts legality.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, rule_kb: Any = None, llm: Any = None) -> None:
        super().__init__()
        self._rule_kb = rule_kb
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            content_item = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            content_item = None
        if not isinstance(content_item, dict) or not content_item.get("product_info"):
            emit_trace_event(
                "compliance_check_rejected",
                {"reason": "missing_or_invalid_content_item", "correlation_id": state.get("correlation_id", "")},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ComplianceCheckNode: missing/invalid content item"],
            }

        product_info = str(content_item.get("product_info", ""))
        rules = lookup_compliance_rules(product_info, self._rule_kb)
        deterministic_flags = flag_prohibited_claims(product_info)

        llm_findings = self._llm_findings(state, product_info, rules)
        report = build_compliance_report(deterministic_flags, llm_findings)

        emit_trace_event(
            "compliance_checked",
            {
                "severity": report["severity"],
                "flag_count": len(report["flags"]),
                "correlation_id": state.get("correlation_id", ""),
            },
            state,
        )

        return {
            "content_item": to_json(content_item),
            "target_platforms": to_json(content_item.get("target_platforms", [])),
            "compliance_report": to_json(report),
            "status": AgentStatus.SUCCESS.value,
        }

    def _llm_findings(self, state: Any, product_info: Any, rules: Any) -> list[dict[str, Any]]:
        if self._llm is None or not hasattr(self._llm, "complete"):
            return []
        try:
            emit_trace_event("compliance_llm_call", {"correlation_id": state.get("correlation_id", "")}, state)
            prompt = (
                f"Assess this promotional copy for 景品表示法 misleading-claim risk, grounded in: "
                f"{[r.get('clause') for r in rules]}. Copy: {product_info}. "
                f"Return JSON list of {{term, reason, severity, remediation}}."
            )
            raw = self._llm.complete([{"role": "user", "content": prompt}])
            text = self._extract_text(raw)
            parsed = json.loads(text) if text else []
            return parsed if isinstance(parsed, list) else []
        except Exception as exc:  # noqa: BLE001 - never silent-swallow; log + fall back
            _logger.warning("LLM compliance call failed (corr=%s): %s", state.get("correlation_id", ""), exc)
            return []

    @staticmethod
    def _extract_text(raw: Any) -> str:
        """Normalise BaseLLM.complete() output (canonical dict {"content": str, ...}); tolerate a bare-string fake."""
        if isinstance(raw, dict):
            content = raw.get("content", "")
            return content if isinstance(content, str) else ""
        if isinstance(raw, str):
            return raw
        return ""
