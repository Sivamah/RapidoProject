"""
ICCES-260 reviewer experiment — R1.3 Exact vs Greedy Pairing Baseline
====================================================================
Compares two strategies on the REQUEST-PAIRING SUB-PROBLEM ONLY:

    - Greedy     : the pairing strategy the current DMFE batch generator
                   uses (sort candidate pairs by compatibility score
                   descending, accept if disjoint — mirroring the disjoint
                   greedy selection in app/dmfe/batch_generator.py).
    - Exact      : a deterministic, *exact* maximum-weight matching over the
                   SAME feasible pair graph (implemented in the standard
                   library only — no networkx / scipy dependency).

Important scope (do not over-read):
    This experiment measures ONLY how the pairing step differs between a
    greedy and an exact selection over an identical set of feasible pairs.
    It does NOT claim, and cannot establish:
        - full joint vehicle-routing optimality,
        - globally optimal dispatch,
        - superiority over a full MILP,
        - superiority over the OR-Tools routing solver.
    Vehicles, drivers, routes and the full pipeline are OUT OF SCOPE here:
    we pair requests / requests by compatibility score alone.

Method
------
    * Build a deterministic pool of requests from a single demand cluster
      (so many feasible pairs exist).
    * For every unordered pair, compute the compatibility score with the
      CURRENT CompatibilityCalculator (app.dmfe.compatibility) — the same
      score DMFE uses.  No scoring logic is modified.
    * An edge is "feasible" when its compatibility score meets the current
      `min_compatibility_score` threshold read from SystemConfig.
    * Greedy matching: sort feasible edges by score desc; accept while both
      endpoints are still unmatched (this mirrors the existing greedy
      disjoint selection).
    * Exact matching: maximum-weight matching (subset DP over the pool).
    * Compare total score, number of matched pairs and unmatched nodes.

Workload-size limitation of the exact solver
    The exact solver is a subset-DP that is exponential in the pool size
    (O(2^N * N)).  It is therefore run on a deliberately small pool
    (POOL_SIZE <= 18) so it completes quickly.  Scaling it to a full
    workload hundreds of requests would be intractable; that is an inherent
    property of exact maximum-weight matching, not a bug in this harness,
    and is documented here and in the results metadata.
"""

from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))
sys.path.insert(0, str(EVAL_DIR.parent))  # backend root

from framework import (  # noqa: E402
    EXPERIMENTS_DIR,
    RESULTS_DIR,
    SYSTEM_CONFIG,
    ExperimentDB,
)

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import SimulationRequest  # noqa: E402
from app.dmfe.compatibility import (  # noqa: E402
    CompatibilityCalculator,
    read_float_value,
)

SEED = 1313
POOL_SIZE = 14           # exact solver budget (documented limitation)
MIN_SCORE_KEY = "min_compatibility_score"
DEFAULT_MIN = 70.0
OUT_FILE = os.path.join(RESULTS_DIR, "r13_exact_matching.json")


# ── solvers (both operate on the same edge list; request ids as nodes) ──────

def greedy_matching(nodes: List[int], edges: List[Tuple[int, int, float]]):
    """Greedy: sort feasible edges by score desc, take disjoint (mirrors the
    current DMFE batch generator's disjoint greedy selection)."""
    edges_sorted = sorted(edges, key=lambda e: e[2], reverse=True)
    used: Set[int] = set()
    pairs: List[Tuple[int, int, float]] = []
    for i, j, w in edges_sorted:
        if i in used or j in used:
            continue
        used.add(i)
        used.add(j)
        pairs.append((i, j, w))
    return pairs


