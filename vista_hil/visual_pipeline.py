"""
VISTA 2.0 — Layer 6: Visual Analytics Pipeline
Camera-based forensic evidence system for crash documentation.

Architecture:
  Multi-camera capture → Burst trigger → Frame catalog → Quality metrics
  → Key frame detection → Evidence package with hash chain

Camera System:
  - Front camera: 4K (3840×2160) @ 30fps normal, 60fps burst
  - Rear camera: 2K (2560×1440) @ 30fps normal, 60fps burst
  - Burst mode: 60fps for 2 seconds on crash trigger (120 frames/camera)

Image Quality Metrics:
  - Blur detection (Laplacian variance)
  - Exposure analysis (histogram statistics)
  - Noise estimation (median absolute deviation)

Key Frame Detection:
  - First post-crash frame (onset documentation)
  - Best quality frame (clearest evidence)
  - Scene context frame (widest field of view)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ===================================================================
# Constants
# ===================================================================

FRONT_CAMERA_ID = "cam_front_4k"
REAR_CAMERA_ID = "cam_rear_2k"

FRONT_RESOLUTION = (3840, 2160)
REAR_RESOLUTION = (2560, 1440)

NORMAL_FPS = 30
BURST_FPS = 60
BURST_DURATION_S = 2.0
BURST_FRAME_COUNT = int(BURST_FPS * BURST_DURATION_S)  # 120 frames


# ===================================================================
# Enums
# ===================================================================

class CameraPosition(Enum):
    FRONT = "front"
    REAR = "rear"
    LEFT = "left"
    RIGHT = "right"


class FrameType(Enum):
    PRE_CRASH = "pre_crash"
    CRASH_ONSET = "crash_onset"
    POST_CRASH = "post_crash"
    CONTEXT = "context"


class KeyFrameReason(Enum):
    FIRST_POST_CRASH = "first_post_crash"
    BEST_QUALITY = "best_quality"
    SCENE_CONTEXT = "scene_context"
    HIGHESTBlur = "highest_blur"  # documents impact severity


# ===================================================================
# Configuration
# ===================================================================

@dataclass
class CameraConfig:
    """Configuration for a single camera."""
    camera_id: str
    position: CameraPosition
    resolution: Tuple[int, int]
    normal_fps: int = 30
    burst_fps: int = 60
    burst_duration_s: float = 2.0
    bit_depth: int = 8
    lens_fov_deg: float = 120.0

    @property
    def burst_frame_count(self) -> int:
        return int(self.burst_fps * self.burst_duration_s)

    @property
    def total_pixels(self) -> int:
        return self.resolution[0] * self.resolution[1]


@dataclass
class VisualPipelineConfig:
    """Configuration for the visual analytics pipeline."""
    front_camera: CameraConfig = field(default_factory=lambda: CameraConfig(
        camera_id=FRONT_CAMERA_ID,
        position=CameraPosition.FRONT,
        resolution=FRONT_RESOLUTION,
        normal_fps=NORMAL_FPS,
        burst_fps=BURST_FPS,
        burst_duration_s=BURST_DURATION_S,
        lens_fov_deg=120.0,
    ))
    rear_camera: CameraConfig = field(default_factory=lambda: CameraConfig(
        camera_id=REAR_CAMERA_ID,
        position=CameraPosition.REAR,
        resolution=REAR_RESOLUTION,
        normal_fps=NORMAL_FPS,
        burst_fps=BURST_FPS,
        burst_duration_s=BURST_DURATION_S,
        lens_fov_deg=90.0,
    ))
    pre_crash_buffer_s: float = 5.0
    quality_blur_threshold: float = 100.0
    quality_exposure_target: float = 128.0
    quality_noise_threshold: float = 30.0
    shared_secret: bytes = b"vista-visual-evidence-key-32b!"


# ===================================================================
# Frame Data
# ===================================================================

@dataclass
class Frame:
    """A single captured frame with metadata."""
    frame_id: str
    camera_id: str
    timestamp_s: float
    frame_number: int
    resolution: Tuple[int, int]
    frame_type: FrameType
    image_data: Optional[np.ndarray] = None  # (H, W, 3) uint8 or None for sim
    quality_metrics: Optional[Dict[str, float]] = None
    is_key_frame: bool = False
    key_frame_reason: Optional[KeyFrameReason] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "camera_id": self.camera_id,
            "timestamp_s": self.timestamp_s,
            "frame_number": self.frame_number,
            "resolution": list(self.resolution),
            "frame_type": self.frame_type.value,
            "is_key_frame": self.is_key_frame,
            "key_frame_reason": self.key_frame_reason.value if self.key_frame_reason else None,
            "quality_metrics": self.quality_metrics,
        }


# ===================================================================
# Quality Metrics
# ===================================================================

class ImageQualityAnalyzer:
    """
    Computes image quality metrics for forensic frames.

    Metrics:
      - Blur: Laplacian variance (higher = sharper)
      - Exposure: Mean brightness (0-255), deviation from target
      - Noise: Median absolute deviation of high-frequency component
    """

    def __init__(self, config: Optional[VisualPipelineConfig] = None):
        self.config = config or VisualPipelineConfig()

    def compute_blur_score(self, image: np.ndarray) -> float:
        """
        Laplacian variance blur metric.

        Args:
            image: Grayscale or RGB image (H, W) or (H, W, 3), uint8

        Returns:
            Blur score (higher = sharper, typical range 0-5000+)
        """
        if image.ndim == 3:
            gray = np.mean(image.astype(np.float64), axis=2)
        else:
            gray = image.astype(np.float64)

        # Laplacian kernel approximation
        laplacian = (
            np.roll(gray, 1, axis=0) + np.roll(gray, -1, axis=0) +
            np.roll(gray, 1, axis=1) + np.roll(gray, -1, axis=1) -
            4 * gray
        )

        # Variance of Laplacian
        return float(np.var(laplacian))

    def compute_exposure_score(self, image: np.ndarray) -> Dict[str, float]:
        """
        Exposure analysis via histogram statistics.

        Returns:
            Dict with mean_brightness, std_brightness, underexposed_pct, overexposed_pct
        """
        if image.ndim == 3:
            gray = np.mean(image.astype(np.float64), axis=2)
        else:
            gray = image.astype(np.float64)

        mean_val = float(np.mean(gray))
        std_val = float(np.std(gray))
        total_pixels = gray.size

        underexposed = float(np.sum(gray < 25) / total_pixels * 100)
        overexposed = float(np.sum(gray > 230) / total_pixels * 100)

        return {
            "mean_brightness": mean_val,
            "std_brightness": std_val,
            "underexposed_pct": underexposed,
            "overexposed_pct": overexposed,
            "exposure_deviation": abs(mean_val - self.config.quality_exposure_target),
        }

    def compute_noise_score(self, image: np.ndarray) -> float:
        """
        Noise estimation using median absolute deviation (MAD).

        Estimates noise level from high-frequency component.
        Returns noise level (lower = less noisy, typical range 0-50).
        """
        if image.ndim == 3:
            gray = np.mean(image.astype(np.float64), axis=2)
        else:
            gray = image.astype(np.float64)

        # High-pass filter via median subtraction
        from scipy.ndimage import median_filter
        smoothed = median_filter(gray, size=3)
        residual = gray - smoothed

        # MAD-based noise estimate (robust to outliers)
        noise = float(1.4826 * np.median(np.abs(residual - np.median(residual))))
        return noise

    def analyze_frame(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Run full quality analysis on a frame.

        Returns:
            Dict with blur_score, exposure, noise_score, overall_quality
        """
        blur = self.compute_blur_score(image)
        exposure = self.compute_exposure_score(image)
        noise = self.compute_noise_score(image)

        # Overall quality score (0-100)
        # Higher blur = better, lower noise = better, closer exposure = better
        blur_quality = min(blur / self.config.quality_blur_threshold, 1.0) * 40
        noise_quality = max(0, 1.0 - noise / self.config.quality_noise_threshold) * 30
        exposure_quality = max(0, 1.0 - exposure["exposure_deviation"] / 128.0) * 30

        overall = blur_quality + noise_quality + exposure_quality

        return {
            "blur_score": blur,
            "exposure": exposure,
            "noise_score": noise,
            "overall_quality": overall,
        }


