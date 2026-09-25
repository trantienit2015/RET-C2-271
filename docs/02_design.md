# RET-C2-271 — Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `SocialCommerceComplianceGraph` (module `src.graph`, alias `Graph`) — inherits `AgentBaseGraph` (L1 direct)
- **L1 Base Type**: `AgentBaseGraph` (L1 direct inheritance — no L2 base class)
- **Category**: Cat 2 — multi-step social-commerce compliance + caption pipeline
- **Pattern**: DocGeneration-style; Cat 2 composition = outer `AgentBaseGraph` + `GraphNode`(main) + inner `BaseGraph`
- **Industry**: RET
- **Trust level (agent default)**: `VERIFIED_EXTERNAL`

## Cat 2 Composition

```
OUTER (AgentBaseGraph - src/graph/graph.py):
  initialize -> pre_process(InputValidate) -> main(ComplianceCaptionGraphNode) -> post_process(OutputValidate) -> finalize

INNER (BaseGraph - src/graph/domain_workflow_graph.py):
  START -> compliance_check -> caption_generate -> disclosure_tag -> output_package -> END   (fail-fast on ERROR)
```

`ComplianceCaptionGraphNode` (a `GraphNode`) lives in `graph.py`, not `src/nodes/` (so PB-6 does not
wrongly assert the standard node lifecycle on it). Data crosses the boundary as a JSON string:
outer `pre_process` serializes the content item to `validated_input`; `extract_input()` passes it;
the inner first step `json.loads` it. Config (`rule_kb`, `llm`) reaches the inner via `_parent_config()`.

## State Schema (`src/schemas/state.py`)

`class State(AgentState)` - flat, all agent-specific fields `NotRequired`; nested dict/list stored as
JSON strings (`to_json`/`from_json`). Fields: `content_item`, `target_platforms`, `compliance_report`,
`captions`, `disclosure_tag`, `upload_package`.

## Nodes

| Slot / step | Node | Responsibility |
|---|---|---|
| outer pre_process | `InputValidateNode` | S-1 (VERIFIED_EXTERNAL) + S-2 credential/PII scan (`_extra_security_gate_input`) + parse/serialize content |
| inner 1 | `ComplianceCheckNode` | KB + LLM grounded 景表法/AI-disclosure eval; deterministic prohibited-claim screen; advisory report |
| inner 2 | `CaptionGenerateNode` | LLM per-platform captions (tiktok/line_voom/instagram); deterministic fallback |
| inner 3 | `DisclosureTagNode` | Deterministic 消費者庁 AI-disclosure tag (non-empty when AI content - PB contract) |
| inner 4 | `OutputPackageNode` | Assemble upload-metadata package (upload itself = Tool `shared/tools/upload_dispatcher`, never in-graph) |
| outer post_process | `OutputValidateNode` | S-3 credential redaction (`_extra_security_gate_output`) + final output |

## Security (5-layer)

- **S-1**: agent default `VERIFIED_EXTERNAL`; every FunctionNode declares `required_trust_level`.
- **S-2**: deterministic regex scan (Bearer/JWT, credential fields, 個人番号, email, phone) -> `status=ERROR` (raise-free) + `_extra_security_gate_input()` re-check.
- **S-3**: output gate strips platform-credential patterns (`_extra_security_gate_output()`), drop+log on catch. Secrets via `ctx.secrets.require()`; never `os.environ`/state.
- **S-4**: `emit_trace_event()` in every node's `execute()`; GraphNode wrapper emits via `extract_input`/`merge_output` (workflow_dispatched / workflow_completed).
- **S-5**: no credentials in source (CI `gate-credential-scan`).

## Output Schema (locked)

`{compliance_report{flags[], severity, remediation}, captions{tiktok, line_voom, instagram}, disclosure_tag, upload_metadata_package}`.
PB contract: `disclosure_tag` present + non-empty whenever captions were generated.

## Dependencies

Deterministic-core: no external KB/LLM/HTTP dependency pinned. A real deployment injects `rule_kb`
(`.search()`) and `llm` (`.complete()`) via graph config; the upload is delegated to
`shared/tools/upload_dispatcher`. `dependencies = []` (framework from wheel).
