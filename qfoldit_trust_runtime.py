"""
qFoldIT Trust & Compliance Runtime
===================================
A default-deny provenance gate that sits in front of UEFN-TOOLBELT's
two dispatch points (`run_toolbelt_tool`, `execute_python`).

WHAT THIS DOES
--------------
- Blocks by default. Nothing is "authorized" just because it exists.
- Distinguishes PROVENANCE (where an asset actually came from) from
  PRESENCE (whether it happens to be in the project). Only provenance
  can justify letting a call through.
- Never invents a licensing relationship. If no manifest entry exists
  for a flagged brand/franchise term, the call is blocked and logged —
  it does NOT get a "probably fine" pass.
- Treats every engine-version change as a trust reset for anything
  that was verified against a different UE major version.

WHAT THIS DOES NOT DO
----------------------
- It cannot confirm that you or your studio actually hold a license
  from Disney / Warner Bros. Discovery / LEGO Group / Paramount /
  Epic's Icon Series program. That confirmation has to exist as a
  real document you attach via `license_manifest.json`. This module
  only enforces that such a document exists before letting a flagged
  call proceed — it is a gate, not a source of legitimacy.

INTEGRATION POINT (in mcp_server.py)
-------------------------------------
    from qfoldit_trust_runtime import TrustRuntime

    trust = TrustRuntime(
        manifest_path="license_manifest.json",
        engine_version="UE6",          # detect this, don't hardcode in prod
        audit_log_path="trust_audit.log.jsonl",
    )

    @mcp.tool()
    def run_toolbelt_tool(tool_name: str, kwargs: dict | None = None) -> str:
        decision = trust.evaluate(tool_name=tool_name, kwargs=kwargs or {})
        if not decision.allowed:
            return trust.deny_response(decision)
        result = _send("run_tool", {"tool_name": tool_name, "kwargs": kwargs or {}},
                        timeout=LONG_OPERATION_TIMEOUT)
        return _j(result)

    @mcp.tool()
    def execute_python(code: str) -> str:
        decision = trust.evaluate(tool_name="execute_python", kwargs={"code": code})
        if not decision.allowed:
            return trust.deny_response(decision)
        ...  # existing body
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable


# ─── Data model ────────────────────────────────────────────────────────────


@dataclass
class ManifestEntry:
    """One real, human-attested license/authorization record.

    Every field here should be filled in from an actual document —
    a signed agreement, a public Epic Content Library listing, a
    written grant — never inferred or auto-generated.
    """
    rightsholder: str
    scope: str                     # e.g. "LEGO Style Gallery — Epic-native content"
    verification_source: str       # URL or document reference proving this is real
    verified_by: str               # human name/handle who checked it
    verified_date: str             # ISO date of verification
    engine_versions_verified: list[str]  # e.g. ["UE5"]
    review_due: str                # ISO date — after this, treat as stale
    notes: str = ""
    # Who this license actually flows through — matters because the
    # obligations differ:
    #   "epic_ip_partner"           -> Epic's IP Partner Licensing Agreement
    #                                   (LEGO, TMNT, etc.) — template-only,
    #                                   Epic collects/splits royalty automatically.
    #   "creator_owned"             -> your own original IP. No Epic partner
    #                                   royalty, but YOU are the one warranting
    #                                   to Epic (Fortnite EULA / UEFN Supplemental
    #                                   Terms) that you actually own it.
    #   "creator_independent_license" -> you separately negotiated rights
    #                                   directly with a rightsholder, outside
    #                                   any Epic partner program. Same warranty
    #                                   obligation as creator_owned, PLUS you
    #                                   must actually hold a document from that
    #                                   rightsholder (verification_source should
    #                                   point at it — a contract ID / internal
    #                                   legal repo link, not a public URL).
    license_type: str = "epic_ip_partner"
    # Structured conditions actually documented in the brand's own rules —
    # filled in only from what the source document says, never guessed.
    template_only: bool | None = None       # must use only Epic-provided templates/assets, no custom import
    no_mixing_other_ip: bool | None = None  # cannot combine with another third-party IP in the same island
    royalty_pct: float | None = None        # revenue share owed to the rightsholder, if documented
    monetization_scope: str = ""            # e.g. "Within Fortnite only"
    rules: list[str] = field(default_factory=list)  # documented conditions, paraphrased from the source
    # Real provenance anchors for this brand, if known — the actual plugin/
    # content-pack identifier(s) the engine reports for genuine assets of
    # this brand. Populate this from a real Content Browser / Asset Registry
    # inspection, never guessed. Empty list = not yet captured -> provenance
    # checks for this brand fall back to the text heuristic and are marked
    # unverified.
    content_plugin_ids: list[str] = field(default_factory=list)


@dataclass
class Decision:
    allowed: bool
    reason: str
    matched_terms: list[str] = field(default_factory=list)
    manifest_entry: str | None = None
    stale_engine_version: bool = False
    conditions: list[str] = field(default_factory=list)  # documented rules the caller must still follow
    # Provenance metadata — did an Epic-native / manifest allow decision come
    # from a real engine-reported asset origin, or only from string matching?
    #   "engine_verified"  — asset_metadata_fn confirmed the resolved plugin
    #                        id matches a known-good namespace/content_plugin_ids
    #   "engine_mismatch"  — asset_metadata_fn was available and DISAGREED
    #                        with what the text claimed (spoofed-path case)
    #   "text_heuristic"   — no engine hook configured; substring match only
    #   "not_applicable"   — decision made before any provenance check ran
    #                        (default deny, no-match-allow, stale, etc.)
    provenance_method: str = "not_applicable"


# ─── Restricted-term watchlist ─────────────────────────────────────────────
# This is a REVIEW TRIGGER list, not a permission list. A match here never
# grants access by itself — it only means "check the manifest, and if
# nothing real is on file, block and log."

DEFAULT_WATCHLIST = [
    # Franchises / rightsholders referenced in your own asset catalog —
    # extend this from your actual Content Library scan, not by guessing.
    "batman", "superman", "wonder woman", "harley quinn", "joker",       # WB/DC
    "rick sanchez", "morty smith",                                       # WB
    "spider-man", "iron man", "avengers", "thor", "wolverine", "deadpool",  # Marvel/Disney
    "star wars", "darth vader", "skywalker", "mandalorian", "grogu",     # Disney
    "lego",                                                              # LEGO Group
    "tmnt", "teenage mutant ninja turtles",                              # Paramount/Nickelodeon
    "squid game",                                                        # Netflix — real Epic IP Partner brand
    "the walking dead", "twdu",                                          # Skybound/AMC — real Epic IP Partner brand
    "kpop demon hunters",                                                # Netflix/Sony — real Epic IP Partner brand
    "simpsons", "homer simpson", "bart simpson",                         # Disney/20th
    # Real people — likeness/right-of-publicity risk, not copyright,
    # but the same "no document = no pass" rule applies.
    "mrbeast", "eminem", "lebron james", "keanu reeves", "ariana grande",
]


# ─── Runtime ────────────────────────────────────────────────────────────────


class TrustRuntime:
    def __init__(
        self,
        manifest_path: str = "license_manifest.json",
        engine_version: str = "UE5",
        audit_log_path: str = "trust_audit.log.jsonl",
        watchlist: list[str] | None = None,
        epic_native_namespace_prefixes: tuple[str, ...] = (
            "/EpicContent/", "/FortniteGame/", "/Engine/",
        ),
        asset_metadata_fn: "Callable[[str], dict[str, Any] | None] | None" = None,
    ):
        self.manifest_path = manifest_path
        self.engine_version = engine_version
        self.audit_log_path = audit_log_path
        self.watchlist = [w.lower() for w in (watchlist or DEFAULT_WATCHLIST)]
        self.epic_native_prefixes = epic_native_namespace_prefixes
        self.manifest: dict[str, ManifestEntry] = self._load_manifest()
        # Optional hook into the LIVE engine (via the same local IPC channel
        # mcp_server.py already uses for run_toolbelt_tool / execute_python —
        # not a network call). Given a candidate asset path/ref string, it
        # should return {"plugin_id": "...", "resolved_path": "..."} from the
        # engine's own Asset Registry, or None if the ref doesn't resolve to
        # a real asset. When wired up, this turns provenance checks from a
        # text heuristic into a real "what does the engine actually say this
        # is" check. When left as None, behavior is unchanged from before —
        # every allow decision is marked provenance_method="text_heuristic".
        self.asset_metadata_fn = asset_metadata_fn

    # -- manifest -------------------------------------------------------

    def _load_manifest(self) -> dict[str, ManifestEntry]:
        if not os.path.exists(self.manifest_path):
            return {}
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        out = {}
        for key, entry in raw.items():
            if key.startswith("_"):
                continue  # documentation/comment keys, not manifest entries
            out[key.lower()] = ManifestEntry(**entry)
        return out

    def reload_manifest(self) -> None:
        """Call this if the manifest file changes at runtime (e.g. hot-reload)."""
        self.manifest = self._load_manifest()

    # -- classification ---------------------------------------------------

    def _is_epic_native_reference(self, text: str) -> bool:
        """True only if the reference points into a namespace Epic itself
        owns/ships. This is the ONLY presence-based signal this module
        trusts, because it's provenance (Epic shipped it), not just
        presence (it's in your project)."""
        return any(prefix.lower() in text.lower() for prefix in self.epic_native_prefixes)

    @staticmethod
    def _normalize(s: str) -> str:
        # Strip anything that isn't a letter/digit so "Spider-Man",
        # "spiderman", and "SPIDER_MAN" all normalize the same way.
        # This is still a blunt instrument (no stemming, no fuzzy/typo
        # matching) — treat it as a first-pass trigger, not a guarantee.
        return re.sub(r"[^a-z0-9]", "", s.lower())

    def _find_watchlist_matches(self, text: str) -> list[str]:
        text_n = self._normalize(text)
        return [term for term in self.watchlist if self._normalize(term) in text_n]

    # -- provenance (real, engine-backed — not just text) -------------------

    _ASSET_REF_RE = re.compile(r"/[A-Za-z0-9_./-]+")

    @classmethod
    def _extract_asset_refs(cls, payload_text: str) -> list[str]:
        """Pull out things that look like UEFN content paths (e.g.
        '/Game/LEGO/Minifig_01', '/EpicContent/StarWars/Grogu') from a
        kwargs payload, so each one can be checked individually against the
        real engine — instead of trusting the payload's claim as a whole."""
        return cls._ASSET_REF_RE.findall(payload_text)

    def verify_asset_provenance(self, payload_text: str) -> tuple[bool, str, list[str]]:
        """Return (is_epic_native, method, checked_refs).

        method is one of:
          "text_heuristic"  — no engine hook, or nothing path-like to check;
                               falls back to the old substring check.
          "engine_verified" — hook confirmed the resolved asset(s) really
                               live in an Epic-native namespace.
          "engine_mismatch" — the TEXT claimed an Epic-native path (old
                               heuristic would have said yes), but the
                               engine disagrees or the ref doesn't resolve
                               at all. This is the spoofing case and is
                               always treated as non-native — text claims
                               are never trusted over what the engine says.
          "engine_checked_non_native" — the engine was consulted and the
                               ref genuinely isn't Epic-native, but the text
                               never claimed it was either (e.g. a plain
                               '/Game/LEGO/...' path) — this is a normal,
                               non-spoofed case that should fall through to
                               the manifest check, not be blocked outright.
        """
        text_claims_native = self._is_epic_native_reference(payload_text)

        if self.asset_metadata_fn is None:
            return text_claims_native, "text_heuristic", []

        refs = self._extract_asset_refs(payload_text)
        if not refs:
            return text_claims_native, "text_heuristic", []

        checked: list[str] = []
        all_native = True
        for ref in refs:
            meta = self.asset_metadata_fn(ref)
            checked.append(ref)
            if meta is None:
                all_native = False
                continue
            resolved_path = meta.get("resolved_path", "")
            if not self._is_epic_native_reference(resolved_path):
                all_native = False

        if all_native:
            return True, "engine_verified", checked
        if text_claims_native:
            # Spoofed: string looked Epic-native, engine says otherwise.
            return False, "engine_mismatch", checked
        return False, "engine_checked_non_native", checked

    # -- decision -----------------------------------------------------------

    def evaluate(self, tool_name: str, kwargs: dict[str, Any]) -> Decision:
        payload_text = json.dumps(kwargs, ensure_ascii=False, default=str)

        matches = self._find_watchlist_matches(payload_text) + self._find_watchlist_matches(tool_name)
        if not matches:
            decision = Decision(allowed=True, reason="No watchlisted terms matched.")
            self._audit(tool_name, kwargs, decision)
            return decision

        # Flagged. If it's a pure Epic-native reference (gallery/device
        # pulled from Epic's own content, not a custom import), allow —
        # that's Epic's own sanctioned distribution channel, not us
        # granting a license. Verify this against the real engine when a
        # hook is available; a text match alone is not proof of provenance.
        is_native, prov_method, checked_refs = self.verify_asset_provenance(payload_text)
        if is_native:
            decision = Decision(
                allowed=True,
                reason=(
                    "Engine-verified: resolved asset(s) live inside an Epic-owned "
                    f"content namespace ({checked_refs}) — not a custom import."
                    if prov_method == "engine_verified" else
                    "Reference resolves inside an Epic-owned content namespace "
                    "(gallery/device shipped by Epic) — not a custom import. "
                    "NOTE: no live-engine hook configured, so this is a text match "
                    "only, not confirmed asset provenance."
                ),
                matched_terms=matches,
                provenance_method=prov_method,
            )
            self._audit(tool_name, kwargs, decision)
            return decision
        if prov_method == "engine_mismatch":
            decision = Decision(
                allowed=False,
                reason=(
                    f"Matched watchlisted term(s) {matches}, and the payload referenced "
                    f"asset path(s) that look Epic-native in text but the live engine "
                    f"either doesn't recognize them or resolves them somewhere else "
                    f"({checked_refs}). Blocked — a spoofed/incorrect path string is "
                    f"never trusted over what the engine actually reports."
                ),
                matched_terms=matches,
                provenance_method="engine_mismatch",
            )
            self._audit(tool_name, kwargs, decision)
            return decision
        # engine_checked_non_native / text_heuristic-non-native: not a
        # spoofing case, just genuinely not in Epic's own namespace. Falls
        # through to the manifest check below, same as before this patch.

        # Otherwise: require a real manifest entry.
        entry = None
        for term in matches:
            if term in self.manifest:
                entry = self.manifest[term]
                break

        if entry is None:
            decision = Decision(
                allowed=False,
                reason=(
                    f"Matched watchlisted term(s) {matches} in a non-Epic-native "
                    f"reference, and no license_manifest.json entry exists for it. "
                    f"This is blocked by default — presence alone never authorizes "
                    f"use. Add a real, verifiable manifest entry if you actually "
                    f"hold rights for this."
                ),
                matched_terms=matches,
            )
            self._audit(tool_name, kwargs, decision)
            return decision

        # Manifest entry exists — check it's not stale against current engine version.
        if self.engine_version not in entry.engine_versions_verified:
            decision = Decision(
                allowed=False,
                reason=(
                    f"Manifest entry for '{matches[0]}' exists but was only verified "
                    f"against {entry.engine_versions_verified}, not the current engine "
                    f"version ({self.engine_version}). Epic's content/plugin namespaces "
                    f"can change across major versions — re-verify and update the "
                    f"manifest before this is trusted again."
                ),
                matched_terms=matches,
                manifest_entry=matches[0],
                stale_engine_version=True,
            )
            self._audit(tool_name, kwargs, decision)
            return decision

        if entry.review_due and entry.review_due < time.strftime("%Y-%m-%d"):
            decision = Decision(
                allowed=False,
                reason=f"Manifest entry for '{matches[0]}' is past its review_due date "
                       f"({entry.review_due}) — treat as stale until re-verified.",
                matched_terms=matches,
                manifest_entry=matches[0],
            )
            self._audit(tool_name, kwargs, decision)
            return decision

        conditions = list(entry.rules)
        if entry.license_type in ("creator_owned", "creator_independent_license"):
            conditions.append(
                f"NOT an Epic IP Partner brand ({entry.license_type}) — Epic does not verify or "
                f"broker this. YOU are warranting to Epic that {entry.rightsholder} actually holds "
                f"and has granted these rights (Fortnite EULA / UEFN Supplemental Terms §1.7). "
                f"Keep the real document behind verification_source current."
            )
        if entry.template_only:
            conditions.append("Template-only: use only the official brand template/assets provided in UEFN — no custom import of this brand's characters or assets.")
        if entry.no_mixing_other_ip:
            conditions.append("No mixing: this brand's assets cannot be combined with another third-party IP in the same island, even with that other IP's own permission.")
        if entry.royalty_pct is not None:
            conditions.append(f"Royalty: {entry.royalty_pct}% of engagement payout owed to {entry.rightsholder} on this island (Epic deducts automatically).")
        if entry.monetization_scope:
            conditions.append(f"Monetization scope: {entry.monetization_scope}")

        manifest_provenance = "text_heuristic"
        if self.asset_metadata_fn is not None:
            refs = self._extract_asset_refs(payload_text)
            if refs and entry.content_plugin_ids:
                plugin_matches = []
                for ref in refs:
                    meta = self.asset_metadata_fn(ref)
                    if meta and meta.get("plugin_id") in entry.content_plugin_ids:
                        plugin_matches.append(ref)
                manifest_provenance = "engine_verified" if plugin_matches else "engine_mismatch"
            elif refs and not entry.content_plugin_ids:
                # Engine hook exists, but this brand's manifest entry hasn't
                # been given real plugin ids to check against yet — say so
                # honestly rather than silently claiming verification.
                manifest_provenance = "text_heuristic"

        if manifest_provenance == "engine_mismatch":
            decision = Decision(
                allowed=False,
                reason=(
                    f"Matched manifest entry '{matches[0]}' by text, but the live engine "
                    f"reports the referenced asset's plugin id does NOT match this brand's "
                    f"documented content_plugin_ids. Blocked — a manifest entry only covers "
                    f"assets that genuinely came from that brand's real content pack, not "
                    f"anything that merely mentions the brand's name."
                ),
                matched_terms=matches,
                manifest_entry=matches[0],
                provenance_method="engine_mismatch",
            )
            self._audit(tool_name, kwargs, decision)
            return decision

        decision = Decision(
            allowed=True,
            reason=f"Covered by manifest entry: {entry.rightsholder} / {entry.scope}",
            provenance_method=manifest_provenance,
            matched_terms=matches,
            manifest_entry=matches[0],
            conditions=conditions,
        )
        self._audit(tool_name, kwargs, decision)
        return decision

    def describe(self, term: str) -> str:
        """Human-readable summary of what's documented for a given watchlist term —
        useful for a `qfoldit_check_license('lego')`-style tool exposed to the agent."""
        entry = self.manifest.get(term.lower())
        if entry is None:
            return f"No manifest entry for '{term}'. Blocked by default — no verified license on file."
        lines = [
            f"{entry.rightsholder} — {entry.scope}",
            f"License type: {entry.license_type}",
            f"Source: {entry.verification_source}",
            f"Verified: {entry.verified_date} by {entry.verified_by} (engine: {entry.engine_versions_verified})",
            f"Review due: {entry.review_due}",
        ]
        if entry.rules:
            lines.append("Documented conditions:")
            lines.extend(f"  - {r}" for r in entry.rules)
        if entry.royalty_pct is not None:
            lines.append(f"Royalty: {entry.royalty_pct}%")
        return "\n".join(lines)

    # -- audit ------------------------------------------------------------

    def _audit(self, tool_name: str, kwargs: dict[str, Any], decision: Decision) -> None:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "tool_name": tool_name,
            "kwargs_preview": json.dumps(kwargs, default=str)[:500],
            "allowed": decision.allowed,
            "reason": decision.reason,
            "matched_terms": decision.matched_terms,
            "manifest_entry": decision.manifest_entry,
            "conditions": decision.conditions,
            "engine_version": self.engine_version,
        }
        with open(self.audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def deny_response(self, decision: Decision) -> str:
        return json.dumps({
            "status": "BLOCKED_BY_TRUST_RUNTIME",
            "reason": decision.reason,
            "matched_terms": decision.matched_terms,
        }, ensure_ascii=False, indent=2)

    def allow_response_note(self, decision: Decision) -> str | None:
        """If the call was allowed via a manifest entry with documented
        conditions, return a short reminder string to surface alongside the
        tool's normal output. Returns None for plain unrestricted calls."""
        if not decision.conditions:
            return None
        return "qFoldIT: allowed under " + (decision.manifest_entry or "manifest") + \
               " — conditions still apply: " + "; ".join(decision.conditions)
