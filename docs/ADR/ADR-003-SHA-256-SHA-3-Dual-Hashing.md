# ADR-003: Why SHA-256 + SHA-3 Dual Hashing

**Date:** 2026-06-14  
**Status:** Accepted  
**Deciders:** VISTA 2.0 Architecture Team  
**Supersedes:** None

---

## Context

VISTA 2.0 produces forensic evidence packages that must be:
- **Tamper-evident:** Any modification to evidence must be detectable
- **Legally admissible:** Must meet SWGDE (Scientific Working Group on Digital Evidence) standards
- **Future-proof:** Evidence may be reviewed 10–20 years after collection
- **Cryptographically strong:** Resistant to known and anticipated attacks

The evidence chain uses hashing for integrity and HMAC for authenticity. The question is whether to use a single hash algorithm or dual hashing.

## Decision

**Use dual hashing: SHA-256 (NIST) + SHA-3 (Keccak) for all evidence records.**

## Rationale

### 1. Defense-in-Depth Against Algorithm Breakage

SHA-256 is currently considered secure, but:
- SHA-1 was deprecated in 2017 after theoretical attacks (SHAttered, 2017)
- MD5 was broken in 2004 (practical collision attacks)
- Quantum computing threatens all Merkle-Damgård hashes (Grover's algorithm halves security)

SHA-3 (Keccak) uses a fundamentally different construction (sponge) than SHA-256 (Merkle-Damgård). An attack on one construction is extremely unlikely to affect the other.

**If SHA-256 is broken:**
- SHA-3 still protects evidence integrity
- Evidence packages remain verifiable

**If SHA-3 is broken:**
- SHA-256 still protects evidence integrity
- Evidence packages remain verifiable

**If both are broken simultaneously:**
- This would require a catastrophic cryptographic breakthrough affecting two fundamentally different constructions
- Even then, HMAC (which uses the hash internally) provides additional protection

### 2. SWGDE Compliance

SWGDE "Best Practices for Digital & Multimedia Evidence" recommends:
- Multiple integrity checks for high-value evidence
- Documentation of algorithms used
- Regular algorithm review and upgrade capability

Dual hashing exceeds SWGDE minimum requirements and demonstrates due diligence.

### 3. Legal Admissibility Standard

In Daubert v. Merrell Dow (1993), the standard for expert testimony requires:
- Testability (hashing is deterministic and testable)
- Peer review (SHA-256 and SHA-3 are extensively peer-reviewed)
- Known error rate (collision resistance: 2^128 for SHA-256, 2^128 for SHA-3)
- General acceptance (both are NIST standards)

Dual hashing strengthens the "general acceptance" factor by demonstrating a conservative, multi-algorithm approach.

### 4. Computational Cost Is Negligible

| Algorithm | Throughput | Time for 1KB | Time for 1MB |
|-----------|-----------|-------------|-------------|
| SHA-256 | 400 MB/s | 2.5μs | 2.5ms |
| SHA-3-256 | 300 MB/s | 3.3μs | 3.3ms |
| HMAC-SHA256 | 350 MB/s | 2.9μs | 2.9ms |
| **Total** | — | **8.7μs** | **8.7ms** |

For a typical crash event (1 second of 4-channel 48kHz audio ≈ 384KB), dual hashing adds < 4ms. This is negligible compared to the 10ms detection latency budget.

### 5. Hash Length Compatibility

Both SHA-256 and SHA-3-256 produce 256-bit (32-byte) digests. This means:
- No storage overhead difference
- No serialization complexity
- Consistent evidence record format

### 6. Industry Best Practice

Dual hashing is used in:
- **Bitcoin:** SHA-256 + RIPEMD-160 (for address generation)
- **PGP/GPG:** SHA-256 + SHA-512 (for signature verification)
- **Certificate Transparency:** SHA-256 + SHA-3 (in proposed upgrades)
- **NIST Post-Quantum Crypto:** SHA-3 as primary hash

## Alternatives Considered

### SHA-256 Only
- **Pros:** Simpler, faster, widely supported
- **Cons:** Single point of failure, no defense-in-depth
- **Verdict:** Rejected — insufficient for forensic evidence

### SHA-3 Only
- **Pros:** Newer, sponge construction, quantum-resistant
- **Cons:** Less battle-tested than SHA-256, smaller ecosystem support
- **Verdict:** Rejected — SHA-256 has more peer review

### SHA-256 + SHA-512
- **Pros:** Same construction, different output sizes
- **Cons:** Same construction = same attack surface, no defense-in-depth
- **Verdict:** Rejected — different constructions are essential

### bcrypt/scrypt (key derivation)
- **Pros:** Memory-hard, resistant to hardware attacks
- **Cons:** Not designed for integrity checking, much slower
- **Verdict:** Rejected — wrong tool for the job

## Consequences

### Positive
- Evidence integrity protected against single-algorithm breakage
- SWGDE-compliant evidence packages
- Legally defensible cryptographic chain of custody
- Negligible performance overhead (< 4ms per event)
- Future-proof against quantum computing advances

### Negative
- Slightly more complex implementation (~50 extra lines)
- Two hash digests to store per evidence record (64 bytes vs 32 bytes)
- Verification requires computing both hashes

### Mitigations
- Implementation complexity is managed by `EvidenceChain` class
- 32 extra bytes per record is negligible (evidence records are kilobytes)
- `verify()` method computes both hashes automatically

## References

1. NIST FIPS 180-4 (2015). "Secure Hash Standard (SHS)." — SHA-256 specification.
2. NIST FIPS 202 (2015). "SHA-3 Standard." — SHA-3/Keccak specification.
3. SWGDE (2019). "Best Practices for Digital & Multimedia Evidence." v3.0.
4. Daubert v. Merrell Dow Pharmaceuticals, Inc., 509 U.S. 579 (1993).
5. Bertoni, G. et al. (2013). "Keccak: The new SHA-3 standard." — sponge construction analysis.
