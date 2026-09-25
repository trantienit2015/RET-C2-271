# RET-C2-271 — Social Commerce Pre-Upload Compliance and Caption Agent

> **Category**: Cat 2 (orchestrates multiple steps to accomplish a specific use case)
> **Industry**: RET

## Overview

Checks a social-commerce promotional post before upload and prepares per-platform captions, an
AI-disclosure tag and an upload metadata package. The input is either a JSON object with
`product_info` (or `content`), an optional `video_ref` and an optional `target_platforms` list
(`tiktok`, `line_voom`, `instagram`; unknown values are dropped and all three are used when none
remain), or plain text that is treated as the product description. Input that is empty or
contains a bearer token/JWT, a credential field, a 12-digit number, an e-mail address or a phone
number is rejected; HTML tags are stripped and the text is capped at 8,000 characters. The entry
node requires a verified external caller.

The compliance step screens the product text for a fixed list of Japanese superlative or
unsubstantiated claim terms (for example 最安値, 日本一, No.1) and returns an advisory report with
flags, severity and remediation hints; it always includes the AI-disclosure rule. A rule
knowledge base can be injected through the graph configuration (`rule_kb` with a `search(text)`
method); none is bundled. Captions are then produced per platform, a fixed AI-disclosure tag is
applied whenever captions exist, and an upload metadata package is assembled with
`upload_ready: false` when a high-severity flag was found. The template does not upload anything.
Credential patterns in the final result are redacted.

A language model is optional. When a client is configured it adds context-based compliance
findings and writes the captions; if a call fails the error is logged and the deterministic
result is used instead. Without a client each caption is the platform prefix plus the first
120 characters of the product text. The bundled HTTP entry point creates an Anthropic client only
when an `ANTHROPIC_API_KEY` secret is available.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | 3.11 or later |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and test specification
```

See `docs/02_design.md` for the design and `docs/03_test_spec.md` for the test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
