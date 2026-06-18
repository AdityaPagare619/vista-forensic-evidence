# ADR-004: Why Dempster-Shafer over Bayesian Fusion

**Date:** 2026-06-14  
**Status:** Accepted  
**Deciders:** VISTA 2.0 Architecture Team  
**Supersedes:** None

---

## Context

VISTA 2.0 fuses evidence from multiple layers (IMU detection, audio classification, visual analysis) into a unified crash assessment. The fusion method must:
- Handle uncertainty from different sensor modalities
- Support "don't know" states (insufficient data from one modality)
- Be computationally efficient for real-time operation
- Produce interpretable confidence scores for forensic use

Two primary frameworks were evaluated:
1. **Bayesian (Bayes' Theorem):** P(crash | evidence) = P(evidence | crash) × P(crash) / P(evidence)
2. **Dempster-Shafer (DS):** Belief + Plausibility intervals for each hypothesis

## Decision

**Use Dempster-Shafer evidence theory for multi-layer fusion.**

## Rationale

### 1. Handling Ignorance ("Don't Know")

In VISTA 2.0, different modalities may have different information states:
- IMU layer: "Detected 50g crash pulse" (high confidence)
- Audio layer: "Microphone failed to initialize" (no data)
- Visual layer: "Image too blurry to classify" (low confidence)

**Bayesian:** Requires a prior P(crash) and likelihoods P(evidence | crash). When data is missing, you must either:
- Assign an arbitrary prior (injecting bias)
- Assume uniform distribution (treating "no data" as "50/50")
- Condition on available data only (ignoring the missing modality)

None of these are correct. "No data" is not the same as "equal probability."

**Dempster-Shafer:** Mass functions can assign mass to:
- {crash} — evidence for crash
- {no_crash} — evidence against crash
- {crash, no_crash} — **ignorance** (insufficient data)

The DS framework naturally represents "I don't know" without biasing the result.

### 2. Explicit Uncertainty Quantification

DS produces two bounds for each hypothesis:
- **Belief (Bel):** Lower bound — what the evidence directly supports
- **Plausibility (Pl):** Upper bound — what the evidence doesn't contradict
- **Uncertainty interval:** Pl - Bel — degree of ignorance

For forensic use, this is powerful:
- "Bel(crash) = 0.85, Pl(crash) = 0.95" → 85–95% confidence range
- "Bel(crash) = 0.30, Pl(crash) = 0.90" → high uncertainty, needs more evidence

Bayesian posterior P(crash) = 0.60 gives no indication of how much ignorance remains.

### 3. No Prior Probability Required

DS does not require a prior P(crash). The prior in Bayesian analysis is problematic:
- What is P(crash) for a random 1-second window? 0.001? 0.01? 0.1?
- The choice of prior significantly affects the posterior
- Different priors lead to different conclusions from the same evidence

DS constructs mass functions directly from evidence, avoiding the prior problem entirely.

### 4. Dempster's Rule of Combination

DS combines evidence from independent sources using Dempster's rule:

```
m₁₂(A) = Σ_{B∩C=A} m₁(B) × m₂(C) / (1 - K)

where K = Σ_{B∩C=∅} m₁(B) × m₂(C)  (conflict measure)
```

This naturally:
- **Amplifies agreement:** When IMU and audio both say "crash", combined belief increases
- **Suppresses conflict:** When IMU says "crash" but audio says "no crash", conflict K increases and the combination is conservative
- **Preserves ignorance:** When one modality has no data, its mass is distributed to {crash, no_crash} and the other modality dominates

### 5. Computational Efficiency

| Operation | Bayesian | Dempster-Shafer |
|-----------|----------|-----------------|
| Mass assignment | N/A (need likelihoods) | O(1) per hypothesis |
| Combination | O(n²) for n hypotheses | O(n²) for n hypotheses |
| Total for 3 layers | O(n²) | O(n²) |
| n (hypotheses) | 2 (crash/no_crash) | 2 (crash/no_crash) |

For 2 hypotheses, both are O(1). The computational cost is identical.

### 6. Forensic Interpretability

DS output is more interpretable for legal proceedings:
- **Belief:** "The evidence directly supports crash with X% confidence"
- **Plausibility:** "The evidence is consistent with crash up to Y% confidence"
- **Uncertainty:** "There is Z% of unexplained uncertainty"

This maps naturally to legal standards of proof:
- "Beyond reasonable doubt" → high Bel, low uncertainty
- "Preponderance of evidence" → Bel > 0.5
- "Probable cause" → Pl > 0.5

## Alternatives Considered

### Bayesian Fusion
- **Pros:** Well-established, principled, widely understood
- **Cons:** Requires priors, can't represent ignorance, sensitive to prior choice
- **Verdict:** Rejected — prior specification problem is unsuitable for forensic use

### Fuzzy Logic
- **Pros:** Handles linguistic uncertainty ("high", "medium", "low")
- **Cons:** Membership functions are subjective, no probabilistic interpretation
- **Verdict:** Rejected — not suitable for quantitative forensic evidence

### Simple Weighted Average
- **Pros:** Simplest, fastest
- **Cons:** No uncertainty quantification, can't handle missing data, no conflict detection
- **Verdict:** Rejected — insufficient for forensic-grade fusion

### Neural Network Fusion
- **Pros:** Can learn complex relationships
- **Cons:** No training data, opaque decisions, not forensically defensible
- **Verdict:** Rejected — black box is unacceptable for legal evidence

## Consequences

### Positive
- Natural representation of ignorance (no data ≠ 50/50)
- Explicit uncertainty intervals for forensic confidence
- No prior probability required
- Conflict detection between modalities
- Computationally equivalent to Bayesian for 2 hypotheses
- Legally interpretable output format

### Negative
- Less familiar to engineers than Bayesian methods
- Dempster's rule can produce counterintuitive results with high conflict
- Requires careful mass function assignment (domain expertise needed)

### Mitigations
- Document mass function assignment rules in code comments
- Implement conflict monitoring: if K > 0.5, flag for human review
- Provide both Bel and Pl in output for transparency
- Include DS tutorial in developer documentation

## References

1. Dempster, A.P. (1967). "Upper and lower probabilities induced by a multivalued mapping." Annals of Mathematical Statistics.
2. Shafer, G. (1976). "A Mathematical Theory of Evidence." Princeton University Press.
3. Sentz, K. & Ferson, S. (2002). "Combination of evidence in Dempster-Shafer theory." Sandia National Laboratories.
4. Kohlas, J. & Monney, P.A. (1995). "A mathematical theory of hints — an approach to the Dempster-Shafer theory of evidence." Springer.
5. Vania, M. & Granata, D. (2020). "Dempster-Shafer theory for sensor fusion in autonomous driving." IEEE Intelligent Vehicles Symposium.
