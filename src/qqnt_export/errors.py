from __future__ import annotations


class SafeFailure(Exception):
    """An error whose message is safe to show without inspecting its cause."""

    def __init__(self, stage: str, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.stage = stage
        self.code = code
        self.public_message = public_message

    def __repr__(self) -> str:
        return f"SafeFailure(stage={self.stage!r}, code={self.code!r}, public_message={self.public_message!r})"


class ExportCancelled(Exception):
    """A user-requested stop, separate from export failures."""
