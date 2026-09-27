# Proton VPN (Omarchy plugin)

Control Proton VPN from the Omarchy bar. Toggle the tunnel, pick a country
or city, and jump to the fastest server. Uses the official `protonvpn` CLI
and your existing Proton session. Credentials are entered directly into the
CLI in a terminal, never into the widget.

## Install

```bash
omarchy plugin add https://github.com/rafiistcool/omarchy-protonvpn.git --enable --yes
```

Install the official CLI on Omarchy/Arch:

```bash
omarchy pkg add proton-vpn-cli
protonvpn signin YOUR_USERNAME
```

Alternatively, click **Sign in with Proton CLI** in the widget to open an
interactive terminal. Proton handles the password and 2FA prompts. Existing
Proton sessions can be reused. Close the GTK app before using the CLI; Proton
does not allow both clients to run simultaneously. The GTK package is not needed.

Requires Python 3, GNU `timeout`, `nmcli`, and the CLI's NetworkManager/keyring/desktop
session dependencies. Tested with `proton-vpn-cli` 1.0.3. This is a desktop
integration, not a headless VPN service.

## Use

| Action | Result |
|---|---|
| Left click | Open the panel |
| Right click | Connect (last country or fastest) / disconnect |
| Middle click | Refresh |
| Click a country | Open its cities, or connect if it has one city |
| Click a city | Connect to the fastest server there |
| Fastest | Connect to the best available server |
| `t` | Toggle |
| `/` | Search |
| `j` / `k` | Move |
| `b` | Back to countries |
| `r` | Refresh |
| `omarchy-shell rafi.protonvpn toggleVpn` | Same toggle from a keybind |
| `omarchy-shell rafi.protonvpn connectCountry DE` | Connect to Germany |
| `omarchy-shell rafi.protonvpn disconnect` | Disconnect |
| `omarchy-shell rafi.protonvpn status` | JSON snapshot |

Optional keybind in `~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + SHIFT + V", "Toggle Proton VPN", "omarchy-shell rafi.protonvpn toggleVpn")
```

## Update and validation

```bash
omarchy plugin update rafi.protonvpn
```

`omarchy update` reloads plugins; it does not pull third-party Git repositories.

From a development checkout:

```bash
node tests/model.test.cjs
python3 -m unittest discover -s tests -v
omarchy plugin validate .
```

Tests use simulated VPN responses; they do not connect or disconnect a real
VPN. The QML test requires Quickshell.

## Status and timeouts

The connected indicator follows confirmed state. A pending action has its own
status text; it never claims a tunnel exists before connection succeeds.
The adapter checks CLI output as well as exit codes, then verifies the actual
status after an action. CLI requests from the widget are serialized. Backend
errors are shown rather than treated as successful connections/disconnections.

Status/list helpers are limited to 15 seconds, connection actions to 60
seconds. Proton cache files follow `XDG_CACHE_HOME` (default `~/.cache`).

## Background CPU usage

A persistent `nmcli monitor` waits for NetworkManager events without polling.
Event bursts are combined into one status check after two seconds. A five-minute
fallback catches missed events and account changes; `refreshIntervalSec` controls
this fallback (minimum 30 seconds). Opening the panel refreshes status immediately.
No country list is loaded at startup. Opening the panel loads it on demand, then
reuses it for one hour; middle-click, `r`, or IPC refresh forces a fresh list.
Successful actions already return verified status, so they do not start a second
redundant CLI check. If the monitor exits, it is retried after one minute.

## CLI integration

The helper uses the documented `status`, `info`, `countries list`, `cities list`,
`connect`, and `disconnect` commands. It does not import Proton's internal
Python API. CLI 1.0.3 provides text output, so an unexpected format is reported
as an error instead of guessing the connection state.

City names/counts and active-server metadata come from Proton's local,
read-only `serverlist.json` cache. The CLI refreshes that cache. This also
works around CLI 1.0.3 ignoring `--country` when `--city` is supplied: the
helper selects the lowest-score available standard server in the selected
country/city, within the cached account tier, then calls `protonvpn connect`
with that explicit server name. Missing city metadata produces an error;
it never falls back to a same-named city in another country. Secure Core and
Tor servers are excluded from city selection.

Country/fastest connections remain available without city cache metadata.
Available features and location selection depend on your Proton plan.

## License

MIT

The backend is shared across monitor bars: multiple displays do not start
extra collectors, file watchers, or VPN listeners.
