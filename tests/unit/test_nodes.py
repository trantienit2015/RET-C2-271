# RET-C2-271 - Unit tests: per-node success + error/edge paths.

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.caption_generate_node import CaptionGenerateNode
from src.nodes.compliance_check_node import ComplianceCheckNode
from src.nodes.disclosure_tag_node import DisclosureTagNode
from src.nodes.output_package_node import OutputPackageNode
from src.nodes.post_process_node import OutputValidateNode
from src.nodes.pre_process_node import InputValidateNode
from src.schemas.state import from_json, to_json

CONTENT = {"product_info": "新発売ドリンク お得", "video_ref": "v1", "target_platforms": ["tiktok", "instagram"]}


class TestInputValidateNode:
    def test_trust_level(self):
        assert InputValidateNode.required_trust_level == TrustLevel.VERIFIED_EXTERNAL

    def test_success(self):
        r = InputValidateNode().execute({"user_input": json.dumps(CONTENT, ensure_ascii=False)})
        assert r["status"] == AgentStatus.SUCCESS
        assert "validated_input" in r
        assert from_json(r["target_platforms"], []) == ["tiktok", "instagram"]

    def test_empty(self):
        assert InputValidateNode().execute({"user_input": ""})["status"] == AgentStatus.ERROR

    def test_credential_rejected(self):
        r = InputValidateNode().execute({"user_input": 'promo "api_key":"sk-secret123456"'})
        assert r["status"] == AgentStatus.ERROR
        assert any("S-2 gate" in e for e in r["error_log"])

    def test_mynumber_rejected(self):
        assert InputValidateNode().execute({"user_input": "promo 123456789012"})["status"] == AgentStatus.ERROR

    def test_extra_gate_input_hook(self):
        assert InputValidateNode()._extra_security_gate_input({"validated_input": "Bearer abcdefghijkl"})["status"] == AgentStatus.ERROR
        clean = {"validated_input": "clean promo"}
        assert InputValidateNode()._extra_security_gate_input(clean) is clean


class _DictLLM:
    """Canonical BaseLLM.complete() fake: returns {"content": str, ...}."""

    def __init__(self, content: str):
        self._content = content

    def complete(self, messages):
        assert isinstance(messages, list), "complete() must receive a messages list, not a bare string"
        return {"content": self._content, "tool_calls": [], "model": "fake", "usage": {}}


class _BadLLM:
    """Dict response missing "content" - must normalise to empty text, not crash."""

    def complete(self, messages):
        assert isinstance(messages, list)
        return {"tool_calls": [], "model": "fake"}


class TestComplianceCheckNode:
    def test_success_flags_prohibited(self):
        content = {**CONTENT, "product_info": "業界No.1 最安値!"}
        r = ComplianceCheckNode().execute({"user_input": json.dumps(content, ensure_ascii=False)})
        assert r["status"] == AgentStatus.SUCCESS
        report = from_json(r["compliance_report"], {})
        assert report["severity"] == "high"
        assert len(report["flags"]) >= 1

    def test_clean_content_no_high(self):
        r = ComplianceCheckNode().execute({"user_input": json.dumps(CONTENT, ensure_ascii=False)})
        report = from_json(r["compliance_report"], {})
        assert report["severity"] in ("none", "medium")

    def test_invalid_input(self):
        assert ComplianceCheckNode().execute({"user_input": "{}"})["status"] == AgentStatus.ERROR

    def test_llm_dict_response_is_normalised_not_stringified(self):
        llm = _DictLLM('[{"term": "業界No.1", "reason": "unsubstantiated", "severity": "high", "remediation": "remove"}]')
        r = ComplianceCheckNode(llm=llm).execute({"user_input": json.dumps(CONTENT, ensure_ascii=False)})
        assert r["status"] == AgentStatus.SUCCESS
        report = from_json(r["compliance_report"], {})
        assert any(f.get("term") == "業界No.1" for f in report["flags"])

    def test_llm_dict_response_missing_content_falls_back_without_crash(self):
        r = ComplianceCheckNode(llm=_BadLLM()).execute({"user_input": json.dumps(CONTENT, ensure_ascii=False)})
        assert r["status"] == AgentStatus.SUCCESS