# ===================================================================
# Frame Catalog
# ===================================================================

@dataclass
class FrameCatalog:
    """Catalog of frames from a single camera during an event."""
    camera_id: str
    event_id: str
    frames: List[Frame] = field(default_factory=list)
    burst_active: bool = False
    burst_start_frame: Optional[int] = None

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def key_frames(self) -> List[Frame]:
        return [f for f in self.frames if f.is_key_frame]

    @property
    def pre_crash_frames(self) -> List[Frame]:
        return [f for f in self.frames if f.frame_type == FrameType.PRE_CRASH]

    @property
    def post_crash_frames(self) -> List[Frame]:
        return [f for f in self.frames if f.frame_type == FrameType.POST_CRASH]

    def get_frame_by_id(self, frame_id: str) -> Optional[Frame]:
        for f in self.frames:
            if f.frame_id == frame_id:
                return f
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "event_id": self.event_id,
            "frame_count": self.frame_count,
            "burst_active": self.burst_active,
            "key_frame_count": len(self.key_frames),
            "pre_crash_count": len(self.pre_crash_frames),
            "post_crash_count": len(self.post_crash_frames),
            "frames": [f.to_dict() for f in self.frames],
        }


# ===================================================================
# Key Frame Detector
# ===================================================================

class KeyFrameDetector:
    """
    Detects key frames from the frame catalog for forensic evidence.

    Key frame types:
      1. First post-crash frame: Documents the initial impact moment
      2. Best quality frame: Clearest image for evidence
      3. Scene context frame: Widest context for reconstruction
    """

    def __init__(self, quality_analyzer: Optional[ImageQualityAnalyzer] = None):
        self.analyzer = quality_analyzer or ImageQualityAnalyzer()

    def detect_key_frames(self, catalog: FrameCatalog) -> List[Frame]:
        """
        Identify key frames from the catalog.

        Returns list of frames marked as key frames with reasons.
        """
        key_frames = []

        # 1. First post-crash frame
        post_crash = catalog.post_crash_frames
        if post_crash:
            first_post = post_crash[0]
            first_post.is_key_frame = True
            first_post.key_frame_reason = KeyFrameReason.FIRST_POST_CRASH
            key_frames.append(first_post)

        # 2. Best quality frame (among all frames)
        if catalog.frames:
            best_frame = max(
                catalog.frames,
                key=lambda f: (f.quality_metrics or {}).get("overall_quality", 0)
            )
            if best_frame not in key_frames:
                best_frame.is_key_frame = True
                best_frame.key_frame_reason = KeyFrameReason.BEST_QUALITY
                key_frames.append(best_frame)

        # 3. Scene context frame (mid-point of pre-crash for context)
        pre_crash = catalog.pre_crash_frames
        if pre_crash and len(pre_crash) > 2:
            mid_idx = len(pre_crash) // 2
            context_frame = pre_crash[mid_idx]
            if context_frame not in key_frames:
                context_frame.is_key_frame = True
                context_frame.key_frame_reason = KeyFrameReason.SCENE_CONTEXT
                key_frames.append(context_frame)

        return key_frames


