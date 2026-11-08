#!/usr/bin/env python3
"""Generate 4K (3840x2160) cover variants for Aether wallpapers.

Source wallpapers are 1920x1080; this intentionally upscales with LANCZOS
to produce a 4K cover-fit variant that_SETUP preview can display on
high-DPI (scaled) displays without stretching. Original files untouched.
"""
import argparse
import pathlib
from PIL import Image

TARGET_W, TARGET_H = 3840, 2160

def cover_4k(src: pathlib.Path, dst: pathlib.Path):
    img = Image.open(src).convert("RGB")
    w, h = img.size
    scale = max(TARGET_W / w, TARGET_H / h)
    nw, nh = int(w * scale + 0.5), int(h * scale + 0.5)
    resized = img.resize((nw, nh), Image.LANCZOS)
    x = (nw - TARGET_W) // 2
    y = (nh - TARGET_H) // 2
    out = resized.crop((x, y, x + TARGET_W, y + TARGET_H))
    out.save(dst, "JPEG", quality=88)
    print(f"  {src.name} -> {dst.name} ({TARGET_W}x{TARGET_H})")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    args = ap.parse_args()
    src_dir = pathlib.Path(args.src)
    dst_dir = pathlib.Path(args.dst)
    dst_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(list(src_dir.glob("*.jpg")))
    for f in files:
        cover_4k(f, dst_dir / f.name)
    print(f"Done: {len(files)} 4K wallpapers")

if __name__ == "__main__":
    main()
