"""
CameraStateManager — deterministic camera state normalization.

The camera heading model in navigation/camera.py tracks heading and uncertainty.
CameraStateManager adds the session-level concept of a "known-safe camera state"
for each traversal context:

  - TRAVERSAL: camera normalized to default (F-reset), heading ≈ 0°
  - FIELD: slight downward pitch for visibility in farming fields
  - CANNON: camera aligned with cannon trajectory before launch

Why this matters for determinism:
  - WASD keys are camera-relative in BSS
  - Inconsistent camera heading → inconsistent movement direction
  - Two runs with the same key sequence can end up in different places
    if the camera angle differs
  - Pre-route camera normalization removes this variable

Shift-lock note:
  - With shift-lock ON: WASD is always screen-relative (more consistent)
  - Without shift-lock: WASD is camera-relative (depends on camera angle)
  - This system assumes shift-lock is OFF (the common macro setup) and
    compensates by normalizing the camera before every traversal.

Public API:
    csm = get_camera_state_manager()
    csm.ensure_traversal_state(stop_event)    # F-reset + settle
    csm.align_for_anchor(anchor_id, stop_event)  # align to anchor's expected heading
    csm.is_traversal_ready() -> bool
"""
from __future__ import annotations

import threading
import time
from enum import Enum, auto
from typing import Optional

from navigation.camera import get_camera
from navigation.anchor_registry import get_anchor_registry
from utils.logger import get_logger

log = get_logger(__name__)

# If camera was last normalized more than this many seconds ago,
# force a re-normalize before the next traversal (conservative).
_NORMALIZE_MAX_AGE = 120.0

# Heading uncertainty above this forces a re-normalize
_HEADING_UNCERTAIN_THRESHOLD = 50.0


class CameraPreset(Enum):
    """Named camera states for deterministic traversal."""
    TRAVERSAL   = "traversal"    # F-reset default; heading = 0°
    FIELD_FARM  = "field_farm"   # slight right rotation for field visibility
    CANNON_PREP = "cannon_prep"  # align to cannon platform heading
    RECOVERY    = "recovery"     # force F-reset, max certainty restoration


