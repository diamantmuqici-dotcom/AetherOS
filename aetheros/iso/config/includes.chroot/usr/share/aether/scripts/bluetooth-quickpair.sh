#!/bin/sh
# Bluetooth quick pair — BlueZ agent + scan
set -e
bluetoothctl --agent=yes --no-pager
bluetoothctl scan on
bluetoothctl devices Paired
bluetoothctl pair "$1" 2>/dev/null || echo "Usage: bluetooth-quickpair.sh <MAC>"
bluetoothctl trust "$1" 2>/dev/null; bluetoothctl connect "$1" 2>/dev/null || true
