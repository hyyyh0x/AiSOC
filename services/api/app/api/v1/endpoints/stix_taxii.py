"""STIX/TAXII threat intelligence publishing endpoints."""

import uuid
from datetime import UTC, datetime
from enum import Enum

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/threatintel/stix", tags=["Threat Intelligence"])


# ── Pydantic models ──────────────────────────────────────────────────────────


class IndicatorPattern(str, Enum):
    ipv4_addr = "ipv4-addr"
    domain_name = "domain-name"
    file_hash = "file:hashes"
    url = "url"
    email_addr = "email-addr"


class STIXIndicator(BaseModel):
    type: str = "indicator"
    spec_version: str = "2.1"
    id: str
    created: str
    modified: str
    name: str
    description: str | None = None
    indicator_types: list[str] = []
    pattern: str
    pattern_type: str = "stix"
    valid_from: str
    valid_until: str | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    labels: list[str] = []


class STIXIndicatorCreate(BaseModel):
    name: str
    description: str | None = None
    indicator_types: list[str] = []
    pattern: str
    pattern_type: str = "stix"
    valid_from: str | None = None
    valid_until: str | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    labels: list[str] = []


class STIXBundle(BaseModel):
    type: str = "bundle"
    id: str
    spec_version: str = "2.1"
    created: str
    objects: list[dict]


class STIXBundleCreate(BaseModel):
    objects: list[dict]


class TAXIICollection(BaseModel):
    id: str
    title: str
    description: str
    can_read: bool = True
    can_write: bool = False
    media_types: list[str] = ["application/stix+json;version=2.1"]


class IndicatorListResponse(BaseModel):
    items: list[STIXIndicator]
    total: int


class BundleListResponse(BaseModel):
    items: list[STIXBundle]
    total: int


class TAXIICollectionListResponse(BaseModel):
    items: list[TAXIICollection]
    total: int


# ── Demo data ────────────────────────────────────────────────────────────────

_now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC).isoformat()

DEMO_INDICATORS: list[STIXIndicator] = [
    STIXIndicator(
        id="indicator--a1b2c3d4-0001-4000-8000-000000000001",
        created=_now,
        modified=_now,
        name="Malicious IP - C2 Server",
        description="Known command-and-control server associated with APT-42 campaigns.",
        indicator_types=["malicious-activity"],
        pattern="[ipv4-addr:value = '198.51.100.47']",
        valid_from=_now,
        confidence=92,
        labels=["c2", "apt-42"],
    ),
    STIXIndicator(
        id="indicator--a1b2c3d4-0002-4000-8000-000000000002",
        created=_now,
        modified=_now,
        name="Phishing Domain",
        description="Domain used in credential-harvesting campaign targeting financial sector.",
        indicator_types=["malicious-activity"],
        pattern="[domain-name:value = 'secure-login.example-phish.com']",
        valid_from=_now,
        confidence=88,
        labels=["phishing", "credential-harvesting"],
    ),
    STIXIndicator(
        id="indicator--a1b2c3d4-0003-4000-8000-000000000003",
        created=_now,
        modified=_now,
        name="Ransomware Hash - LockBit Variant",
        description="SHA-256 hash of a LockBit 3.0 ransomware payload.",
        indicator_types=["malicious-activity"],
        pattern="[file:hashes.'SHA-256' = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855']",
        valid_from=_now,
        confidence=95,
        labels=["ransomware", "lockbit"],
    ),
    STIXIndicator(
        id="indicator--a1b2c3d4-0004-4000-8000-000000000004",
        created=_now,
        modified=_now,
        name="Exfiltration URL",
        description="URL used for data exfiltration via HTTPS tunnel.",
        indicator_types=["malicious-activity"],
        pattern="[url:value = 'https://drop.evil-cdn.example/upload']",
        valid_from=_now,
        confidence=78,
        labels=["exfiltration", "data-theft"],
    ),
    STIXIndicator(
        id="indicator--a1b2c3d4-0005-4000-8000-000000000005",
        created=_now,
        modified=_now,
        name="Suspicious Email Sender",
        description="Email address associated with BEC campaigns targeting executives.",
        indicator_types=["anomalous-activity"],
        pattern="[email-addr:value = 'cfo-urgent@spoofed-corp.example']",
        valid_from=_now,
        confidence=70,
        labels=["bec", "social-engineering"],
    ),
]

DEMO_BUNDLES: list[STIXBundle] = [
    STIXBundle(
        id="bundle--f47ac10b-58cc-4372-a567-0e02b2c3d479",
        created=_now,
        objects=[ind.model_dump() for ind in DEMO_INDICATORS[:3]],
    ),
]

DEMO_TAXII_COLLECTIONS: list[TAXIICollection] = [
    TAXIICollection(
        id="collection--01",
        title="AiSOC Threat Feed",
        description="Curated indicators from AiSOC automated threat intelligence pipeline.",
    ),
    TAXIICollection(
        id="collection--02",
        title="Community IOCs",
        description="Community-contributed indicators of compromise.",
        can_write=True,
    ),
    TAXIICollection(
        id="collection--03",
        title="MITRE ATT&CK Mapping",
        description="Indicators mapped to MITRE ATT&CK techniques.",
    ),
]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/indicators", response_model=IndicatorListResponse)
async def list_indicators(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    label: str | None = Query(default=None),
) -> IndicatorListResponse:
    """List STIX 2.1 indicators from the threat intelligence store."""
    items = list(DEMO_INDICATORS)
    if label:
        items = [i for i in items if label in i.labels]
    return IndicatorListResponse(items=items, total=len(items))


@router.post("/indicators", response_model=STIXIndicator, status_code=status.HTTP_201_CREATED)
async def create_indicator(body: STIXIndicatorCreate) -> STIXIndicator:
    """Publish a new STIX 2.1 indicator."""
    now_iso = datetime.now(UTC).isoformat()
    indicator = STIXIndicator(
        id=f"indicator--{uuid.uuid4()}",
        created=now_iso,
        modified=now_iso,
        name=body.name,
        description=body.description,
        indicator_types=body.indicator_types,
        pattern=body.pattern,
        pattern_type=body.pattern_type,
        valid_from=body.valid_from or now_iso,
        valid_until=body.valid_until,
        confidence=body.confidence,
        labels=body.labels,
    )
    DEMO_INDICATORS.append(indicator)
    return indicator


@router.get("/bundles", response_model=BundleListResponse)
async def list_bundles() -> BundleListResponse:
    """List STIX 2.1 bundles."""
    return BundleListResponse(items=DEMO_BUNDLES, total=len(DEMO_BUNDLES))


@router.post("/bundles", response_model=STIXBundle, status_code=status.HTTP_201_CREATED)
async def create_bundle(body: STIXBundleCreate) -> STIXBundle:
    """Create a new STIX 2.1 bundle from a list of STIX objects."""
    if not body.objects:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bundle must contain at least one STIX object.",
        )
    bundle = STIXBundle(
        id=f"bundle--{uuid.uuid4()}",
        created=datetime.now(UTC).isoformat(),
        objects=body.objects,
    )
    DEMO_BUNDLES.append(bundle)
    return bundle


@router.get("/taxii/collections", response_model=TAXIICollectionListResponse)
async def list_taxii_collections() -> TAXIICollectionListResponse:
    """List TAXII 2.1 collections for server compatibility."""
    return TAXIICollectionListResponse(
        items=DEMO_TAXII_COLLECTIONS,
        total=len(DEMO_TAXII_COLLECTIONS),
    )
