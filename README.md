# Proton VPN (Omarchy plugin)

Control Proton VPN from the Omarchy bar. Toggle the tunnel, pick a country
or city, and jump to the fastest server. Uses the Proton VPN session already
on this machine — the same Python API as the GTK app. It never asks for a
password.

## Install

```bash
omarchy plugin add https://github.com/rafiistcool/omarchy-protonvpn.git --enable --yes
```

Needs `proton-vpn-gtk-app` (or at least `python-proton-vpn-api-core`) and a
signed-in Proton VPN session. Sign in once with the official app if the
widget says you are signed out.

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

## Notes

Do not treat this as a second Proton client running next to a busy GTK window.
If connect fails while `protonvpn-app` is open, close the app and retry.

## License

MIT
