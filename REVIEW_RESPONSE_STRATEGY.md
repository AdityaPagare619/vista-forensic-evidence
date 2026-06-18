# IJVSS REVIEW RESPONSE STRATEGY
## How We Will Handle Reviewers — Prepared Before We Receive Them

---

## 1. THE REALITY OF ACADEMIC PUBLICATION

### What Actually Happens After Submission

```
Submission → Editor Assignment (1-2 weeks) → Peer Review (3-5 weeks)
    ↓                                              ↓
Decision Letter ←──────────────────────────────────┘
    ↓
┌─── ACCEPT (rare, ~5% first round)
├─── MINOR REVISION → Resubmit (1-2 weeks) → Accept (~70%)
├─── MAJOR REVISION → Resubmit (4-8 weeks) → Accept (~50%)
└─── REJECT → Revise & resubmit elsewhere (~20%)
```

**The most likely outcome for any paper is MAJOR or MINOR REVISION, not acceptance or rejection.** This is normal. It means the reviewer sees potential but wants improvements.

### Key Insight from Research
"Most common outcome is a major or minor revision, the implication being that the journal editor and reviewers think your work is promising, but that it has certain imperfections that need to be addressed prior to publication." — Niklas Elmqvist, Professor, Aarhus University

**Translation:** If we get a revision, it means the reviewer is INTERESTED. They invested time to read our paper carefully. That's a good sign.

---

## 2. LIKELY IJVSS REVIEWER CONCERNS (Predicted)

Based on the paper content, IJVSS audience, and the research review experience, here are the MOST LIKELY concerns:

### Category A: "Must Fix" (If raised, revision is mandatory)

| # | Likely Concern | Our Response Strategy |
|---|---------------|----------------------|
| A1 | "No hardware-level validation — only algorithmic on CISS waveforms" | We explicitly state this as Stage-1 in the paper. Add: "This staged approach is standard in automotive sensor validation. Stage-2 hardware-in-loop is the defined next phase." Reference: SAE standards. |
| A2 | "False positive rate unknown — no real-world driving data" | Admit this openly. Add: "False-positive characterization under real driving conditions constitutes Stage-3 of the validation framework. The present work establishes the algorithmic upper-bound for detection accuracy." Frame as SCOPE, not weakness. |
| A3 | "MPU6050 ±16g range insufficient for frontal crashes" | We already address this: "saturation-aware lower-bound reporting" and "multi-modal corroboration framework provides independent channels." Add: "The detection framework is sensor-agnostic: upgrading to a higher-range device extends dynamic range without algorithmic changes." |
| A4 | "Self-verification is insufficient — needs TPM/HSM for real trust" | Acknowledge: "The cryptographic implementation uses standard-library functions for verifiability. Production deployment would require hardware security modules (TPM/HSM) for the trust anchor, which is addressed in the deployment framework documentation." |

### Category B: "Should Address" (Helps if fixed, doesn't kill paper)

| # | Likely Concern | Our Response Strategy |
|---|---------------|----------------------|
| B1 | "Why only 160 cases? Sample size seems small for the claims made" | Report exact binomial CI for detection rate: [90.5%, 97.7%]. Note that CISS 2024 is the standard validation corpus for crash reconstruction (Watson et al. use similar sizes). |
| B2 | "The paper doesn't cite any IJVSS crash papers except Smitha 2026" | Acknowledge and add 2-3 more IJVSS citations if relevant papers exist. The Smitha citation shows venue awareness. |
| B3 | "Multi-modal corroboration is described but not validated" | True — we describe the architecture but validation is Stage-3. Reframe as "design description" not "validation." |
| B4 | "The paper is too short for the scope of claims" | This is actually a strength — IJVSS papers are 3-5 pages. We're within range. |

### Category C: "Nice to Address" (Shows responsiveness)

| # | Likely Concern | Our Response Strategy |
|---|---------------|----------------------|
| C1 | "Add more comparison with existing commercial systems" | Add comparison with Octo Telematics, Zendrive, Arity in revision |
| C2 | "Discuss applicability to commercial vehicles (trucks, buses)" | Add one paragraph in Discussion noting the framework is sensor-agnostic and extendable |
| C3 | "Discuss temperature effects on MEMS" | Add brief paragraph on temperature compensation |
| C4 | "More references needed" | Add 3-5 more references to bring total to 25-30 |

---

## 3. RESPONSE LETTER TEMPLATE

### Structure (Following Best Practices)

