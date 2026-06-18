"""
VISTA 2.0 — Deployment & Fleet Architecture Test Suite (Layer 8)

Comprehensive tests covering:
  1. Device registration with TPM-like identity
  2. Telemetry collection and aggregation
  3. OTA update simulation
  4. Evidence chain from device to cloud
  5. Fleet health monitoring

Run: python -m pytest test_deployment.py -v
"""

import hashlib
import time

import numpy as np
import pytest

from vista_hil.deployment import (
    AlertSeverity,
    DeviceIdentity,
    DeviceRegistry,
    DeviceStatus,
    FleetAlert,
    FleetEvidenceChain,
    FleetEvidenceRecord,
    FleetHealthMonitor,
    FleetManager,
    HealthStatus,
    OTAPackage,
    OTAPackageStatus,
    OTAUpdateManager,
    OTAUpdateRecord,
    TelemetryAggregate,
    TelemetryCollector,
    TelemetryEntry,
    TelemetryType,
    generate_tpm_identity,
    MIN_TPM_KEY_LENGTH,
)


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def registry():
    """Fresh device registry."""
    return DeviceRegistry()


@pytest.fixture
def telemetry():
    """Fresh telemetry collector."""
    return TelemetryCollector(aggregation_window_s=60.0)


@pytest.fixture
def ota():
    """Fresh OTA update manager."""
    return OTAUpdateManager()


@pytest.fixture
def evidence_chain():
    """Fresh evidence chain."""
    return FleetEvidenceChain(b"test-fleet-secret-32-bytes-ok!!!")


@pytest.fixture
def health_monitor():
    """Fresh health monitor with short timeout for testing."""
    return FleetHealthMonitor(heartbeat_timeout_s=5.0)


@pytest.fixture
def fleet_manager():
    """Fresh fleet manager."""
    return FleetManager(b"test-fleet-secret-32-bytes-ok!!!")


@pytest.fixture
def sample_device():
    """A sample device identity."""
    return generate_tpm_identity("sample-hardware-seed-001")


# ===================================================================
# TPM Identity Tests
# ===================================================================

class TestTPMIdentity:

    def test_generate_deterministic(self):
        """Same seed should produce same identity."""
        id1 = generate_tpm_identity("test-seed")
        id2 = generate_tpm_identity("test-seed")
        assert id1.device_id == id2.device_id
        assert id1.tpm_pubkey == id2.tpm_pubkey

    def test_different_seeds_different_ids(self):
        """Different seeds should produce different identities."""
        id1 = generate_tpm_identity("seed-alpha")
        id2 = generate_tpm_identity("seed-beta")
        assert id1.device_id != id2.device_id

    def test_device_id_format(self):
        identity = generate_tpm_identity("test")
        assert identity.device_id.startswith("VISTA-")

    def test_tpm_pubkey_format(self):
        identity = generate_tpm_identity("test")
        assert identity.tpm_pubkey.startswith("tpm-pub-")

    def test_tpm_cert_format(self):
        identity = generate_tpm_identity("test")
        assert identity.tpm_cert.startswith("tpm-cert-")

    def test_hardware_serial_unique(self):
        id1 = generate_tpm_identity("seed-1")
        id2 = generate_tpm_identity("seed-2")
        assert id1.hardware_serial != id2.hardware_serial

    def test_registration_time_set(self):
        identity = generate_tpm_identity("test")
        assert identity.registration_time > 0

    def test_to_dict(self):
        identity = generate_tpm_identity("test")
        d = identity.to_dict()
        assert "device_id" in d
        assert "tpm_pubkey" in d
        assert "tpm_cert" in d
        assert "status" in d


# ===================================================================
# Device Registry Tests
# ===================================================================

