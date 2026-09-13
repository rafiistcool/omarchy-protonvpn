#!/usr/bin/env python3
"""JSON control plane for the rafi.protonvpn Omarchy plugin.

Talks to the same Proton VPN Python API the GTK app uses. Prints one JSON
object on stdout. Proton's own loggers are kept off stdout so the shell can
parse the result.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

SECURE_CORE = 1
TOR = 2
SKIP_FEATURES = SECURE_CORE | TOR
CONNECT_TIMEOUT_SEC = 45
PROTON0 = Path("/sys/class/net/proton0")
CACHE = Path.home() / ".cache" / "Proton" / "VPN"
SERVERLIST_PATH = CACHE / "serverlist.json"
PERSISTENCE_PATH = CACHE / "connection" / "connection_persistence.json"


def _silence_loggers() -> None:
    logging.basicConfig(level=logging.CRITICAL, stream=sys.stderr)
    logging.getLogger().setLevel(logging.CRITICAL)
    for name in ("proton", "proton.vpn", "proton.session"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def emit(payload: dict[str, Any], code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return code


def fail(message: str, **extra: Any) -> int:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return emit(payload, 1)


def proton0_up() -> bool:
    if not PROTON0.exists():
        return False
    oper = PROTON0 / "operstate"
    if not oper.exists():
        return True
    try:
        state = oper.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return True
    return state in ("up", "unknown", "dormant")


def load_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def country_name(code: str) -> str:
    try:
        from proton.vpn.session.servers.country_codes import get_country_name_by_code

        return str(get_country_name_by_code(code) or code)
    except Exception:
        return code


def lookup_server(server_id: str, server_name: str) -> dict[str, Any]:
    data = load_json(SERVERLIST_PATH) or {}
    logicals = data.get("LogicalServers") or []
    if not isinstance(logicals, list):
        return {}
    sid = str(server_id or "")
    name = str(server_name or "")
    for server in logicals:
        if not isinstance(server, dict):
            continue
        if (sid and str(server.get("ID") or "") == sid) or (
            name and str(server.get("Name") or "") == name
        ):
            code = str(server.get("ExitCountry") or "").upper()
            return {
                "country": code,
                "countryName": country_name(code) if code else "",
                "city": str(server.get("City") or ""),
                "server": str(server.get("Name") or name),
                "load": server.get("Load"),
            }
    if name:
        return {"server": name}
    return {}


def persistence_server() -> dict[str, Any]:
    data = load_json(PERSISTENCE_PATH) or {}
    server = data.get("server") or {}
    if not isinstance(server, dict):
        return {}
    return lookup_server(str(server.get("server_id") or ""), str(server.get("server_name") or ""))


def is_logged_in() -> bool:
    try:
        from proton.vpn.core.api import ProtonVPNAPI
        from proton.vpn.core.session_holder import ClientTypeMetadata

        with contextlib.redirect_stdout(io.StringIO()):
            api = ProtonVPNAPI(ClientTypeMetadata(type="cli"))
            return bool(api.is_user_logged_in())
    except Exception:
        return False


def cmd_status() -> int:
    connected = proton0_up()
    details = persistence_server() if connected else {}
    logged_in = True if connected else is_logged_in()
    return emit(
        {
            "ok": True,
            "loggedIn": logged_in,
            "connected": connected,
            "country": details.get("country") or "",
            "countryName": details.get("countryName") or "",
            "city": details.get("city") or "",
            "server": details.get("server") or "",
            "load": details.get("load"),
            "error": "",
        }
    )


def cmd_countries() -> int:
    data = load_json(SERVERLIST_PATH)
    if not data:
        return fail("Server list cache is missing. Open Proton VPN once to refresh it.")

    max_tier = data.get("MaxTier")
    try:
        max_tier_n = int(max_tier) if max_tier is not None else 99
    except (TypeError, ValueError):
        max_tier_n = 99

    grouped: dict[str, dict[str, Any]] = {}
    logicals = data.get("LogicalServers") or []
    if not isinstance(logicals, list):
        return fail("Server list cache is unreadable.")

    for server in logicals:
        if not isinstance(server, dict):
            continue
        if server.get("Status") != 1:
            continue
        try:
            features = int(server.get("Features") or 0)
        except (TypeError, ValueError):
            features = 0
        if features & SKIP_FEATURES:
            continue
        try:
            tier = int(server.get("Tier") or 0)
        except (TypeError, ValueError):
            tier = 0
        if tier > max_tier_n:
            continue
        code = str(server.get("ExitCountry") or "").upper()
        if len(code) != 2:
            continue
        city = str(server.get("City") or "").strip()
        entry = grouped.get(code)
        if entry is None:
            entry = {"code": code, "name": country_name(code), "servers": 0, "cities": {}}
            grouped[code] = entry
        entry["servers"] += 1
        if city:
            cities = entry["cities"]
            cities[city] = cities.get(city, 0) + 1

    countries = []
    for entry in grouped.values():
        city_items = [
            {"name": name, "servers": count}
            for name, count in sorted(entry["cities"].items(), key=lambda item: item[0].lower())
        ]
        countries.append(
            {
                "code": entry["code"],
                "name": entry["name"],
                "servers": entry["servers"],
                "cities": city_items,
            }
        )
    countries.sort(key=lambda item: item["name"].lower())
    return emit({"ok": True, "countries": countries})


class StateWaiter:
    def __init__(self, loop: asyncio.AbstractEventLoop, targets: set[int]):
        self.loop = loop
        self.targets = targets
        self.event = asyncio.Event()
        self.state = None

    def status_update(self, state: Any) -> None:
        self.state = state
        state_type = getattr(state, "type", None)
        if state_type in self.targets:
            self.loop.call_soon_threadsafe(self.event.set)


async def _api_session():
    from proton.vpn.connection.enum import ConnectionStateEnum
    from proton.vpn.core.api import ProtonVPNAPI
    from proton.vpn.core.session_holder import ClientTypeMetadata
    from proton.vpn.core.vpnconnector import VPNConnector
    from proton.vpn.session.exceptions import ServerNotFoundError

    api = ProtonVPNAPI(ClientTypeMetadata(type="cli"))
    if not api.is_user_logged_in():
        raise RuntimeError("Not signed in. Open Proton VPN and sign in first.")

    await api.refresher.get_up_to_date_server_list()
    await api.refresher.get_up_to_date_client_config()
    connector = await api.get_vpn_connector()
    return api, connector, ConnectionStateEnum, ServerNotFoundError, VPNConnector


async def _wait_for(connector: Any, targets: set[int], timeout: int) -> Any:
    loop = asyncio.get_running_loop()
    waiter = StateWaiter(loop, targets)
    current = getattr(connector, "current_state", None)
    if current is not None and getattr(current, "type", None) in targets:
        return current
    connector.register(waiter)
    try:
        await asyncio.wait_for(waiter.event.wait(), timeout=timeout)
        return waiter.state
    except asyncio.TimeoutError as exc:
        raise TimeoutError("Timed out waiting for Proton VPN") from exc
    finally:
        with contextlib.suppress(Exception):
            connector.unregister(waiter)


async def _connect(kind: str, value: str) -> dict[str, Any]:
    from proton.vpn.connection.enum import ConnectionStateEnum

    api, connector, _enum, ServerNotFoundError, _cls = await _api_session()
    server_list = api.server_list
    try:
        if kind == "fastest":
            logical = server_list.get_fastest()
        elif kind == "country":
            logical = server_list.get_fastest_in_country(value)
        elif kind == "city":
            logical = server_list.get_fastest_in_city(value)
        else:
            raise RuntimeError(f"Unknown connect kind: {kind}")
    except ServerNotFoundError as exc:
        raise RuntimeError(str(exc) or "No server available for that location") from exc

    if logical is None:
        raise RuntimeError("No server available for that location")

    settings = await api.load_settings()
    vpn_server = connector.get_vpn_server(logical, api.client_config)
    await connector.connect(vpn_server, protocol=getattr(settings, "protocol", None))
    state = await _wait_for(
        connector,
        {ConnectionStateEnum.CONNECTED, ConnectionStateEnum.ERROR},
        CONNECT_TIMEOUT_SEC,
    )
    state_type = getattr(state, "type", None)
    if state_type == ConnectionStateEnum.ERROR:
        raise RuntimeError("Proton VPN failed to connect")
    if state_type != ConnectionStateEnum.CONNECTED:
        raise RuntimeError("Proton VPN did not reach connected state")

    code = str(getattr(logical, "exit_country", "") or "").upper()
    return {
        "ok": True,
        "connected": True,
        "loggedIn": True,
        "country": code,
        "countryName": country_name(code) if code else "",
        "city": str(getattr(logical, "city", "") or ""),
        "server": str(getattr(logical, "name", "") or ""),
        "load": getattr(logical, "load", None),
        "error": "",
    }


async def _disconnect() -> dict[str, Any]:
    from proton.vpn.connection.enum import ConnectionStateEnum

    _api, connector, _enum, _err, _cls = await _api_session()
    if not connector.is_connection_active and not proton0_up():
        return {
            "ok": True,
            "connected": False,
            "loggedIn": True,
            "country": "",
            "countryName": "",
            "city": "",
            "server": "",
            "load": None,
            "error": "",
        }
    await connector.disconnect()
    await _wait_for(connector, {ConnectionStateEnum.DISCONNECTED, ConnectionStateEnum.ERROR}, CONNECT_TIMEOUT_SEC)
    return {
        "ok": True,
        "connected": False,
        "loggedIn": True,
        "country": "",
        "countryName": "",
        "city": "",
        "server": "",
        "load": None,
        "error": "",
    }


def run_async(coro: Any) -> dict[str, Any]:
    with contextlib.redirect_stdout(io.StringIO()):
        return asyncio.run(coro)


def cmd_connect(kind: str, value: str) -> int:
    try:
        payload = run_async(_connect(kind, value))
    except Exception as exc:
        return fail(str(exc) or "Connect failed")
    return emit(payload)


def cmd_disconnect() -> int:
    try:
        payload = run_async(_disconnect())
    except Exception as exc:
        return fail(str(exc) or "Disconnect failed")
    return emit(payload)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ctl.py", add_help=True)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Connection snapshot")
    sub.add_parser("countries", help="Country and city list from cache")

    connect = sub.add_parser("connect", help="Connect to a location")
    connect.add_argument("target", nargs="?", default="fastest")
    connect.add_argument("value", nargs="?")

    sub.add_parser("disconnect", help="Disconnect Proton VPN")
    return parser.parse_args(argv)


def connect_kind(target: str, value: Optional[str]) -> tuple[str, str]:
    raw = str(target or "fastest").strip()
    extra = str(value or "").strip()
    lowered = raw.lower()
    if lowered in ("fastest", "quick"):
        return "fastest", ""
    if lowered in ("country", "cc"):
        if not extra:
            raise ValueError("connect country needs a country code")
        return "country", extra.upper()
    if lowered in ("city",):
        if not extra:
            raise ValueError("connect city needs a city name")
        return "city", extra
    if len(raw) == 2 and raw.isalpha() and not extra:
        return "country", raw.upper()
    raise ValueError("Usage: connect fastest | connect country DE | connect city Berlin")


def main(argv: list[str]) -> int:
    _silence_loggers()
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code == 0:
            return 0
        return fail("Invalid arguments")

    if args.command == "status":
        return cmd_status()
    if args.command == "countries":
        return cmd_countries()
    if args.command == "disconnect":
        return cmd_disconnect()
    if args.command == "connect":
        try:
            kind, value = connect_kind(args.target, args.value)
        except ValueError as exc:
            return fail(str(exc))
        return cmd_connect(kind, value)
    return fail("Unknown command")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
