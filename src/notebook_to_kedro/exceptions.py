"""Project-specific exceptions."""


class NotebookLoadError(ValueError):
    """Raised when a notebook cannot be loaded under the MVP contract."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize the error with a stable diagnostic code."""
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
