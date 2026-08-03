import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qfoldit.compliance.trust_runtime import TrustRuntime  # noqa: E402
from qfoldit.monetization.monetization_registry import MonetizationRegistry  # noqa: E402


def _fresh_registry():
    fd1, commission_log = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd1)
    fd2, audit_log = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd2)
    trust = TrustRuntime(manifest_path="qfoldit/compliance/license_manifest.json", engine_version="UE5", audit_log_path=audit_log)
    return MonetizationRegistry(
        channels_path="qfoldit/monetization/monetization_channels.json",
        commission_log_path=commission_log,
        trust=trust,
    )


def test_channels_load():
    r = _fresh_registry()
    assert "engagement_payout" in r.channels
    assert "off_platform_commission" in r.channels
    assert r.channels["in_island_transactions"].channel_type == "fortnite_native"


def test_plain_l_system_commission_accepted():
    r = _fresh_registry()
    d = r.evaluate_commission(
        "Generate a branching fern-like L-system fractal plant, custom axiom, 6 iterations",
        task_type="l_system",
    )
    assert d.accepted is True
    assert d.requires_paid_backend is False


def test_drug_design_commission_flags_paid_backend():
    r = _fresh_registry()
    d = r.evaluate_commission(
        "Run a small molecule design pass against this target protein and give me top ADME candidates",
        task_type="drug_design",
    )
    assert d.accepted is True
    assert d.requires_paid_backend is True
    assert d.backend_used == "boltz_api"


def test_commission_referencing_trademarked_character_blocked():
    """A customer asking for a molecular structure model 'shaped like
    Spider-Man' must hit the exact same watchlist/manifest gate as a
    UEFN tool call would — Marvel isn't a covered Game Collections brand."""
    r = _fresh_registry()
    d = r.evaluate_commission(
        "Model an atomic structure sculpture in the shape of Spider-Man",
        task_type="molecular_structure",
    )
    assert d.accepted is False
    assert d.ip_check is not None
    assert "spider-man" in d.ip_check.matched_terms


def test_commission_referencing_licensed_brand_still_gated_through_manifest():
    """If someone extends the watchlist with a brand that IS in the
    manifest (e.g. lego), commissions for it should pass, same as a
    UEFN call would."""
    r = _fresh_registry()
    d = r.evaluate_commission(
        "Model a LEGO-style molecular structure diorama for a display case",
        task_type="molecular_structure",
    )
    # "lego" is in the default watchlist AND has a real manifest entry
    assert d.accepted is True
    assert d.ip_check.manifest_entry == "lego"


def test_commission_ledger_is_logged():
    r = _fresh_registry()
    r.evaluate_commission("Fold this protein sequence and estimate binding affinity", task_type="drug_design")
    with open(r.commission_log_path) as f:
        lines = f.readlines()
    assert len(lines) == 1


def test_boltz_cost_estimate_none_when_rate_unconfigured():
    """boltz_pricing.json ships with rate_usd_per_gpu_second=null on purpose —
    a commission must get a time estimate but NOT a fabricated dollar figure."""
    r = _fresh_registry()
    d = r.evaluate_commission(
        "Fold this protein sequence and estimate binding affinity",
        task_type="drug_design",
        sequence_length=250,
    )
    assert d.requires_paid_backend is True
    assert d.backend_used == "boltz_api"
    assert d.cost_estimate is not None
    assert d.cost_estimate.estimated_seconds > 0
    assert d.cost_estimate.estimated_cost_usd is None


def test_boltz_cost_estimate_computes_when_rate_configured():
    """With a real rate filled in, the estimate produces an actual figure —
    scales with sequence_length via the local (non-network) rate table."""
    fd, pricing_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(pricing_path, "w") as f:
        import json
        json.dump({
            "gpu_type": "A10G",
            "rate_usd_per_gpu_second": 0.001,
            "baseline_seconds_per_100_residues": 45,
            "overhead_seconds": 20,
            "calibrated_from_real_runs": True,
        }, f)

    r = _fresh_registry()
    d = r.evaluate_commission(
        "Fold this protein sequence and estimate binding affinity",
        task_type="drug_design",
        sequence_length=200,
        pricing_path=pricing_path,
    )
    assert d.cost_estimate.estimated_cost_usd is not None
    assert d.cost_estimate.estimated_cost_usd > 0
    # Longer sequence -> more estimated compute seconds, all else equal.
    d_long = r.evaluate_commission(
        "Fold this protein sequence and estimate binding affinity",
        task_type="drug_design",
        sequence_length=800,
        pricing_path=pricing_path,
    )
    assert d_long.cost_estimate.estimated_seconds > d.cost_estimate.estimated_seconds


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _run_all()
