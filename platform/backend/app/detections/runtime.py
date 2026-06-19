"""Process-wide singleton for the built-in detection pack + engine.

The Sigma `RulePack` is expensive to build (it walks ``rules/`` recursively,
parses every YAML, and validates each rule's detection AST), so we want
to do it exactly once per process and reuse the same `DetectionEngine`
across every event that comes in through the API. This module owns that
lifecycle.

Callers should treat the engine as read-only at runtime. Hot-reloading
(for tenant overrides or `detection-author` agent PRs) is provided by
`reload()` and `add_rule()` below — both rebuild the engine atomically
under the same lock that protects first-use construction.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from .engine import DetectionEngine
from .pack import RulePack
from .sigma import SigmaRule

logger = logging.getLogger(__name__)

_BUILTIN_RULES_DIR = Path(__file__).parent / "rules"

_lock = threading.Lock()
_engine: DetectionEngine | None = None
_pack: RulePack | None = None


def _build_engine() -> DetectionEngine:
    """Load the built-in rule pack and wrap it in a `DetectionEngine`.

    We deliberately load in non-strict mode so a single bad rule in the
    pack never bricks the API; the loader logs each skipped file. CI runs
    the smoke test in strict mode to catch broken rules pre-merge.

    The ``verticals/`` subdirectory is excluded — those rules are
    delivered per-tenant through ``detections/registry.py`` based on
    explicit ``TenantPackAssignment`` rows. Loading them into the
    process-wide engine would mean every tenant gets every vertical's
    detections, which defeats the point of vertical packs.
    """
    pack = RulePack.load_directory(
        _BUILTIN_RULES_DIR,
        name="builtin",
        strict=False,
        exclude_subdirs=("verticals",),
    )
    logger.info("detection_runtime:engine_ready rules=%d", len(pack))
    return DetectionEngine(pack=pack)


def get_engine() -> DetectionEngine:
    """Return the process-wide `DetectionEngine`, building it on first use."""
    global _engine, _pack
    if _engine is not None:
        return _engine
    with _lock:
        if _engine is None:
            _engine = _build_engine()
            _pack = _engine.pack
        return _engine


def get_pack() -> RulePack:
    """Return the underlying `RulePack` (mostly for introspection endpoints)."""
    if _pack is None:
        get_engine()
    assert _pack is not None
    return _pack


def reset() -> None:
    """Drop the cached engine. Tests only — production should not call this."""
    global _engine, _pack
    with _lock:
        _engine = None
        _pack = None


def reload() -> DetectionEngine:
    """Rebuild the engine from disk.

    Called by the detection-author agent after a new YAML lands on the
    rules directory (locally or via GitOps merge) and by tests that need
    to pick up file-system changes without restarting the process. The
    rebuild happens under the same lock as first-use construction so a
    concurrent ``get_engine()`` either sees the previous engine or the
    new one — never a half-built pack.
    """
    global _engine, _pack
    with _lock:
        _engine = _build_engine()
        _pack = _engine.pack
        return _engine


def add_rule(rule: SigmaRule) -> DetectionEngine:
    """Add (or replace) a single rule on the live engine.

    Used by the detection-author *preview* flow where an analyst wants
    to see retro-hunt results from a proposed rule before opening the
    GitOps PR. The rule lives only in memory until ``reload()`` is
    called or the process restarts; callers that want persistence must
    also write the YAML to disk.
    """
    global _engine, _pack
    with _lock:
        if _pack is None or _engine is None:
            _engine = _build_engine()
            _pack = _engine.pack
        _pack.add(rule)
        # Rebuild the engine so any cached field-index or compiled state
        # picks up the new rule. Cheap relative to the rule pack load.
        _engine = DetectionEngine(pack=_pack)
        return _engine
