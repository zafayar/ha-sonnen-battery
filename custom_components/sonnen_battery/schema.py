"""The schema library Home Assistant uses.

Newer Home Assistant validates with probatio (voluptuous-compatible) and aliases
`voluptuous` to it. Importing probatio directly keeps type checking accurate;
older versions only have voluptuous.
"""

try:
    import probatio as vol
except ImportError:  # pragma: no cover - Home Assistant before probatio
    import voluptuous as vol  # type: ignore[no-redef]

__all__ = ["vol"]
