"""
qFoldIT Monetization Registry
================================
Two fundamentally different money flows, documented separately because
mixing them causes real mistakes:

  A) FORTNITE/UEFN-NATIVE — money flows through Epic's own systems
     (Engagement Payout pool, in-island V-Bucks sales, brand royalty
     splits). Governed entirely by Epic's Developer Rules / Monetization
     Agreement. qFoldIT has no control over these mechanics, only over
     whether an island qualifies (compliance, per the Trust Runtime).

  B) OFF-PLATFORM COMMISSIONS ("Cameo-style" tasks) — a partner/customer
     pays qFoldIT directly for a custom generated output: an L-system
     plant, a drug-design candidate, a molecular/atomic structure model,
     etc. This has NOTHING to do with Fortnite's payout system — it's
     your own storefront/API business. But it still has to pass through
     compliance, because a customer can ask for something that collides
     with the same watchlist (e.g. "make an L-system tree shaped like
     [a trademarked character]"), and it may consume metered third-party
     compute (Boltz) that has to be priced in.

This module documents (A) as reference data and implements a working
gate for (B): every commission request is checked against the Trust
Runtime's watchlist/manifest BEFORE it's accepted for payment, and
flagged if it requires a paid backend call.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from qfoldit.compliance.trust_runtime import TrustRuntime, Decision


@dataclass
class BoltzCostEstimate:
    estimated_seconds: float
    estimated_cost_usd: float | None   # None = rate not configured yet, NOT "free"
    gpu_type: str | None
    calibrated_from_real_runs: bool
    note: str


_DEFAULT_PRICING_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "boltz_pricing.json")


def estimate_boltz_cost(
    sequence_length: int,
    num_samples: int = 1,
    pricing_path: str | None = None,
) -> BoltzCostEstimate:
    """Local, offline compute-cost estimate for a Boltz-2 job.

    Deliberately does NOT call any pricing API — this repo's Security
    guarantees zero outbound network calls. The dollar rate has to come
    from boltz_pricing.json, filled in by hand from your real Modal
    billing dashboard. If it's missing, this returns a time estimate but
    estimated_cost_usd=None — callers must not silently treat that as free.
    """
    pricing_path = pricing_path or _DEFAULT_PRICING_PATH
    if os.path.exists(pricing_path):
        with open(pricing_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        cfg = {}

    baseline = cfg.get("baseline_seconds_per_100_residues", 45)
    overhead = cfg.get("overhead_seconds", 20)
    rate = cfg.get("rate_usd_per_gpu_second")
    gpu_type = cfg.get("gpu_type")
    calibrated = bool(cfg.get("calibrated_from_real_runs", False))

    seconds = overhead + baseline * (max(sequence_length, 0) / 100.0) * max(num_samples, 1)

    if rate is None:
        return BoltzCostEstimate(
            estimated_seconds=seconds,
            estimated_cost_usd=None,
            gpu_type=gpu_type,
            calibrated_from_real_runs=calibrated,
            note=(
                "rate_usd_per_gpu_second is not set in boltz_pricing.json — "
                "fill it in from your real Modal billing before quoting a price. "
                "Time estimate below is provided, cost is not."
            ),
        )

    cost = round(seconds * float(rate), 4)
    note = "Estimate from a local rate table" + (
        "" if calibrated else " that has NOT yet been calibrated against real "
        "timed Boltz runs — treat as a rough order of magnitude, not a quote."
    )
    return BoltzCostEstimate(
        estimated_seconds=seconds,
        estimated_cost_usd=cost,
        gpu_type=gpu_type,
        calibrated_from_real_runs=calibrated,
        note=note,
    )


@dataclass
class MonetizationChannel:
    name: str
    channel_type: str          # "fortnite_native" | "off_platform_commission"
    mechanism: str
    revenue_split: str
    source: str
    status: str                 # active | preview | sunsetting
    notes: str = ""


@dataclass
class CommissionDecision:
    accepted: bool
    reason: str
    ip_check: Decision | None = None
    requires_paid_backend: bool = False
    backend_used: str | None = None
    cost_estimate: BoltzCostEstimate | None = None


class MonetizationRegistry:
    _DEFAULT_CHANNELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monetization_channels.json")

    def __init__(
        self,
        channels_path: str | None = None,
        commission_log_path: str = "commission_ledger.log.jsonl",
        trust: TrustRuntime | None = None,
    ):
        self.channels_path = channels_path or self._DEFAULT_CHANNELS_PATH
        self.commission_log_path = commission_log_path
        self.channels: dict[str, MonetizationChannel] = self._load()
        # Reuse the same compliance gate already built for UEFN calls —
        # a commissioned task description is just another kind of
        # "kwargs" to scan against the watchlist/manifest.
        self.trust = trust

    def _load(self) -> dict[str, MonetizationChannel]:
        if not os.path.exists(self.channels_path):
            return {}
        with open(self.channels_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        out = {}
        for key, rec in raw.items():
            if key.startswith("_"):
                continue
            out[key] = MonetizationChannel(**rec)
        return out

    def list_channels(self, channel_type: str | None = None) -> list[str]:
        if channel_type is None:
            return list(self.channels.keys())
        return [k for k, v in self.channels.items() if v.channel_type == channel_type]

    def describe(self, name: str) -> str:
        ch = self.channels.get(name)
        if ch is None:
            return f"'{name}' not registered."
        return (
            f"{ch.name} ({ch.channel_type}) — status: {ch.status}\n"
            f"Mechanism: {ch.mechanism}\n"
            f"Split: {ch.revenue_split}\n"
            f"Source: {ch.source}\n"
            + (f"Notes: {ch.notes}" if ch.notes else "")
        )

    # ---- Off-platform commission gate ("Cameo-style" tasks) ------------

    KNOWN_PAID_BACKEND_TRIGGERS = {
        "boltz_api": [
            "fold", "structure prediction", "docking", "adme", "screen",
            "molecule design", "small molecule", "protein design",
        ],
    }

    def evaluate_commission(
        self,
        task_description: str,
        task_type: str,  # "l_system" | "drug_design" | "molecular_structure" | other
        sequence_length: int | None = None,
        num_samples: int = 1,
        pricing_path: str | None = None,
    ) -> CommissionDecision:
        """Gate a customer-paid commission request before accepting payment.

        1. Run the request text through the SAME trust runtime watchlist
           used for UEFN calls — a commission asking for a trademarked
           character's likeness gets the same default-deny treatment.
        2. Flag if fulfilling it will call a metered paid backend, so
           pricing can account for real pass-through cost rather than
           quoting a flat fee and eating the loss.
        3. If the metered backend is Boltz and a sequence_length was given,
           attach a local, offline cost_estimate (see estimate_boltz_cost) —
           still requires a real rate_usd_per_gpu_second in
           boltz_pricing.json before it produces an actual dollar figure.
        """
        ip_decision = None
        if self.trust is not None:
            ip_decision = self.trust.evaluate(
                tool_name=f"commission:{task_type}",
                kwargs={"task_description": task_description},
            )
            if not ip_decision.allowed:
                result = CommissionDecision(
                    accepted=False,
                    reason=f"Blocked by IP compliance: {ip_decision.reason}",
                    ip_check=ip_decision,
                )
                self._log_commission(task_description, task_type, result)
                return result

        requires_paid_backend = False
        backend_used = None
        text_l = task_description.lower()
        for backend, triggers in self.KNOWN_PAID_BACKEND_TRIGGERS.items():
            if any(t in text_l for t in triggers):
                requires_paid_backend = True
                backend_used = backend
                break

        cost_estimate = None
        if requires_paid_backend and backend_used == "boltz_api" and sequence_length is not None:
            cost_estimate = estimate_boltz_cost(
                sequence_length=sequence_length,
                num_samples=num_samples,
                pricing_path=pricing_path,
            )

        note_parts = [
            f"; requires metered backend ({backend_used}) — price in pass-through cost"
            if requires_paid_backend else "; no metered backend detected"
        ]
        if cost_estimate is not None:
            if cost_estimate.estimated_cost_usd is not None:
                note_parts.append(f"; estimated cost ${cost_estimate.estimated_cost_usd} "
                                   f"(~{round(cost_estimate.estimated_seconds)}s compute)")
            else:
                note_parts.append(f"; {cost_estimate.note}")

        result = CommissionDecision(
            accepted=True,
            reason="Passed IP compliance check" + "".join(note_parts),
            ip_check=ip_decision,
            requires_paid_backend=requires_paid_backend,
            backend_used=backend_used,
            cost_estimate=cost_estimate,
        )
        self._log_commission(task_description, task_type, result)
        return result

    def _log_commission(self, task_description: str, task_type: str, result: CommissionDecision) -> None:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "task_type": task_type,
            "task_description_preview": task_description[:300],
            "accepted": result.accepted,
            "reason": result.reason,
            "requires_paid_backend": result.requires_paid_backend,
            "backend_used": result.backend_used,
            "estimated_cost_usd": result.cost_estimate.estimated_cost_usd if result.cost_estimate else None,
            "estimated_seconds": result.cost_estimate.estimated_seconds if result.cost_estimate else None,
        }
        with open(self.commission_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
