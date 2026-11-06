"""Small shared widgets."""
import customtkinter as ctk


class Collapsible(ctk.CTkFrame):
    """A header button that shows or hides a body frame."""

    def __init__(self, master, title: str, open: bool = False) -> None:
        super().__init__(master, fg_color="transparent")
        self._title = title
        self._open = open
        self._btn = ctk.CTkButton(self, text="", anchor="w", fg_color="transparent", hover_color="#374151",
                                  height=26, command=self.toggle)
        self._btn.pack(fill="x")
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self._sync()

    def toggle(self) -> None:
        self._open = not self._open
        self._sync()

    def _sync(self) -> None:
        self._btn.configure(text=("v " if self._open else "> ") + self._title)
        if self._open:
            self.body.pack(fill="x", padx=4, pady=2)
        else:
            self.body.pack_forget()
