"""AgentCore Platform v1.0 - RET-C2-271 outer graph (Cat 2).

Cat 2: outer AgentBaseGraph with the fixed 5-node backbone. Domain complexity is
encapsulated in ComplianceCaptionGraphNode (the `main` slot), which wraps the inner
ComplianceCaptionWorkflowGraph. Do NOT override add_edges().

Backbone: initialize -> pre_process(InputValidate) -> main(GraphNode) -> post_process(OutputValidate) -> finalize

ComplianceCaptionGraphNode lives here (not under src/nodes/) - scaffold Cat 2 sample
places the GraphNode wrapper in graph.py alongside the outer graph. The PB-6
invoke-order test only discovers BaseNode subclasses under src/nodes/, and a
GraphNode's __call__ intentionally skips the standard S-2/S-4/S-3 lifecycle (gating is
delegated to the inner subgraph), so placing it under src/nodes/ would make PB-6
wrongly assert the standard lifecycle on it.
"""

from typing import Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.post_process_node import OutputValidateNode
from src.nodes.pre_process_node import InputValidateNode
from src.schemas.state import State


class ComplianceCaptionGraphNode(GraphNode):
    """Wraps the inner social-commerce compliance + caption workflow (Cat 2 composition)."""

    # S-1: outer main-slot boundary - first caller-facing gate on this
    # path (InputValidateNode is pre_process; this GraphNode is main). Matches
    # config/agent.yaml agent-level default.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    # "propagate": re-raise inner errors as SubgraphError (fail fast - default).
    error_strategy: ClassVar[str] = "propagate"
    # No HITL in this template.
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, rule_kb: Any = None, llm: Any = None) -> None:
        super().__init__()
        self._rule_kb = rule_kb
        self._llm = llm

    def get_subgraph(self) -> Any:
        from src.graph.domain_workflow_graph import ComplianceCaptionWorkflowGraph

        sg = ComplianceCaptionWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        # S-4: emit a dispatch event inside the GraphNode boundary (extract_input runs
        # inside GraphNode.execute()); the wrapper does not override execute().
        emit_trace_event(
            "workflow_dispatched",
            {"correlation_id": state.get("correlation_id", "")},
            state,
        )
        # validated_input (JSON string of the content item) is set by InputValidateNode.
        return cast(str, state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        emit_trace_event(
            "workflow_completed",
            {"correlation_id": state.get("correlation_id", ""), "status": str(sub_result.get("status"))},
            state,
        )
        return {
            "content_item": sub_result.get("content_item"),
            "target_platforms": sub_result.get("target_platforms"),
            "compliance_report": sub_result.get("compliance_report"),
            "captions": sub_result.get("captions"),
            "disclosure_tag": sub_result.get("disclosure_tag", ""),
            "upload_package": sub_result.get("upload_package"),
            "result": sub_result.get("output"),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {"rule_kb": self._rule_kb, "llm": self._llm}


class SocialCommerceComplianceGraph(AgentBaseGraph):
    """RET-C2-271 - Social Commerce Pre-Upload Compliance & Caption Agent (Cat 2)."""

    @property
    def name(self) -> str:
        return "ret-c2-271"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects initialize + finalize

        rule_kb = self.config.get("rule_kb")
        llm = self.config.get("llm")

        self._nodes["pre_process"] = InputValidateNode()
        self._nodes["main"] = ComplianceCaptionGraphNode(rule_kb=rule_kb, llm=llm)
        self._nodes["post_process"] = OutputValidateNode()

    # add_edges() is NOT overridden - backbone wiring belongs to the framework.


# Alias for agent.yaml module:"src.graph" resolution (AgentRegistry / api/server.py).
Graph = SocialCommerceComplianceGraph