class CameraStateManager:
    """
    Session-level camera state coordinator.

    Not thread-safe — call from the navigation thread only.
    """

    def __init__(self) -> None:
        self._cam       = get_camera()
        self._registry  = get_anchor_registry()
        self._last_norm: float = 0.0

    # ------------------------------------------------------------------ #
    # Traversal normalization                                              #
    # ------------------------------------------------------------------ #

    def ensure_traversal_state(
        self,
        stop_event: threading.Event,
        force: bool = False,
    ) -> bool:
        """
        Ensure the camera is in a known state before a route begins.

        Performs F-reset + optical-flow settle if:
          - Camera was never normalized this session
          - Heading uncertainty is too high
          - More than _NORMALIZE_MAX_AGE seconds since last normalization
          - force=True

        Returns True when the camera is in traversal state, False if stop_event.
        """
        if stop_event.is_set():
            return False

        age    = time.monotonic() - self._last_norm
        unc    = self._cam.heading_uncertainty
        needs  = (
            force
            or self._last_norm == 0.0
            or age > _NORMALIZE_MAX_AGE
            or unc > _HEADING_UNCERTAIN_THRESHOLD
        )

        if not needs:
            log.debug("CameraState: traversal-ready (age=%.0fs unc=%.1f°)", age, unc)
            return True

        log.debug("CameraState: normalizing (age=%.0fs unc=%.1f° force=%s)", age, unc, force)
        ok = self._cam.normalize(stop_event)
        if ok:
            self._last_norm = time.monotonic()
        return ok

    # ------------------------------------------------------------------ #
    # Anchor-specific alignment                                            #
    # ------------------------------------------------------------------ #

    def align_for_anchor(
        self,
        anchor_id: str,
        stop_event: threading.Event,
    ) -> bool:
        """
        Align camera heading to the expected heading for the given anchor.

        Uses AnchorRegistry.expected_heading.  If the anchor has no expected
        heading (None), performs a standard normalize only.

        Returns True when aligned (within heading_tolerance), False if stop_event.
        """
        if stop_event.is_set():
            return False

        anchor = self._registry.get(anchor_id)
        if anchor is None or anchor.expected_heading is None:
            return self.ensure_traversal_state(stop_event)

        if not self.ensure_traversal_state(stop_event):
            return False

        return self._cam.align_to_heading(
            anchor.expected_heading,
            stop_event,
            tolerance=anchor.heading_tolerance,
        )

    # ------------------------------------------------------------------ #
    # Pre-movement heading alignment                                       #
    # ------------------------------------------------------------------ #

    def align_for_heading(
        self,
        target_deg: float,
        stop_event: threading.Event,
        tolerance: float = 15.0,
    ) -> bool:
        """
        Align camera to a specific heading before a walk segment begins.
        Calls align_to_heading() after ensuring the camera is in a usable state.
        """
        if stop_event.is_set():
            return False

        # If the camera is too uncertain, normalize first
        if self._cam.heading_uncertainty > _HEADING_UNCERTAIN_THRESHOLD:
            log.debug("CameraState: high uncertainty (%.1f°) — normalizing before align",
                      self._cam.heading_uncertainty)
            if not self._cam.normalize(stop_event):
                return False
            self._last_norm = time.monotonic()

        return self._cam.align_to_heading(target_deg, stop_event, tolerance)

    # ------------------------------------------------------------------ #
    # Camera presets                                                      #
    # ------------------------------------------------------------------ #

    def apply_preset(
        self,
        preset: CameraPreset,
        stop_event: threading.Event,
    ) -> bool:
        """
        Apply a named camera preset before traversal.

        TRAVERSAL:   F-reset only (standard normalization)
        FIELD_FARM:  F-reset + 15° right rotation for slight downward visibility
        CANNON_PREP: F-reset (cannon alignment done per-anchor via align_for_anchor)
        RECOVERY:    Force F-reset regardless of age/uncertainty
        """
        if stop_event.is_set():
            return False

        if preset == CameraPreset.RECOVERY:
            return self.ensure_traversal_state(stop_event, force=True)

        if preset == CameraPreset.TRAVERSAL:
            return self.ensure_traversal_state(stop_event)

        if preset == CameraPreset.FIELD_FARM:
            ok = self.ensure_traversal_state(stop_event)
            if ok and not stop_event.is_set():
                # Slight right rotation for better field coverage
                self._cam.rotate(1)
            return ok

        if preset == CameraPreset.CANNON_PREP:
            # Cannon alignment is handled by align_for_anchor per cannon definition
            return self.ensure_traversal_state(stop_event)

        return self.ensure_traversal_state(stop_event)

    # ------------------------------------------------------------------ #
    # State queries                                                        #
    # ------------------------------------------------------------------ #

    @property
    def is_traversal_ready(self) -> bool:
        """True when camera is in an acceptable state for traversal."""
        age = time.monotonic() - self._last_norm
        return (
            self._last_norm > 0.0
            and age <= _NORMALIZE_MAX_AGE
            and self._cam.heading_uncertainty <= _HEADING_UNCERTAIN_THRESHOLD
        )

    @property
    def heading(self) -> float:
        return self._cam.heading

    @property
    def heading_uncertainty(self) -> float:
        return self._cam.heading_uncertainty

    @property
    def heading_confidence(self) -> float:
        """Normalized [0, 1] confidence in the heading estimate."""
        unc = self._cam.heading_uncertainty
        return max(0.0, min(1.0, 1.0 - unc / 180.0))


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[CameraStateManager] = None
_inst_lock = threading.Lock()


def get_camera_state_manager() -> CameraStateManager:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = CameraStateManager()
    return _instance