class TestCaptionGenerateNode:
    def test_success(self):
        r = CaptionGenerateNode().execute({"content_item": to_json(CONTENT)})
        assert r["status"] == AgentStatus.SUCCESS
        caps = from_json(r["captions"], {})
        assert set(caps.keys()) == {"tiktok", "instagram"}

    def test_missing_product_info(self):
        r = CaptionGenerateNode().execute({"content_item": to_json({"product_info": "", "target_platforms": []})})
        assert r["status"] == AgentStatus.ERROR

    def test_llm_dict_response_is_normalised_not_stringified(self):
        r = CaptionGenerateNode(llm=_DictLLM("Great new drink, try it now!")).execute({"content_item": to_json(CONTENT)})
        assert r["status"] == AgentStatus.SUCCESS
        caps = from_json(r["captions"], {})
        assert caps["tiktok"] == "Great new drink, try it now!"
        assert "{'content'" not in caps["tiktok"] and '"content"' not in caps["tiktok"]

    def test_llm_dict_response_missing_content_falls_back_without_crash(self):
        r = CaptionGenerateNode(llm=_BadLLM()).execute({"content_item": to_json(CONTENT)})
        assert r["status"] == AgentStatus.SUCCESS


class TestDisclosureTagNode:
    def test_tag_present_when_captions(self):
        r = DisclosureTagNode().execute({"captions": to_json({"tiktok": "hi"})})
        assert r["status"] == AgentStatus.SUCCESS
        assert r["disclosure_tag"]
        assert "AI" in r["disclosure_tag"]

    def test_tag_still_nonempty_without_captions(self):
        r = DisclosureTagNode().execute({"captions": to_json({})})
        assert r["disclosure_tag"]  # non-empty (#PR)


class TestOutputPackageNode:
    def test_success(self):
        state = {
            "content_item": to_json(CONTENT),
            "captions": to_json({"tiktok": "a", "instagram": "b"}),
            "disclosure_tag": "#AI",
            "compliance_report": to_json({"severity": "none"}),
        }
        r = OutputPackageNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        pkg = from_json(r["upload_package"], {})
        assert pkg["upload_ready"] is True
        assert set(pkg["per_platform"].keys()) == {"tiktok", "instagram"}

    def test_high_severity_not_upload_ready(self):
        state = {
            "content_item": to_json(CONTENT),
            "captions": to_json({"tiktok": "a"}),
            "disclosure_tag": "#AI",
            "compliance_report": to_json({"severity": "high"}),
        }
        pkg = from_json(OutputPackageNode().execute(state)["upload_package"], {})
        assert pkg["upload_ready"] is False

    def test_missing_content(self):
        assert OutputPackageNode().execute({"content_item": to_json({})})["status"] == AgentStatus.ERROR


class TestOutputValidateNode:
    def test_success(self):
        state = {
            "compliance_report": to_json({"severity": "none", "flags": []}),
            "captions": to_json({"tiktok": "a"}),
            "disclosure_tag": "#AI",
            "upload_package": to_json({"upload_ready": True}),
        }
        r = OutputValidateNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert r["formatted_output"]["disclosure_tag"] == "#AI"

    def test_upstream_error_short_circuits(self):
        assert OutputValidateNode().execute({"status": AgentStatus.ERROR})["status"] == AgentStatus.ERROR

    def test_extra_gate_output_redacts(self):
        leaked = '{"per_platform":{"x":{"caption":"Bearer abcdefghijklmnop"}}}'
        out = OutputValidateNode()._extra_security_gate_output({"result": leaked})
        assert "[REDACTED_CREDENTIAL]" in out["result"]

    def test_extra_gate_output_clean_passthrough(self):
        state = {"result": '{"ok": true}'}
        assert OutputValidateNode()._extra_security_gate_output(state) is state
