# A-DMFE IEEE Conference Paper — Submission Notes

**Title:** Feasibility-First Unified Dispatch of Passenger, Food, and Parcel Requests with Adaptive Compatibility Learning
**Authors:** Sivasubramanian M (corresponding, sivamah25@gmail.com), Sadhana T, Rakshana S, S. R. Ramya
**Length:** 8 pages, IEEE conference two-column format

---

## 1. How to compile

The paper is written against the **official IEEEtran class**
(`\documentclass[conference]{IEEEtran}`), which Overleaf provides.

1. Create a blank Overleaf project, upload `main.tex`, `fig_compat.pdf`, `fig_efficiency.pdf`, `fig_co2.pdf`.
2. Set the compiler to **pdfLaTeX** and compile twice (cross-references need two passes).
3. Confirm it still lands on 8 pages.

The attached PDF was compiled offline with a close emulation of IEEEtran, since
the official class could not be downloaded in the build environment. Layout
metrics (margins, column width, font sizes, section styles) match the real
class, but **verify the page count in Overleaf before submitting** — if it
spills to 9 pages, the easiest cut is the subsection "Revisiting the Research
Gaps" in Section V, which is summarised again in the Conclusion.

No external `.bib` file is needed; the bibliography is inline.

---

## 2. What changed from your original draft

### Defects fixed

| Issue in original | Fix |
|---|---|
| References [2] and [9] were the same Zhang/Markos/Yu paper | Merged into one entry |
| References [4] and [11] were the same Chen et al. paper | Merged into one entry |
| References [3] and [5] had no venue, year, or DOI | [3] replaced with Pillac et al., *EJOR* 2013 (complete); [5] removed, its citations redirected to the complete Liu et al. entry |
| References [7]–[11] were never cited in the body | Every reference is now cited at least once |
| Section V-A reported 43 requests / 3 batches; V-C reported 2,320 trips and 611.3 L fuel | Both removed; replaced with the seeded 50/100/250/500 experiment |
| "69.8% completion rate" | Removed — your code counts trips with status `Assigned`, so it was a dispatch rate, not a completion rate |
| Average delay reported as a distinct finding from waiting time | `avg_delay_min` and `avg_waiting_min` are the identical expression in `evaluation/framework.py:527,550`. Reported once, correctly labelled **waiting time** |
| "XAI score 87%", "AI confidence 98.4%", "batch success rate 92.1%" — undefined | Removed |
| Claimed the compatibility distribution sits "between 70% and 95%" | It does not. Measured mean is 57 with SD 14; ~60% of pairs fall **below** τ=70. Corrected, and reframed as evidence the filter is selective |
| Table 2 printed before Table 1; Arabic numerals; captions inconsistent | Roman numerals, correct order, captions above tables and below figures |
| Orphan float page "8a" | Gone |
| Figure 1 unreadable | Redrawn as a vector TikZ diagram |
| Algorithms 1–3 and Table 4 (never exercised in the evaluation) | Cut; one consolidated Algorithm 1 retained |
| Notifications / dashboard / module-responsibility sections | Cut as product description rather than research |

### Evaluation replaced

The 43-request pilot is gone. The paper now reports the seeded experiment
already in `backend/evaluation/results/admfe_repetitions.json`: **36 runs**,
four pool sizes (50/100/250/500), 5 seeds each at N≤250 and 3 at N=500,
60-vehicle heterogeneous fleet.

This enables a **seed-matched paired ablation (n=18)** separating the
framework's contribution from the adaptive layer's — the kind of ablation
reviewers ask for. Every number in the paper was recomputed from that JSON and
independently re-verified against it.

---

## 3. Three things I made the paper admit

These will feel uncomfortable, but each one is a defect a reviewer would find
anyway, and volunteering it is far better than being caught:

**a) The learning rule never ran.** `timing.learning_calls = 0` in all 36
runs. No trip completes inside a single dispatch pass, so no outcome label was
ever produced and θ never moved from its initialisation. Equations (10)–(12)
are now presented as a *design* contribution that the architecture supports —
explicitly **not** validated by this evaluation. Claiming otherwise would have
been the single easiest thing for a reviewer to disprove from your own logs.

**b) The N=250 and N=500 results are not like-for-like.** At those pool sizes
the 60-vehicle fleet serves only ~110 requests while the baseline serves all
250/500. Since Algorithm 1 processes pairs in descending score order, the
served subset is the *most batchable* one. The headline claims therefore rest
on N=50 and N=100, where every arm serves the full pool. This is why the
headline figure is **37–40%**, not the 46% the saturated pools would suggest.

**c) The complexity bound is not achieved.** Pairs scored grew 489 → 1,817 →
11,049 → 44,095, a fit of N^1.96 — effectively quadratic. The geographic
candidate window never bound, so O(|R|·k) is an available optimisation, not an
achieved one. Stated plainly in Threats to Validity, and made the first item of
future work.

Each of these is framed as a bounded limitation with a clear path forward, which
is how strong papers handle weaknesses.

---

## 4. On the <5% similarity target

I cannot run Turnitin or iThenticate, so I cannot give you a number. What I can
tell you:

**The prose is entirely rewritten.** No sentence survives verbatim from your
original draft, and none is copied from any source. Technical phrasing was
varied deliberately.

**Check this before you submit.** If your original draft was ever uploaded
anywhere — a college portal, a previous submission, a project repository, a
supervisor's Turnitin check — it will self-match at a very high percentage
regardless of what I wrote. This is the single most common cause of a
surprise 40%+ score on an otherwise original paper. Ask whoever runs the check
to exclude your own prior submission from the comparison database, or use a
draft/no-repository submission mode.

**Set the checker up correctly.** Exclude the bibliography, exclude quoted
material, and exclude matches below 1%. Without these, reference lists and
standard phrases alone can push you past 5%.

**Expect residual matches on:** the reference list itself, standard equation
surroundings, and stock technical collocations ("vehicle routing problem",
"time-window overlap", "mixed-integer linear program"). These are unavoidable
and every reviewer knows it.

---

## 5. Honest assessment of acceptance odds

Nobody can guarantee acceptance, and be sceptical of anyone who says otherwise.
What I can say is what changed:

**Now working in your favour:** a real ablation with n=18 seed-matched pairs
and effect sizes; formal analysis (boundedness, Lipschitz bound, fail-closed
proposition) that most applied student papers lack; a reproducibility table with
every parameter; and honest reporting of costs and limitations, which reviewers
read as competence.

**Still working against you:** the evaluation is simulation-only with
geometric distances rather than road-network data; the fleet saturates at
higher loads; and the learning contribution is unvalidated. None of these is
fatal for a conference paper, and all three are disclosed.

**Biggest single improvement available if you have time:** re-run the
experiment with the fleet scaled to demand (e.g. 60/120/300/600 vehicles for
N=50/100/250/500). That removes the saturation caveat entirely and would let
you make the strong claim at all four pool sizes. Everything else is polish.

**Before submitting:** confirm the co-author email addresses are current, check
the target conference's page limit (some allow 6, not 8) and whether they
require anonymisation for review — if they do, the author block must be
stripped.