class TestDeviceRegistry:

    def test_register_device(self, registry):
        identity = registry.register_device("hw-seed-001")
        assert identity.device_id.startswith("VISTA-")
        assert registry.device_count == 1

    def test_register_multiple_devices(self, registry):
        registry.register_device("hw-001")
        registry.register_device("hw-002")
        assert registry.device_count == 2

    def test_duplicate_registration_rejected(self, registry):
        registry.register_device("hw-seed")
        with pytest.raises(ValueError, match="already registered"):
            registry.register_device("hw-seed")

    def test_get_device(self, registry):
        identity = registry.register_device("hw-001")
        retrieved = registry.get_device(identity.device_id)
        assert retrieved is not None
        assert retrieved.device_id == identity.device_id

    def test_get_nonexistent_device(self, registry):
        assert registry.get_device("nonexistent") is None

    def test_verify_identity_valid(self, registry):
        identity = registry.register_device("hw-001")
        assert registry.verify_identity(identity.device_id, identity.tpm_pubkey)

    def test_verify_identity_wrong_key(self, registry):
        identity = registry.register_device("hw-001")
        assert not registry.verify_identity(identity.device_id, "wrong-key")

    def test_verify_identity_nonexistent_device(self, registry):
        assert not registry.verify_identity("nonexistent", "key")

    def test_update_status(self, registry):
        identity = registry.register_device("hw-001")
        result = registry.update_status(identity.device_id, DeviceStatus.MAINTENANCE)
        assert result
        device = registry.get_device(identity.device_id)
        assert device.status == DeviceStatus.MAINTENANCE

    def test_update_status_nonexistent(self, registry):
        result = registry.update_status("nonexistent", DeviceStatus.ONLINE)
        assert not result

    def test_update_firmware(self, registry):
        identity = registry.register_device("hw-001")
        result = registry.update_firmware(identity.device_id, "2.1.0")
        assert result
        device = registry.get_device(identity.device_id)
        assert device.firmware_version == "2.1.0"

    def test_heartbeat(self, registry):
        identity = registry.register_device("hw-001")
        registry.update_status(identity.device_id, DeviceStatus.OFFLINE)

        result = registry.heartbeat(identity.device_id)
        assert result
        device = registry.get_device(identity.device_id)
        assert device.status == DeviceStatus.ONLINE

    def test_heartbeat_nonexistent(self, registry):
        assert not registry.heartbeat("nonexistent")

    def test_stale_devices(self, registry):
        identity = registry.register_device("hw-001")
        # Force old timestamp
        device = registry.get_device(identity.device_id)
        device.last_seen = time.time() - 600

        stale = registry.get_stale_devices(timeout_s=300)
        assert len(stale) == 1
        assert stale[0].device_id == identity.device_id

    def test_list_devices_all(self, registry):
        registry.register_device("hw-001")
        registry.register_device("hw-002")
        devices = registry.list_devices()
        assert len(devices) == 2

    def test_list_devices_by_status(self, registry):
        d1 = registry.register_device("hw-001")
        registry.register_device("hw-002")
        registry.update_status(d1.device_id, DeviceStatus.MAINTENANCE)

        online = registry.list_devices(DeviceStatus.ONLINE)
        maintenance = registry.list_devices(DeviceStatus.MAINTENANCE)
        assert len(online) == 1
        assert len(maintenance) == 1

    def test_online_count(self, registry):
        registry.register_device("hw-001")
        registry.register_device("hw-002")
        assert registry.online_count == 2

    def test_to_dict(self, registry):
        registry.register_device("hw-001")
        d = registry.to_dict()
        assert d["device_count"] == 1
        assert d["online_count"] == 1


# ===================================================================
# Telemetry Collector Tests
# ===================================================================

