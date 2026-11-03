#!/usr/bin/env python3
"""Build the portfolio site from the works/ folder into docs/.

    works/
        Design/                     <- category (folder name = filter name)
            Curry Campaign EDM/     <- one project; folder name = title
                info.txt            <- optional: title, year, role ... + description
                cover.jpg           <- optional; otherwise the first image
                01.jpg ...
        Photography/                <- images straight inside a category
            DSC0001.jpg ...            are shown one by one
        Video/
            Video links.docx        <- every YouTube / Vimeo link in a .docx
                                       or .txt becomes its own project

Folders whose name starts with "_" are skipped (drafts / templates).
Run:  python3 build.py
"""
import html
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKS = ROOT / "works"
SRC = ROOT / "src"
OUT = ROOT / "docs"
CACHE = ROOT / "cache" / "videos.json"
DOMAIN = "www.bunnychung.com"
CATEGORY_ORDER = ["Design", "Printing", "Video", "Photography"]

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
VIDEO_EXT = {".mp4", ".webm", ".mov"}
RESIZE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PX = 2000        # long edge of normal images
TALL_RATIO = 1.6     # height / width above this = long image (EDM, landing page)
TALL_W = 1200        # long images are scaled by width so text stays readable
THUMB_W = 900        # card covers
WARN_MB = 50         # GitHub rejects files over 100 MB
LINK_RE = re.compile(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be|vimeo\.com)/[^\s\"<>]+")


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


def sips(*args):
    return subprocess.run(["sips", *map(str, args)], capture_output=True, text=True)


def image_size(path):
    if not shutil.which("sips") or path.suffix.lower() == ".svg":
        return 0, 0
    out = sips("-g", "pixelWidth", "-g", "pixelHeight", path).stdout
    w = re.search(r"pixelWidth: (\d+)", out)
    h = re.search(r"pixelHeight: (\d+)", out)
    return (int(w.group(1)), int(h.group(1))) if w and h else (0, 0)


