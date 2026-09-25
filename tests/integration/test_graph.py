# RET-C2-271 - Integration test: full graph compile + invoke (Cat 2 outer + inner).

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import Graph


def _payload(result):
    """The framework surfaces formatted_output as `output` (a dict here); tolerate a JSON string too."""
    out = result.get("output")
    if isinstance(out, str):
        return json.loads(out) if out else {}
    return out or {}


CONTENT = {
    "product_info": "新発売スキンケア おすすめ",
    "video_ref": "vid-1",
    "target_platforms": ["tiktok", "line_voom", "instagram"],
}


class TestAgentIntegration:
    def test_full_pipeline_success(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-1", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="mkt")
        result = agent.invoke(json.dumps(CONTENT, ensure_ascii=False), ctx=ctx)

        assert result["status"] == "success"
        assert len(result.get("node_history", [])) >= 5

        payload = _payload(result)
        assert "compliance_report" in payload
        assert set(payload["captions"].keys()) == {"tiktok", "line_voom", "instagram"}
        assert payload["disclosure_tag"]  # PB contract: disclosure tag present
        assert "upload_metadata_package" in payload

    def test_prohibited_claim_flagged_high(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-2", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="mkt")
        content = {**CONTENT, "product_info": "業界No.1 最安値 絶対"}
        result = agent.invoke(json.dumps(content, ensure_ascii=False), ctx=ctx)
        payload = _payload(result)
        assert payload["compliance_report"]["severity"] == "high"
        assert payload["upload_metadata_package"]["upload_ready"] is False

    def test_s1_gate_denies_low_trust_at_entry_node(self):
        """S-1: the entry node (VERIFIED_EXTERNAL) denies an ANONYMOUS caller.

        Verified at the node __call__ boundary (BaseNode.__call__ runs the S-1 gate
        against state["caller_trust_level"]) - the deterministic gate location.
        """
        from src.nodes.pre_process_node import InputValidateNode

        st = {
            "user_input": json.dumps(CONTENT, ensure_ascii=False),
            "caller_trust_level": TrustLevel.ANONYMOUS.value,
        }
        result = InputValidateNode()(st)
        assert result["status"] in ("error", AgentStatus.ERROR)
        assert any("S-1 trust gate denied" in e for e in result.get("error_log", []))

    def test_empty_input_error(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-4", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="mkt")
        result = agent.invoke("", ctx=ctx)
        assert result["status"] in ("error", "cancelled")