class TestTelemetryCollector:

    def test_ingest_single(self, telemetry):
        entry = telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, 45.0)
        assert entry.device_id == "dev-01"
        assert entry.value == 45.0
        assert entry.sequence == 0

    def test_ingest_multiple(self, telemetry):
        for i in range(5):
            telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, 10.0 + i)
        entries = telemetry.get_entries("dev-01", TelemetryType.ACCEL_PEAK_G)
        assert len(entries) == 5

    def test_sequence_auto_increment(self, telemetry):
        e1 = telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, 10.0)
        e2 = telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, 20.0)
        e3 = telemetry.ingest("dev-01", TelemetryType.BATTERY_PCT, 80.0)
        e4 = telemetry.ingest("dev-01", TelemetryType.BATTERY_PCT, 75.0)

        assert e1.sequence == 0
        assert e2.sequence == 1
        assert e3.sequence == 0  # Different type, separate counter
        assert e4.sequence == 1

    def test_get_entries_filter_by_type(self, telemetry):
        telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, 10.0)
        telemetry.ingest("dev-01", TelemetryType.BATTERY_PCT, 80.0)
        telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, 20.0)

        accel_entries = telemetry.get_entries("dev-01", TelemetryType.ACCEL_PEAK_G)
        assert len(accel_entries) == 2

    def test_get_entries_filter_by_time(self, telemetry):
        now = time.time()
        telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, 10.0,
                         timestamp_s=now - 100)
        telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, 20.0,
                         timestamp_s=now)

        recent = telemetry.get_entries("dev-01", TelemetryType.ACCEL_PEAK_G,
                                        since_s=now - 50)
        assert len(recent) == 1
        assert recent[0].value == 20.0

    def test_aggregate(self, telemetry):
        now = time.time()
        for i in range(10):
            telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G,
                             10.0 + i * 5, timestamp_s=now - (10 - i))

        agg = telemetry.aggregate("dev-01", TelemetryType.ACCEL_PEAK_G)
        assert agg is not None
        assert agg.count == 10
        assert agg.min_value == 10.0
        assert agg.max_value == 55.0
        assert abs(agg.mean_value - 32.5) < 0.01

    def test_aggregate_no_data(self, telemetry):
        agg = telemetry.aggregate("nonexistent", TelemetryType.ACCEL_PEAK_G)
        assert agg is None

    def test_get_latest_telemetry(self, telemetry):
        telemetry.ingest("dev-01", TelemetryType.BATTERY_PCT, 100.0)
        telemetry.ingest("dev-01", TelemetryType.BATTERY_PCT, 80.0)
        telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, 25.0)

        latest = telemetry.get_latest_telemetry("dev-01")
        assert TelemetryType.BATTERY_PCT in latest
        assert latest[TelemetryType.BATTERY_PCT].value == 80.0
        assert latest[TelemetryType.ACCEL_PEAK_G].value == 25.0

    def test_get_all_device_ids(self, telemetry):
        telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, 10.0)
        telemetry.ingest("dev-02", TelemetryType.ACCEL_PEAK_G, 20.0)

        ids = telemetry.get_all_device_ids()
        assert ids == {"dev-01", "dev-02"}

    def test_get_total_entries(self, telemetry):
        telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, 10.0)
        telemetry.ingest("dev-01", TelemetryType.BATTERY_PCT, 80.0)
        telemetry.ingest("dev-02", TelemetryType.ACCEL_PEAK_G, 20.0)

        assert telemetry.get_total_entries() == 3

    def test_to_dict(self, telemetry):
        telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, 10.0)
        d = telemetry.to_dict()
        assert d["total_entries"] == 1
        assert d["device_count"] == 1


# ===================================================================
# OTA Update Manager Tests
# ===================================================================

