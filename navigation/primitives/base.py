"""
BasePrimitive — abstract base for all navigation primitive operations.

A primitive is a single, atomic, perception-driven action.  Examples:
  WalkDuration, WalkUntilAnchor, Jump, AlignHeading, ValidateAnchor, UseCannon

Each primitive:
  1. Accepts an InputInterface (for key presses) and a FrameManager (for frames)
  2. Executes its action
  3. Returns a PrimitiveResult describing what happened

Primitives are NOT responsible for high-level planning or recovery.
They are the lowest-level building blocks of a RouteEdge execution sequence.

Contract:
  - Primitives MUST check stop_event every tick
  - Primitives MUST NOT call pyautogui directly — use execution.input_interface
  - Primitives MUST NOT call mss directly — use perception.frame_manager
  - Primitives MUST NOT mutate shared state — return results, let callers decide
"""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Optional


class TerminalReason(Enum):
    SUCCESS       = auto()   # action completed as intended
    STOP_EVENT    = auto()   # external stop_event was set
    TIMEOUT       = auto()   # time limit exceeded (fallback)
    STALLED       = auto()   # no perceptible movement/progress
    ANCHOR_FOUND  = auto()   # perception-driven stop (landmark detected)
    ANCHOR_MISSED = auto()   # expected landmark not found after action
    HEADING_OK    = auto()   # camera aligned within tolerance
    HEADING_FAIL  = auto()   # camera could not align
    INPUT_ERROR   = auto()   # key input subsystem error


@dataclass
class PrimitiveResult:
    """
    Result of one primitive execution.

    success:        True if the action achieved its primary goal
    confidence:     perception confidence of the outcome [0, 1]
    elapsed_sec:    wall time the primitive ran
    terminal_reason: why the primitive stopped
    evidence:       per-signal values for debug/logging
    drift_detected: perception signals were inconsistent during execution
    """
    success:         bool
    confidence:      float
    elapsed_sec:     float
    terminal_reason: TerminalReason
    evidence:        Dict[str, float] = field(default_factory=dict)
    drift_detected:  bool = False
    message:         str = ""

    @classmethod
    def stopped(cls, elapsed: float = 0.0) -> "PrimitiveResult":
        return cls(
            success=False,
            confidence=0.0,
            elapsed_sec=elapsed,
            terminal_reason=TerminalReason.STOP_EVENT,
        )

    @classmethod
    def timeout(cls, elapsed: float, confidence: float = 0.0) -> "PrimitiveResult":
        return cls(
            success=False,
            confidence=confidence,
            elapsed_sec=elapsed,
            terminal_reason=TerminalReason.TIMEOUT,
        )


class BasePrimitive(ABC):
    """
    Abstract base for all navigation primitives.

    Subclasses implement execute() which is the single entry point.
    The stop_event is always the first check in any loop.
    """

    @abstractmethod
    def execute(self, stop_event: threading.Event) -> PrimitiveResult:
        """
        Run the primitive.

        Must be callable from the navigation thread.
        Must not block indefinitely — check stop_event every tick.
        Must return a PrimitiveResult describing what happened.
        """
        ...

    # ------------------------------------------------------------------ #
    # Shared helpers for subclasses                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _elapsed(t0: float) -> float:
        return round(time.monotonic() - t0, 4)

    @staticmethod
    def _check_stop(stop_event: threading.Event) -> bool:
        """Return True if we should abort."""
        return stop_event.is_set()
