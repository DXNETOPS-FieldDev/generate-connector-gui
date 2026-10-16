"""API schema constants for AppNeta alarm connector payloads."""

VALID_SEVERITIES    = frozenset({"CLEARED", "CRITICAL", "INDETERMINATE", "MAJOR", "MINOR", "WARNING"})
VALID_NOISE_FILTERS = frozenset({"FREQUENT"})
VALID_NOTIFY_ON     = frozenset({"ALARM_RAISED", "ALARM_CLEARED"})
VALID_METHODS       = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})
VALID_AUTH_TYPES    = frozenset({"NONE", "BASIC", "BEARER"})
_GLOB_CHARS         = frozenset("*?!+")

# The n10 is AppNeta's software agent; the API represents it as two separate
# type strings depending on the host OS. "n10" is not a value the API returns.
_MP_TYPE_ALIASES: dict[str, list[str]] = {
    "n10": ["Windows", "macOS"],
}
