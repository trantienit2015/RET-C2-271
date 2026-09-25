"""AgentCore Platform v1.0 - RET-C2-271 inner domain workflow graph.

Cat 2 inner graph: the multi-step social-commerce compliance + caption pipeline.
Instantiated by ComplianceCaptionGraphNode.get_subgraph() in graph.py.

Pipeline (linear, fail-fast on ERROR):
    START -> compliance_check -> caption_generate -> disclosure_tag -> output_package -> END
"""

from typing import Any, cast
from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus

from src.nodes.caption_generate_node import CaptionGenerateNode
from src.nodes.compliance_check_node import ComplianceCheckNode
from src.nodes.disclosure_tag_node import DisclosureTagNode
from src.nodes.output_package_node import OutputPackageNode
from src.schemas.state import State


class ComplianceCaptionWorkflowGraph(BaseGraph):
    """Inner graph for the RET-C2-271 social-commerce compliance + caption workflow."""

    @property
    def name(self) -> str:
        return "social-commerce-compliance-workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        # No mandatory config: rule_kb / llm are optional (deterministic fallbacks exist).
        pass

    def register_nodes(self) -> None:
        # No super() - BaseGraph.register_nodes() is abstract. initialize/finalize are
        # outer backbone concerns, not inner.
        rule_kb = self.config.get("rule_kb")
        llm = self.config.get("llm")

        self._nodes["compliance_check"] = ComplianceCheckNode(rule_kb=rule_kb, llm=llm)
        self._nodes["caption_generate"] = CaptionGenerateNode(llm=llm)
        self._nodes["disclosure_tag"] = DisclosureTagNode()
        self._nodes["output_package"] = OutputPackageNode()

    def add_edges(self) -> None:
        # Linear pipeline; any node returning ERROR short-circuits to END.
        self._sg.add_edge(START, "compliance_check")
        self._sg.add_conditional_edges(
            "compliance_check",
            lambda s: END if self._is_error(s) else "caption_generate",
            {"caption_generate": "caption_generate", END: END},
        )
        self._sg.add_conditional_edges(
            "caption_generate",
            lambda s: END if self._is_error(s) else "disclosure_tag",
            {"disclosure_tag": "disclosure_tag", END: END},
        )
        self._sg.add_conditional_edges(
            "disclosure_tag",
            lambda s: END if self._is_error(s) else "output_package",
            {"output_package": "output_package", END: END},
        )
        self._sg.add_edge("output_package", END)

    @staticmethod
    def _is_error(state: AgentState) -> bool:
        return cast(bool, state.get("status") == AgentStatus.ERROR.value)

    def route(self, state: AgentState) -> str:
        # Required by BaseGraph ABC. Fail-fast semantics mirror add_edges().
        return END if self._is_error(state) else "output_package"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "content_item": state.get("content_item"),
            "target_platforms": state.get("target_platforms"),
            "compliance_report": state.get("compliance_report"),
            "captions": state.get("captions"),
            "disclosure_tag": state.get("disclosure_tag", ""),
            "upload_package": state.get("upload_package"),
            "output": state.get("upload_package"),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
