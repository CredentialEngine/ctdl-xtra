"""Errors shared by the CLI and the server."""


class UserError(Exception):
    """A problem the user can fix (bad argument, missing input, refused publish). Printed without a traceback."""


class ConflictError(Exception):
    """A conditional write lost a race: the object changed since it was read (stale ETag) or already exists."""
