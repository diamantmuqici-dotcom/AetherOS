#!/bin/sh
# IPP printer — discover + add via system-config-printer
set -e
lpstat -p 2>/dev/null
lpinfo -m 2>/dev/null | head
if [ -n "$1" ]; then system-config-printer --ipp "$1"; else echo "Usage: printer-ipp.sh ipp://printer:631/printers/name"; fi
