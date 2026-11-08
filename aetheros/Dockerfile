# AetherOS reproducible builder — Debian 13 Trixie
FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LIVE_BUILD_DEBCONF_NOCHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    live-build \
    debian-cd \
    isolinux \
    syslinux-common \
    squashfs-tools \
    genisoimage \
    xorriso \
    dosfstools \
    mtools \
    python3 \
    python3-gi \
    python3-pil \
    make \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Reproducible: pin builder + record source
WORKDIR /work
# BUILD_DATE and SOURCE_COMMIT are injected at build time for /etc/aether/build-info
ARG SOURCE_COMMIT=unknown
ARG BUILD_DATE=unknown
RUN echo "Source commit: ${SOURCE_COMMIT}" > /etc/aether-build-info && \
    echo "Build date (UTC): ${BUILD_DATE}" >> /etc/aether-build-info

CMD ["bash", "scripts/build-iso.sh"]
