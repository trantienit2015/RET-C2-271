# RET-C2-271 - Framework compliance tests TC-01..TC-08.
# Adapted to this template's real architecture (Cat 2: outer pre/post + GraphNode-wrapped inner nodes).

import os
import re

import pytest
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.nodes import (
    caption_generate_node,
    compliance_check_node,
    disclosure_tag_node,
    output_package_node,
    post_process_node,
    pre_process_node,
)
from src.schemas.state import State, to_json

_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
TRUST = TrustLevel.VERIFIED_EXTERNAL.value

_ALLOWED_INNER_TYPES = {"str", "int", "bool", "float"}


def _src_files():
    for root, _d, files in os.walk(_SRC):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


# TC-01 - State is a flat TypedDict extending AgentState, added fields are primitives/JSON-str.
class TestTC01StateContract:
    def test_state_is_typeddict_extending_agent_state(self):
        assert hasattr(State, "__annotations__")
        assert "user_input" in AgentState.__annotations__
        assert set(AgentState.__annotations__).issubset(set(State.__annotations__))

    def test_added_fields_are_primitives_or_json_str(self):
        added = [k for k in State.__annotations__ if k not in AgentState.__annotations__]
        assert added, "State must declare agent-specific fields"
        for name in added:
            ann = State.__annotations__[name]
            # `from __future__ import annotations` renders these as ForwardRef/str
            # (e.g. "NotRequired[str | None]") rather than real type objects.
            if isinstance(ann, str):
                ann_str = ann
            elif hasattr(ann, "__forward_arg__"):
                ann_str = ann.__forward_arg__
            else:
                ann_str = getattr(ann, "__name__", str(ann))
            inner = ann_str.replace("NotRequired[", "").rstrip("]")
            tokens = {t.strip() for t in inner.replace("|", " ").split() if t.strip() and t.strip() != "None"}
            assert tokens and tokens.issubset(_ALLOWED_INNER_TYPES), (
                f"{name}: {ann_str} - compound fields must be JSON-string-encoded"
            )


# TC-02 - Empty/missing input yields a fail-closed ERROR outcome, no raise.
class TestTC02Validation:
    def test_empty_input_no_raise(self):
        node = pre_process_node.InputValidateNode()
        out = node.execute({"user_input": ""})
        assert out["status"] == AgentStatus.ERROR.value
        assert out["error_log"]

    def test_missing_content_item_no_raise(self):
        node = compliance_check_node.ComplianceCheckNode()
        out = node.execute({"user_input": ""})
        assert out["status"] == AgentStatus.ERROR.value
        assert out["error_log"]


# TC-03 - No JWT / API keys / secrets in src/; no direct os.environ reads.
class TestTC03NoCredentials:
    def test_no_credential_literals(self):
        pat = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []

    def test_no_os_environ_secret_reads(self):
        # The standalone entry point is the ONE permitted os.environ reader: it
        # authenticates the caller (INVOKE_AUTH_TOKEN) BEFORE any InvocationContext
        # exists, so ctx.secrets cannot apply. That token is a deployment-level
        # caller credential, not an agent secret, and is never stored in state.
        # See "Entry-point exception" / the STG runbook.
        offenders = []
        for fp in _src_files():
            if os.path.normpath(fp).endswith(os.path.join("src", "api", "server.py")):
                continue
            with open(fp, encoding="utf-8") as f:
                if "os.environ" in f.read():
                    offenders.append(fp)
        assert offenders == []

    def test_entry_point_env_read_is_limited_to_the_caller_auth_token(self):
        """The entry-point exception is narrow: only the two caller-auth tokens may be read
        (INVOKE_AUTH_TOKEN -> VERIFIED_EXTERNAL, STG_INTERNAL_RUNNER_TOKEN -> INTERNAL)."""
        import re

        server = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "src", "api", "server.py")
        if not os.path.exists(server):
            return
        with open(server, encoding="utf-8") as f:
            content = f.read()
        reads = re.findall(r"os\.environ(?:\.get)?[(\[]\s*[\"']([A-Z_]+)[\"']", content)
        assert set(reads) <= {"INVOKE_AUTH_TOKEN", "STG_INTERNAL_RUNNER_TOKEN"}, f"unexpected env reads: {reads}"