class TestOTAUpdateManager:

    def test_create_package(self, ota):
        fw_data = b"firmware-binary-data" * 100
        pkg = ota.create_package("2.1.0", "Bug fixes", fw_data)
        assert pkg.version == "2.1.0"
        assert pkg.size_bytes == len(fw_data)
        assert len(pkg.checksum_sha256) == 64

    def test_create_multiple_packages(self, ota):
        ota.create_package("2.1.0", "Update 1", b"data1")
        ota.create_package("2.2.0", "Update 2", b"data2")
        pkg = ota.create_package("2.3.0", "Update 3", b"data3")
        assert pkg.version == "2.3.0"

    def test_schedule_update(self, ota):
        pkg = ota.create_package("2.1.0", "Update", b"fw-data")
        result = ota.schedule_update("dev-01", pkg.package_id)
        assert result
        assert "dev-01" in ota.get_pending_updates()

    def test_schedule_update_nonexistent_package(self, ota):
        result = ota.schedule_update("dev-01", "nonexistent-package")
        assert not result

    def test_simulate_update_success(self, ota):
        pkg = ota.create_package("2.1.0", "Update", b"fw-data")
        ota.schedule_update("dev-01", pkg.package_id)

        record = ota.simulate_update("dev-01", success=True,
                                      from_version="2.0.0", to_version="2.1.0")
        assert record.status == OTAPackageStatus.COMPLETE
        assert record.completed_at is not None
        assert record.from_version == "2.0.0"
        assert record.to_version == "2.1.0"

    def test_simulate_update_failure(self, ota):
        pkg = ota.create_package("2.1.0", "Update", b"fw-data")
        ota.schedule_update("dev-01", pkg.package_id)

        record = ota.simulate_update("dev-01", success=False)
        assert record.status == OTAPackageStatus.FAILED
        assert record.error_message is not None

    def test_simulate_update_clears_pending(self, ota):
        pkg = ota.create_package("2.1.0", "Update", b"fw-data")
        ota.schedule_update("dev-01", pkg.package_id)
        assert "dev-01" in ota.get_pending_updates()

        ota.simulate_update("dev-01", success=True)
        assert "dev-01" not in ota.get_pending_updates()

    def test_get_update_history(self, ota):
        pkg = ota.create_package("2.1.0", "Update", b"fw-data")
        ota.schedule_update("dev-01", pkg.package_id)
        ota.simulate_update("dev-01", success=True)

        history = ota.get_update_history("dev-01")
        assert len(history) == 1
        assert history[0].status == OTAPackageStatus.COMPLETE

    def test_verify_package_valid(self, ota):
        fw_data = b"firmware-binary-data"
        pkg = ota.create_package("2.1.0", "Update", fw_data)
        assert ota.verify_package(pkg.package_id, fw_data)

    def test_verify_package_tampered(self, ota):
        fw_data = b"firmware-binary-data"
        pkg = ota.create_package("2.1.0", "Update", fw_data)
        assert not ota.verify_package(pkg.package_id, b"tampered-data")

    def test_verify_package_nonexistent(self, ota):
        assert not ota.verify_package("nonexistent", b"data")

    def test_to_dict(self, ota):
        ota.create_package("2.1.0", "Update", b"data")
        d = ota.to_dict()
        assert d["package_count"] == 1


# ===================================================================
# Fleet Evidence Chain Tests
# ===================================================================