def export_image(src, dst, width_cap=None):
    """Copy an image, shrinking it with macOS `sips`. Returns (w, h) of the output."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    w, h = image_size(src)
    if src.suffix.lower() in RESIZE_EXT and w:
        if width_cap:
            args = ["--resampleWidth", min(w, width_cap)]
        elif h / w > TALL_RATIO:
            args = ["--resampleWidth", min(w, TALL_W)]
        else:
            args = ["-Z", min(max(w, h), MAX_PX)]
        if sips(*args, "-s", "formatOptions", "82", src, "--out", dst).returncode == 0:
            return image_size(dst)
    shutil.copy2(src, dst)
    return w, h


def media_files(folder):
    return sorted(
        (p for p in folder.iterdir()
         if p.is_file() and p.suffix.lower() in IMAGE_EXT | VIDEO_EXT),
        key=lambda p: p.name.lower(),
    )


def build_project(title, category, files, meta=None, desc="", key=None):
    meta = meta or {}
    slug = slugify(meta.get("slug") or key or f"{category}-{title}")
    covers = [p for p in files if p.stem.lower() == "cover"]
    cover = covers[0] if covers else next(
        (p for p in files if p.suffix.lower() in IMAGE_EXT), None)

    media, cover_info = [], {}
    for p in files:
        mb = p.stat().st_size / 1e6
        if mb > WARN_MB:
            print(f"  ! {p.relative_to(ROOT)} is {mb:.0f} MB — "
                  "consider YouTube/Vimeo and a link instead")
        rel = f"media/{slug}/{slugify(p.stem)}{p.suffix.lower()}"
        if p.suffix.lower() in VIDEO_EXT:
            (OUT / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, OUT / rel)
            media.append({"type": "video", "src": rel})
            continue
        w, h = export_image(p, OUT / rel)
        item = {"type": "image", "src": rel, "w": w, "h": h}
        if p == cover:
            thumb = f"media/{slug}/thumb-{slugify(p.stem)}.jpg"
            tw, th = export_image(p, OUT / thumb, width_cap=THUMB_W)
            cover_info = {"cover": thumb, "coverRatio": round(h / w, 3) if w else 0}
            if covers and len(files) > 1:
                continue  # a file named cover.* is only shown on the card
        media.append(item)

    for url in filter(None, (meta.get("video"), meta.get("video2"))):
        media.insert(0, {"type": "embed", "src": url})

    return {
        "slug": slug,
        "title": meta.get("title") or title,
        "year": meta.get("year", ""),
        "category": meta.get("category") or category,
        "role": meta.get("role", ""),
        "client": meta.get("client", ""),
        "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        "link": meta.get("link", ""),
        "order": float(meta.get("order", 0) or 0),
        "cover": "", "coverRatio": 0, **cover_info,
        "description": desc,
        "media": media,
    }


# ---------- video links ----------

def links_in(path):
    if path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as z:
            text = z.read("word/document.xml").decode("utf-8")
            text += z.read("word/_rels/document.xml.rels").decode("utf-8")
        text = html.unescape(re.sub(r"<[^>]+>", " ", text.replace("Target=\"", " ")))
    else:
        text = path.read_text(encoding="utf-8")
    seen, out = set(), []
    # keep document order: scan document.xml text first, rels only add missing ones
    for url in LINK_RE.findall(text):
        vid = video_id(url)
        if vid and vid not in seen:
            seen.add(vid)
            out.append(url)
    return out


def video_id(url):
    m = re.search(r"(?:youtu\.be/|v=|shorts/|embed/)([\w-]{11})", url)
    if m:
        return "yt:" + m.group(1)
    m = re.search(r"vimeo\.com/(?:video/)?(\d+)", url)
    return "vimeo:" + m.group(1) if m else None


def fetch(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def video_meta(url, cache):
    """Title + thumbnail from oEmbed, cached so offline builds still work."""
    vid = video_id(url)
    if vid in cache:
        return cache[vid]
    info = {"title": "", "thumb": ""}
    try:
        if vid.startswith("yt:"):
            d = json.loads(fetch("https://www.youtube.com/oembed?format=json&url="
                                 + urllib.parse.quote(url, safe="")))
            info["title"] = d.get("title", "")
            y = vid[3:]
            for name in ("maxresdefault", "sddefault", "hqdefault"):
                try:
                    fetch(f"https://i.ytimg.com/vi/{y}/{name}.jpg")
                    info["thumb"] = f"https://i.ytimg.com/vi/{y}/{name}.jpg"
                    break
                except Exception:
                    pass
        else:
            d = json.loads(fetch("https://vimeo.com/api/oembed.json?url="
                                 + urllib.parse.quote(url, safe="")))
            info["title"] = d.get("title", "")
            info["thumb"] = d.get("thumbnail_url", "")
    except Exception as e:
        print(f"  ! could not fetch info for {url}: {e}")
        return info
    cache[vid] = info
    return info


def build_videos(path, category, cache):
    projects = []
    for url in links_in(path):
        vid = video_id(url)
        info = video_meta(url, cache)
        slug = slugify(vid)
        p = {
            "slug": slug, "title": info["title"] or url, "year": "", "category": category,
            "role": "", "client": "", "tags": [], "link": "", "order": 0,
            "cover": "", "coverRatio": 0.5625, "description": "",
            "media": [{"type": "embed", "src": url}], "video": True,
        }
        if info["thumb"]:
            dst = OUT / "media" / slug / "thumb.jpg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                dst.write_bytes(fetch(info["thumb"]))
                p["cover"] = f"media/{slug}/thumb.jpg"
            except Exception:
                p["cover"] = info["thumb"]
        print(f"  ▶ {p['title']}")
        projects.append(p)
    return projects


# ---------- main ----------

def visible_dirs(folder):
    return sorted((d for d in folder.iterdir()
                   if d.is_dir() and not d.name.startswith(("_", "."))),
                  key=lambda d: d.name.lower())


def build_category(folder, cache):
    cat = folder.name
    projects = []
    for sub in visible_dirs(folder):
        print(f"· {cat} / {sub.name}")
        files = media_files(sub)
        meta, desc = parse_info(sub / "info.txt")
        if files or meta:
            projects.append(build_project(sub.name, cat, files, meta, desc))
    loose = media_files(folder)
    if loose:
        # images straight inside a category are shown one by one (photography)
        print(f"· {cat} ({len(loose)} photos)")
    for p in loose:
        item = build_project("", cat, [p], key=f"{cat}-{p.stem}")
        item["photo"] = True
        projects.append(item)
    for doc in sorted(folder.iterdir()):
        if doc.suffix.lower() in {".docx", ".txt"} and doc.name != "info.txt" \
                and not doc.name.startswith(("~$", ".")):
            print(f"· {cat} / {doc.name}")
            projects.extend(build_videos(doc, cat, cache))
    return projects


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    works = []
    for folder in visible_dirs(WORKS) if WORKS.exists() else []:
        works.extend(build_category(folder, cache))

    rank = {c.lower(): i for i, c in enumerate(CATEGORY_ORDER)}
    works.sort(key=lambda w: (-w["order"], rank.get(w["category"].lower(), 99)))

    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n")

    page = (SRC / "index.html").read_text(encoding="utf-8")
    data = json.dumps(works, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("/*__WORKS__*/[]", data)
    (OUT / "index.html").write_text(page, encoding="utf-8")

    for extra in SRC.iterdir():
        if extra.name != "index.html":
            dst = OUT / extra.name
            (shutil.copytree if extra.is_dir() else shutil.copy2)(extra, dst)

    (OUT / "CNAME").write_text(DOMAIN + "\n")
    (OUT / ".nojekyll").write_text("")
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"Built {len(works)} work(s) → docs/  ({size:.0f} MB)")


if __name__ == "__main__":
    sys.exit(main())
