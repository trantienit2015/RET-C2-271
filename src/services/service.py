"""AgentCore Platform v1.0 - RET-C2-271 domain service layer.

Deterministic domain logic for the social-commerce pre-upload compliance +
caption-generation agent:
  - content-item parsing (product info + target platforms)
  - 景品表示法 / 消費者庁 AI-disclosure compliance rule lookup (deterministic-core +
    injectable KB) and prohibited-claim flagging
  - platform-optimised caption assembly (deterministic fallback; LLM-essential
    wording is produced in the node with an injected LLM)
  - AI-disclosure tag rules (消費者庁 framework)
  - upload-metadata package assembly (the HTTP upload itself is a Tool:
    shared/tools/upload_dispatcher, never in-graph)
  - output sanitisation: strip platform-credential patterns from the package

No agenticstar imports. No business logic lives in nodes - nodes call these
pure functions and own only the FunctionNode/state/security plumbing.
"""

from __future__ import annotations

import json
import re
from typing import Any

_SUPPORTED_PLATFORMS = ("tiktok", "line_voom", "instagram")

# Superlative / unsubstantiated-claim terms always flagged under 景品表示法
# (優良誤認 / 有利誤認). Deterministic screen; the LLM adds context-grounded findings.
_PROHIBITED_TERMS = (
    "最安値",
    "業界No",
    "日本一",
    "世界一",
    "No.1",
    "No.１",
    "最高",
    "唯一",
    "完全無添加",
    "100%安全",
    "絶対",
    "必ず痩せ",
)


def parse_content_item(raw: str) -> dict[str, Any] | None:
    """Parse the caller payload into {product_info, video_ref, target_platforms}.

    Accepts JSON; falls back to treating the whole string as product_info text.
    Returns None only for empty input.
    """
    if not raw or not raw.strip():
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            platforms = obj.get("target_platforms") or list(_SUPPORTED_PLATFORMS)
            platforms = [p for p in platforms if p in _SUPPORTED_PLATFORMS] or list(_SUPPORTED_PLATFORMS)
            return {
                "product_info": str(obj.get("product_info", obj.get("content", ""))),
                "video_ref": str(obj.get("video_ref", "")),
                "target_platforms": platforms,
            }
    except (TypeError, ValueError):
        pass
    return {"product_info": raw.strip(), "video_ref": "", "target_platforms": list(_SUPPORTED_PLATFORMS)}


def lookup_compliance_rules(product_info: str, rule_kb: Any | None = None) -> list[dict[str, Any]]:
    """Return applicable 景表法 / AI-disclosure rules for the content.

    A real deployment injects a KB (rule_kb.search(text) -> list[dict]); the
    deterministic-core fallback returns the always-applicable AI-disclosure rule.
    """
    rules: list[dict[str, Any]] = []
    if rule_kb is not None and hasattr(rule_kb, "search"):
        try:
            found = rule_kb.search(product_info) or []
            for r in found:
                rules.append({"clause": r.get("clause", ""), "text": r.get("text", "")})
        except Exception:  # noqa: BLE001 - KB failure must not crash the pipeline
            pass
    rules.append(
        {
            "clause": "消費者庁 AI-disclosure framework",
            "text": "AI-generated promotional content must carry an explicit AI-disclosure tag.",
        }
    )
    return rules


def flag_prohibited_claims(product_info: str) -> list[dict[str, Any]]:
    """Deterministic screen for prohibited 景表法 superlative/unsubstantiated claims."""
    flags = []
    for term in _PROHIBITED_TERMS:
        if term in product_info:
            flags.append(
                {
                    "term": term,
                    "reason": "unsubstantiated/superlative claim (優良誤認/有利誤認 risk under 景品表示法)",
                    "severity": "high",
                    "remediation": f"remove or substantiate the claim '{term}' before upload",
                }
            )
    return flags


def build_compliance_report(
    flags: list[dict[str, Any]], llm_findings: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Assemble the compliance report (advisory framing)."""
    all_flags = list(flags) + list(llm_findings or [])
    severity = "high" if any(f.get("severity") == "high" for f in all_flags) else ("medium" if all_flags else "none")
    return {
        "advisory_notice": "Advisory only - not a legal determination. Review flagged items before upload.",
        "flags": all_flags,
        "severity": severity,
        "remediation": [f.get("remediation", "") for f in all_flags if f.get("remediation")],
    }


def build_disclosure_tag(is_ai_generated: bool) -> str:
    """Deterministic AI-disclosure tag per 消費者庁 framework.

    Non-empty whenever AI-generated content is present (PB contract).
    """
    if is_ai_generated:
        return "#AI生成コンテンツ #PR (AI-assisted content - 消費者庁 AI-disclosure)"
    return "#PR"


def fallback_caption(platform: str, product_info: str) -> str:
    """Deterministic caption when no LLM is provisioned (keeps pipeline runnable)."""
    base = product_info.strip()[:120]
    prefix = {"tiktok": "[TikTok]", "line_voom": "[LINE]", "instagram": "[IG]"}.get(platform, "")
    return f"{prefix} {base}".strip()


def assemble_upload_package(
    content_item: dict[str, Any], captions: dict[str, Any], disclosure_tag: str, compliance_report: dict[str, Any]
) -> dict[str, Any]:
    """Assemble the upload-metadata package (Tool-call input for upload_dispatcher).

    The actual HTTP upload is delegated to shared/tools/upload_dispatcher - never here.
    """
    return {
        "video_ref": content_item.get("video_ref", ""),
        "per_platform": {
            p: {"caption": captions.get(p, ""), "disclosure_tag": disclosure_tag}
            for p in content_item.get("target_platforms", [])
        },
        "compliance_severity": compliance_report.get("severity", "none"),
        "upload_ready": compliance_report.get("severity") != "high",
    }


_CRED_PATTERN_RE = re.compile(
    r'("(?:access_token|api_key|client_secret|password)"\s*:\s*"[^"]*"|Bearer\s+[A-Za-z0-9._-]{10,}|eyJ[A-Za-z0-9._-]{10,})'
)


def redact_credentials(text: str) -> tuple[str, bool]:
    """Strip platform-credential patterns from the output package. Returns (text, was_redacted)."""
    if not text:
        return text, False
    redacted = _CRED_PATTERN_RE.sub("[REDACTED_CREDENTIAL]", text)
    return redacted, redacted != text
