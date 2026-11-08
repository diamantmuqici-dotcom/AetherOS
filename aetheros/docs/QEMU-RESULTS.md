# QEMU test matrix

`make test-qemu` boots `aetheros-live-*.iso` with QEMU + KVM:
`qemu-system-x86_64 -m 4096 -smp 2 -enable-kvm -cdrom <iso> -boot d -vga virtio`

| Case | Need | Expected |
|------|------|----------|
| Baseline | 4GB RAM | Live desktop, Setup opens |
| Weak HW | 2GB RAM | Adaptive perf → low (blur/transparency off) |
| Hi-DPI | 3840x2160 | 4K wallpaper variant used, no stretch |
| UEFI | OVMF | ISO hybrid boots |

Record results in `docs/QEMU-RESULTS.md` after each run.
