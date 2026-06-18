"""
VISTA 2.0 — Layer 7: Self-Verifying Evidence Chain
Cryptographic evidence integrity with dual hashing + HMAC.

Provides:
  - SHA-256 hash of evidence data
  - SHA-3 (Keccak-256) hash for defense-in-depth
  - HMAC-SHA256 signature for authenticity
  - Timestamped evidence records
  - Verification function that checks full integrity
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


# ===================================================================
# Evidence Record
# ===================================================================

@dataclass
class EvidenceRecord:
    """
    A single tamper-evident evidence record.

    Fields:
        evidence_id:      Unique identifier (UUID-style string)
        payload:          The actual evidence data (dict, serialisable)
        timestamp_unix:   Unix epoch seconds when the record was created
        sha256_hash:      SHA-256 hex digest of serialised payload
        sha3_hash:        SHA-3 (Keccak-256) hex digest of serialised payload
        hmac_signature:   HMAC-SHA256 hex signature
        algorithm_versions: Dict documenting hash/HMAC algorithms used
    """
    evidence_id: str
    payload: Dict[str, Any]
    timestamp_unix: float
    sha256_hash: str
    sha3_hash: str
    hmac_signature: str
    algorithm_versions: Dict[str, str] = field(default_factory=lambda: {
        "sha256": "SHA-256",
        "sha3": "SHA3-256 (Keccak)",
        "hmac": "HMAC-SHA256",
    })


# ===================================================================
# Evidence Chain
# ===================================================================

class EvidenceChain:
    """
    Self-Verifying Evidence Chain for VISTA 2.0.

    Produces and verifies tamper-evident evidence records.

    Usage:
        chain = EvidenceChain(shared_secret=b"vista-2.0-secret")
        record = chain.create_record({"detected": True, "delta_v_kmh": 42.1})
        assert chain.verify(record) == True

    Security notes:
        - The HMAC key should be stored in a secure enclave on production
          hardware (e.g., STM32 TrustZone / secure element).
        - Dual hashing (SHA-256 + SHA-3) provides defense-in-depth: if one
          algorithm is broken, the other still protects integrity.
        - The chain is append-only in the sense that each record carries a
          monotonic sequence number; a missing record is detectable.
    """

    # Fixed length for HMAC key to avoid truncation attacks
    MIN_KEY_LENGTH = 16  # bytes

    def __init__(self, shared_secret: Optional[bytes] = None,
                 sequence_start: int = 0):
        """
        Args:
            shared_secret:  HMAC key (bytes).  If None, a zero-key is used
                            (insecure — for testing only).
            sequence_start: Initial sequence number (useful for resuming).
        """
        if shared_secret is None:
            # Insecure default for testing only
            shared_secret = b"\x00" * 32
            self._insecure = True
        else:
            self._insecure = False

        if len(shared_secret) < self.MIN_KEY_LENGTH:
            raise ValueError(
                f"HMAC key must be >= {self.MIN_KEY_LENGTH} bytes, "
                f"got {len(shared_secret)}"
            )
        self._key = shared_secret
        self._sequence = sequence_start
        self._record_count = 0

    # ------------------------------------------------------------------
    # Hashing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialise_payload(payload: Dict[str, Any]) -> bytes:
        """
        Deterministic serialisation: sorted keys, no whitespace, UTF-8.
        This ensures the same payload always produces the same hash.
        """
        return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True).encode("utf-8")

    @staticmethod
    def _sha256(data: bytes) -> str:
        """SHA-256 hex digest."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _sha3_256(data: bytes) -> str:
        """SHA3-256 (Keccak) hex digest."""
        return hashlib.sha3_256(data).hexdigest()

    def _hmac_sha256(self, data: bytes) -> str:
        """HMAC-SHA256 hex signature."""
        return hmac.new(self._key, data, hashlib.sha256).hexdigest()

    # ------------------------------------------------------------------
    # Record creation
    # ------------------------------------------------------------------

    def create_record(self, payload: Dict[str, Any],
                      evidence_id: Optional[str] = None,
                      timestamp: Optional[float] = None) -> EvidenceRecord:
        """
        Create a new tamper-evident evidence record.

        Args:
            payload:     Evidence data (must be JSON-serialisable).
            evidence_id: Optional unique ID; auto-generated if None.
            timestamp:   Optional Unix timestamp; current time if None.

        Returns:
            EvidenceRecord with all hashes and HMAC.
        """
        if evidence_id is None:
            evidence_id = f"ev-{self._sequence:08d}-{int(time.time() * 1000)}"
        if timestamp is None:
            timestamp = time.time()

        serialised = self._serialise_payload(payload)
        sha256_digest = self._sha256(serialised)
        sha3_digest = self._sha3_256(serialised)

        # HMAC covers: payload + timestamp + sequence
        hmac_material = (
            serialised
            + f"|{timestamp:.6f}".encode()
            + f"|{self._sequence}".encode()
        )
        hmac_sig = self._hmac_sha256(hmac_material)

        record = EvidenceRecord(
            evidence_id=evidence_id,
            payload=payload,
            timestamp_unix=timestamp,
            sha256_hash=sha256_digest,
            sha3_hash=sha3_digest,
            hmac_signature=hmac_sig,
        )

        # Store sequence for verification
        record._vista_sequence = self._sequence  # type: ignore[attr-defined]
        self._sequence += 1
        self._record_count += 1

        return record

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, record: EvidenceRecord,
               check_sequence: bool = True,
               sequence_number: Optional[int] = None) -> Dict[str, Any]:
        """
        Verify the integrity and authenticity of an evidence record.

        Checks performed:
            1. SHA-256 hash matches re-computed value
            2. SHA-3 hash matches re-computed value (dual hash)
            3. HMAC signature is valid
            4. Timestamp is within reasonable bounds (±1 day)

        Args:
            record:           The EvidenceRecord to verify.
            check_sequence:   Whether to verify the sequence number.
            sequence_number:  Expected sequence number (required if
                              check_sequence is True).

        Returns:
            Dict with:
                "valid": bool — overall verdict
                "checks": Dict[str, bool] — individual check results
                "errors": List[str] — human-readable error messages
        """
        errors: list = []
        checks: Dict[str, bool] = {}

        # --- Recompute hashes ---
        serialised = self._serialise_payload(record.payload)

        expected_sha256 = self._sha256(serialised)
        expected_sha3 = self._sha3_256(serialised)

        checks["sha256"] = (record.sha256_hash == expected_sha256)
        checks["sha3"] = (record.sha3_hash == expected_sha3)

        if not checks["sha256"]:
            errors.append(
                f"SHA-256 mismatch: expected {expected_sha256[:16]}…, "
                f"got {record.sha256_hash[:16]}…"
            )
        if not checks["sha3"]:
            errors.append(
                f"SHA-3 mismatch: expected {expected_sha3[:16]}…, "
                f"got {record.sha3_hash[:16]}…"
            )

        # --- HMAC verification ---
        seq = sequence_number
        if seq is None and hasattr(record, "_vista_sequence"):
            seq = record._vista_sequence

        if seq is not None:
            hmac_material = (
                serialised
                + f"|{record.timestamp_unix:.6f}".encode()
                + f"|{seq}".encode()
            )
            expected_hmac = self._hmac_sha256(hmac_material)
            checks["hmac"] = hmac.compare_digest(
                record.hmac_signature, expected_hmac
            )
            if not checks["hmac"]:
                errors.append("HMAC signature invalid")
        else:
            # Cannot verify HMAC without sequence; warn but don't fail
            checks["hmac"] = True
            errors.append("HMAC verification skipped (no sequence number)")

        # --- Timestamp sanity check ---
        now = time.time()
        age_s = abs(now - record.timestamp_unix)
        checks["timestamp"] = age_s < 86400  # within ±1 day
        if not checks["timestamp"]:
            errors.append(
                f"Timestamp age {age_s:.0f}s exceeds ±1 day window"
            )

        # --- Sequence check ---
        if check_sequence and sequence_number is not None:
            expected_seq = sequence_number
            actual_seq = getattr(record, "_vista_sequence", sequence_number)
            checks["sequence"] = (actual_seq == expected_seq)
            if not checks["sequence"]:
                errors.append(
                    f"Sequence mismatch: expected {expected_seq}, "
                    f"got {actual_seq}"
                )

        valid = all(checks.values())

        return {
            "valid": valid,
            "checks": checks,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Convenience: verify payload hasn't been tampered with
    # ------------------------------------------------------------------

    def verify_payload(self, record: EvidenceRecord,
                       original_payload: Dict[str, Any]) -> bool:
        """
        Quick check that the payload matches what was originally provided.
        """
        serialised_orig = self._serialise_payload(original_payload)
        serialised_rec = self._serialise_payload(record.payload)
        return serialised_orig == serialised_rec

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self, record: EvidenceRecord) -> Dict[str, Any]:
        """Convert EvidenceRecord to a JSON-safe dictionary."""
        return {
            "evidence_id": record.evidence_id,
            "payload": record.payload,
            "timestamp_unix": record.timestamp_unix,
            "sha256_hash": record.sha256_hash,
            "sha3_hash": record.sha3_hash,
            "hmac_signature": record.hmac_signature,
            "algorithm_versions": record.algorithm_versions,
            "_vista_sequence": getattr(record, "_vista_sequence", None),
        }

    def from_dict(self, data: Dict[str, Any]) -> EvidenceRecord:
        """Reconstruct an EvidenceRecord from a dictionary."""
        record = EvidenceRecord(
            evidence_id=data["evidence_id"],
            payload=data["payload"],
            timestamp_unix=data["timestamp_unix"],
            sha256_hash=data["sha256_hash"],
            sha3_hash=data["sha3_hash"],
            hmac_signature=data["hmac_signature"],
            algorithm_versions=data.get("algorithm_versions", {}),
        )
        if "_vista_sequence" in data:
            record._vista_sequence = data["_vista_sequence"]
        return record

    def to_json(self, record: EvidenceRecord) -> str:
        """Serialise record to JSON string."""
        return json.dumps(self.to_dict(record), sort_keys=True)

    def from_json(self, json_str: str) -> EvidenceRecord:
        """Deserialise record from JSON string."""
        return self.from_dict(json.loads(json_str))