class TestFleetEvidenceChain:

    def test_append_record(self, evidence_chain):
        record = evidence_chain.append_record(
            "dev-01", "heartbeat", {"v": 1}
        )
        assert record.device_id == "dev-01"
        assert record.event_type == "heartbeat"
        assert record.sequence == 0

    def test_chain_growth(self, evidence_chain):
        evidence_chain.append_record("dev-01", "heartbeat", {})
        evidence_chain.append_record("dev-01", "crash", {"v": 1})
        evidence_chain.append_record("dev-01", "heartbeat", {})

        chain = evidence_chain.get_chain("dev-01")
        assert len(chain) == 3

    def test_sequence_monotonic(self, evidence_chain):
        for i in range(5):
            record = evidence_chain.append_record("dev-01", "heartbeat", {"i": i})
            assert record.sequence == i

    def test_previous_hash_links(self, evidence_chain):
        r1 = evidence_chain.append_record("dev-01", "heartbeat", {})
        r2 = evidence_chain.append_record("dev-01", "heartbeat", {})
        r3 = evidence_chain.append_record("dev-01", "heartbeat", {})

        assert r1.previous_hash == "0" * 64  # Genesis
        assert r2.previous_hash == r1.sha256_hash
        assert r3.previous_hash == r2.sha256_hash

    def test_verify_valid_chain(self, evidence_chain):
        evidence_chain.append_record("dev-01", "heartbeat", {})
        evidence_chain.append_record("dev-01", "crash", {"v": 1})
        evidence_chain.append_record("dev-01", "heartbeat", {})

        result = evidence_chain.verify_chain("dev-01")
        assert result["valid"]
        assert result["record_count"] == 3
        assert len(result["errors"]) == 0

    def test_verify_empty_chain(self, evidence_chain):
        result = evidence_chain.verify_chain("nonexistent")
        assert result["valid"]
        assert result["record_count"] == 0

    def test_verify_tampered_payload(self, evidence_chain):
        evidence_chain.append_record("dev-01", "heartbeat", {"v": 1})
        evidence_chain.append_record("dev-01", "heartbeat", {"v": 2})

        # Tamper
        records = evidence_chain.get_chain("dev-01")
        records[0].payload = {"v": 999}

        result = evidence_chain.verify_chain("dev-01")
        assert not result["valid"]

    def test_verify_broken_chain(self, evidence_chain):
        evidence_chain.append_record("dev-01", "heartbeat", {})
        evidence_chain.append_record("dev-01", "heartbeat", {})

        # Tamper with chain link
        records = evidence_chain.get_chain("dev-01")
        records[1].previous_hash = "fake-hash"

        result = evidence_chain.verify_chain("dev-01")
        assert not result["valid"]

    def test_verify_wrong_sequence(self, evidence_chain):
        evidence_chain.append_record("dev-01", "heartbeat", {})
        evidence_chain.append_record("dev-01", "heartbeat", {})

        records = evidence_chain.get_chain("dev-01")
        records[1].sequence = 999  # Wrong sequence

        result = evidence_chain.verify_chain("dev-01")
        assert not result["valid"]

    def test_separate_device_chains(self, evidence_chain):
        evidence_chain.append_record("dev-01", "heartbeat", {})
        evidence_chain.append_record("dev-02", "heartbeat", {})

        chain1 = evidence_chain.get_chain("dev-01")
        chain2 = evidence_chain.get_chain("dev-02")
        assert len(chain1) == 1
        assert len(chain2) == 1

    def test_get_device_ids(self, evidence_chain):
        evidence_chain.append_record("dev-01", "heartbeat", {})
        evidence_chain.append_record("dev-02", "heartbeat", {})
        evidence_chain.append_record("dev-03", "heartbeat", {})

        ids = evidence_chain.get_device_ids()
        assert ids == {"dev-01", "dev-02", "dev-03"}

    def test_get_total_records(self, evidence_chain):
        evidence_chain.append_record("dev-01", "heartbeat", {})
        evidence_chain.append_record("dev-01", "crash", {})
        evidence_chain.append_record("dev-02", "heartbeat", {})

        assert evidence_chain.get_total_records() == 3

    def test_dual_hash_different(self, evidence_chain):
        record = evidence_chain.append_record("dev-01", "heartbeat", {})
        assert record.sha256_hash != record.sha3_hash

    def test_to_dict(self, evidence_chain):
        evidence_chain.append_record("dev-01", "heartbeat", {})
        record = evidence_chain.get_chain("dev-01")[0]
        d = record.to_dict()
        assert "record_id" in d
        assert "sha256_hash" in d

    def test_secret_too_short(self):
        with pytest.raises(ValueError, match="Secret must be"):
            FleetEvidenceChain(b"short")


# ===================================================================
# Fleet Health Monitor Tests
# ===================================================================

