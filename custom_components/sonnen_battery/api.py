"""Client for the sonnenBatterie local JSON API (v2, token based).

No Home Assistant imports, so it can be tested on its own.
"""

from __future__ import annotations

import json
from typing import Any

import aiohttp

AUTH_HEADER = "Auth-Token"
DEFAULT_TIMEOUT = 10
SETPOINT_DIRECTIONS = ("charge", "discharge")


class SonnenError(Exception):
    """Base error for the sonnen API."""


class SonnenConnectionError(SonnenError):
    """The battery could not be reached or gave an unusable reply."""


class SonnenAuthError(SonnenError):
    """The API token was rejected."""


class SonnenApi:
    """Talks to one sonnenBatterie on the local network."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._session = session
        self._base = normalise_host(host)
        self._token = token
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    @property
    def base_url(self) -> str:
        return self._base

    async def _request(self, method: str, path: str, body: dict[str, str] | None = None) -> Any:
        url = f"{self._base}/api/v2/{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers={AUTH_HEADER: self._token},
                # JSON, as sonnen's own Python library and ioBroker adapter send it.
                json=body,
                timeout=self._timeout,
            ) as resp:
                if resp.status in (401, 403):
                    raise SonnenAuthError(f"{path}: token rejected ({resp.status})")
                if resp.status >= 400:
                    raise SonnenConnectionError(f"{path}: HTTP {resp.status}")
                text = await resp.text()
        except TimeoutError as err:
            raise SonnenConnectionError(f"{path}: timed out") from err
        except aiohttp.ClientError as err:
            raise SonnenConnectionError(f"{path}: {err}") from err
        if not text.strip():
            return None  # setpoint commands may answer with an empty body
        try:
            return json.loads(text)
        except ValueError as err:
            raise SonnenConnectionError(f"{path}: invalid JSON") from err

    async def async_get_status(self) -> dict[str, Any]:
        """Live power flows, state of charge and system state."""
        return _as_dict(await self._request("GET", "status"), "status")

    async def async_get_latest_data(self) -> dict[str, Any]:
        """Status flags (ic_status): status LED, shutdown reason, last full charge."""
        return _as_dict(await self._request("GET", "latestdata"), "latestdata")

    async def async_get_powermeter(self) -> list[dict[str, Any]]:
        """The internal meters, which include lifetime kWh counters."""
        return normalise_powermeter(await self._request("GET", "powermeter"))

    async def async_get_battery(self) -> dict[str, Any]:
        """Battery module details: cycle count, state of health, temperatures."""
        return _as_dict(await self._request("GET", "battery"), "battery")

    async def async_get_configurations(self) -> dict[str, Any]:
        return _as_dict(await self._request("GET", "configurations"), "configurations")

    async def async_set_configuration(self, key: str, value: str) -> dict[str, Any]:
        """Change one setting. Needs write access enabled for the token."""
        reply = await self._request("PUT", "configurations", body={key: str(value)})
        return reply if isinstance(reply, dict) else {}

    async def async_set_power_setpoint(self, direction: str, watts: int) -> None:
        """Charge or discharge at a fixed power. Only works in manual mode."""
        if direction not in SETPOINT_DIRECTIONS or watts < 0:
            raise ValueError(f"invalid setpoint: {direction} {watts}")
        await self._request("POST", f"setpoint/{direction}/{int(watts)}")


def normalise_host(host: str) -> str:
    """'192.168.1.5' -> 'http://192.168.1.5'; keeps an explicit scheme or port."""
    host = host.strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host


def normalise_powermeter(raw: Any) -> list[dict[str, Any]]:
    """Some firmware returns the meters as a list, some as {"1": {...}, ...}."""
    if isinstance(raw, dict):
        raw = [raw[k] for k in sorted(raw, key=_index_key)]
    if not isinstance(raw, list):
        raise SonnenConnectionError("powermeter: unexpected reply")
    return [m for m in raw if isinstance(m, dict)]


def _index_key(key: str) -> tuple[int, str]:
    return (int(key), "") if str(key).isdigit() else (1 << 30, str(key))


def _as_dict(reply: Any, path: str) -> dict[str, Any]:
    if not isinstance(reply, dict):
        raise SonnenConnectionError(f"{path}: unexpected reply")
    if "ReturnCode" in reply:
        # The battery reports some errors as HTTP 200 with only a return code.
        raise SonnenConnectionError(f"{path}: battery returned code {reply['ReturnCode']}")
    return reply
