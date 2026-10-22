"""HTTP client: headers, error mapping and reply normalisation."""

from __future__ import annotations

from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.sonnen_battery.api import (
    SonnenApi,
    SonnenAuthError,
    SonnenConnectionError,
    normalise_host,
    normalise_powermeter,
)

from .conftest import HOST, TOKEN, load_fixture


@pytest.fixture
async def api(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> SonnenApi:
    # Depends on aioclient_mock so the session is the mocked one, never a real one.
    return SonnenApi(async_get_clientsession(hass), "192.168.1.50", TOKEN)


async def test_sends_token_and_parses_status(api: SonnenApi, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{HOST}/api/v2/status", json=load_fixture("status.json"))
    status = await api.async_get_status()
    assert status["USOC"] == 55
    _, _, _, headers = aioclient_mock.mock_calls[0]
    assert headers["Auth-Token"] == TOKEN


@pytest.mark.parametrize("code", [401, 403])
async def test_rejected_token(api: SonnenApi, aioclient_mock: AiohttpClientMocker, code: int) -> None:
    aioclient_mock.get(f"{HOST}/api/v2/status", status=code)
    with pytest.raises(SonnenAuthError):
        await api.async_get_status()


async def test_server_error(api: SonnenApi, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{HOST}/api/v2/status", status=500)
    with pytest.raises(SonnenConnectionError):
        await api.async_get_status()


@pytest.mark.parametrize("exc", [TimeoutError(), aiohttp.ClientConnectionError()])
async def test_network_errors(api: SonnenApi, aioclient_mock: AiohttpClientMocker, exc) -> None:
    aioclient_mock.get(f"{HOST}/api/v2/status", exc=exc)
    with pytest.raises(SonnenConnectionError):
        await api.async_get_status()


async def test_invalid_json(api: SonnenApi, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{HOST}/api/v2/status", text="<html>not json</html>")
    with pytest.raises(SonnenConnectionError):
        await api.async_get_status()


async def test_unexpected_shape(api: SonnenApi, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{HOST}/api/v2/battery", json=[1, 2, 3])
    with pytest.raises(SonnenConnectionError):
        await api.async_get_battery()


async def test_set_configuration(api: SonnenApi, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.put(f"{HOST}/api/v2/configurations", json={"EM_USOC": "20"})
    assert await api.async_set_configuration("EM_USOC", "20") == {"EM_USOC": "20"}
    _, _, data, headers = aioclient_mock.mock_calls[0]
    assert data == {"EM_USOC": "20"}
    assert headers["Auth-Token"] == TOKEN


async def test_set_configuration_sends_json(api: SonnenApi, aioclient_mock: AiohttpClientMocker) -> None:
    """A JSON body, as sonnen's own library sends it; not form data."""
    aioclient_mock.put(f"{HOST}/api/v2/configurations", json={})
    session = api._session
    with patch.object(session, "request", wraps=session.request) as request:
        await api.async_set_configuration("EM_OperatingMode", 2)
    kwargs = request.call_args.kwargs
    assert kwargs["json"] == {"EM_OperatingMode": "2"}
    assert "data" not in kwargs


async def test_return_code_reply_is_an_error(api: SonnenApi, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{HOST}/api/v2/status", json={"ReturnCode": 503})
    with pytest.raises(SonnenConnectionError, match="503"):
        await api.async_get_status()


async def test_latest_data(api: SonnenApi, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{HOST}/api/v2/latestdata", json=load_fixture("latestdata.json"))
    assert (await api.async_get_latest_data())["ic_status"]["secondssincefullcharge"] == 7200


async def test_powermeter_dict_reply(api: SonnenApi, aioclient_mock: AiohttpClientMocker) -> None:
    meters = load_fixture("powermeter.json")
    aioclient_mock.get(f"{HOST}/api/v2/powermeter", json={"2": meters[1], "1": meters[0]})
    assert await api.async_get_powermeter() == meters


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("192.168.1.50", "http://192.168.1.50"),
        (" 192.168.1.50/ ", "http://192.168.1.50"),
        ("http://battery.local:8080", "http://battery.local:8080"),
        ("https://battery.local", "https://battery.local"),
    ],
)
def test_normalise_host(host: str, expected: str) -> None:
    assert normalise_host(host) == expected


def test_normalise_powermeter_rejects_garbage() -> None:
    with pytest.raises(SonnenConnectionError):
        normalise_powermeter("nope")
    assert normalise_powermeter([{"a": 1}, "junk"]) == [{"a": 1}]


@pytest.mark.parametrize("direction", ["charge", "discharge"])
async def test_power_setpoint(api: SonnenApi, aioclient_mock: AiohttpClientMocker, direction: str) -> None:
    # The battery answers setpoints with an empty body; that's a success.
    aioclient_mock.post(f"{HOST}/api/v2/setpoint/{direction}/1500", text="")
    await api.async_set_power_setpoint(direction, 1500)
    assert aioclient_mock.call_count == 1


@pytest.mark.parametrize(("direction", "watts"), [("up", 100), ("charge", -5)])
async def test_power_setpoint_rejects_bad_input(api: SonnenApi, direction: str, watts: int) -> None:
    with pytest.raises(ValueError):
        await api.async_set_power_setpoint(direction, watts)
