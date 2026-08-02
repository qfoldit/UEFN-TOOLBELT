"""
qFoldIT Trust & Compliance Dashboard
=====================================
A visualization panel over the three qfoldit_* logs/manifests that live at
the repo root (license_manifest.json, trust_audit.log.jsonl,
commission_ledger.log.jsonl). Read-only — this window never writes to any
of them, it just summarizes what qfoldit_trust_runtime.py and
qfoldit_monetization_registry.py have already recorded.

Registered under category="Dashboard" per registry.py's standard 3-step
tool pattern, so it shows up as its own button next to "launch_qt" — no
changes to dashboard_pyside6.py required.
"""

from __future__ import annotations

import json
import os

from ..registry import register_tool
from ..core.base_window import ToolbeltWindow, _PYSIDE6
from ..core import log_info, log_error

if _PYSIDE6:
    from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QLabel, QScrollArea


def _repo_root() -> str:
    """Same 3-up-from-UEFN_Toolbelt convention used by update_toolbelt in
    dashboard_pyside6.py — this file is one level deeper (tools/), so go
    up one more."""
    import UEFN_Toolbelt as _tb
    return os.path.abspath(os.path.join(os.path.dirname(_tb.__file__), "..", "..", ".."))


def _read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return out


def _summarize(root: str) -> dict:
    manifest = _read_json(os.path.join(root, "license_manifest.json"))
    audit = _read_jsonl(os.path.join(root, "trust_audit.log.jsonl"))
    commissions = _read_jsonl(os.path.join(root, "commission_ledger.log.jsonl"))

    brands = {k: v for k, v in manifest.items() if not k.startswith("_")}

    allowed = sum(1 for a in audit if a.get("allowed"))
    blocked = sum(1 for a in audit if not a.get("allowed"))
    by_provenance: dict[str, int] = {}
    for a in audit:
        m = a.get("provenance_method", "not_applicable")
        by_provenance[m] = by_provenance.get(m, 0) + 1

    accepted_commissions = sum(1 for c in commissions if c.get("accepted"))
    blocked_commissions = sum(1 for c in commissions if not c.get("accepted"))
    priced = [c.get("estimated_cost_usd") for c in commissions if c.get("estimated_cost_usd") is not None]
    total_priced_usd = round(sum(priced), 4) if priced else None
    unpriced_paid_backend = sum(
        1 for c in commissions
        if c.get("requires_paid_backend") and c.get("estimated_cost_usd") is None
    )

    return {
        "brands": brands,
        "audit_total": len(audit),
        "allowed": allowed,
        "blocked": blocked,
        "by_provenance": by_provenance,
        "commissions_total": len(commissions),
        "accepted_commissions": accepted_commissions,
        "blocked_commissions": blocked_commissions,
        "total_priced_usd": total_priced_usd,
        "unpriced_paid_backend": unpriced_paid_backend,
    }


if _PYSIDE6:

    class QFoldITTrustDashboard(ToolbeltWindow):
        def __init__(self):
            super().__init__(title="UEFN Toolbelt — qFoldIT Trust & Compliance", width=1000, height=720)
            self._build_ui()
            self.refresh()

        def _build_ui(self):
            central = QWidget()
            self.setCentralWidget(central)
            vl = QVBoxLayout(central)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(0)

            bar, bl = self.make_topbar("qFOLDIT TRUST & COMPLIANCE")
            bl.addWidget(self.make_btn("Refresh", accent=True, cb=self.refresh))
            bl.addStretch()
            vl.addWidget(bar)

            scroll, inner = self.make_scroll_panel(width=0, border_left=False)
            inner_vl = QVBoxLayout(inner)
            inner_vl.setContentsMargins(12, 12, 12, 12)
            inner_vl.setSpacing(10)
            vl.addWidget(scroll, stretch=1)
            self._body = inner_vl

        def _clear_body(self):
            while self._body.count():
                item = self._body.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

        def _section(self, title: str) -> QVBoxLayout:
            lbl = self.make_label(title, bold=True, size=13)
            self._body.addWidget(lbl)
            self._body.addWidget(self.make_divider())
            box = QVBoxLayout()
            wrap = QWidget()
            wrap.setLayout(box)
            self._body.addWidget(wrap)
            return box

        def refresh(self):
            self._clear_body()
            try:
                summary = _summarize(_repo_root())
            except Exception as e:
                self._body.addWidget(self.make_label(f"Could not load qFoldIT data: {e}"))
                return

            gate = self._section("IP Compliance Gate — Audit Log")
            gate.addWidget(self.make_label(
                f"{summary['allowed']} allowed  ·  {summary['blocked']} blocked  "
                f"·  {summary['audit_total']} decisions total"
            ))
            for method, count in sorted(summary["by_provenance"].items()):
                gate.addWidget(self.make_label(f"    provenance = {method}: {count}"))

            brands = self._section(f"Licensed Brands ({len(summary['brands'])})")
            for key, entry in sorted(summary["brands"].items()):
                royalty = entry.get("royalty_pct")
                royalty_s = f"{royalty}%" if royalty is not None else "not confirmed"
                due = entry.get("review_due", "?")
                plugins = entry.get("content_plugin_ids") or []
                plugin_s = ", ".join(plugins) if plugins else "not yet captured"
                brands.addWidget(self.make_label(
                    f"{entry.get('rightsholder', key)} — royalty: {royalty_s}  ·  "
                    f"review due: {due}  ·  content_plugin_ids: {plugin_s}"
                ))

            comm = self._section("Off-Platform Commissions")
            comm.addWidget(self.make_label(
                f"{summary['accepted_commissions']} accepted  ·  "
                f"{summary['blocked_commissions']} blocked by IP gate  ·  "
                f"{summary['commissions_total']} total"
            ))
            if summary["total_priced_usd"] is not None:
                comm.addWidget(self.make_label(f"Total priced (configured rate): ${summary['total_priced_usd']}"))
            if summary["unpriced_paid_backend"]:
                comm.addWidget(self.make_label(
                    f"⚠ {summary['unpriced_paid_backend']} commission(s) used a metered backend "
                    f"(e.g. Boltz) with no rate configured in boltz_pricing.json — cost unknown, "
                    f"not zero."
                ))

            self._body.addStretch()


_WINDOW = None


def launch_qfoldit_dashboard() -> None:
    global _WINDOW
    if not _PYSIDE6:
        log_error("[qFoldIT] PySide6 not available — cannot open dashboard.")
        return
    if _WINDOW is None or not _WINDOW.isVisible():
        _WINDOW = QFoldITTrustDashboard()
    _WINDOW.show_in_uefn()
    _WINDOW.activateWindow()
    log_info("[qFoldIT] Trust & Compliance dashboard open.")


@register_tool(
    name="qfoldit_trust_dashboard",
    category="Dashboard",
    description="Visualize qFoldIT's IP compliance audit log, licensed brands, and commission pricing — read-only.",
    icon="⛨",
    tags=["qfoldit", "trust", "compliance", "license", "dashboard", "monetization"],
)
def open_qfoldit_dashboard(**kwargs) -> None:
    launch_qfoldit_dashboard()
