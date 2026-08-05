"""
qFoldIT Watchlist Extensions Loader
====================================
Loads additional REVIEW-TRIGGER term sets from JSON files in
`qfoldit/compliance/watchlists/` and merges them into a flat term list
that `TrustRuntime(watchlist=...)` can consume, plus a metadata lookup
(`{term: {...}}`) used to enrich the deny-reason text with a category
(e.g. "scientific_equipment_trademark" vs. the entertainment-IP terms
already in `trust_runtime.DEFAULT_WATCHLIST`).

WHY A SEPARATE FILE PER DOMAIN INSTEAD OF ONE BIG LIST
-------------------------------------------------------
`DEFAULT_WATCHLIST` in trust_runtime.py covers entertainment IP that
flows (or plausibly could flow) through Epic's IP Partner Licensing
Agreement program. The extensions here (scientific equipment, vehicles)
have a different legal basis (trademark / trade dress on real-world
commercial products, no Epic-brokered licensing channel at all) and a
different owner in most studios (legal/BD, not the UEFN content team).
Keeping them in separate JSON files means:
  - they can be reviewed, versioned, and enabled/disabled independently
    of the core entertainment-IP list,
  - a project that has zero interest in vehicles or lab equipment can
    skip loading these files entirely (default TrustRuntime behavior
    is unchanged if this loader is never called),
  - each domain's honest false-positive-risk notes stay next to the
    terms they describe instead of being buried in one giant file.

WHAT THIS DOES NOT DO
----------------------
It does not add anything to license_manifest.json. A term appearing in
one of these files being matched still resolves to BLOCKED unless a
real manifest entry exists for it -- exactly like every other watchlist
term. This loader only decides *which terms trigger the check in the
first place*, never whether a match is allowed.
"""

from __future__ import annotations

import json
import os
from typing import Any

_WATCHLISTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlists")


def load_watchlist_extension(path: str) -> dict[str, dict[str, Any]]:
    """Load one watchlist JSON file into {term: metadata}. Skips '_README'."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    out: dict[str, dict[str, Any]] = {}
    for key, meta in raw.items():
        if key.startswith("_"):
            continue
        out[key.lower()] = meta
    return out


def load_all_watchlist_extensions(directory: str | None = None) -> dict[str, dict[str, Any]]:
    """Load and merge every *.json file in the watchlists/ directory.
    Returns {} if the directory doesn't exist -- never raises, so this
    is safe to call unconditionally from TrustRuntime setup code."""
    directory = directory or _WATCHLISTS_DIR
    merged: dict[str, dict[str, Any]] = {}
    if not os.path.isdir(directory):
        return merged
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".json"):
            continue
        merged.update(load_watchlist_extension(os.path.join(directory, fname)))
    return merged


def flatten_enabled_terms(extension: dict[str, dict[str, Any]]) -> tuple[list[str], dict[str, str]]:
    """Turn {term: {"aliases": [...], "enabled": bool, ...}} into
    (flat_term_list, alias_to_canonical_map) suitable for
    TrustRuntime(watchlist=..., aliases=...).

    Respects 'enabled': false (defaults to enabled if the key is
    absent) so a high-false-positive-risk bare word documented in the
    JSON (e.g. a generic word flagged 'enabled': false) never silently
    ends up live in the matcher -- it stays visible in the file for
    review, but isn't auto-armed.

    IMPORTANT FIX: earlier versions of this function flattened aliases
    directly into the term list with no memory of which canonical term
    they belonged to. That's harmless as long as no extension-watchlist
    brand has a manifest entry (every match is blocked regardless of
    which alias/term matched), but it's a real latent bug: the moment a
    real manifest entry gets added for one of these brands, a match on
    an ALIAS (e.g. "kamaz-54901") would fail to resolve to the manifest
    key ("kamaz") and get treated as a phantom unmatched/unlicensed term
    instead of the actual licensed one. Returning the alias map and
    threading it through to TrustRuntime(aliases=...) closes that gap
    now, before it's needed, rather than after someone hits it.
    """
    terms: list[str] = []
    alias_map: dict[str, str] = {}
    for term, meta in extension.items():
        if meta.get("enabled", True) is False:
            continue
        terms.append(term)
        for a in meta.get("aliases", []):
            a_lower = a.lower()
            terms.append(a_lower)
            alias_map[a_lower] = term
    return terms, alias_map


def build_extended_watchlist(
    base_watchlist: list[str],
    directory: str | None = None,
) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, str]]:
    """Convenience entry point: merge `base_watchlist` (e.g.
    trust_runtime.DEFAULT_WATCHLIST) with every enabled term from the
    watchlists/ directory.

    Returns (merged_terms, metadata, alias_map) -- pass merged_terms as
    TrustRuntime(watchlist=...), alias_map as TrustRuntime(aliases=...),
    and keep metadata around if you want to look up category/rightsholder
    for a matched term yourself (e.g. in a custom deny-reason formatter).
    """
    extension = load_all_watchlist_extensions(directory)
    extended_terms, alias_map = flatten_enabled_terms(extension)
    merged = list(dict.fromkeys([*base_watchlist, *extended_terms]))  # dedupe, keep order
    return merged, extension, alias_map