class TestFleetHealthMonitor:

    def test_check_heartbeat_stale(self, health_monitor):
        device = DeviceIdentity(
            device_id="stale-dev", tpm_pubkey="", tpm_cert="",
            hardware_serial="STALE",
            last_seen=time.time() - 100,
        )
        alert = health_monitor.check_heartbeat(device)
        assert alert is not None
        assert alert.severity == AlertSeverity.WARNING

    def test_check_heartbeat_ok(self, health_monitor):
        device = DeviceIdentity(
            device_id="ok-dev", tpm_pubkey="", tpm_cert="",
            hardware_serial="OK",
            last_seen=time.time(),
        )
        alert = health_monitor.check_heartbeat(device)
        assert alert is None

    def test_check_battery_low(self, health_monitor):
        alert = health_monitor.check_battery("dev-01", 8.5)
        assert alert is not None
        assert alert.severity == AlertSeverity.CRITICAL
        assert "8.5" in alert.message

    def test_check_battery_warning(self, health_monitor):
        alert = health_monitor.check_battery("dev-01", 15.0)
        assert alert is not None
        assert alert.severity == AlertSeverity.WARNING

    def test_check_battery_ok(self, health_monitor):
        alert = health_monitor.check_battery("dev-01", 80.0)
        assert alert is None

    def test_check_storage_low(self, health_monitor):
        alert = health_monitor.check_storage("dev-01", 0.5)
        assert alert is not None
        assert alert.severity == AlertSeverity.CRITICAL

    def test_check_storage_warning(self, health_monitor):
        alert = health_monitor.check_storage("dev-01", 3.0)
        assert alert is not None
        assert alert.severity == AlertSeverity.WARNING

    def test_check_storage_ok(self, health_monitor):
        alert = health_monitor.check_storage("dev-01", 50.0)
        assert alert is None

    def test_check_cpu_temp_high(self, health_monitor):
        alert = health_monitor.check_cpu_temp("dev-01", 88.0)
        assert alert is not None
        assert alert.severity == AlertSeverity.CRITICAL

    def test_check_cpu_temp_warning(self, health_monitor):
        alert = health_monitor.check_cpu_temp("dev-01", 75.0)
        assert alert is not None
        assert alert.severity == AlertSeverity.WARNING

    def test_check_cpu_temp_ok(self, health_monitor):
        alert = health_monitor.check_cpu_temp("dev-01", 45.0)
        assert alert is None

    def test_check_crash_event_severe(self, health_monitor):
        alert = health_monitor.check_crash_event("dev-01", {"delta_v_kmh": 90.0})
        assert alert.severity == AlertSeverity.CRITICAL

    def test_check_crash_event_moderate(self, health_monitor):
        alert = health_monitor.check_crash_event("dev-01", {"delta_v_kmh": 50.0})
        assert alert.severity == AlertSeverity.WARNING

    def test_check_crash_event_minor(self, health_monitor):
        alert = health_monitor.check_crash_event("dev-01", {"delta_v_kmh": 15.0})
        assert alert.severity == AlertSeverity.INFO

    def test_acknowledge_alert(self, health_monitor):
        device = DeviceIdentity(
            device_id="dev-01", tpm_pubkey="", tpm_cert="",
            hardware_serial="X", last_seen=time.time() - 100,
        )
        alert = health_monitor.check_heartbeat(device)
        assert not alert.acknowledged

        result = health_monitor.acknowledge_alert(alert.alert_id)
        assert result
        assert alert.acknowledged

    def test_acknowledge_nonexistent(self, health_monitor):
        result = health_monitor.acknowledge_alert("nonexistent")
        assert not result

    def test_get_alerts_filter_device(self, health_monitor):
        device1 = DeviceIdentity(
            device_id="dev-01", tpm_pubkey="", tpm_cert="",
            hardware_serial="X", last_seen=time.time() - 100,
        )
        device2 = DeviceIdentity(
            device_id="dev-02", tpm_pubkey="", tpm_cert="",
            hardware_serial="Y", last_seen=time.time() - 100,
        )
        health_monitor.check_heartbeat(device1)
        health_monitor.check_heartbeat(device2)

        alerts_dev1 = health_monitor.get_alerts(device_id="dev-01")
        assert len(alerts_dev1) == 1
        assert alerts_dev1[0].device_id == "dev-01"

    def test_get_alerts_filter_severity(self, health_monitor):
        health_monitor.check_battery("dev-01", 5.0)  # Critical
        health_monitor.check_battery("dev-02", 15.0)  # Warning

        critical = health_monitor.get_alerts(severity=AlertSeverity.CRITICAL)
        assert len(critical) == 1

    def test_get_alerts_unacknowledged(self, health_monitor):
        device = DeviceIdentity(
            device_id="dev-01", tpm_pubkey="", tpm_cert="",
            hardware_serial="X", last_seen=time.time() - 100,
        )
        alert = health_monitor.check_heartbeat(device)
        health_monitor.acknowledge_alert(alert.alert_id)

        unacked = health_monitor.get_alerts(unacknowledged_only=True)
        assert len(unacked) == 0

    def test_get_fleet_summary(self, health_monitor):
        health_monitor.check_battery("dev-01", 5.0)
        health_monitor.check_battery("dev-02", 15.0)

        summary = health_monitor.get_fleet_summary()
        assert summary["total_alerts"] == 2
        assert "critical" in summary["severity_counts"]
        assert "warning" in summary["severity_counts"]

    def test_to_dict(self, health_monitor):
        health_monitor.check_battery("dev-01", 5.0)
        d = health_monitor.to_dict()
        assert "total_alerts" in d
        assert "alerts" in d


