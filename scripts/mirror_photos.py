#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公開中の写真を、写真受付GASの公開フィードから静的ファイルへ写す（ミラー）。

アルバム（album.html）は最初に photos.json を読んで描く。Drive の画像を毎回直接読むと
遅く、枚数が増えると Drive 側で読み込みを断られる（429）ので、公開中の写真を
GitHub Pages 上の WebP へ写しておく。写すのはこの台本で、公開リポジトリ shogo-bio/2nyan の
GitHub Actions（.github/workflows/mirror-photos.yml）が10分おきに動かす。
作業用リポジトリの「公開リポジトリへ反映」でも、反映の直前に同じものを一度動かす。

    python3 scripts/mirror_photos.py                 # サイトの根（photos.json のある場所）で
    python3 scripts/mirror_photos.py --limit 40      # 1回に新しく取り込む上限（Drive をたたきすぎない）
    python3 scripts/mirror_photos.py --dry-run       # 何も書かずに、やることだけ表示

出力:
    img/photos/<写真ID>.webp     長辺1000px（拡大表示用）
    img/photos/<写真ID>.t.webp   長辺480px（一覧用）
    photos.json                  写真の一覧（写真ID・画像の場所・撮影者・猫ID・時刻）

決まりごと:
  - フィードに無い写真は取り下げ済みなので、ファイルごと消す。
  - ただし旧アルバムの写真（写真ID photo_legacy_…）は、Drive へ移し終える
    （フィードに旧写真が現れる）までは、いまの photos.json のぶんをそのまま残す。
  - 写真が変わらなければ photos.json も触らない（10分おきに空のコミットを積まないため）。
  - RENDER_VERSION を上げると、次のミラーで全部を作り直す（大きさや画質を変えたとき）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_FEED = (
    "https://script.google.com/macros/s/"
    "AKfycbzAq0PSSxFgFEPuh1ejakU3mKvfobaf3m7sMjZlrQLm6KVZN77mrhlJnzKbvnVEBhED/exec?action=album"
)
LEGACY_PREFIX = "photo_legacy_"
PHOTO_DIR = "img/photos"
# 旧アルバム（img/album/）と同じ大きさに揃える。幅で決めるのは、縦長の写真を
# 長辺で切り詰めると画面での見え方が一段小さくなるため（f000: 1000×1778 が 562×1000 になっていた）。
# 縦は、極端に縦長の写真でファイルが膨らまないための保険。
FULL_W, FULL_H, FULL_Q = 1000, 2000, 72
THUMB_W, THUMB_H, THUMB_Q = 400, 800, 72
RENDER_VERSION = 2          # 大きさや画質を変えたら1つ上げる（次のミラーで作り直す）
UA = "2nyan-mirror/1 (+https://shogo-bio.github.io/2nyan/)"
JST = dt.timezone(dt.timedelta(hours=9))


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch(url: str, tries: int = 3, timeout: int = 60) -> bytes:
    """GET。Drive は 302 で別ホストへ飛ぶので追う。429・5xx は少し待って数回まで。"""
    delay = 2
    for i in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                body = res.read()
                ctype = res.headers.get("Content-Type", "")
                if ctype.startswith("text/html"):
                    raise RuntimeError("HTML が返った（共有設定か、Drive の確認画面）")
                return body
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if i < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError("unreachable")


def safe_id(photo_id: str) -> bool:
    return bool(photo_id) and all(c.isalnum() or c in "_-" for c in photo_id) and len(photo_id) <= 100


def fit(img, max_w: int, max_h: int):
    """幅 max_w に収める。縦が max_h を超えるときはそちらにも合わせる。拡大はしない。"""
    from PIL import Image

    scale = min(1.0, max_w / img.width, max_h / img.height)
    if scale >= 1.0:
        return img.copy()
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)


def convert(data: bytes, full_path: Path, thumb_path: Path) -> None:
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    full_path.parent.mkdir(parents=True, exist_ok=True)
    fit(img, FULL_W, FULL_H).save(full_path, "WEBP", quality=FULL_Q, method=6)
    fit(img, THUMB_W, THUMB_H).save(thumb_path, "WEBP", quality=THUMB_Q, method=6)


