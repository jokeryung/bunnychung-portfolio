#!/usr/bin/env python3
"""Build the portfolio site from the works/ folder into docs/.

Each work is one folder inside works/, e.g.

    works/2025-hku-ai-avatar/
        info.txt        <- title, year, category ... then a description
        cover.jpg       <- optional; otherwise the first image is used
        01.jpg 02.png clip.mp4 ...

Folders whose name starts with "_" are skipped (drafts / templates).
Run:  python3 build.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKS = ROOT / "works"
SRC = ROOT / "src"
OUT = ROOT / "docs"
DOMAIN = "www.bunnychung.com"

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
VIDEO_EXT = {".mp4", ".webm", ".mov"}
RESIZE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PX = 2000                     # long edge of images on the site
WARN_MB = 50                      # GitHub rejects files over 100 MB


def slugify(name):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return s or "work"


def parse_info(path):
    """info.txt: 'key: value' lines, then '---', then free-text description."""
    meta, desc = {}, ""
    if not path.exists():
        return meta, desc
    text = path.read_text(encoding="utf-8")
    head, sep, body = text.partition("\n---")
    if not sep:
        head, body = text, ""
    for line in head.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    desc = body.lstrip("-\n").strip()
    return meta, desc


def export_media(src, dst):
    """Copy a media file, shrinking large photos with macOS `sips`."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in RESIZE_EXT and shutil.which("sips"):
        r = subprocess.run(
            ["sips", "-Z", str(MAX_PX), str(src), "--out", str(dst)],
            capture_output=True,
        )
        if r.returncode == 0:
            return
    shutil.copy2(src, dst)


def build_work(folder):
    meta, desc = parse_info(folder / "info.txt")
    slug = slugify(meta.get("slug") or folder.name)
    files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXT | VIDEO_EXT
    )
    covers = [p for p in files if p.stem.lower() == "cover"]
    cover = covers[0] if covers else next(
        (p for p in files if p.suffix.lower() in IMAGE_EXT), None)

    media = []
    for p in files:
        mb = p.stat().st_size / 1e6
        if mb > WARN_MB:
            print(f"  ! {p.relative_to(ROOT)} is {mb:.0f} MB — "
                  "consider uploading to YouTube/Vimeo and using 'video:' instead")
        rel = f"media/{slug}/{slugify(p.stem)}{p.suffix.lower()}"
        export_media(p, OUT / rel)
        if p == cover and len(files) > 1:
            continue  # cover is shown on the card; gallery shows the rest
        kind = "video" if p.suffix.lower() in VIDEO_EXT else "image"
        media.append({"type": kind, "src": rel})

    for url in filter(None, (meta.get("video"), meta.get("video2"))):
        media.insert(0, {"type": "embed", "src": url})

    return {
        "slug": slug,
        "title": meta.get("title") or folder.name,
        "year": meta.get("year", ""),
        "category": meta.get("category", "Other"),
        "role": meta.get("role", ""),
        "client": meta.get("client", ""),
        "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        "link": meta.get("link", ""),
        "order": float(meta.get("order", 0) or 0),
        "cover": f"media/{slug}/{slugify(cover.stem)}{cover.suffix.lower()}" if cover else "",
        "description": desc,
        "media": media,
    }


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()

    works = []
    for folder in sorted(WORKS.iterdir()) if WORKS.exists() else []:
        if folder.is_dir() and not folder.name.startswith(("_", ".")):
            print(f"· {folder.name}")
            works.append(build_work(folder))
    # higher 'order' first, then newest year first
    works.sort(key=lambda w: (w["order"], w["year"]), reverse=True)

    html = (SRC / "index.html").read_text(encoding="utf-8")
    data = json.dumps(works, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("/*__WORKS__*/[]", data)
    (OUT / "index.html").write_text(html, encoding="utf-8")

    for extra in SRC.iterdir():
        if extra.name != "index.html":
            dst = OUT / extra.name
            (shutil.copytree if extra.is_dir() else shutil.copy2)(extra, dst)

    (OUT / "CNAME").write_text(DOMAIN + "\n")
    (OUT / ".nojekyll").write_text("")
    print(f"Built {len(works)} work(s) → docs/")


if __name__ == "__main__":
    sys.exit(main())
