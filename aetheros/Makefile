# AetherOS — reproducible build
DISTRO_CODENAME := trixie
ARCH := amd64
ISO_NAME := aetheros-live-$(DISTRO_CODENAME)-$(ARCH).iso
DOCKER_IMAGE := aetheros/builder:0.1.0
SHELL := /bin/bash

.PHONY: help iso builder test-qemu clean wallpapers thumbs

help:
	@echo "AetherOS build:"
	@echo "  make iso        build live ISO (Docker required)"
	@echo "  make builder    build Docker builder image"
	@echo "  make test-qemu  boot ISO in QEMU/KVM"
	@echo "  make clean      clean ISO build dirs"
	@echo "  make wallpapers copy wallpapers into payload"
	@echo "  make thumbs     generate thumbnails"

builder:
	docker build -t $(DOCKER_IMAGE) -f Dockerfile .

iso: | builder
	docker run --rm -v $(PWD):/work -w /work aetheros/builder:0.1.0 bash scripts/build-iso.sh

test-qemu:
	@if [ -f "$(ISO_NAME)" ]; then \
		qemu-system-x86_64 -m 4096 -smp 2 -enable-kvm -cdrom $(ISO_NAME) -boot d -vga virtio; \
	elif [ -f "iso/$(ISO_NAME)" ]; then \
		qemu-system-x86_64 -m 4096 -smp 2 -enable-kvm -cdrom iso/$(ISO_NAME) -boot d -vga virtio; \
	else \
		echo "ISO not found. Run 'make iso' first."; exit 1; \
	fi

wallpapers:
	mkdir -p iso/config/includes.chroot/usr/share/backgrounds/aether
	cp -v assets/wallpapers/*.jpg iso/config/includes.chroot/usr/share/backgrounds/aether/
	cp -v assets/wallpapers/*.jpg iso/config/includes.chroot/usr/share/aether/wallpapers/ 2>/dev/null || true

thumbs:
	python3 scripts/mk-thumbs.py --src assets/wallpapers --dst assets/wallpapers/thumbs --width 480

clean:
	rm -rf iso/.build iso/build.log iso/aether-live-*.iso iso/*.iso $(ISO_NAME)
