#!/bin/sh
# System logs — dump journal + dmesg
mkdir -p ~/Logs
journalctl -n 1000 --no-pager > ~/Logs/journal-$(date +%F).log
dmesg > ~/Logs/dmesg-$(date +%F).log 2>/dev/null || echo "dmesg needs sudo" > ~/Logs/dmesg-$(date +%F).log
echo "Logs saved to ~/Logs"
