"""Cyble-native CTI tools — the moat from the plan.

Dark-web mention checks, brand intel, ASM, vuln intel.
These are flagged cyble_native=True so the UI can highlight them.
"""
from __future__ import annotations

from typing import Any

from app.tools.registry import RiskClass, tool

# Mock IOC enrichment database (in real life this hits Cyble's CTI APIs)
_IOC_DB: dict[str, dict[str, Any]] = {
    "185.220.101.42": {
        "type": "ip",
        "threat_score": 92,
        "tags": ["tor_exit_node", "c2_infrastructure", "fin7_associated"],
        "first_seen": "2024-08-12",
        "actor": "FIN7",
        "campaigns": ["Carbanak Q3"],
        "darkweb_mentions": 14,
    },
    "evil-update.duckdns.org": {
        "type": "domain",
        "threat_score": 88,
        "tags": ["typosquat", "phishing", "credential_harvester"],
        "registered": "2026-04-18",
        "darkweb_mentions": 3,
    },
    "9c2a4e1a7b8d3f6e0c1b5a9d8e7f6c5b4a3d2e1f0c9b8a7d6e5f4c3b2a1d0e9f": {
        "type": "sha256",
        "threat_score": 96,
        "malware_family": "Cobalt Strike Beacon",
        "first_seen": "2025-11-04",
        "yara_hits": ["cobaltstrike_x64", "shellcode_loader"],
    },
}


@tool(
    name="cti.enrich_ioc",
    integration="cyble-cti",
    risk=RiskClass.READ,
    description="Enrich an IOC with Cyble threat intelligence: actor, campaign, dark-web mentions.",
    params={
        "type": "object",
        "properties": {"ioc": {"type": "string"}, "ioc_type": {"type": "string"}},
        "required": ["ioc"],
    },
    result={
        "type": "object",
        "properties": {
            "ioc": {"type": "string"},
            "found": {"type": "boolean"},
            "threat_score": {"type": "integer"},
            "type": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "actor": {"type": "string"},
            "campaigns": {"type": "array", "items": {"type": "string"}},
            "darkweb_mentions": {"type": "integer"},
            "first_seen": {"type": "string"},
            "malware_family": {"type": "string"},
            "yara_hits": {"type": "array", "items": {"type": "string"}},
            "registered": {"type": "string"},
        },
        "required": ["ioc", "found"],
    },
    cyble_native=True,
    tags=["enrichment", "moat"],
)
async def cti_enrich_ioc(ioc: str, ioc_type: str = "auto") -> dict[str, Any]:
    record = _IOC_DB.get(ioc)
    if record:
        return {"ioc": ioc, "found": True, **record}
    return {"ioc": ioc, "found": False, "threat_score": 0}


@tool(
    name="cti.darkweb_search",
    integration="cyble-darkweb",
    risk=RiskClass.READ,
    description="Search Cyble's dark-web crawl index for mentions of an entity (domain, email, brand).",
    params={
        "type": "object",
        "properties": {"query": {"type": "string"}, "days": {"type": "integer", "default": 30}},
        "required": ["query"],
    },
    cyble_native=True,
    tags=["moat"],
)
async def cti_darkweb_search(query: str, days: int = 30) -> dict[str, Any]:
    return {
        "query": query,
        "days": days,
        "hits": [
            {
                "forum": "exploit.in",
                "ts": "2026-04-26T03:14:00Z",
                "snippet": f"Selling fresh access to *{query}* corporate VPN — $4,500 BTC",
                "actor_handle": "ghostvendor",
                "confidence": "high",
            },
            {
                "forum": "telegram:leakroom",
                "ts": "2026-04-22T19:08:00Z",
                "snippet": f"Database leak referencing {query} employee credentials, 1.2k rows",
                "confidence": "medium",
            },
        ],
    }


@tool(
    name="cti.brand_intel",
    integration="cyble-brand",
    risk=RiskClass.READ,
    description="Brand intelligence: typosquats, phishing kits, fake apps, executive impersonation.",
    params={
        "type": "object",
        "properties": {"brand": {"type": "string"}},
        "required": ["brand"],
    },
    cyble_native=True,
    tags=["moat"],
)
async def cti_brand_intel(brand: str) -> dict[str, Any]:
    return {
        "brand": brand,
        "active_typosquats": 7,
        "phishing_kits_observed": 2,
        "examples": [
            f"{brand}-secure.com",
            f"{brand}-portal.duckdns.org",
        ],
    }


@tool(
    name="cti.asm_lookup",
    integration="cyble-asm",
    risk=RiskClass.READ,
    description="Attack-surface management: external assets, exposed services, certs for a domain.",
    params={
        "type": "object",
        "properties": {"domain": {"type": "string"}},
        "required": ["domain"],
    },
    cyble_native=True,
    tags=["moat"],
)
async def cti_asm_lookup(domain: str) -> dict[str, Any]:
    return {
        "domain": domain,
        "external_assets": 412,
        "high_risk_findings": [
            {"asset": f"vpn.{domain}", "issue": "Pulse Secure VPN — known CVE-2024-21887 exposed", "severity": "critical"},
            {"asset": f"api-staging.{domain}", "issue": "Swagger UI exposed without auth", "severity": "high"},
        ],
    }


@tool(
    name="cti.vuln_intel",
    integration="cyble-vuln",
    risk=RiskClass.READ,
    description="Vulnerability intelligence: CVE exploitation status, ITW evidence, patch priority.",
    params={
        "type": "object",
        "properties": {"cve": {"type": "string"}},
        "required": ["cve"],
    },
    cyble_native=True,
    tags=["moat"],
)
async def cti_vuln_intel(cve: str) -> dict[str, Any]:
    return {
        "cve": cve,
        "exploited_in_wild": True,
        "first_itw": "2024-02-14",
        "exploit_kits": ["Metasploit", "PoC on Github"],
        "ransomware_use": ["CL0P", "Akira"],
        "patch_priority": "P0",
    }
