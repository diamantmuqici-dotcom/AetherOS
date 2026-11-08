#!/bin/sh
# Accessibility quick toggles
espeak-ng --version >/dev/null 2>&1 || echo "Install espeak-ng/orca for SR"
gsettings set org.gnome.desktop.a11y.applications screen-reader "${1:-false}"
echo "SR set to ${1:-false}"