# ===================================================================
# Fleet Manager Integration Tests
# ===================================================================

class TestFleetManager:

    def test_register_device(self, fleet_manager):
        identity = fleet_manager.register_device("fleet-hw-001")
        assert identity.device_id.startswith("VISTA-")
        assert fleet_manager.registry.device_count == 1

    def test_process_heartbeat(self, fleet_manager):
        identity = fleet_manager.register_device("fleet-hw-001")
        fleet_manager.process_heartbeat(identity.device_id, {
            TelemetryType.BATTERY_PCT: 85.0,
            TelemetryType.SPEED_KMH: 60.0,
        })

        # Check telemetry was ingested
        entries = fleet_manager.telemetry.get_entries(
            identity.device_id, TelemetryType.BATTERY_PCT
        )
        assert len(entries) == 1
        assert entries[0].value == 85.0

    def test_record_crash_event(self, fleet_manager):
        identity = fleet_manager.register_device("fleet-hw-001")
        fleet_manager.record_crash_event(identity.device_id, {
            "delta_v_kmh": 45.0,
            "peak_g": 50.0,
        })

        # Check evidence chain
        chain = fleet_manager.evidence.get_chain(identity.device_id)
        crash_records = [r for r in chain if r.event_type == "crash"]
        assert len(crash_records) == 1

    def test_get_fleet_status(self, fleet_manager):
        d1 = fleet_manager.register_device("hw-001")
        d2 = fleet_manager.register_device("hw-002")

        fleet_manager.process_heartbeat(d1.device_id, {
            TelemetryType.BATTERY_PCT: 80.0,
        })
        fleet_manager.record_crash_event(d2.device_id, {"delta_v_kmh": 30.0})

        status = fleet_manager.get_fleet_status()
        assert status["registry"]["device_count"] == 2
        assert status["telemetry"]["total_entries"] == 1
        assert status["evidence"]["total_records"] >= 2

    def test_full_lifecycle(self, fleet_manager):
        """Test complete device lifecycle: register → heartbeat → crash → update."""
        # Register
        dev = fleet_manager.register_device("lifecycle-hw-001")
        assert fleet_manager.registry.device_count == 1

        # Heartbeats
        for i in range(5):
            fleet_manager.process_heartbeat(dev.device_id, {
                TelemetryType.BATTERY_PCT: 100.0 - i * 5,
                TelemetryType.SPEED_KMH: 60.0 + i * 2,
            })

        # Crash event
        fleet_manager.record_crash_event(dev.device_id, {
            "delta_v_kmh": 42.5,
            "peak_g": 50.0,
            "detected": True,
        })

        # OTA update
        fw_data = b"new-firmware-v2.1" * 100
        pkg = fleet_manager.ota.create_package("2.1.0", "Crash fix", fw_data)
        fleet_manager.ota.schedule_update(dev.device_id, pkg.package_id)
        record = fleet_manager.ota.simulate_update(dev.device_id, success=True,
                                                    from_version="2.0.0",
                                                    to_version="2.1.0")
        fleet_manager.registry.update_firmware(dev.device_id, "2.1.0")

        # Verify
        status = fleet_manager.get_fleet_status()
        assert status["registry"]["device_count"] == 1
        assert status["telemetry"]["total_entries"] == 10  # 5 heartbeats × 2 telemetry types
        assert status["evidence"]["total_records"] >= 7  # reg + 5 heartbeats + crash

        # Evidence chain valid
        chain_result = fleet_manager.evidence.verify_chain(dev.device_id)
        assert chain_result["valid"]


