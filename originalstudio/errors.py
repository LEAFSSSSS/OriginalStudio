class StudioError(Exception):
    """An expected failure that is safe to explain to the local user."""

    def __init__(self, message: str, code: str = "invalid_request", status: int = 422):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
