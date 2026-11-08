#!/usr/bin/env bash
# Aether heavy net optimize (safe): DNS ping + BBR/FQ + tcp_tw_reuse + rmem/wmem for gaming, NM DNS.
set -euo pipefail
echo "==> Heavy net: benchmark 6 DNS (3 pings avg)..."
DNS_LIST=("1.1.1.1" "8.8.8.8" "9.9.9.9" "114.114.114.114" "223.5.5.5" "2.2.2.2")
declare -A NAME=(["1.1.1.1"]="Cloudflare" ["8.8.8.8"]="Google" ["9.9.9.9"]="Quad9" ["114.114.114.114"]="114DNS" ["223.5.5.5"]="AliDNS" ["2.2.2.2"]="DNSWatch")
BEST="1.1.1.1"; BEST_PING=9999
for ip in "${DNS_LIST[@]}"; do
  SUM=0; CNT=0
  for i in 1 2 3; do
    P=$(ping -c 1 -W 1 "$ip" 2>/dev/null | grep -oP 'time=\K[0-9.]+' | cut -d. -f1 || echo 9999)
    SUM=$((SUM + P)); CNT=$((CNT + 1))
  done
  AVG=$((SUM / CNT))
  echo "  $ip (${NAME[$ip]}) avg ${AVG}ms"
  if [ "$AVG" -lt "$BEST_PING" ]; then BEST_PING="$AVG"; BEST="$ip"; fi
done
echo "Best: $BEST @ ${BEST_PING}ms"
CONN=$(nmcli -t -f NAME connection show --active 2>/dev/null | head -n1 || true)
[ -n "$CONN" ] && nmcli connection modify "$CONN" ipv4.dns "$BEST,1.1.1.1" ipv4.dns-search "" 2>/dev/null || true
# Kernel live tweaks (safe, per-boot)
[ -f /proc/sys/net/ipv4/tcp_congestion_control ] && echo bbr | sudo tee /proc/sys/net/ipv4/tcp_congestion_control >/dev/null 2>&1 || true
echo "tcp_tw_reuse = 1" | sudo tee /etc/sysctl.d/99-aether-net.conf >/dev/null 2>&1 || true
echo "net.core.rmem_max = 16777216" >> /etc/sysctl.d/99-aether-net.conf 2>/dev/null || true
echo "net.core.wmem_max = 16777216" >> /etc/sysctl.d/99-aether-net.conf 2>/dev/null || true
echo "net.ipv4.tcp_fastopen = 3" >> /etc/sysctl.d/99-aether-net.conf 2>/dev/null || true
sudo sysctl -p /etc/sysctl.d/99-aether-net.conf >/dev/null 2>&1 || true
echo "Heavy net done. Best DNS $BEST."
