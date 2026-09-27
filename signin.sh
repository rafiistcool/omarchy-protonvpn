#!/usr/bin/env bash
# Credentials are entered directly into Proton's interactive CLI.
read -r -p 'Proton username: ' proton_username
if [[ -n "$proton_username" ]]; then
  protonvpn signin -- "$proton_username"
fi
read -r -p 'Press Enter to close… ' _
