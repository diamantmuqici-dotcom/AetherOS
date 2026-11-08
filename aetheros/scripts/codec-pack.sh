#!/bin/sh
# Codec pack note — official Debian multimedia (NOT ubuntu restricted)
cat <<EOF
Aether ships open codecs (GStreamer/Ffmpeg, GPL). For patented codecs (H.264/H.265/AAC):
  echo "deb http://deb.debian.org/debian bookworm main contrib non-free non-free-firmware" | sudo tee /etc/apt/sources.list.d/nonfree.list
  sudo apt update && sudo apt install debian-multimedia-keyring -y
  sudo apt install ffmpeg gstreamer1.0-plugins-ugly gstreamer1.0-libav libavcodec-extra -y
This is opt-in; stock ISO stays open-only.
EOF
