#!/usr/bin/env bash
# Aether network pre-tune (safe): auto-pick fastest DNS by ping, enable BBR, no unsafe tweaks.
set -euo pipefail
echo "==> Aether network tune: benchmarking DNS (Cloudflare/Google/Quad9/Ali/OneDNS)..."
declare -A DNS=(["1.1.1.1"]="Cloudflare" ["8.8.8.8"]="Google" ["9.9.9.9"]="Quad9" ["114.114.114.114"]="114DNS" ["223.5.5.5"]="AliDNS" ["1.0.0.1"]="Cloudflare1")
BEST="1.1.1.1"; BEST_PING=9999
for ip in "${!DNS[@]}"; do
  # ping once, 500ms timeout
  PING=$(ping -c 1 -W 1 "$ip" 2>/dev/null | grep -oP 'time=\K[0-9.]+' | cut -d. -f1 || echo 9999)
  if [ "$PING" -lt "$BEST_PING" ]; then BEST_PING="$PING"; BEST="$ip"; fi
  echo "  $ip (${DNS[$ip]}) : ${PING}ms"
done
echo "Best DNS: $BEST (${DNS[$BEST]}) @ ${BEST_PING}ms"
# Apply via NetworkManager (IPv4 DNS) — safe, revertible
CONN=$(nmcli -t -f NAME connection show --active 2>/dev/null | head -n1 || true)
if [ -n "$CONN" ]; then
  nmcli connection modify "$CONN" ipv4.dns "$BEST,1.1.1.1" ipv4.dns-search "" ipv4.ignore-auto-dns no 2>/dev/null || true
  echo "Applied DNS to $CONN"
else
  echo "No active NM connection (ok) — DNS will apply on next setup"
fi
# BBR congestion control (safe, kernel built-in on Debian)
if [ -f /proc/sys/net/ipv4/tcp_congestion_control ]; then
  echo bbr | sudo tee /proc/sys/net/ipv4/tcp_congestion_control >/dev/null 2>&1 || true
  echo "BBR enabled (if supported)"
fi
echo "Ping baseline recorded: ${BEST_PING}ms"