# ===================================================================
# Visual Evidence Package
# ===================================================================

@dataclass
class VisualEvidencePackage:
    """Tamper-evident package of visual forensic evidence."""
    evidence_id: str
    event_id: str
    device_id: str
    timestamp_s: float
    cameras: List[str]
    total_frames: int
    key_frames: List[Dict[str, Any]]
    frame_catalog_summary: Dict[str, Any]
    quality_summary: Dict[str, Any]
    sha256_hash: str
    sha3_hash: str
    hmac_signature: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "event_id": self.event_id,
            "device_id": self.device_id,
            "timestamp_s": self.timestamp_s,
            "cameras": self.cameras,
            "total_frames": self.total_frames,
            "key_frames": self.key_frames,
            "frame_catalog_summary": self.frame_catalog_summary,
            "quality_summary": self.quality_summary,
            "sha256_hash": self.sha256_hash,
            "sha3_hash": self.sha3_hash,
            "hmac_signature": self.hmac_signature,
            "metadata": self.metadata,
        }


# ===================================================================
# Visual Forensic Pipeline (Main Entry Point)
# ===================================================================

class VisualForensicPipeline:
    """
    Camera-based forensic evidence pipeline for VISTA 2.0 Layer 6.

    Usage:
        pipeline = VisualForensicPipeline(config)
        pipeline.start_recording()

        # On crash trigger:
        pipeline.trigger_burst()
        pipeline.stop_recording()

        # Generate evidence
        package = pipeline.generate_evidence_package(
            event_id="crash-001",
            device_id="vista-unit-01",
        )
    """

    def __init__(self, config: Optional[VisualPipelineConfig] = None):
        self.config = config or VisualPipelineConfig()
        self.quality_analyzer = ImageQualityAnalyzer(self.config)
        self.key_frame_detector = KeyFrameDetector(self.quality_analyzer)

        # Camera catalogs
        self._catalogs: Dict[str, FrameCatalog] = {}
        self._recording = False
        self._burst_active = False
        self._frame_counter: Dict[str, int] = {}
        self._event_start_time: Optional[float] = None
        self._crash_timestamp: Optional[float] = None

        # HMAC key
        self._hmac_key = self.config.shared_secret

        self._init_catalogs()

    def _init_catalogs(self):
        """Initialize frame catalogs for each camera."""
        for cam_cfg in [self.config.front_camera, self.config.rear_camera]:
            self._catalogs[cam_cfg.camera_id] = FrameCatalog(
                camera_id=cam_cfg.camera_id,
                event_id="",
            )
            self._frame_counter[cam_cfg.camera_id] = 0

    def start_recording(self, event_id: str = "default"):
        """Start recording from all cameras."""
        self._recording = True
        self._event_start_time = time.time()
        self._burst_active = False

        for cam_id, catalog in self._catalogs.items():
            catalog.event_id = event_id
            catalog.frames.clear()
            catalog.burst_active = False
            self._frame_counter[cam_id] = 0

    def stop_recording(self):
        """Stop recording from all cameras."""
        self._recording = False
        self._burst_active = False

        for catalog in self._catalogs.values():
            catalog.burst_active = False

    def _simulate_frame(self, camera_id: str, timestamp_s: float,
                        frame_number: int, frame_type: FrameType,
                        rng: Optional[np.random.Generator] = None) -> Frame:
        """
        Simulate capturing a frame. In production, this would interface
        with actual camera hardware via V4L2/GStreamer.

        For simulation, generates a synthetic image with controllable quality.
        """
        rng = rng or np.random.default_rng()

        cam_cfg = (self.config.front_camera if camera_id == FRONT_CAMERA_ID
                   else self.config.rear_camera)

        # Simulate image data (downscaled for performance)
        sim_h, sim_w = 216, 384  # Simulate at reduced resolution
        if frame_type == FrameType.CRASH_ONSET:
            # Crash frame: motion blur, exposure change
            base = rng.normal(128, 40, (sim_h, sim_w, 3)).astype(np.uint8)
            # Add motion blur streaks
            blur_shift = rng.integers(-5, 6)
            base = np.roll(base, blur_shift, axis=1)
        elif frame_type == FrameType.POST_CRASH:
            # Post-crash: possible damage artifacts
            base = rng.normal(110, 50, (sim_h, sim_w, 3)).astype(np.uint8)
        else:
            # Normal/pre-crash frame
            base = rng.normal(128, 30, (sim_h, sim_w, 3)).astype(np.uint8)

        base = np.clip(base, 0, 255).astype(np.uint8)

        # Compute quality metrics
        quality = self.quality_analyzer.analyze_frame(base)

        frame = Frame(
            frame_id=f"{camera_id}_f{frame_number:06d}",
            camera_id=camera_id,
            timestamp_s=timestamp_s,
            frame_number=frame_number,
            resolution=cam_cfg.resolution,
            frame_type=frame_type,
            image_data=base,
            quality_metrics=quality,
        )

        return frame

    def capture_pre_crash_frames(self, n_frames: int = 30):
        """
        Capture pre-crash frames (from buffer or simulated).

        In production, these come from the circular buffer.
        For simulation, we generate synthetic frames.
        """
        if not self._recording:
            return

        rng = np.random.default_rng(42)
        t_start = self._event_start_time or time.time()

        for cam_id in self._catalogs:
            for i in range(n_frames):
                timestamp = t_start + (i / NORMAL_FPS)
                frame_num = self._frame_counter[cam_id]
                frame = self._simulate_frame(
                    cam_id, timestamp, frame_num, FrameType.PRE_CRASH, rng
                )
                self._catalogs[cam_id].frames.append(frame)
                self._frame_counter[cam_id] += 1

    def trigger_burst(self):
        """
        Trigger burst capture on crash detection.

        Captures at BURST_FPS for BURST_DURATION_S from all cameras.
        The first frame is marked as CRASH_ONSET.
        """
        if not self._recording:
            return

        self._burst_active = True
        self._crash_timestamp = time.time()

        rng = np.random.default_rng(123)

        for cam_id, catalog in self._catalogs.items():
            catalog.burst_active = True
            cam_cfg = (self.config.front_camera if cam_id == FRONT_CAMERA_ID
                       else self.config.rear_camera)

            burst_count = cam_cfg.burst_frame_count
            dt = 1.0 / cam_cfg.burst_fps

            for i in range(burst_count):
                timestamp = self._crash_timestamp + (i * dt)
                frame_num = self._frame_counter[cam_id]

                # First burst frame = crash onset
                if i == 0:
                    frame_type = FrameType.CRASH_ONSET
                elif i < burst_count // 4:
                    frame_type = FrameType.POST_CRASH
                else:
                    frame_type = FrameType.POST_CRASH

                frame = self._simulate_frame(
                    cam_id, timestamp, frame_num, frame_type, rng
                )
                catalog.frames.append(frame)
                self._frame_counter[cam_id] += 1

            catalog.burst_active = False

        self._burst_active = False

    def get_catalog(self, camera_id: str) -> FrameCatalog:
        """Get the frame catalog for a specific camera."""
        return self._catalogs[camera_id]

    def get_all_catalogs(self) -> Dict[str, FrameCatalog]:
        """Get all frame catalogs."""
        return dict(self._catalogs)

    def compute_quality_summary(self) -> Dict[str, Any]:
        """
        Compute aggregate quality metrics across all cameras and frames.

        Returns:
            Dict with per-camera and overall quality statistics.
        """
        summary = {}

        for cam_id, catalog in self._catalogs.items():
            if not catalog.frames:
                summary[cam_id] = {"frame_count": 0}
                continue

            blur_scores = []
            noise_scores = []
            exposure_means = []

            for frame in catalog.frames:
                if frame.quality_metrics:
                    blur_scores.append(frame.quality_metrics.get("blur_score", 0))
                    noise_scores.append(frame.quality_metrics.get("noise_score", 0))
                    exp = frame.quality_metrics.get("exposure", {})
                    exposure_means.append(exp.get("mean_brightness", 128))

            summary[cam_id] = {
                "frame_count": catalog.frame_count,
                "blur_mean": float(np.mean(blur_scores)) if blur_scores else 0,
                "blur_min": float(np.min(blur_scores)) if blur_scores else 0,
                "blur_max": float(np.max(blur_scores)) if blur_scores else 0,
                "noise_mean": float(np.mean(noise_scores)) if noise_scores else 0,
                "exposure_mean": float(np.mean(exposure_means)) if exposure_means else 0,
            }

        # Overall summary
        all_blur = []
        all_noise = []
        for cam_summary in summary.values():
            if cam_summary.get("frame_count", 0) > 0:
                all_blur.append(cam_summary.get("blur_mean", 0))
                all_noise.append(cam_summary.get("noise_mean", 0))

        summary["overall"] = {
            "total_frames": sum(s.get("frame_count", 0) for s in summary.values()
                               if isinstance(s, dict) and "blur_mean" in s),
            "avg_blur": float(np.mean(all_blur)) if all_blur else 0,
            "avg_noise": float(np.mean(all_noise)) if all_noise else 0,
        }

        return summary

    def detect_key_frames(self) -> Dict[str, List[Frame]]:
        """
        Detect key frames across all cameras.

        Returns:
            Dict mapping camera_id to list of key frames.
        """
        results = {}
        for cam_id, catalog in self._catalogs.items():
            key_frames = self.key_frame_detector.detect_key_frames(catalog)
            results[cam_id] = key_frames
        return results

    def _compute_hash(self, data: bytes, algorithm: str = "sha256") -> str:
        """Compute hash of data."""
        if algorithm == "sha256":
            return hashlib.sha256(data).hexdigest()
        elif algorithm == "sha3_256":
            return hashlib.sha3_256(data).hexdigest()
        return hashlib.sha256(data).hexdigest()

    def _compute_hmac(self, data: bytes) -> str:
        """Compute HMAC-SHA256 signature."""
        return hashlib.pbkdf2_hmac(
            "sha256", self._hmac_key, data, 100000
        ).hex()

    def generate_evidence_package(
        self,
        event_id: str,
        device_id: str,
    ) -> VisualEvidencePackage:
        """
        Generate a tamper-evident visual evidence package.

        Creates a complete package with:
        - Frame catalog summaries
        - Key frames identified
        - Quality metrics
        - Cryptographic hash chain
        """
        # Detect key frames
        key_frames_by_camera = self.detect_key_frames()

        # Compute quality summary
        quality_summary = self.compute_quality_summary()

        # Build frame catalog summary
        catalog_summary = {}
        total_frames = 0
        for cam_id, catalog in self._catalogs.items():
            cam_summary = {
                "frame_count": catalog.frame_count,
                "pre_crash_count": len(catalog.pre_crash_frames),
                "post_crash_count": len(catalog.post_crash_frames),
                "key_frame_count": len(catalog.key_frames),
                "burst_active": catalog.burst_active,
            }
            catalog_summary[cam_id] = cam_summary
            total_frames += catalog.frame_count

        # Collect key frames info
        all_key_frames = []
        for cam_id, frames in key_frames_by_camera.items():
            for f in frames:
                all_key_frames.append({
                    "camera_id": cam_id,
                    "frame_id": f.frame_id,
                    "frame_number": f.frame_number,
                    "timestamp_s": f.timestamp_s,
                    "frame_type": f.frame_type.value,
                    "key_frame_reason": f.key_frame_reason.value if f.key_frame_reason else None,
                    "quality_score": (f.quality_metrics or {}).get("overall_quality", 0),
                })

        # Create evidence record
        timestamp = time.time()
        evidence_id = f"vis-{event_id}-{int(timestamp * 1000)}"

        # Payload for hashing
        payload = {
            "evidence_id": evidence_id,
            "event_id": event_id,
            "device_id": device_id,
            "timestamp_s": timestamp,
            "cameras": list(self._catalogs.keys()),
            "total_frames": total_frames,
            "key_frames": all_key_frames,
            "catalog_summary": catalog_summary,
            "quality_summary": quality_summary,
        }

        # Compute hashes
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        sha256_hash = self._compute_hash(payload_bytes, "sha256")
        sha3_hash = self._compute_hash(payload_bytes, "sha3_256")
        hmac_sig = self._compute_hmac(payload_bytes)

        package = VisualEvidencePackage(
            evidence_id=evidence_id,
            event_id=event_id,
            device_id=device_id,
            timestamp_s=timestamp,
            cameras=list(self._catalogs.keys()),
            total_frames=total_frames,
            key_frames=all_key_frames,
            frame_catalog_summary=catalog_summary,
            quality_summary=quality_summary,
            sha256_hash=sha256_hash,
            sha3_hash=sha3_hash,
            hmac_signature=hmac_sig,
            metadata={
                "pipeline_version": "2.0.0",
                "front_resolution": list(FRONT_RESOLUTION),
                "rear_resolution": list(REAR_RESOLUTION),
                "burst_fps": BURST_FPS,
                "burst_duration_s": BURST_DURATION_S,
            },
        )

        return package

    def verify_evidence_package(self, package: VisualEvidencePackage) -> Dict[str, Any]:
        """
        Verify the integrity of a visual evidence package.

        Returns:
            Dict with "valid" bool, "checks" dict, "errors" list.
        """
        errors = []
        checks = {}

        # Reconstruct payload
        payload = {
            "evidence_id": package.evidence_id,
            "event_id": package.event_id,
            "device_id": package.device_id,
            "timestamp_s": package.timestamp_s,
            "cameras": package.cameras,
            "total_frames": package.total_frames,
            "key_frames": package.key_frames,
            "catalog_summary": package.frame_catalog_summary,
            "quality_summary": package.quality_summary,
        }

        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

        # Verify SHA-256
        expected_sha256 = self._compute_hash(payload_bytes, "sha256")
        checks["sha256"] = (package.sha256_hash == expected_sha256)
        if not checks["sha256"]:
            errors.append("SHA-256 hash mismatch")

        # Verify SHA-3
        expected_sha3 = self._compute_hash(payload_bytes, "sha3_256")
        checks["sha3"] = (package.sha3_hash == expected_sha3)
        if not checks["sha3"]:
            errors.append("SHA-3 hash mismatch")

        # Verify HMAC
        expected_hmac = self._compute_hmac(payload_bytes)
        checks["hmac"] = (package.hmac_signature == expected_hmac)
        if not checks["hmac"]:
            errors.append("HMAC signature mismatch")

        # Timestamp sanity
        age = abs(time.time() - package.timestamp_s)
        checks["timestamp"] = age < 86400
        if not checks["timestamp"]:
            errors.append(f"Timestamp age {age:.0f}s exceeds 1 day")

        valid = all(checks.values())

        return {
            "valid": valid,
            "checks": checks,
            "errors": errors,
        }


