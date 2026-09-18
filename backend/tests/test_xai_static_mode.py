"""
Regression: XAI explanations must work in STATIC DMFE mode.

`admfe.mode = static` is the Phase 9 fixed-weight baseline used for
DMFE-vs-A-DMFE research comparison.  On that path
`CompatibilityResult.decision_confidence` is None, and `confidence` used to be
bound only inside the `result is None` branch of
`_generate_explanation_for_request` — so every explanation raised
UnboundLocalError and `/api/xai/explanations` returned 500 for the entire
baseline configuration.

No engine, scoring or decision logic is exercised here beyond what the
explanation builder already calls.
"""

from __future__ import annotations

from app.dmfe.compatibility import CompatibilityCalculator
from app.services.xai_service import _generate_explanation_for_request


def _explain(db, req, mode):
    return _generate_explanation_for_request(
        db, CompatibilityCalculator(), req, "Test Provider", 60.0,
        {"mode": mode}, None,
    )


def test_static_mode_explanation_has_confidence(db, make_request):
    """Static mode must produce an explanation, not UnboundLocalError."""
    r1 = make_request(
        request_type="ride",
        pickup_lat=11.0168, pickup_lng=76.9558,
        drop_lat=11.0200, drop_lng=76.9700,
    )
    make_request(
        request_type="ride",
        pickup_lat=11.0170, pickup_lng=76.9560,
        drop_lat=11.0210, drop_lng=76.9710,
    )

    exp = _explain(db, r1, "static")

    assert exp.confidence_score is not None
    assert 0.0 <= exp.confidence_score <= 100.0
    assert exp.decision
    assert exp.factors is not None


def test_no_partner_still_has_confidence(db, make_request):
    """The lone-request path (no comparable partner) stays intact."""
    req = make_request(
        request_type="parcel",
        pickup_lat=11.0300, pickup_lng=76.9600,
        drop_lat=11.0400, drop_lng=76.9900,
    )

    exp = _explain(db, req, "static")

    assert exp.decision == "Standalone Direct Routing"
    assert 0.0 <= exp.confidence_score <= 100.0
