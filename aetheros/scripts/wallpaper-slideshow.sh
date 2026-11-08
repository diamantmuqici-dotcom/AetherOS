#!/bin/sh
# Wallpaper slideshow — rotate /usr/share/backgrounds/aether every N minutes (cron/systemd timer friendly)
INTERVAL=${INTERVAL:-300}
DIR=${DIR:-/usr/share/backgrounds/aether}
while true; do
  PIC=$(ls "$DIR"/*.jpg 2>/dev/null | shuf -n 1)
  if [ -n "$PIC" ]; then
    gsettings set org.gnome.desktop.background picture-uri "file://$PIC"
    gsettings set org.gnome.desktop.background picture-uri-dark "file://$PIC"
  fi
  sleep "$INTERVAL"
done