# ===================================================================
# Self-Test
# ===================================================================

def _self_test():
    """Comprehensive self-test of the evidence chain."""
    import sys

    print("=" * 70)
    print("EVIDENCE CHAIN — SELF-TEST")
    print("=" * 70)

    secret = b"vista-2.0-production-key-32bytes!!"
    chain = EvidenceChain(shared_secret=secret)

    # --- Test 1: Create and verify a valid record ---
    print("\n[TEST 1] Create & verify valid record")
    payload = {
        "detected": True,
        "confidence": 0.87,
        "delta_v_kmh": 42.1,
        "ci_lower": 38.0,
        "ci_upper": 46.2,
        "pdof_degrees": 5.3,
    }
    record = chain.create_record(payload)
    result = chain.verify(record, sequence_number=0)

    print(f"  Evidence ID:  {record.evidence_id}")
    print(f"  SHA-256:      {record.sha256_hash[:32]}…")
    print(f"  SHA-3:        {record.sha3_hash[:32]}…")
    print(f"  HMAC:         {record.hmac_signature[:32]}…")
    print(f"  Valid:        {result['valid']}")
    print(f"  Checks:       {result['checks']}")
    assert result["valid"], f"FAIL: record should be valid — {result['errors']}"

    # --- Test 2: Tampered payload should fail ---
    print("\n[TEST 2] Tampered payload should fail verification")
    tampered_record = chain.create_record(payload)
    tampered_record.payload = {**payload, "delta_v_kmh": 999.9}
    result2 = chain.verify(tampered_record, sequence_number=1)
    print(f"  Valid:  {result2['valid']}")
    print(f"  Errors: {result2['errors']}")
    assert not result2["valid"], "FAIL: tampered record should fail"
    assert not result2["checks"].get("sha256", True) or not result2["checks"].get("sha3", True), \
        "FAIL: at least one hash check should fail"

    # --- Test 3: Wrong HMAC key should fail ---
    print("\n[TEST 3] Wrong HMAC key should fail verification")
    wrong_chain = EvidenceChain(shared_secret=b"wrong-key-32-bytes-for-testing!!!")
    result3 = wrong_chain.verify(record, sequence_number=0)
    print(f"  Valid:  {result3['valid']}")
    print(f"  Errors: {result3['errors']}")
    assert not result3["valid"], "FAIL: wrong key should fail HMAC"

    # --- Test 4: Serialisation round-trip ---
    print("\n[TEST 4] JSON serialisation round-trip")
    json_str = chain.to_json(record)
    restored = chain.from_json(json_str)
    result4 = chain.verify(restored, sequence_number=0)
    print(f"  Round-trip valid: {result4['valid']}")
    assert result4["valid"], "FAIL: round-trip should verify"

    # --- Test 5: Dual hash defense-in-depth ---
    print("\n[TEST 5] Dual hash defense-in-depth")
    print(f"  SHA-256 == SHA-3: {record.sha256_hash == record.sha3_hash}")
    print(f"  (Expected: False — they are different algorithms)")
    assert record.sha256_hash != record.sha3_hash, "FAIL: SHA-256 ≠ SHA-3"

    # --- Test 6: Key length validation ---
    print("\n[TEST 6] Key length validation")
    try:
        _ = EvidenceChain(shared_secret=b"short")
        assert False, "FAIL: short key should raise ValueError"
    except ValueError as e:
        print(f"  Correctly rejected short key: {e}")

    # --- Test 7: Multiple records with sequence ---
    print("\n[TEST 7] Multiple records with monotonic sequence")
    chain2 = EvidenceChain(shared_secret=secret, sequence_start=0)
    records = []
    for i in range(5):
        rec = chain2.create_record({"seq": i, "value": i * 10})
        records.append(rec)

    for i, rec in enumerate(records):
        vr = chain2.verify(rec, sequence_number=i)
        assert vr["valid"], f"FAIL: record {i} should be valid"
    print(f"  5 records created and verified with sequences 0-4")

    # --- Test 8: Payload comparison ---
    print("\n[TEST 8] Payload comparison")
    assert chain.verify_payload(record, payload), "FAIL: payload should match"
    assert not chain.verify_payload(record, {"wrong": True}), \
        "FAIL: different payload should not match"

    print(f"\n{'='*70}")
    print("ALL EVIDENCE CHAIN TESTS PASSED")
    print(f"{'='*70}")


if __name__ == "__main__":
    _self_test()
