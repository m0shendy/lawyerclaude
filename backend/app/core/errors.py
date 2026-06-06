"""Application error type producing the standard error envelope.

Every error response in the API uses the shape::

    {"error": {"code": "<lower_snake_code>", "message": "<human message>"}}

Services raise :class:`ApiError`; the handlers installed in ``app.main``
translate it (and framework exceptions) into that envelope.
"""


class ApiError(Exception):
    """Raise from services/routers to return a structured error response.

    Args:
        status_code: HTTP status code for the response.
        code: machine-readable lower_snake code (e.g. ``not_found``,
            ``forbidden``, ``invalid_state``, ``review_gate_blocked``).
        message: human-readable message.
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
