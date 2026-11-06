"""
TemplateSystem — centralized, cached multi-scale template matching.

Improvements over detection/template_matcher.py:
  - Templates loaded from disk once and cached in memory indefinitely
  - Named template groups: scan multiple templates in one call
  - Structured MatchResult with position, confidence, and matched scale
  - Retina-aware: the caller passes a BGR frame; scaling is handled internally
  - Region-restricted: pass a crop to limit search to a known HUD area
  - Thread-safe: template cache uses a RLock; frame ops are stateless

Architecture:
    TemplateSystem is read-only at runtime — it never writes templates.
    The calibration tool writes new PNGs; call ts.invalidate() to reload.
    Templates live in templates/ (flat) or templates/<subdir>/ (grouped).

Multi-scale strategy:
    Tries scales [1.0, 0.75, 1.25, 0.5] against the input frame.
    On Retina displays captured images may be 2× or 0.5× of template size
    depending on how the template was captured vs the runtime capture.
    The scale that yields the highest match score wins.

Public API:
    ts = get_template_system()

    # Single template
    r = ts.match("hive_exterior", frame)
    if r.found:
        print(r.center, r.confidence)

    # Group scan — returns sorted list; stop_on_first for early exit
    rs = ts.match_group("death_indicators", frame, threshold=0.85)

    # Landmark sub-directory
    r = ts.match("spawn_platform", frame, subdir="landmarks")
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Scale factors tried in order (first match that exceeds threshold wins,
# but we always scan all scales and keep the best overall score)
_SCALES = (1.0, 0.75, 1.25, 0.5)


@dataclass
class MatchResult:
    name:        str
    found:       bool
    confidence:  float                            # 0–1 from TM_CCOEFF_NORMED
    rect:        Tuple[int, int, int, int] = (0, 0, 0, 0)   # (x, y, w, h) in crop/frame pixels
    center:      Tuple[int, int]           = (0, 0)          # (cx, cy)
    scale:       float                     = 1.0             # which scale matched best


# ── Named template groups ──────────────────────────────────────────────────────
# Groups let callers scan a logical set in one call.  Add new entries freely;
# unknown group names return an empty list.

GROUPS: Dict[str, List[str]] = {
    "death_indicators": [
        "respawn_screen",
        "death_notification",
        "respawn_button",
    ],
    "hive_indicators": [
        "hive_exterior",
        "hive_door",
        "hive_interior",
    ],
    "field_identifiers": [
        "sunflower_field",
        "dandelion_field",
        "bamboo_field",
        "clover_field",
        "blue_flower_field",
        "strawberry_field",
        "stump_field",
        "rose_field",
        "pineapple_patch",
        "pine_tree_forest",
        "mushroom_platform",
    ],
    "navigation_anchors": [
        "spawn_platform",
        "red_cannon",
        "hive_exterior",
        "upper_platform",
    ],
    "wealth_clock_indicators": [
        "wealth_clock_face",
        "wealth_clock_prompt",
    ],
    "mob_indicators": [
        "mob_health_bar",
        "ladybug_mob",
        "rhino_beetle_mob",
    ],
}


class TemplateSystem:
    """
    Thread-safe, in-memory-cached template matcher.

    Missing templates produce MatchResult(found=False, confidence=0.0) —
    never raise exceptions.  This makes it safe to reference templates
    that have not yet been captured via calibration.
    """

    def __init__(self) -> None:
        self._lock  = threading.RLock()
        self._cache: Dict[str, Optional[np.ndarray]] = {}

    # ------------------------------------------------------------------ #
    # Single template match                                                #
    # ------------------------------------------------------------------ #

    def match(
        self,
        name: str,
        frame: np.ndarray,
        threshold: float = 0.80,
        multi_scale: bool = True,
        subdir: str = "",
    ) -> MatchResult:
        """
        Find template <name> inside frame (BGR).

        name:        template filename without .png extension
        frame:       full-frame or region crop in BGR format
        threshold:   minimum confidence to count as found
        multi_scale: try multiple scales to handle Retina / zoom variation
        subdir:      subdirectory under templates/ (e.g. "landmarks")
        """
        try:
            import cv2
        except ImportError:
            return MatchResult(name=name, found=False, confidence=0.0)

        tmpl = self._load(name, subdir)
        if tmpl is None:
            return MatchResult(name=name, found=False, confidence=0.0)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        th0, tw0 = tmpl.shape[:2]
        fh,  fw  = gray.shape[:2]

        best_val   = 0.0
        best_loc   = (0, 0)
        best_scale = 1.0
        best_tw    = tw0
        best_th    = th0

        scales = _SCALES if multi_scale else (1.0,)

        for scale in scales:
            tw = max(1, int(tw0 * scale))
            th = max(1, int(th0 * scale))
            if th > fh or tw > fw:
                continue

            resized = cv2.resize(tmpl, (tw, th))
            result  = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > best_val:
                best_val   = float(max_val)
                best_loc   = max_loc
                best_scale = scale
                best_tw    = tw
                best_th    = th

        found  = best_val >= threshold
        x, y   = best_loc
        cx, cy = x + best_tw // 2, y + best_th // 2

        return MatchResult(
            name=name,
            found=found,
            confidence=round(best_val, 3),
            rect=(x, y, best_tw, best_th),
            center=(cx, cy),
            scale=best_scale,
        )

    # ------------------------------------------------------------------ #
    # Group match                                                          #
    # ------------------------------------------------------------------ #

    def match_group(
        self,
        group: str,
        frame: np.ndarray,
        threshold: float = 0.80,
        stop_on_first: bool = True,
        subdir: str = "",
    ) -> List[MatchResult]:
        """
        Match all templates in a named group.

        Returns a list sorted by confidence descending.
        stop_on_first=True exits immediately when a result exceeds threshold,
        saving CPU on groups like "death_indicators" where any match is conclusive.
        """
        names = GROUPS.get(group, [])
        results: List[MatchResult] = []

        for name in names:
            r = self.match(name, frame, threshold, subdir=subdir)
            results.append(r)
            if stop_on_first and r.found:
                break

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def best_in_group(
        self,
        group: str,
        frame: np.ndarray,
        threshold: float = 0.80,
    ) -> Optional[MatchResult]:
        """Return the single highest-confidence match in a group, or None."""
        results = self.match_group(group, frame, threshold, stop_on_first=False)
        if results and results[0].found:
            return results[0]
        return None

    # ------------------------------------------------------------------ #
    # Template management                                                  #
    # ------------------------------------------------------------------ #

    def invalidate(self, name: Optional[str] = None, subdir: str = "") -> None:
        """
        Evict one or all cached templates.
        Call after calibration captures new reference images.
        """
        with self._lock:
            if name:
                key = f"{subdir}/{name}" if subdir else name
                self._cache.pop(key, None)
            else:
                self._cache.clear()

    def has_template(self, name: str, subdir: str = "") -> bool:
        """True if the template PNG exists on disk (does not load it)."""
        return self._path(name, subdir).exists()

    def list_available(self, subdir: str = "") -> List[str]:
        """List names of all template PNGs in a directory (stems only)."""
        base = (_TEMPLATES_DIR / subdir) if subdir else _TEMPLATES_DIR
        if not base.exists():
            return []
        return sorted(p.stem for p in base.glob("*.png"))

    def add_group(self, name: str, templates: List[str]) -> None:
        """Register a new named group at runtime (e.g. for calibration tool)."""
        GROUPS[name] = templates

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _load(self, name: str, subdir: str) -> Optional[np.ndarray]:
        key = f"{subdir}/{name}" if subdir else name
        with self._lock:
            if key in self._cache:
                return self._cache[key]

        path = self._path(name, subdir)
        tmpl: Optional[np.ndarray] = None
        if path.exists():
            try:
                import cv2
                raw = cv2.imread(str(path))
                if raw is not None:
                    tmpl = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
                else:
                    log.warning("cv2.imread returned None for: %s", path)
            except Exception as exc:
                log.debug("Template load error %s: %s", name, exc)
        else:
            log.debug("Template not found: %s", path)

        with self._lock:
            self._cache[key] = tmpl
        return tmpl

    def _path(self, name: str, subdir: str) -> Path:
        base = (_TEMPLATES_DIR / subdir) if subdir else _TEMPLATES_DIR
        return base / f"{name}.png"


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[TemplateSystem] = None
_inst_lock = threading.Lock()


def get_template_system() -> TemplateSystem:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = TemplateSystem()
    return _instance
