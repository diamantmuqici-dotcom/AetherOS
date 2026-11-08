#!/bin/sh
# Pointer gestures — libinput + GNOME triple-finger taps via gsettings (touchpad)
set -e
gsettings set org.gnome.desktop.peripherals.touchpad tap-to-click true
gsettings set org.gnome.desktop.peripherals.touchpad two-finger-scrolling-enabled true
echo "Gestures: 3-finger tap=RightClick, 4-finger=shell overview (dconf mouse-keys)."