# TC-04 - InvocationContext is never stored in State after invoke.
class TestTC04ContextIsolation:
    def test_no_invocationcontext_in_state_after_invoke(self):
        from src.graph.graph import Graph

        agent = Graph(config={"max_retry": 1, "rule_kb": None, "llm": None})
        agent.compile()
        ctx = InvocationContext(session_id="tc04", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="tc04-caller")
        result = agent.invoke('{"product_info": "New sneaker line", "target_platforms": ["tiktok"]}', ctx=ctx)
        for v in result.values():
            assert not isinstance(v, InvocationContext)

    def test_from_state_available(self):
        assert hasattr(InvocationContext, "from_state")


# TC-05 - Domain events: the S-4 side-effect node emits >=1 domain event;
# no node under src/nodes/ ever re-emits a framework backbone lifecycle event.
class TestTC05Audit:
    def test_post_process_node_emits_domain_event(self, monkeypatch):
        events = []
        monkeypatch.setattr(post_process_node, "emit_trace_event", lambda e, p, s: events.append(e))
        state = {
            "status": AgentStatus.SUCCESS.value,
            "compliance_report": to_json({"severity": "none", "flags": []}),
            "captions": to_json({"tiktok": "New sneaker line"}),
            "disclosure_tag": "#AD",
            "upload_package": to_json({"upload_ready": True}),
        }
        out = post_process_node.OutputValidateNode().execute(state)
        assert out["status"] == AgentStatus.SUCCESS.value
        assert len(events) >= 1
        assert "output_validated" in events
        assert not ({"node_start", "node_complete", "node_error", "node_skip"} & set(events))

    def test_source_has_no_backbone_events(self):
        pat = re.compile(r'emit_trace_event\(\s*["\'](node_start|node_complete|node_error|node_skip)["\']')
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []


# TC-06 / TC-07 - S-2/S-3 gates are @final on FunctionNode (overriding raises TypeError at class def).
class TestTC0607FinalGates:
    def test_input_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadIn(FunctionNode):  # noqa: N801
                def _security_gate_input(self, state):
                    return state

    def test_output_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadOut(FunctionNode):  # noqa: N801
                def _security_gate_output(self, result):
                    return result

    def test_extra_hook_is_overridable(self):
        assert post_process_node.OutputValidateNode._extra_security_gate_output is not FunctionNode._extra_security_gate_output

    def test_output_gate_blocks_credentials(self):
        # The @final S-3 credential scan actually fires (not vacuous): a
        # credential in the result is blocked, never returned as-is.
        node = post_process_node.OutputValidateNode()
        with pytest.raises(Exception):
            node._security_gate_output({"result": "token AKIAIOSFODNN7EXAMPLE leaked"})


# TC-08 - required_trust_level enforced: insufficient trust -> ERROR state, no raise.
class TestTC08TrustGate:
    def test_declared_trust_levels_valid(self):
        for cls in (
            pre_process_node.InputValidateNode,
            compliance_check_node.ComplianceCheckNode,
            caption_generate_node.CaptionGenerateNode,
            disclosure_tag_node.DisclosureTagNode,
            output_package_node.OutputPackageNode,
            post_process_node.OutputValidateNode,
        ):
            assert cls.required_trust_level in (TrustLevel.ANONYMOUS, TrustLevel.VERIFIED_EXTERNAL, TrustLevel.INTERNAL)

    def test_insufficient_trust_returns_error(self):
        node = pre_process_node.InputValidateNode()
        out = node({"caller_trust_level": TrustLevel.ANONYMOUS.value, "user_input": "New sneaker line"})
        assert str(out.get("status")).lower().endswith("error")

    def test_sufficient_trust_succeeds(self):
        node = pre_process_node.InputValidateNode()
        out = node({"caller_trust_level": TRUST, "user_input": "New sneaker line"})
        assert out["status"] == AgentStatus.SUCCESS.value
        assert out["content_item"]
