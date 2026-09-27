#!/usr/bin/env python3
"""Translate the official Proton VPN CLI into the widget's JSON protocol.

No Proton Python imports. The read-only server cache supplies city metadata
and country-scoped server selection (CLI 1.0 ignores --country with --city).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
SERVERLIST_PATH = CACHE_HOME / "Proton/VPN/serverlist.json"
LOCK_PATH = CACHE_HOME / "omarchy-protonvpn/cli.lock"
SKIP_FEATURES = 1 | 2  # Secure Core and Tor need explicit opt-in.


class CliError(RuntimeError):
    pass


class CLI:
    def __init__(self, seconds=13):
        self.deadline = time.monotonic() + seconds

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise CliError("Proton VPN CLI timed out")
        return remaining

    def run(self, *args):
        try:
            result = subprocess.run(
                ["protonvpn", *args], stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=self.remaining(),
                env=dict(os.environ, LC_ALL="C.UTF-8", LANG="C.UTF-8", NO_COLOR="1"),
            )
        except FileNotFoundError as exc:
            raise CliError("Install proton-vpn-cli to use this widget") from exc
        except subprocess.TimeoutExpired as exc:
            raise CliError("Proton VPN CLI timed out") from exc
        output = result.stdout + "\n" + result.stderr
        # The GUI-running guard in CLI 1.0 exits successfully after printing Error.
        error = re.search(r"^\s*Error:\s*(.+)$", output, re.MULTILINE)
        if error:
            raise CliError(error.group(1).strip()[:250])
        if result.returncode or "Traceback (most recent call last)" in output:
            raise CliError(f"Proton VPN CLI {args[0]} failed; run it in a terminal for details")
        return result.stdout


def server_cache():
    try:
        data = json.loads(SERVERLIST_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("LogicalServers"), list):
            raise ValueError
        return data
    except (OSError, ValueError):
        return {}


def available_servers(data):
    try:
        tier = int(data["MaxTier"])
    except (KeyError, ValueError, TypeError):
        return []  # Do not assume access to paid servers when metadata is missing.
    result = []
    for server in data.get("LogicalServers", []):
        if not isinstance(server, dict):
            continue
        try:
            if (server.get("Status") == 1 and int(server["Tier"]) <= tier
                    and not int(server["Features"]) & SKIP_FEATURES
                    and re.fullmatch(r"[A-Z]{2}", server.get("ExitCountry", ""))
                    and isinstance(server.get("Name"), str)):
                result.append(server)
        except (KeyError, ValueError, TypeError):
            continue
    return result


def parse_countries(output):
    # tabulate's simple format separates the name and code by >=2 spaces.
    if not re.search(r"^Country\s+Code\s*$", output, re.MULTILINE):
        raise CliError("Unrecognized Proton VPN country list")
    countries = []
    for line in output.splitlines():
        match = re.fullmatch(r"(.+?)\s{2,}([A-Z]{2})\s*", line)
        if match:
            countries.append({"code": match[2], "name": match[1].strip(), "cities": []})
    if not countries:
        raise CliError("Proton VPN returned no countries")
    return countries


def countries(cli):
    result = parse_countries(cli.run("countries", "list"))
    # This command refreshes Proton's server cache before we read city metadata.
    servers = available_servers(server_cache())
    grouped = {}
    for server in servers:
        group = grouped.setdefault(server["ExitCountry"], [])
        group.append(server)
    for country in result:
        entries = grouped.get(country["code"], [])
        country["servers"] = len(entries)
        cities = {}
        for entry in entries:
            city = str(entry.get("City") or "").strip()
            if city:
                cities[city] = cities.get(city, 0) + 1
        country["cities"] = [{"name": name, "servers": count}
                             for name, count in sorted(cities.items(), key=lambda pair: pair[0].casefold())]
    return {"ok": True, "countries": result}


def parse_status(output):
    matches = re.findall(r"^Status: (Connected|Disconnected)\s*$", output, re.MULTILINE)
    if len(matches) != 1:
        raise CliError("Unrecognized Proton VPN status")
    result = dict(ok=True, backend="cli", connected=matches[0] == "Connected",
                  loggedIn=True, country="", countryName="", city="", server="", load=None, error="")
    if not result["connected"]:
        return result
    server = re.search(r"^Server: (\S+) in (.+)$", output, re.MULTILINE)
    load = re.search(r"^Load: (\d+)%\s*$", output, re.MULTILINE)
    if not server:
        raise CliError("Incomplete Proton VPN connected status")
    result["server"] = server[1]
    result["countryName"] = server[2].strip().split(", ")[-1]
    result["load"] = int(load[1]) if load else None
    for cached in server_cache().get("LogicalServers", []):
        if isinstance(cached, dict) and cached.get("Name") == server[1]:
            result["country"] = str(cached.get("ExitCountry") or "")
            result["city"] = str(cached.get("City") or "")
            break
    return result


def status(cli):
    result = parse_status(cli.run("status"))
    if not result["connected"]:
        account = re.search(r"^Account: '(.*)'\s*$", cli.run("info"), re.MULTILINE)
        if not account:
            raise CliError("Unrecognized Proton VPN account status")
        result["loggedIn"] = account[1] not in ("", "None")
    return result


def city_server(city, country):
    candidates = [s for s in available_servers(server_cache())
                  if s["ExitCountry"] == country and str(s.get("City") or "").casefold() == city.casefold()]
    def score(server):
        try:
            value = float(server["Score"])
            return value if math.isfinite(value) else math.inf
        except (KeyError, TypeError, ValueError):
            return math.inf
    if not candidates:
        raise CliError("No available server in that city and country; refresh the location list")
    return min(candidates, key=score)["Name"]


def connect(cli, target, value, country):
    selected = ""
    if target == "fastest":
        args = ["connect"]
    elif target == "country":
        if not re.fullmatch(r"[A-Z]{2}", value):
            raise CliError("Country must be a two-letter code")
        args = ["connect", "--country", value]
    elif target == "city":
        if not value or not re.fullmatch(r"[A-Z]{2}", country):
            raise CliError("City selection needs a city and a two-letter country code")
        cli.run("cities", "list", country)  # Refresh metadata, validate country/auth.
        selected = city_server(value, country)
        args = ["connect", "--", selected]
    else:
        raise CliError("Unknown connection target")
    output = cli.run(*args)
    if not re.search(r"^Connected to \S+ in .+", output, re.MULTILINE):
        raise CliError("Proton VPN did not confirm a connection")
    result = status(cli)
    if not result["connected"] or (selected and result["server"] != selected):
        raise CliError("Proton VPN did not reach the requested connection")
    if target == "country" and result["country"] and result["country"] != value:
        raise CliError("Proton VPN connected to a different country")
    return result


def disconnect(cli):
    output = cli.run("disconnect")
    if not re.search(r"^Disconnected\.\s*$", output, re.MULTILINE):
        raise CliError("Proton VPN did not confirm disconnection")
    result = status(cli)
    if result["connected"]:
        raise CliError("Proton VPN is still connected")
    return result


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "countries", "disconnect"):
        commands.add_parser(command)
    action = commands.add_parser("connect")
    action.add_argument("target", choices=("fastest", "country", "city"), default="fastest", nargs="?")
    action.add_argument("value", default="", nargs="?")
    action.add_argument("--country", default="")
    args = parser.parse_args(argv)
    cli = CLI(55 if args.command in ("connect", "disconnect") else 13)
    try:
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOCK_PATH.open("a") as lock:
            # Status, list and action helpers share one CLI session at a time.
            while True:
                cli.remaining()
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(.05)
            if args.command == "connect":
                result = connect(cli, args.target, args.value.upper() if args.target == "country" else args.value,
                                 args.country.upper())
            else:
                result = {"status": status, "countries": countries, "disconnect": disconnect}[args.command](cli)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (CliError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