```
================================================================
RESPONSE TO IJVSS REVIEWERS
Manuscript ID: [XXX]
Title: VISTA: Self-Verifying Crash Forensics on Consumer Embedded Hardware
================================================================

Dear Editor,

We thank you and the reviewers for the constructive evaluation of our 
manuscript. The feedback has been instrumental in strengthening the 
contribution. We address each comment point-by-point below.

SIGNIFICANT CHANGES IN THIS REVISION:
1. [List major changes with page/line references]
2. [List major changes with page/line references]
3. [List major changes with page/line references]

----------------------------------------------------------------------
REVIEWER 1
----------------------------------------------------------------------

Comment 1: [Reviewer's exact comment]
Response: [Our response, with reference to specific changes]
Changed in manuscript: [Location of change]

[Repeat for each comment]

----------------------------------------------------------------------
REVIEWER 2
----------------------------------------------------------------------

Comment 1: [Reviewer's exact comment]
Response: [Our response]
Changed in manuscript: [Location of change]

[Repeat for each comment]

----------------------------------------------------------------------
CONCLUSION

We believe the revisions have significantly strengthened the manuscript. 
We remain available for any additional clarification.

Sincerely,
[Authors]
================================================================
```

### Response Strategy per Comment Type

**If reviewer is RIGHT (we agree):**
"We thank the reviewer for this insightful observation. We have addressed this by [specific action taken in the revision]. The change appears in [section/page/line]."

**If reviewer is PARTIALLY RIGHT:**
"We appreciate this perspective. We have incorporated the reviewer's suggestion by [specific action] while maintaining our approach to [specific aspect]. The revised text now clarifies [what was clarified]."

**If reviewer is WRONG but we must respect:**
"We understand the reviewer's concern regarding [topic]. We would like to clarify that [explanation]. However, we have additionally [smaller change] to improve clarity on this point. The revised text now states [what was changed]."

**If reviewer asks for something out of scope:**
"We agree that [topic] is an important direction. However, [this is beyond the scope of the present study]. We have added a note in [section] acknowledging this as a direction for future work."

---

## 4. SPECIFIC RESPONSE DRAFTS (Pre-Built for Likely Comments)

### A1: "No hardware validation — only algorithmic"

> "We appreciate this important observation. The paper explicitly frames this as a Stage-1 algorithmic validation (see Table 2, Validation Stages), following the standard automotive sensor validation methodology in which algorithmic benchmarking precedes hardware-level characterisation~[reference]. The staged approach isolates algorithmic performance from hardware-specific error sources, providing the performance upper-bound against which subsequent hardware testing is measured. Stage-2 hardware-in-loop validation using instrumented crash sled testing is the defined next phase and constitutes an independent contribution to the validation framework. We have strengthened the manuscript to clarify this scope distinction in the Experimental Setup section."

### A2: "False positive rate unknown"

> "We acknowledge that false-positive characterization under real driving conditions is an essential validation component. This work establishes Stage-1 algorithmic validation on the CISS reference corpus; the false-positive rate under naturalistic driving constitutes Stage-3 of the validation framework (Table 2). The staged validation methodology ensures that algorithmic accuracy, hardware transfer error, and operational false-positive rates are independently characterized rather than conflated. We have added language clarifying that Stage-3 is the defined phase for false-positive characterization."

### A3: "MPU6050 range insufficient"

> "We agree that the ±16g range limits the reconstruction accuracy for high-severity frontal impacts. The paper addresses this in three ways: (1) saturation-aware lower-bound reporting ensures conservative rather than extrapolated estimates; (2) the multi-modal corroboration framework provides OBD-II speed profiling and acoustic detection as independent channels that supplement the inertial estimate when saturation occurs; (3) the detection framework is explicitly described as sensor-agnostic — upgrading to a higher-range device (e.g., ±200g) extends dynamic range without algorithmic changes. The side-impact accuracy of 10.35-11.52 km/h demonstrates that the system is effective within the sensor's characterized envelope."

### A4: "Self-verification insufficient"

> "We agree that the current implementation uses standard-library cryptographic functions for maximum verifiability. Production deployment would require a hardware trust anchor (TPM or HSM) for the cryptographic key chain. We have added a note in the Evidence Preservation section clarifying that the standard-library implementation serves the verification principle of ISO/IEC 27037 while production deployment would incorporate hardware security modules."

### B1: "Sample size 160 too small"

> "The 160-case validation uses the established CISS stratified sampling methodology [Watson et al., reference]. The exact binomial 95% CI for the 95.0% detection rate is [90.5%, 97.7%], confirming adequate statistical power for the claims made. The sample is balanced across four crash configurations (40 each), which is standard practice in crash reconstruction validation literature."

---

## 5. WHAT TO DO BEFORE REVIEWERS ARRIVE

### Immediate Actions (While Waiting)