# ===================================================================
# Edge Case Tests
# ===================================================================

class TestEdgeCases:

    def test_empty_registry(self, registry):
        assert registry.device_count == 0
        assert registry.list_devices() == []

    def test_empty_telemetry(self, telemetry):
        assert telemetry.get_total_entries() == 0
        assert telemetry.get_all_device_ids() == set()

    def test_empty_evidence_chain(self, evidence_chain):
        result = evidence_chain.verify_chain("nonexistent")
        assert result["valid"]
        assert result["record_count"] == 0

    def test_empty_health_monitor(self, health_monitor):
        summary = health_monitor.get_fleet_summary()
        assert summary["total_alerts"] == 0

    def test_rapid_heartbeat(self, registry):
        identity = registry.register_device("rapid-hw")
        for _ in range(100):
            registry.heartbeat(identity.device_id)
        device = registry.get_device(identity.device_id)
        assert device is not None

    def test_many_telemetry_entries(self, telemetry):
        for i in range(1000):
            telemetry.ingest("dev-01", TelemetryType.ACCEL_PEAK_G, float(i))
        assert telemetry.get_total_entries() == 1000

    def test_many_evidence_records(self, evidence_chain):
        for i in range(100):
            evidence_chain.append_record("dev-01", "heartbeat", {"i": i})
        chain = evidence_chain.get_chain("dev-01")
        assert len(chain) == 100

        result = evidence_chain.verify_chain("dev-01")
        assert result["valid"]


# ===================================================================
# Telemetry Entry Tests
# ===================================================================

class TestTelemetryEntry:

    def test_to_dict(self):
        entry = TelemetryEntry(
            device_id="dev-01",
            telemetry_type=TelemetryType.ACCEL_PEAK_G,
            value=45.0,
            timestamp_s=1234567890.0,
            sequence=5,
        )
        d = entry.to_dict()
        assert d["device_id"] == "dev-01"
        assert d["telemetry_type"] == "accel_peak_g"
        assert d["value"] == 45.0


# ===================================================================
# Fleet Alert Tests
# ===================================================================

class TestFleetAlert:

    def test_to_dict(self):
        alert = FleetAlert(
            alert_id="alert-001",
            device_id="dev-01",
            severity=AlertSeverity.WARNING,
            message="Test alert",
            timestamp_s=1234567890.0,
        )
        d = alert.to_dict()
        assert d["alert_id"] == "alert-001"
        assert d["severity"] == "warning"
        assert d["acknowledged"] is False


# ===================================================================
# Enum Tests
# ===================================================================

class TestEnums:

    def test_device_status_values(self):
        assert DeviceStatus.ONLINE.value == "online"
        assert DeviceStatus.OFFLINE.value == "offline"
        assert DeviceStatus.UPDATING.value == "updating"

    def test_telemetry_type_values(self):
        assert TelemetryType.ACCEL_PEAK_G.value == "accel_peak_g"
        assert TelemetryType.BATTERY_PCT.value == "battery_pct"

    def test_ota_status_values(self):
        assert OTAPackageStatus.PENDING.value == "pending"
        assert OTAPackageStatus.COMPLETE.value == "complete"
        assert OTAPackageStatus.FAILED.value == "failed"

    def test_health_status_values(self):
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"

    def test_alert_severity_values(self):
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.CRITICAL.value == "critical"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
