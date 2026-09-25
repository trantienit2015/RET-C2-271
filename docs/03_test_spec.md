# RET-C2-271 — Test Specification

## Test Strategy

Deterministic-core: LLM and KB are injected (or absent with deterministic fallbacks), so the full
suite runs offline. Unit tests cover each node (success + error/edge). Integration compiles the
outer+inner Cat 2 graph and invokes end-to-end. Proof-of-boundary tests verify framework invariants.

## Unit Tests (`tests/unit/test_nodes.py`)

| Node | Cases |
|---|---|
| InputValidateNode | trust=VERIFIED_EXTERNAL; success; empty→ERROR; credential→ERROR; 個人番号→ERROR; `_extra_security_gate_input` hook (block + passthrough) |
| ComplianceCheckNode | prohibited claim→severity high; clean→none/medium; invalid input→ERROR |
| CaptionGenerateNode | per-platform captions; missing product info→ERROR |
| DisclosureTagNode | tag present+AI when captions; tag non-empty even without captions (PB contract) |
| OutputPackageNode | upload_ready true (low severity); false (high severity); missing content→ERROR |
| OutputValidateNode | success; upstream error short-circuit; `_extra_security_gate_output` redacts credential; clean passthrough |

## Integration Tests (`tests/integration/test_graph.py`)

| ID | Test | Expected |
|---|---|---|
| I-1 | full pipeline | SUCCESS; ≥5 nodes; compliance_report + 3 captions + disclosure_tag + upload package |
| I-2 | prohibited claim | severity high; upload_ready false |
| I-3 | ANONYMOUS caller | error/cancelled (S-1) |
| I-4 | empty input | error/cancelled |

## Proof-of-Boundary Tests (`tests/proof_of_boundary/`)

| PB | File | Verifies |
|---|---|---|
| PB-2 | `test_state_safety.py` | state holds only JSON-serializable primitives |
| PB-4 | `test_import_isolation.py` | no agenticstar / mediator / other-agent imports |
| PB-6 | `test_pb_invoke_order.py` | S-1 → node_start → S-2 → execute → S-3 → node_complete per node under src/nodes/ |

## Framework Compliance (TC map)

TC-01 state contract (PB-2) · TC-02 SecurityViolation-equivalent (InputValidate credential/PII) ·
TC-03 no credentials in src (CI gate) · TC-05 emit_trace_event in every execute() · TC-06/07 gate
hooks (InputValidate/OutputValidate) · TC-08 trust enforced (I-3).