def entry_from_feed(photo: dict, legacy_key: str | None) -> dict:
    pid = str(photo["photoId"])
    e = {
        "photoId": pid,
        "thumb": f"{PHOTO_DIR}/{pid}.t.webp",
        "full": f"{PHOTO_DIR}/{pid}.webp",
        "credit": str(photo.get("credit") or "有志"),
        "catIds": str(photo.get("catIds") or "").strip(),
        "publishedAt": str(photo.get("publishedAt") or ""),
        "addedAt": str(photo.get("addedAt") or ""),
        "v": RENDER_VERSION,
    }
    key = legacy_key or (pid[len(LEGACY_PREFIX):] if pid.startswith(LEGACY_PREFIX) else "")
    if key:
        e["legacyKey"] = key
    return e


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path("."), help="サイトの根（photos.json のある場所）")
    ap.add_argument("--feed", default=os.environ.get("ALBUM_FEED_URL") or DEFAULT_FEED)
    ap.add_argument("--limit", type=int, default=40, help="1回に新しく取り込む上限")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    root: Path = args.root
    json_path = root / "photos.json"
    photo_dir = root / PHOTO_DIR
    prev: dict = {}
    prev_list: list = []
    if json_path.exists():
        try:
            prev_list = json.loads(json_path.read_text(encoding="utf-8")).get("photos") or []
            prev = {str(p.get("photoId")): p for p in prev_list if p.get("photoId")}
        except (ValueError, AttributeError) as e:
            log(f"注意: いまの photos.json を読めなかったので作り直す（{e}）")

    try:
        feed = json.loads(fetch(args.feed).decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        log(f"NG: フィードを読めなかった: {e}")
        return 1
    if not feed.get("ok") or not isinstance(feed.get("photos"), list):
        log(f"NG: フィードの形が違う: {str(feed)[:200]}")
        return 1
    photos = [p for p in feed["photos"] if safe_id(str(p.get("photoId") or ""))]
    photos.sort(key=lambda p: str(p.get("addedAt") or "9999"))   # 古い順（アルバムの並び）
    legacy_imported = feed.get("legacyManaged") is True or any(str(p["photoId"]).startswith(LEGACY_PREFIX) for p in photos)

    entries: list = []
    keep_files: set = set()
    # 旧アルバムのぶんは、Drive へ移し終えるまで、いまの一覧をそのまま残す
    if not legacy_imported:
        kept = 0
        for p in prev_list:
            pid = str(p.get("photoId") or "")
            if pid.startswith(LEGACY_PREFIX) and (root / str(p.get("full", ""))).exists():
                entries.append(p)
                keep_files.update([Path(str(p.get("full", ""))).name, Path(str(p.get("thumb", ""))).name])
                kept += 1
        if kept:
            log(f"旧アルバム: {kept}枚をそのまま残す（Drive への移し替え前）")

    fetched = failed = reused = 0
    for p in photos:
        pid = str(p["photoId"])
        full_path = photo_dir / f"{pid}.webp"
        thumb_path = photo_dir / f"{pid}.t.webp"
        legacy_key = (prev.get(pid) or {}).get("legacyKey")
        stale = (prev.get(pid) or {}).get("v") != RENDER_VERSION   # 大きさ・画質を変えたら作り直す
        if full_path.exists() and thumb_path.exists() and not stale:
            entries.append(entry_from_feed(p, legacy_key))
            keep_files.update([full_path.name, thumb_path.name])
            reused += 1
            continue
        if fetched + failed >= args.limit:
            if pid in prev:
                entries.append(prev[pid])
                keep_files.update([Path(prev[pid].get("full", "")).name, Path(prev[pid].get("thumb", "")).name])
            log(f"次回に回す: {pid}（1回の上限 {args.limit}）")
            continue
        url = str(p.get("imageUrl") or "")
        if not url:
            log(f"飛ばす: {pid}（画像のURLが無い）")
            continue
        if args.dry_run:
            log(f"取り込む予定: {pid} ← {url}")
            fetched += 1
            entries.append(entry_from_feed(p, legacy_key))
            continue
        try:
            data = fetch(url)
            convert(data, full_path, thumb_path)
        except Exception as e:  # noqa: BLE001
            failed += 1
            log(f"取り込めなかった: {pid}: {e}")
            for path in (full_path, thumb_path):
                if path.exists():
                    path.unlink()
            if pid in prev:
                entries.append(prev[pid])
            continue
        fetched += 1
        entries.append(entry_from_feed(p, legacy_key))
        keep_files.update([full_path.name, thumb_path.name])
        log(f"取り込んだ: {pid}（{full_path.stat().st_size // 1024}KB / {thumb_path.stat().st_size // 1024}KB）")

    # 参照されなくなったファイル（取り下げた写真）を消す
    removed = 0
    if photo_dir.exists() and not args.dry_run:
        for f in photo_dir.iterdir():
            if f.is_file() and f.name not in keep_files:
                f.unlink()
                removed += 1

    changed = [{k: v for k, v in e.items()} for e in entries] != prev_list
    log(f"公開中 {len(photos)}枚 / 一覧 {len(entries)}枚（使い回し {reused}・新規 {fetched}・失敗 {failed}・消した {removed}）"
        + ("・旧写真は移し替え済み" if legacy_imported else ""))
    if not changed:
        log("変化なし（photos.json は触らない）")
        return 0
    if args.dry_run:
        log("dry-run: photos.json を書き換える予定")
        return 0
    out = {
        "note": "アルバムが最初に読む写真の一覧。GitHub Actions のミラー（scripts/mirror_photos.py）が公開中の写真から作る。",
        "source": "mirror",
        "generatedAt": dt.datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "photos": entries,
    }
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"書き出し: {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
