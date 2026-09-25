"""AgentCore Platform v1.0 - RET-C2-271 OutputPackageNode (inner step 4)."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import assemble_upload_package


class OutputPackageNode(FunctionNode):
    """Assemble the upload-metadata package (inner final step).

    The actual HTTP upload is a delegated Tool (shared/tools/upload_dispatcher) and is
    NEVER performed in-graph - this node only assembles the metadata the Tool consumes.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        content_item = from_json(state.get("content_item"), {})
        captions = from_json(state.get("captions"), {})
        disclosure_tag = state.get("disclosure_tag", "")
        compliance_report = from_json(state.get("compliance_report"), {})

        if not isinstance(content_item, dict) or not content_item:
            emit_trace_event(
                "output_package_rejected",
                {"reason": "missing_content_item", "correlation_id": state.get("correlation_id", "")},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["OutputPackageNode: missing content item"],
            }

        package = assemble_upload_package(content_item, captions, disclosure_tag, compliance_report)

        emit_trace_event(
            "upload_package_assembled",
            {
                "upload_ready": package.get("upload_ready"),
                "platforms": list(package.get("per_platform", {}).keys()),
                "correlation_id": state.get("correlation_id", ""),
            },
            state,
        )
        return {"upload_package": to_json(package), "status": AgentStatus.SUCCESS.value}
