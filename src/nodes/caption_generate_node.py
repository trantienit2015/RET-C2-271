"""AgentCore Platform v1.0 - RET-C2-271 CaptionGenerateNode (inner step 2)."""

import logging
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import fallback_caption

_logger = logging.getLogger("ret_c2_271.caption_generate")


class CaptionGenerateNode(FunctionNode):
    """Synthesise platform-optimised captions (tiktok / line_voom / instagram).

    LLM-essential wording; deterministic fallback keeps the pipeline runnable without an
    LLM. LLM failures are logged with correlation_id (no silent swallow).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any = None) -> None:
        super().__init__()
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        content_item = from_json(state.get("content_item"), {})
        product_info = str(content_item.get("product_info", "")) if isinstance(content_item, dict) else ""
        platforms = content_item.get("target_platforms", []) if isinstance(content_item, dict) else []
        if not product_info:
            emit_trace_event(
                "caption_generate_rejected",
                {"reason": "no_product_info", "correlation_id": state.get("correlation_id", "")},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["CaptionGenerateNode: no product info to caption"],
            }

        use_llm = self._llm is not None and hasattr(self._llm, "complete")
        captions = {}
        for p in platforms:
            captions[p] = self._caption(state, p, product_info, use_llm)

        emit_trace_event(
            "captions_generated",
            {"platforms": list(captions.keys()), "correlation_id": state.get("correlation_id", "")},
            state,
        )
        return {"captions": to_json(captions), "status": AgentStatus.SUCCESS.value}

    def _caption(self, state: Any, platform: Any, product_info: Any, use_llm: Any) -> str:
        if not use_llm:
            return fallback_caption(platform, product_info)
        try:
            emit_trace_event("caption_llm_call", {"platform": platform}, state)
            messages = [{"role": "user", "content": f"Write a {platform} caption for: {product_info}"}]
            out = self._llm.complete(messages)
            text = self._extract_text(out)
            return text.strip() if text else fallback_caption(platform, product_info)
        except Exception as exc:  # noqa: BLE001 - log + deterministic fallback
            _logger.warning("LLM caption failed (corr=%s, %s): %s", state.get("correlation_id", ""), platform, exc)
            return fallback_caption(platform, product_info)

    @staticmethod
    def _extract_text(raw: Any) -> str:
        """Normalise BaseLLM.complete() output (canonical dict {"content": str, ...}); tolerate a bare-string fake."""
        if isinstance(raw, dict):
            content = raw.get("content", "")
            return content if isinstance(content, str) else ""
        if isinstance(raw, str):
            return raw
        return ""
