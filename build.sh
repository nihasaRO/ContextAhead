#!/usr/bin/env bash
# Builds bin/ContextAhead.prg, for the Instinct 3 Solar by default (45 mm and 50 mm share one target).
# Usage: ./build.sh                          (release build)
#        ./build.sh --sim                    (build, then open it in the Connect IQ simulator)
#        ./build.sh --export                 (store package bin/ContextAhead.iq for the Connect IQ Store)
set -euo pipefail
cd "$(dirname "$0")"

DEVICE="${DEVICE:-instinct3solar45mm}"
OUT="bin/ContextAhead.prg"
KEY="${CONNECTIQ_DEVELOPER_KEY:-$HOME/.connectiq/developer_key.der}"

# 1. Find the SDK: $CONNECTIQ_SDK, else the one selected in SDK Manager.
SDK="${CONNECTIQ_SDK:-}"
if [ -z "$SDK" ]; then
  for cfg in "$HOME/Library/Application Support/Garmin/ConnectIQ/current-sdk.cfg" \
             "$HOME/.Garmin/ConnectIQ/current-sdk.cfg"; do
    if [ -f "$cfg" ]; then SDK="$(tr -d '\r\n' < "$cfg")"; break; fi
  done
fi
if [ -z "$SDK" ] || [ ! -x "$SDK/bin/monkeyc" ]; then
  echo "Connect IQ SDK not found. Install it with Garmin's SDK Manager, or set CONNECTIQ_SDK=/path/to/sdk" >&2
  exit 1
fi

# 2. Developer key (any RSA 4096 key works for sideloading; keep it for future builds).
if [ ! -f "$KEY" ]; then
  echo "No developer key found, creating one at $KEY"
  mkdir -p "$(dirname "$KEY")"
  openssl genrsa -out "${KEY%.der}.pem" 4096
  openssl pkcs8 -topk8 -inform PEM -outform DER -in "${KEY%.der}.pem" -out "$KEY" -nocrypt
fi

# 3. Compile.
mkdir -p bin
if [ "${1:-}" = "--export" ]; then
  "$SDK/bin/monkeyc" -e -r -O 2z -f monkey.jungle -y "$KEY" -o "bin/ContextAhead.iq"
  echo "Exported bin/ContextAhead.iq  ->  upload it at apps.garmin.com (Developer > Upload an app)"
  exit 0
fi
"$SDK/bin/monkeyc" -r -O 2z -f monkey.jungle -d "$DEVICE" -y "$KEY" -o "$OUT"
echo "Built $OUT  ->  copy it to GARMIN/APPS on the watch"

if [ "${1:-}" = "--sim" ]; then
  "$SDK/bin/connectiq" &
  sleep 4
  "$SDK/bin/monkeydo" "$OUT" "$DEVICE"
fi
