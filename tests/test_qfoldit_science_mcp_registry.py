import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qfoldit.science.mcp_registry import ScienceMCPRegistry  # noqa: E402


def _fresh():
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    return ScienceMCPRegistry(connection_log_path=path)


def test_verified_auto_connects():
    r = _fresh()
    ok, _ = r.can_connect("protein_design_mcp")
    assert ok is True


def test_connected_auto_connects():
    r = _fresh()
    ok, _ = r.can_connect("boltz_api")
    assert ok is True


def test_best_effort_blocked_by_default():
    r = _fresh()
    ok, reason = r.can_connect("uefn_mcp_server_kirchuvakov")
    assert ok is False
    assert "best_effort" in reason


def test_best_effort_allowed_with_explicit_flag():
    r = _fresh()
    ok, _ = r.can_connect("uefn_mcp_server_kirchuvakov", allow_best_effort=True)
    assert ok is True


def test_reference_only_never_connects_even_with_flag():
    r = _fresh()
    ok, _ = r.can_connect("unity_mcp_server", allow_best_effort=True)
    assert ok is False


def test_unregistered_server_blocked():
    r = _fresh()
    ok, reason = r.can_connect("some_random_mcp_nobody_registered")
    assert ok is False
    assert "not in science_mcp_registry.json" in reason


def test_connection_attempts_are_logged():
    r = _fresh()
    r.can_connect("protein_design_mcp")
    r.connect("boltz_api")
    r.connect("unity_mcp_server")
    with open(r.connection_log_path) as f:
        pass  # can_connect alone doesn't log; only connect() does — check that
    r2 = _fresh()
    r2.connect("boltz_api")
    r2.connect("unity_mcp_server")
    with open(r2.connection_log_path) as f:
        lines = f.readlines()
    assert len(lines) == 2


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
