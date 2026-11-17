#!/usr/bin/env bash
# Aether boot net tune (runs at early boot): DNS auto-pick + ping baseline
set -euo pipefail
# same benchmark as optimize-network.sh but quick (2s)
BEST="1.1.1.1"; BEST_PING=9999
for ip in 1.1.1.1 8.8.8.8 9.9.9.9 223.5.5.5 114.114.114.114; do
  PING=$(ping -c 1 -W 1 "$ip" 2>/dev/null | grep -oP 'time=\K[0-9.]+' | cut -d. -f1 || echo 9999)
  [ "$PING" -lt "$BEST_PING" ] && BEST_PING="$PING" && BEST="$ip"
done
mkdir -p /etc/aether
echo "$BEST # chosen at boot $(date -u +%FT%TZ) ping=${BEST_PING}ms" > /etc/aether/best-dns
# apply to active connections
for conn in $(nmcli -t -f NAME connection show --active 2>/dev/null || true); do
  nmcli connection modify "$conn" ipv4.dns "$BEST,1.1.1.1" 2>/dev/null || true
  nmcli connection up "$conn" 2>/dev/null || true
done
# BBR if available
[ -f /proc/sys/net/ipv4/tcp_congestion_control ] && echo bbr | tee /proc/sys/net/ipv4/tcp_congestion_control >/dev/null 2>&1 || true
echo "Aether net tune: DNS $BEST ${BEST_PING}ms" >> /var/log/aether-boot.log
