"""
Log console widget: scrolling text box that reads from LOG_QUEUE.
Must be polled via after() from the main thread — never call directly from bg threads.
"""
import queue
import logging
from typing import Optional

import customtkinter as ctk

from utils.logger import LOG_QUEUE


_LEVEL_COLORS = {
    logging.DEBUG:    "#6b7280",   # gray
    logging.INFO:     "#d1d5db",   # light
    logging.WARNING:  "#f59e0b",   # amber
    logging.ERROR:    "#ef4444",   # red
    logging.CRITICAL: "#dc2626",   # deep red
}


class LogConsole(ctk.CTkFrame):
    def __init__(self, parent, poll_ms: int = 200, max_lines: int = 500, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._poll_ms = poll_ms
        self._max_lines = max_lines
        self._line_count = 0

        self._text = ctk.CTkTextbox(self, state="disabled", wrap="word", font=("Courier", 11))
        self._text.pack(fill="both", expand=True, padx=4, pady=4)

        # Configure color tags (CTkTextbox exposes the underlying tk.Text)
        for level, color in _LEVEL_COLORS.items():
            self._text._textbox.tag_configure(f"level_{level}", foreground=color)

        self._start_polling()

    def _start_polling(self) -> None:
        self._poll()

    def _poll(self) -> None:
        processed = 0
        try:
            while processed < 30:  # drain up to 30 lines per tick
                level, msg = LOG_QUEUE.get_nowait()
                self._append(level, msg)
                processed += 1
        except queue.Empty:
            pass
        self.after(self._poll_ms, self._poll)

    def _append(self, level: int, msg: str) -> None:
        self._text.configure(state="normal")
        tag = f"level_{level}"
        self._text._textbox.insert("end", msg + "\n", tag)
        self._line_count += 1

        # Trim to max_lines
        if self._line_count > self._max_lines:
            self._text._textbox.delete("1.0", "2.0")
            self._line_count -= 1

        self._text._textbox.see("end")
        self._text.configure(state="disabled")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._line_count = 0
        self._text.configure(state="disabled")
