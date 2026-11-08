#!/usr/bin/env python3
"""Generate cover-fit thumbnails for Aether wallpapers (offline, no stretch)."""
import argparse
import pathlib
from PIL import Image

def cover_thumb(src: pathlib.Path, dst: pathlib.Path, width: int):
    img = Image.open(src).convert("RGB")
    w, h = img.size
    r = w / h
    tw = width
    th = int(width / r)
    # cover: scale to fill thumb box, center-crop
    scale = max(tw / w, th / h)
    nw, nh = int(w * scale + 0.5), int(h * scale + 0.5)
    resized = img.resize((nw, nh), Image.LANCZOS)
    x = (nw - tw) // 2
    y = (nh - th) // 2
    thumb = resized.crop((x, y, x + tw, y + th))
    thumb.save(dst, "JPEG", quality=86)
    print(f"  {src.name} -> {dst.name} ({tw}x{th})")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--width", type=int, default=480)
    args = ap.parse_args()
    src_dir = pathlib.Path(args.src)
    dst_dir = pathlib.Path(args.dst)
    dst_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(list(src_dir.glob("*.jpg")) + list(src_dir.glob("*.png")))
    if not files:
        raise SystemExit(f"No wallpapers in {src_dir}")
    for f in files:
        cover_thumb(f, dst_dir / f.name, args.width)
    print(f"Done: {len(files)} thumbnails")

if __name__ == "__main__":
    main()
