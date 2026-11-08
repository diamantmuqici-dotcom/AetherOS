#!/bin/sh
# Focus mode — DND + dim
MIN=${1:-25}
[ "$MIN" = "off" ] && gsettings set org.gnome.desktop.notifications show-banners true && exit 0
gsettings set org.gnome.desktop.notifications show-banners false
sleep "$((MIN*60))"
gsettings set org.gnome.desktop.notifications show-banners true
