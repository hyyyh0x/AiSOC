"""REST endpoints for the analyst console.

Every route here that touches tenant data resolves a `TenantContext` via
`require_tenant` before running a query, and every query goes through
`apply_tenant_filter()` (or a row-level `ensure_row_visible()` check).
The dev-anon path in `require_tenant` still lets the existing demo
bootstrap call these endpoints without a bearer token; see
`app.security.tenant` for the precedence rules.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlmodel import Session, select

from app.agents.attack_path import AttackPathAgent
from app.agents.detection_validation import DetectionValidationAgent
from app.agents.hunter import HunterAgent
from app.agents.orchestrator import Orchestrator
from app.models.detection_validation import ValidationRun, ValidationRunStatus
from app.api.events import bus
from app.config import settings
from app.db import get_session, session_scope
from app.detections.runtime import get_engine
from app.detections.sigma import Hit
from app.memory import (
    detection_count,
    detection_kb_backend_name,
    detection_search,
    episodic_backend_name,
    graph_backend_name,
    scratchpad,
)
from app.memory.autopop import populate_from_alert
from app.memory.embedding import embedding_dim, embedding_provider_name
from app.models.alert import Alert
from app.models.case import Case, CaseStatus, Severity
from app.models.tool_call import ToolCall
from app.models.trace import AgentTrace
from app.realtime.case_events import publish_case_created
from app.realtime.ocsf import OcsfEvent, normalize_event, ocsf_to_sigma_payload
from app.realtime.stream import TOPICS, get_stream
from app.security import (
    TenantContext,
    apply_tenant_filter,
    ensure_row_visible,
    require_tenant,
)
from app.tools.registry import registry

router = APIRouter()


# ── Health ─────────────────────────────────────────────────────────────
@router.get("/health")
def health() -> dict[str, Any]:
    """Unauthenticated liveness probe — must not leak any tenant data."""
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}


# ── Whoami ─────────────────────────────────────────────────────────────
@router.get("/whoami")
def whoami(ctx: TenantContext = Depends(require_tenant)) -> dict[str, Any]:
    """Echo back the resolved tenant context — useful for console debugging
    and for end-to-end tests asserting the JWT path is wired up correctly."""
    return {
        "subject": ctx.subject,
        "tenant_id": ctx.claims.tenant_id,
        "active_tenant_id": ctx.active_tenant_id,
        "roles": list(ctx.claims.roles),
        "is_mssp": ctx.is_mssp,
        "is_admin": ctx.is_admin,
        "mssp_parent_tenant_id": ctx.claims.mssp_parent_tenant_id,
        "allowed_tenants": list(ctx.claims.allowed_tenants),
        "viewable_tenant_ids": ctx.viewable_tenant_ids(),
    }


# ── Tools ───────────────────────────────────────────────────────────────
@router.get("/tools")
def list_tools(
    ctx: TenantContext = Depends(require_tenant),
) -> list[dict[str, Any]]:
    """Tool catalog filtered through the per-tenant allowlist.

    The registry is global, but `registry.allowed_for_tenant(tenant_id)`
    masks tools that a tenant isn't licensed for (e.g. Cyble-native
    deep-dark-web pivots gated behind add-on SKUs).
    """
    allowed = registry.allowed_for_tenant(ctx.active_tenant_id)
    return [
        {
            "name": t.name,
            "integration": t.integration,
            "risk_class": t.risk_class.value,
            "description": t.description,
            "cyble_native": t.cyble_native,
            "tags": t.tags,
        }
        for t in allowed
    ]


# ── Alerts ──────────────────────────────────────────────────────────────
class AlertIngest(BaseModel):
    external_id: str
    source: str
    title: str
    description: str = ""
    severity: str = "medium"
    detection_rule: str | None = None
    mitre_tactics: list[str] = []
    mitre_techniques: list[str] = []
    src_user: str | None = None
    src_host: str | None = None
    src_ip: str | None = None
    dst_ip: str | None = None
    process_name: str | None = None
    file_hash: str | None = None
    raw: dict = {}


@router.post("/alerts")
def ingest_alert(
    payload: AlertIngest,
    bg: BackgroundTasks,
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    """Create a Case + Alert under the caller's active tenant.

    All downstream agent work, tool calls, traces, and HITL requests
    inherit `tenant_id` from the Case row.
    """
    tenant_id = ctx.active_tenant_id

    alert = Alert(tenant_id=tenant_id, **payload.model_dump())

    case = Case(
        tenant_id=tenant_id,
        title=payload.title,
        severity=Severity(payload.severity) if payload.severity in [s.value for s in Severity] else Severity.MEDIUM,
        status=CaseStatus.NEW,
        mitre_techniques=payload.mitre_techniques,
    )
    session.add(case)
    session.commit()
    session.refresh(case)
    alert.case_id = case.id
    session.add(alert)
    session.commit()
    session.refresh(alert)

    # Mirror the alert's entities into the threat graph so cross-case
    # pivots ("what else has talked to this C2?") work without an agent
    # having to walk every row first. Wrapped at the helper level so a
    # graph backend hiccup never breaks ingestion.
    populate_from_alert(alert)

    bg.add_task(_run_orchestrator, case.id, tenant_id)
    return {"alert_id": alert.id, "case_id": case.id, "tenant_id": tenant_id, "queued": True}


async def _run_orchestrator(case_id: int, tenant_id: str) -> None:
    """Background entrypoint for the per-case agent graph.

    `tenant_id` is passed explicitly rather than inferred from the Case
    row so the orchestrator's constructor can fail fast if the case has
    been moved between tenants (it shouldn't, but defense in depth).

    We emit ``case.created`` on the realtime stream + bus *here* rather
    than at HTTP-handler time so the publish only happens after the
    Case row is durably committed and visible to other workers. This
    avoids the classic "websocket fires before SELECT can see the row"
    race that bites every multi-process deployment.
    """
    with session_scope() as s:
        case = s.get(Case, case_id)
        if case is not None:
            await publish_case_created(
                tenant_id=tenant_id,
                case_id=case_id,
                title=case.title,
                severity=case.severity.value,
                status=case.status.value,
                source="orchestrator-bootstrap",
            )
        orch = Orchestrator(s, case_id, tenant_id=tenant_id, on_event=bus.publish)
        await orch.run()


# ── Events (raw event ingest → Sigma engine → Alert/Case) ──────────────
class EventIngest(BaseModel):
    """A normalized event landing on the realtime detection path.

    Connectors call this once they've shaped vendor logs into the common
    schema. The `source` and `external_id` (when present) let us trace
    back to the upstream system, and `event` is the OCSF-ish payload
    every Sigma rule evaluates against.

    Theme 1: t1-realtime-data will eventually replace this synchronous
    HTTP path with Kafka → engine workers → ClickHouse, but the contract
    here stays the same.
    """

    source: str
    event: dict
    external_id: str | None = None


def _hit_mitre_split(tags: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Split Sigma ``attack.*`` tags into (tactics, techniques).

    Sigma convention: ``attack.t1059`` / ``attack.t1059.001`` for techniques,
    everything else under ``attack.`` (e.g. ``attack.execution``) is a
    tactic. We preserve casing as it appears in the rule.
    """
    tactics: list[str] = []
    techniques: list[str] = []
    for tag in tags:
        if not tag.startswith("attack."):
            continue
        rest = tag[len("attack.") :]
        if rest.startswith("t") and rest[1:2].isdigit():
            techniques.append(rest.upper())
        else:
            tactics.append(rest)
    return tactics, techniques


def _alert_from_hit(
    *,
    hit: Hit,
    ocsf: OcsfEvent,
    source: str,
    external_id_override: str | None,
    tenant_id: str,
) -> Alert:
    """Project a detection ``Hit`` + normalized OCSF event onto an Alert row.

    Entity fields (user/host/ip/process/hash) come straight off the
    normalized :class:`OcsfEvent`; that's the whole point of running the
    OCSF normalizer in front of Sigma — every Sigma rule and every Alert
    row sees the same canonical fields regardless of upstream dialect.

    The original payload survives in ``Alert.raw`` under ``event`` so
    forensic re-parse is still possible if our normalizer ever gets a
    dialect wrong.
    """
    tactics, techniques = _hit_mitre_split(hit.tags)
    external_id = external_id_override or ocsf.external_id or f"sigma:{hit.rule_id}:{id(ocsf):x}"
    description = (
        f"Sigma rule '{hit.title}' matched selections: "
        f"{', '.join(hit.matched_selections) or '(implicit)'}"
    )
    return Alert(
        tenant_id=tenant_id,
        external_id=external_id,
        source=source,
        title=hit.title,
        description=description,
        severity=hit.severity.value,
        detection_rule=hit.rule_id,
        mitre_tactics=tactics,
        mitre_techniques=techniques,
        src_user=ocsf.actor_user,
        src_host=ocsf.src_host,
        src_ip=ocsf.src_ip,
        dst_ip=ocsf.dst_ip,
        process_name=ocsf.actor_process_name,
        file_hash=ocsf.file_hash,
        raw={
            "event": ocsf.raw,
            "ocsf": ocsf.to_dict(),
            "matched_selections": list(hit.matched_selections),
        },
    )


@router.post("/events")
async def ingest_event(
    payload: EventIngest,
    bg: BackgroundTasks,
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    """Evaluate one raw event against the Sigma engine; spawn cases per hit.

    The ingest path is intentionally short:

    1. **Normalize** the raw vendor payload to OCSF — one chokepoint, one
       canonical shape regardless of whether the connector spoke Sysmon,
       ECS, or half-baked OCSF.
    2. **Publish** the normalized event onto the OCSF stream so the
       ClickHouse sink (and any future analytical consumer) sees every
       event we ingest, even ones that don't trigger any Sigma rule.
       This is what makes retro-hunt possible.
    3. **Evaluate** Sigma rules against a flat projection of the OCSF
       event, so rules written against either OCSF or Sysmon dialect
       light up against the same payload.
    4. **Persist** an Alert + spawn a Case per matched rule, mirror
       entities into the threat graph, and hand the case off to the
       background orchestrator.

    Pre-engine ingestion (``POST /alerts``) is still the path SIEMs use
    when they've already done detection. ``/events`` is the path for
    EDR-style raw telemetry where Cyble AiSOC owns detection end-to-end.
    """
    tenant_id = ctx.active_tenant_id

    # OCSF normalization — never raises, always returns *something*.
    ocsf = normalize_event(
        source=payload.source,
        event=payload.event,
        external_id=payload.external_id,
    )

    # Publish to OCSF stream regardless of detection outcome. Downstream
    # consumers (ClickHouse sink, retro-hunt, BAS verifier) need every
    # event, not just the ones a Sigma rule happened to flag today.
    stream_payload = {"tenant_id": tenant_id, **ocsf.to_dict()}
    try:
        await get_stream().publish(TOPICS.EVENTS_OCSF, stream_payload)
    except Exception:  # noqa: BLE001 — publish must never break ingest
        # The in-memory backend never throws here; this guards the Kafka
        # path where a broker outage shouldn't take down detection.
        pass

    # Sigma evaluation uses the flat alias-rich projection so rules in
    # either OCSF or Sysmon dialect match against the same payload.
    sigma_event = ocsf_to_sigma_payload(ocsf)
    engine = get_engine()
    hits = engine.evaluate(sigma_event)

    if not hits:
        return {
            "tenant_id": tenant_id,
            "hits": 0,
            "case_ids": [],
            "normalization_dialect": ocsf.normalization_dialect,
        }

    case_ids: list[int] = []
    alert_ids: list[int] = []
    for hit in hits:
        alert = _alert_from_hit(
            hit=hit,
            ocsf=ocsf,
            source=payload.source,
            external_id_override=payload.external_id,
            tenant_id=tenant_id,
        )
        try:
            severity = Severity(hit.severity.value)
        except ValueError:
            severity = Severity.MEDIUM

        tactics, techniques = _hit_mitre_split(hit.tags)
        case = Case(
            tenant_id=tenant_id,
            title=hit.title,
            severity=severity,
            status=CaseStatus.NEW,
            mitre_techniques=techniques,
        )
        session.add(case)
        session.commit()
        session.refresh(case)
        alert.case_id = case.id
        session.add(alert)
        session.commit()
        session.refresh(alert)

        populate_from_alert(alert)
        bg.add_task(_run_orchestrator, case.id, tenant_id)
        case_ids.append(case.id)
        alert_ids.append(alert.id)

    return {
        "tenant_id": tenant_id,
        "hits": len(hits),
        "case_ids": case_ids,
        "alert_ids": alert_ids,
        "rules_fired": [h.rule_id for h in hits],
        "normalization_dialect": ocsf.normalization_dialect,
    }


# ── Detection rule introspection ───────────────────────────────────────
@router.get("/detections/rules")
def list_detection_rules(
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    """Return a thin summary of the loaded Sigma rule pack.

    Useful for the analyst console "what rules are live?" panel and for
    smoke-testing that the engine actually came up after a deploy.
    """
    engine = get_engine()
    rules = [
        {
            "id": r.id,
            "title": r.title,
            "severity": r.severity.value,
            "tags": list(r.tags),
        }
        for r in engine.pack.rules
    ]
    return {"count": len(rules), "rules": rules}


# ── Detection Knowledge Base (DKB) ─────────────────────────────────────
class DetectionSearchRequest(BaseModel):
    """Search request for the Detection Knowledge Base.

    The DKB powers "what detection content do we already have for X?"
    queries from the Hunter, Detection Author, and Investigator agents,
    plus the analyst-console rule explorer. Search is hybrid: a vector
    similarity score (the analyst-friendly "is this rule about the same
    *concept*?") is blended with a keyword score (exact tag/title hits).
    """

    query: str = ""
    limit: int = 10
    severity: str | None = None
    tag: str | None = None
    logsource: dict[str, str] | None = None


@router.post("/detections/search")
def search_detection_kb(
    body: DetectionSearchRequest,
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    """Hybrid (vector + keyword) search across the Detection Knowledge Base.

    Detection content is *shared* across tenants — these are public-style
    rules, not customer data — but we still scope the call to the caller's
    tenant so future vertical packs (Theme 3d) can shadow built-ins on a
    per-tenant basis without changing this contract.
    """
    matches = detection_search(
        query=body.query,
        k=max(1, min(body.limit, 50)),
        severity=body.severity,
        tag=body.tag,
        logsource=body.logsource,
        tenant_id=ctx.active_tenant_id,
    )
    return {
        "backend": detection_kb_backend_name(),
        "total_indexed": detection_count(),
        "matches": [
            {
                "id": m.rule.id,
                "title": m.rule.title,
                "severity": m.rule.severity.value,
                "tags": list(m.rule.tags),
                "score": round(m.score, 4),
                "vector_score": round(m.vector_score, 4),
                "keyword_score": round(m.keyword_score, 4),
            }
            for m in matches
        ],
    }


# ── Memory substrate status ────────────────────────────────────────────
@router.get("/memory/status")
def memory_status(
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    """Report which memory backends are actually live.

    This is what the analyst console and platform smoke tests hit to
    answer "is this deployment running real Qdrant/Neo4j/Redis, or did
    something fall back to the SQLite/in-memory mirror?". We never
    expose raw connection strings — just the resolved backend name and
    enough metadata to drive a status pill in the UI.
    """
    return {
        "embedding": {
            "provider": embedding_provider_name(),
            "dim": embedding_dim(),
        },
        "episodic": {"backend": episodic_backend_name()},
        "graph": {"backend": graph_backend_name()},
        "scratchpad": {"backend": scratchpad.backend_name()},
        "detection_kb": {
            "backend": detection_kb_backend_name(),
            "total_indexed": detection_count(),
        },
    }


# ── Cases ───────────────────────────────────────────────────────────────
@router.get("/cases")
def list_cases(
    status: str | None = None,
    severity: str | None = None,
    limit: int = 100,
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> list[dict[str, Any]]:
    q = select(Case).order_by(Case.created_at.desc()).limit(limit)
    q = apply_tenant_filter(q, Case.tenant_id, ctx)
    rows = session.exec(q).all()
    out = []
    for c in rows:
        if status and c.status.value != status:
            continue
        if severity and c.severity.value != severity:
            continue
        out.append(_case_to_dict(c))
    return out


@router.get("/cases/{case_id}")
def get_case(
    case_id: int,
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    case = session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    ensure_row_visible(ctx, case.tenant_id)

    # Tenant-scope the related queries as well — even though Alert/Trace/
    # ToolCall rows attached to this case should already share its tenant,
    # we don't trust the join: the filter is the same one we'd use under
    # row-level security.
    alerts_q = apply_tenant_filter(
        select(Alert).where(Alert.case_id == case_id), Alert.tenant_id, ctx
    )
    traces_q = apply_tenant_filter(
        select(AgentTrace).where(AgentTrace.case_id == case_id).order_by(AgentTrace.created_at.asc()),
        AgentTrace.tenant_id,
        ctx,
    )
    tools_q = apply_tenant_filter(
        select(ToolCall).where(ToolCall.case_id == case_id).order_by(ToolCall.created_at.asc()),
        ToolCall.tenant_id,
        ctx,
    )

    alerts = session.exec(alerts_q).all()
    traces = session.exec(traces_q).all()
    tools = session.exec(tools_q).all()
    return {
        **_case_to_dict(case),
        "alerts": [_alert_to_dict(a) for a in alerts],
        "traces": [_trace_to_dict(t) for t in traces],
        "tool_calls": [_tool_to_dict(t) for t in tools],
    }


@router.get("/cases/{case_id}/report")
def get_case_report(
    case_id: int,
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    """Multi-modal case report (Theme 2k).

    Returns a structured ``CaseReport`` JSON document built on demand from
    the canonical case tables: timeline, attack graph, ATT&CK heatmap,
    and blast-radius map. Nothing is persisted — each call recomputes
    from current state so the panels never disagree with the audit log
    (including rollbacks).

    The plain-English narrative (``case.narrative``) continues to live
    on the case row itself; this endpoint is the *structured* companion
    that the analyst console renders alongside it.
    """
    from app.reports import build_case_report

    case = session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    ensure_row_visible(ctx, case.tenant_id)

    try:
        report = build_case_report(
            session,
            case_id=case_id,
            tenant_id=ctx.active_tenant_id,
            case=case,
        )
    except PermissionError as exc:
        # Defense-in-depth: ensure_row_visible already passed, but the
        # builder asserts again. Surface as 403.
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return report.to_dict()


@router.post("/cases/{case_id}/rerun")
def rerun_case(
    case_id: int,
    bg: BackgroundTasks,
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    case = session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    ensure_row_visible(ctx, case.tenant_id)
    bg.add_task(_run_orchestrator, case_id, case.tenant_id)
    return {"case_id": case_id, "queued": True}


# ── Hunter ──────────────────────────────────────────────────────────────
class HuntRequest(BaseModel):
    hypothesis: str


@router.post("/hunts")
async def run_hunt(
    payload: HuntRequest,
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    """Hunter runs against a synthetic 'hunt case' to keep it isolated."""
    case = Case(
        tenant_id=ctx.active_tenant_id,
        title=f"Hunt: {payload.hypothesis[:80]}",
        status=CaseStatus.INVESTIGATING,
        severity=Severity.INFO,
    )
    session.add(case)
    session.commit()
    session.refresh(case)

    # Hunts are user-initiated, not alert-driven, but they still produce
    # a real Case row — emit case.created so the UI shows the hunt in the
    # live case feed alongside alert-spawned cases.
    await publish_case_created(
        tenant_id=ctx.active_tenant_id,
        case_id=case.id,
        title=case.title,
        severity=case.severity.value,
        status=case.status.value,
        source="hunt",
    )

    hunter = HunterAgent(session, case.id, tenant_id=ctx.active_tenant_id)
    result = await hunter.run_hypothesis(payload.hypothesis)
    # Surface the explorer's structured verdict so the UI can render the
    # tree and the analyst doesn't have to dig into traces to find what
    # the hunt actually concluded. We keep `summary` first for backwards
    # compatibility with the existing UI consumers.
    return {
        "case_id": case.id,
        "tenant_id": ctx.active_tenant_id,
        "summary": result.summary,
        "verdict": result.verdict.value,
        "nodes_explored": result.nodes_explored,
        "tool_calls": result.tool_calls,
        "retro_calls": result.retro_calls,
        "iocs_pivoted": list(result.iocs_pivoted),
        "follow_ups": list(result.follow_ups),
        "root_category": result.root.category.value,
    }


# ── Attack-Path Agent (t2g) ─────────────────────────────────────────────
class AttackPathScanRequest(BaseModel):
    """Trigger a pre-attack-path scan for the active tenant.

    ``domain`` is the brand domain handed to the ASM lookup. In
    production this will come from the tenant's brand profile; for the
    API we accept it explicitly so callers can scan a sibling domain
    or a recently-acquired subsidiary without first updating tenant
    config.
    """

    domain: str | None = None
    risk_threshold: float | None = None


@router.post("/attack-paths/scan")
async def run_attack_path_scan(
    payload: AttackPathScanRequest,
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    """Run the Attack-Path Agent once and return discovered paths.

    The agent stitches ASM + Cloud IAM + K8s RBAC + IdP OAuth into the
    threat graph, ranks pre-attack paths, and opens proactive
    ``Severity.HIGH`` cases for every path above the risk threshold.
    The response includes the structured paths so the analyst console
    can render the attack-path graph immediately without polling.
    """
    threshold = payload.risk_threshold if payload.risk_threshold is not None else 0.70
    if not 0.0 <= threshold <= 1.0:
        raise HTTPException(status_code=400, detail="risk_threshold must be in [0, 1]")
    agent = AttackPathAgent(
        session,
        tenant_id=ctx.active_tenant_id,
        domain=payload.domain,
        risk_threshold=threshold,
    )
    result = await agent.scan()
    return result.to_dict()


# ── Continuous Detection Validation Agent (t2h-bas) ─────────────────────
@router.post("/detection-validation/scan")
async def run_detection_validation_scan(
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    """Run one BAS-style validation sweep for the active tenant.

    Replays the synthetic OCSF simulation catalogue through the live
    detection engine, diffs against the previous green baseline, and
    opens proactive cases for any drifted simulations + a roll-up case
    for MITRE technique coverage regressions. Returns the run summary
    so the console can render results without polling.
    """
    agent = DetectionValidationAgent(session, tenant_id=ctx.active_tenant_id)
    result = await agent.scan()
    return result.to_dict()


@router.get("/detection-validation/runs")
def list_detection_validation_runs(
    limit: int = 25,
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> list[dict[str, Any]]:
    """Recent validation runs for the active tenant, newest first.

    Powers the drift-history timeline. Per-simulation detail is omitted
    here for response size; fetch a single run via ``/detection-validation/runs/{id}``.
    """
    if limit <= 0 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be in [1, 200]")
    stmt = apply_tenant_filter(
        select(ValidationRun), ValidationRun.tenant_id, ctx
    ).order_by(ValidationRun.started_at.desc()).limit(limit)
    runs = session.exec(stmt).all()
    return [
        {
            "id": r.id,
            "tenant_id": r.tenant_id,
            "status": r.status.value,
            "simulations_run": r.simulations_run,
            "simulations_fired": r.simulations_fired,
            "simulations_silent": r.simulations_silent,
            "drift_count": r.drift_count,
            "coverage_regressions": r.coverage_regressions,
            "mitre_covered": list(r.mitre_covered or []),
            "mitre_dropped": list(r.mitre_dropped or []),
            "baseline_run_id": r.baseline_run_id,
            "cases_opened": list(r.cases_opened or []),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


@router.get("/detection-validation/runs/{run_id}")
def get_detection_validation_run(
    run_id: int,
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    """Full detail of one validation run, including per-simulation results."""
    run = session.get(ValidationRun, run_id)
    if run is None or run.tenant_id not in ctx.viewable_tenant_ids():
        raise HTTPException(status_code=404, detail="validation run not found")
    return {
        "id": run.id,
        "tenant_id": run.tenant_id,
        "status": run.status.value,
        "simulations_run": run.simulations_run,
        "simulations_fired": run.simulations_fired,
        "simulations_silent": run.simulations_silent,
        "drift_count": run.drift_count,
        "coverage_regressions": run.coverage_regressions,
        "mitre_covered": list(run.mitre_covered or []),
        "mitre_dropped": list(run.mitre_dropped or []),
        "simulation_results": dict(run.simulation_results or {}),
        "cases_opened": list(run.cases_opened or []),
        "baseline_run_id": run.baseline_run_id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/detection-validation/coverage")
def get_detection_validation_coverage(
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    """Latest MITRE technique coverage for the active tenant.

    Reads the most recent COMPLETED ValidationRun and returns the
    covered/dropped technique sets so the dashboard can render the
    ATT&CK coverage heatmap without re-running the agent.
    """
    stmt = (
        apply_tenant_filter(select(ValidationRun), ValidationRun.tenant_id, ctx)
        .where(ValidationRun.status == ValidationRunStatus.COMPLETED)
        .order_by(ValidationRun.started_at.desc())
        .limit(1)
    )
    latest = session.exec(stmt).first()
    if latest is None:
        return {
            "run_id": None,
            "mitre_covered": [],
            "mitre_dropped": [],
            "as_of": None,
        }
    return {
        "run_id": latest.id,
        "mitre_covered": list(latest.mitre_covered or []),
        "mitre_dropped": list(latest.mitre_dropped or []),
        "as_of": latest.completed_at.isoformat() if latest.completed_at else None,
    }


# ── Stats / dashboard ───────────────────────────────────────────────────
@router.get("/stats")
def stats(
    session: Session = Depends(get_session),
    ctx: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    q = apply_tenant_filter(select(Case), Case.tenant_id, ctx)
    cases = session.exec(q).all()
    by_status: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    closed_durations: list[float] = []
    for c in cases:
        by_status[c.status.value] = by_status.get(c.status.value, 0) + 1
        by_severity[c.severity.value] = by_severity.get(c.severity.value, 0) + 1
        if c.closed_at:
            closed_durations.append((c.closed_at - c.created_at).total_seconds())

    auto_resolved = sum(
        1 for c in cases if c.status.value.startswith("closed_") and c.assignee is None
    )
    total = len(cases)
    return {
        "total_cases": total,
        "by_status": by_status,
        "by_severity": by_severity,
        "avg_mttr_seconds": (
            round(sum(closed_durations) / len(closed_durations), 1) if closed_durations else None
        ),
        "auto_resolved": auto_resolved,
        "auto_resolution_rate": round(auto_resolved / total, 3) if total else 0.0,
        "tools_registered": len(registry.allowed_for_tenant(ctx.active_tenant_id)),
        "viewable_tenants": ctx.viewable_tenant_ids(),
    }


# ── WebSocket: live activity ────────────────────────────────────────────
@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    """Live event feed. Authentication for WebSocket goes via the
    `token` query param (browsers can't easily set Authorization on a
    WS handshake). Subscribers are filtered to events for tenants they
    can view; see `bus.subscribe(tenant_ids=...)`.
    """
    token = websocket.query_params.get("token")
    tenant_ids: list[str] | None = None
    if token:
        try:
            from app.security.jwt import claims_from_payload, decode_token  # local import to avoid bootstrap cycle

            claims = claims_from_payload(decode_token(token))
            if claims.is_admin:
                tenant_ids = None  # admin sees everything
            elif claims.is_mssp:
                # MSSP analyst sees their parent tenant + every allowed child.
                tenant_ids = list(claims.allowed_tenants) + [claims.tenant_id]
            else:
                tenant_ids = [claims.tenant_id]
        except Exception:
            # Don't reveal which step failed — just close the socket.
            await websocket.close(code=4401)
            return
    elif settings.dev_allow_anon_tenant:
        # Anonymous dev mode: restrict to the default tenant so we don't leak
        # MSSP / sibling events on the demo console.
        tenant_ids = [settings.default_tenant]
    else:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    q = bus.subscribe(tenant_ids=tenant_ids)
    try:
        while True:
            ev = await q.get()
            await websocket.send_json(ev)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(q)


# ── Serializers ─────────────────────────────────────────────────────────
def _case_to_dict(c: Case) -> dict[str, Any]:
    return {
        "id": c.id,
        "tenant_id": c.tenant_id,
        "title": c.title,
        "narrative": c.narrative,
        "status": c.status.value,
        "severity": c.severity.value,
        "verdict": c.verdict.value,
        "confidence": c.confidence,
        "assignee": c.assignee,
        "mitre_techniques": c.mitre_techniques,
        "affected_users": c.affected_users,
        "affected_hosts": c.affected_hosts,
        "iocs": c.iocs,
        "response_actions": c.response_actions,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
        "closed_at": c.closed_at.isoformat() if c.closed_at else None,
    }


def _alert_to_dict(a: Alert) -> dict[str, Any]:
    return {
        "id": a.id,
        "external_id": a.external_id,
        "tenant_id": a.tenant_id,
        "source": a.source,
        "title": a.title,
        "description": a.description,
        "severity": a.severity,
        "detection_rule": a.detection_rule,
        "mitre_tactics": a.mitre_tactics,
        "mitre_techniques": a.mitre_techniques,
        "src_user": a.src_user,
        "src_host": a.src_host,
        "src_ip": a.src_ip,
        "dst_ip": a.dst_ip,
        "process_name": a.process_name,
        "file_hash": a.file_hash,
        "created_at": a.created_at.isoformat(),
    }


def _trace_to_dict(t: AgentTrace) -> dict[str, Any]:
    return {
        "id": t.id,
        "tenant_id": t.tenant_id,
        "agent": t.agent.value,
        "step": t.step.value,
        "summary": t.summary,
        "detail": t.detail,
        "tokens_in": t.tokens_in,
        "tokens_out": t.tokens_out,
        "latency_ms": t.latency_ms,
        "created_at": t.created_at.isoformat(),
    }


def _tool_to_dict(t: ToolCall) -> dict[str, Any]:
    return {
        "id": t.id,
        "tenant_id": t.tenant_id,
        "tool_name": t.tool_name,
        "integration": t.integration,
        "risk_class": t.risk_class.value,
        "params": t.params,
        "result": t.result,
        "success": t.success,
        "error": t.error,
        "hitl_required": t.hitl_required,
        "hitl_approved_by": t.hitl_approved_by,
        "duration_ms": t.duration_ms,
        "created_at": t.created_at.isoformat(),
    }