1. **Prepare revised manuscript skeleton** — have the LaTeX template ready with "Track Changes" equivalent (maintain both versions)
2. **Pre-draft responses to predicted concerns** — use the drafts above as starting points
3. **Collect additional citations** — have 3-5 extra IJVSS-relevant references ready
4. **Prepare supplementary materials** — if VISTA 2.0 code/data can be shared, prepare a Zenodo/GitHub link
5. **Check IJVSS timeline** — they're bimonthly, so reviews should come within 4-8 weeks

### What NOT to Do

- ❌ Don't argue with reviewers about everything
- ❌ Don't provide excessive detail where a short response suffices
- ❌ Don't promise things you can't deliver (e.g., hardware testing within the revision window)
- ❌ Don't rewrite large sections unnecessarily — only address what's questioned
- ❌ Don't compare yourself to reviewers or question their expertise

### What to DO

- ✅ Thank every reviewer genuinely
- ✅ Quote each comment, then respond
- ✅ Make specific changes with line/section references
- ✅ Respectfully disagree where evidence supports it
- ✅ Acknowledge limitations honestly (they already exist in the paper)
- ✅ Add one strong paragraph per major revision point

---

## 6. IF REJECTED: RESUBMISSION STRATEGY

### Scenario: Desk Reject (Editor rejects without review)

**Likelihood:** Low (paper is within scope)
**Response:** Email editor politely, ask for clarification, prepare resubmission to alternative journal (SAE International Journal of Transportation Safety, or Safety Science)

### Scenario: Reviewer Reject (Reviewer says reject but editor may not)

**Likelihood:** Medium (one reviewer might not see value in consumer MEMS approach)
**Response:** Respond to ALL reviewers anyway. Show the editor that you're taking feedback seriously. The editor can overrule a single reviewer.

### Scenario: Major Revision

**Likelihood:** High (this is the most common outcome)
**Response:** This is the ideal scenario. We have VISTA 2.0 ready. Key revision actions:
1. Strengthen the multi-modal corroboration section (add validation details)
2. Add false-positive characterization discussion
3. Address MPU6050 range concern directly in the text
4. Add 3-5 more references (IJVSS-specific papers)
5. Revise the abstract to acknowledge scope boundaries more explicitly

### Scenario: Minor Revision

**Likelihood:** Low-Medium (if reviewer is positive)
**Response:** This means the reviewer likes the work. Quick fixes:
1. Formatting adjustments
2. Reference additions
3. Minor clarifications
4. Abstract tightening

---

## 7. THE GOLDEN RULES FROM EXPERT RESEARCHERS

From Niklas Elmqvist (Professor, Aarhus University):
1. **"Above all: make the changes"** — Don't go in with a rebuttal mindset
2. **"Be meek, not weak"** — Respect reviewers but don't give in to everything
3. **"Make the changes explicit"** — Highlight every revision in the response
4. **"Address each comment"** — Use line-by-line responses
5. **"Don't alienate reviewers"** — The unequal power dynamic means you lose if you fight

From the Politikon guide:
1. **Prioritize comments** — Critical issues first
2. **Address each comment** — Don't skip any
3. **Highlight changes** — Make it easy to see what changed
4. **Follow guidelines** — Adhere to IJVSS format requirements

---

## 8. OUR SPECIFIC RESPONSE STRATEGY

### For VISTA: The 3-Thing Rule

For every reviewer comment, we do exactly one of these three things:

**S1: Fix it** (best) — Make the change they asked for. Show exactly where in the manuscript.

**S2: Explain it** (acceptable) — If we disagree, provide evidence-based reasoning. Be respectful but firm. Reference standards or literature that support our position.

**S3: Scope it** (last resort) — If the comment is out of scope, acknowledge it and reframe as a future direction. Never ignore.

### Our Strengths as Authors

1. We have VISTA 2.0 codebase ready — can implement any requested changes quickly
2. We have extensive simulation and testing infrastructure — can generate supporting evidence
3. We have honest limitations already stated in the paper — no hidden weaknesses
4. We have the IJVSS sample paper style study — we know the venue
5. We have multiple expert perspectives already incorporated

### Our Weaknesses to Manage

1. No hardware validation — must frame as deliberate staging
2. No false positive rate — must frame as Stage-3
3. Consumer hardware only — must frame as cost-performance trade-off
4. Academic institution (not industry) — can be turned into strength (independent research)
5. First author is a student — can be strength (fresh perspective) or weakness (perceived inexperience)

---

*This strategy document is prepared BEFORE receiving reviewer comments. It provides pre-built responses, a clear framework for handling reviews, and an honest assessment of our vulnerabilities. When the actual review arrives, we adapt these templates to the specific comments while maintaining the core principle: "Above all, make the changes."*