def exact_max_weight_matching(nodes: List[int], edges: List[Tuple[int, int, float]]):
    """EXACT maximum-weight matching via subset DP (stdlib only).

    nodes: disjoint ids; edges: (i, j, weight) with i != j.
    Returns the max-total-weight set of disjoint pairs.

    Complexity O(2^N * N) in the pool size N.  This is why the pool must be
    kept small (see module docstring / results metadata).
    """
    N = len(nodes)
    idx = {n: k for k, n in enumerate(nodes)}
    w = [[0.0] * N for _ in range(N)]
    for i, j, wgt in edges:
        w[idx[i]][idx[j]] = wgt
        w[idx[j]][idx[i]] = wgt

    size = 1 << N
    # dp[mask]: max weight matching on the vertex indices set in `mask`.
    # choice[mask]: the partner index (0..N-1) of the LOWEST set bit in the
    # optimal solution for `mask`, or -1 if that vertex is left unmatched.
    dp = [0.0] * size
    choice = [-1] * size

    for mask in range(1, size):
        if mask & (mask - 1) == 0:
            dp[mask] = 0.0
            choice[mask] = -1
            continue
        low = (mask & -mask).bit_length() - 1          # lowest set index
        rest = mask & ~(1 << low)
        best = dp[rest]                                # leave `low` unmatched
        best_j = -1
        m = rest
        while m:
            b = (m & -m).bit_length() - 1
            cand = w[low][b] + dp[rest & ~(1 << b)]
            if cand > best:
                best = cand
                best_j = b
            m &= m - 1
        dp[mask] = best
        choice[mask] = best_j

    pairs: List[Tuple[int, int, float]] = []
    mask = size - 1
    while mask:
        low = (mask & -mask).bit_length() - 1
        j = choice[mask]
        if j >= 0 and (mask >> j) & 1:
            pairs.append((nodes[low], nodes[j], w[low][j]))
            mask &= ~(1 << low)
            mask &= ~(1 << j)
        else:
            mask &= ~(1 << low)

    return pairs