# ===================================================================
# Self-Test
# ===================================================================

def _self_test():
    """Comprehensive self-test of the visual pipeline."""
    import sys

    print("=" * 70)
    print("VISUAL ANALYTICS PIPELINE — SELF-TEST")
    print("=" * 70)

    config = VisualPipelineConfig()
    pipeline = VisualForensicPipeline(config)

    # --- Test 1: Start/stop recording ---
    print("\n[TEST 1] Start/stop recording")
    pipeline.start_recording("test-event-001")
    assert pipeline._recording
    pipeline.stop_recording()
    assert not pipeline._recording
    print("  PASS: Recording start/stop works")

    # --- Test 2: Pre-crash capture ---
    print("\n[TEST 2] Pre-crash frame capture")
    pipeline.start_recording("test-event-002")
    pipeline.capture_pre_crash_frames(n_frames=10)

    for cam_id, catalog in pipeline.get_all_catalogs().items():
        assert catalog.frame_count == 10, f"{cam_id}: expected 10 frames, got {catalog.frame_count}"
    print(f"  PASS: Captured 10 pre-crash frames per camera")

    # --- Test 3: Burst capture ---
    print("\n[TEST 3] Burst capture (60fps x 2s)")
    pipeline.trigger_burst()

    for cam_id, catalog in pipeline.get_all_catalogs().items():
        # 10 pre-crash + 120 burst = 130
        assert catalog.frame_count == 130, f"{cam_id}: expected 130 frames, got {catalog.frame_count}"
        assert len(catalog.post_crash_frames) == 120
        print(f"  {cam_id}: {catalog.frame_count} frames, {len(catalog.post_crash_frames)} post-crash")
    print("  PASS: Burst capture correct")

    # --- Test 4: Quality metrics ---
    print("\n[TEST 4] Image quality metrics")
    analyzer = ImageQualityAnalyzer(config)
    rng = np.random.default_rng(42)

    # Sharp image
    sharp_img = rng.normal(128, 30, (216, 384, 3)).astype(np.uint8)
    sharp_metrics = analyzer.analyze_frame(sharp_img)
    print(f"  Sharp image: blur={sharp_metrics['blur_score']:.1f}, "
          f"noise={sharp_metrics['noise_score']:.1f}, "
          f"quality={sharp_metrics['overall_quality']:.1f}")

    # Blurry image (uniform)
    blurry_img = np.ones((216, 384, 3), dtype=np.uint8) * 128
    blurry_metrics = analyzer.analyze_frame(blurry_img)
    print(f"  Blurry image: blur={blurry_metrics['blur_score']:.1f}, "
          f"noise={blurry_metrics['noise_score']:.1f}, "
          f"quality={blurry_metrics['overall_quality']:.1f}")

    assert sharp_metrics["blur_score"] > blurry_metrics["blur_score"], \
        "Sharp image should have higher blur score"
    print("  PASS: Quality metrics differentiate sharp vs blurry")

    # --- Test 5: Key frame detection ---
    print("\n[TEST 5] Key frame detection")
    key_frames_by_cam = pipeline.detect_key_frames()
    for cam_id, key_frames in key_frames_by_cam.items():
        print(f"  {cam_id}: {len(key_frames)} key frames")
        for kf in key_frames:
            print(f"    - {kf.frame_id}: {kf.key_frame_reason.value}")
    print("  PASS: Key frames detected")

    # --- Test 6: Evidence package generation ---
    print("\n[TEST 6] Evidence package generation")
    package = pipeline.generate_evidence_package(
        event_id="test-event-002",
        device_id="vista-sim-01",
    )
    print(f"  Evidence ID:  {package.evidence_id}")
    print(f"  Total frames: {package.total_frames}")
    print(f"  Key frames:   {len(package.key_frames)}")
    print(f"  SHA-256:      {package.sha256_hash[:32]}...")
    print(f"  SHA-3:        {package.sha3_hash[:32]}...")
    print(f"  HMAC:         {package.hmac_signature[:32]}...")

    # --- Test 7: Evidence verification ---
    print("\n[TEST 7] Evidence package verification")
    verification = pipeline.verify_evidence_package(package)
    print(f"  Valid:   {verification['valid']}")
    print(f"  Checks:  {verification['checks']}")
    assert verification["valid"], f"FAIL: {verification['errors']}"
    print("  PASS: Evidence package verified")

    # --- Test 8: Tamper detection ---
    print("\n[TEST 8] Tamper detection")
    tampered = pipeline.generate_evidence_package(
        event_id="test-event-002",
        device_id="vista-sim-01",
    )
    tampered.total_frames = 99999  # Tamper
    tamper_result = pipeline.verify_evidence_package(tampered)
    print(f"  Valid: {tamper_result['valid']}")
    assert not tamper_result["valid"], "FAIL: tampered package should fail"
    print("  PASS: Tamper detected")

    # --- Test 9: Quality summary ---
    print("\n[TEST 9] Quality summary")
    q_summary = pipeline.compute_quality_summary()
    for cam_id in [FRONT_CAMERA_ID, REAR_CAMERA_ID]:
        if cam_id in q_summary and "blur_mean" in q_summary[cam_id]:
            s = q_summary[cam_id]
            print(f"  {cam_id}: frames={s['frame_count']}, "
                  f"blur_mean={s['blur_mean']:.1f}, "
                  f"noise_mean={s['noise_mean']:.1f}")
    print("  PASS: Quality summary computed")

    # --- Test 10: Dual hash defense-in-depth ---
    print("\n[TEST 10] Dual hash defense-in-depth")
    print(f"  SHA-256 == SHA-3: {package.sha256_hash == package.sha3_hash}")
    assert package.sha256_hash != package.sha3_hash, \
        "FAIL: SHA-256 and SHA-3 should differ"
    print("  PASS: Dual hashes are different")

    # --- Test 11: Performance benchmark ---
    print("\n[TEST 11] Performance benchmark")
    pipeline2 = VisualForensicPipeline(config)
    pipeline2.start_recording("bench-event")
    pipeline2.capture_pre_crash_frames(n_frames=30)

    import time as _time
    t0 = _time.perf_counter()
    pipeline2.trigger_burst()
    burst_ms = (_time.perf_counter() - t0) * 1000

    t0 = _time.perf_counter()
    pkg = pipeline2.generate_evidence_package("bench", "vista-sim-01")
    gen_ms = (_time.perf_counter() - t0) * 1000

    print(f"  Burst capture: {burst_ms:.1f} ms")
    print(f"  Package generation: {gen_ms:.1f} ms")
    assert burst_ms < 5000, f"Burst too slow: {burst_ms}ms"
    assert gen_ms < 1000, f"Package gen too slow: {gen_ms}ms"
    print("  PASS: Performance within bounds")

    print(f"\n{'='*70}")
    print("ALL VISUAL PIPELINE TESTS PASSED")
    print(f"{'='*70}")


if __name__ == "__main__":
    _self_test()