def main() -> None:
    exp = ExperimentDB()
    db = SessionLocal()
    try:
        exp.reset_schema()
        effective_config = dict(SYSTEM_CONFIG)
        rng = random.Random(SEED)
        exp.seed_system_config_with(db, effective_config)
        exp.seed_fleet(db, rng)
        from app.services.mock_adapters import generate_simulation_requests

        random.seed(SEED)
        # Single-cluster burst -> many feasible pairs among nearby requests.
        pool_all = generate_simulation_requests(
            count=POOL_SIZE, db=db,
            request_types={"ride": 0.5, "food": 0.3, "parcel": 0.2},
            same_cluster=True,
        )
        requests = pool_all[:POOL_SIZE]
        if len(requests) < POOL_SIZE:
            raise RuntimeError(
                f"Only {len(requests)} requests generated for pool of "
                f"{POOL_SIZE}; aborting (no fabricated rows).")

        nodes = [r.id for r in requests]
        calc = CompatibilityCalculator()
        threshold = read_float_value(db, MIN_SCORE_KEY, DEFAULT_MIN)

        edges: List[Tuple[int, int, float]] = []
        pair_scores: Dict[Tuple[int, int], float] = {}
        rejected_pairs = 0
        for a in range(len(requests)):
            for b in range(a + 1, len(requests)):
                try:
                    res = calc.compute([requests[a], requests[b]], db)
                except Exception as exc:  # noqa: BLE001 — surface + reroute loudly
                    raise RuntimeError(
                        f"CompatibilityCalculator failed on pair "
                        f"({requests[a].id},{requests[b].id}): {exc}") from exc
                score = float(res.compatibility_score)
                pair_scores[(nodes[a], nodes[b])] = score
                if score >= threshold:
                    edges.append((nodes[a], nodes[b], score))
                else:
                    rejected_pairs += 1

        greedy = greedy_matching(nodes, edges)
        exact = exact_max_weight_matching(nodes, edges)

        def summarize(pairs: List[Tuple[int, int, float]]) -> Dict[str, Any]:
            used = set()
            for i, j, _ in pairs:
                used.add(i)
                used.add(j)
            return {
                "matched_pairs": len(pairs),
                "matched_requests": len(used),
                "unmatched_requests": len(nodes) - len(used),
                "total_score": round(sum(w for _, _, w in pairs), 2),
                "avg_score": round(
                    (sum(w for _, _, w in pairs) / len(pairs)), 2) if pairs else 0.0,
                "pairs": [{"a": i, "b": j, "score": round(w, 2)}
                          for i, j, w in sorted(pairs, key=lambda p: (-p[2], p[0]))],
            }

        g_out = summarize(greedy)
        e_out = summarize(exact)

        # improvement = (exact - greedy) / max(greedy, eps) * 100
        denom = g_out["total_score"] if g_out["total_score"] else 1e-9
        rel_improvement_pct = round(
            (e_out["total_score"] - g_out["total_score"]) / denom * 100.0, 2)

        result = {
            "experiment": "R1.3 exact vs greedy request pairing",
            "reviewer_mapping": "R1.3",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "seed": SEED,
            "mode": SYSTEM_CONFIG.get("admfe.mode", "adaptive"),
            "parameters": {
                "pool_size": POOL_SIZE,
                "threshold": threshold,
                "min_compatibility_score_key": MIN_SCORE_KEY,
                "graph": "request-pair compatibility graph",
                "score_oracle": "CompatibilityCalculator.compute([a,b], db)",
                "exact_method": "subset-DP maximum-weight matching (stdlib only)",
                "greedy_method": "disjoint greedy on score-desc sorted pairs",
            },
            "graph_stats": {
                "nodes": len(nodes),
                "pairs_evaluated": len(pair_scores),
                "feasible_edges": len(edges),
                "rejected_by_threshold": rejected_pairs,
                "min_score_seen": round(min(pair_scores.values()), 2) if pair_scores else None,
                "max_score_seen": round(max(pair_scores.values()), 2) if pair_scores else None,
            },
            "greedy": g_out,
            "exact": e_out,
            "comparison": {
                "total_score_greedy": g_out["total_score"],
                "total_score_exact": e_out["total_score"],
                "delta_score": round(e_out["total_score"] - g_out["total_score"], 2),
                "relative_improvement_pct": rel_improvement_pct,
                "matched_pairs_greedy": g_out["matched_pairs"],
                "matched_pairs_exact": e_out["matched_pairs"],
                "unmatched_greedy": g_out["unmatched_requests"],
                "unmatched_exact": e_out["unmatched_requests"],
            },
            "scope": (
                "Pairing sub-problem ONLY. Uses the current CompatibilityCalculator "
                "score as the pair weight. Does NOT claim full routing / MILP / "
                "OR-Tools optimality; vehicles/drivers/routes are out of scope."),
            "workload_limitation": (
                f"The exact solver is a subset-DP, exponential in pool size "
                f"(O(2^N*N)); it was run on a small deterministic pool of "
                f"{POOL_SIZE} requests so it completes quickly. It does not "
                f"scale to full workloads by design."),
            "limitations": (
                "Comparisons reflect the pairing step only; synthetic requests; "
                "not a human or field study."),
        }

        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)

        print("\n=== R1.3 Exact vs Greedy Pairing ===")
        print(f"seed={SEED} pool={POOL_SIZE} threshold={threshold}")
        print(f"  feasible edges: {len(edges)} / {len(pair_scores)} pairs evaluated")
        print(f"  GREEDY: pairs={g_out['matched_pairs']} "
              f"score={g_out['total_score']} unmatched={g_out['unmatched_requests']}")
        print(f"  EXACT : pairs={e_out['matched_pairs']} "
              f"score={e_out['total_score']} unmatched={e_out['unmatched_requests']}")
        print(f"  delta total score = {result['comparison']['delta_score']} "
              f"({rel_improvement_pct:+.2f}%)")
        print(f"  wrote {OUT_FILE}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
