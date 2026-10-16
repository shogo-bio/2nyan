# 猫倶楽部 支援ページ

東京科学大学 横浜キャンパスの猫たちを見守る有志の集まり「猫倶楽部」のWebページです。

## 構成

- `index.html` — 支援ページ本体（CSS/JSも全部この中）
- `album.html` — アルバム（撮影者・猫ちゃんでの絞り込み・リアクション・人気順）。写真は `photos.json` から読む
- `photos.json` / `img/photos/` — 公開中の写真の一覧と画像。GitHub Actions の「写真のミラー」（`.github/workflows/mirror-photos.yml`・`scripts/mirror_photos.py`）が10分おきに作り直す。手で直しても次のミラーで戻る
- `manifest.webmanifest` / `sw.js` / `icons/` — ホーム画面アプリ化（PWA）用
- `img/` — ページの写真（webp形式）。`img/site/` はトップページで使う写真

## このリポジトリについて

ここは配信専用の場所です。中身は作業用リポジトリから自動で書き出されており、
履歴は反映のたびに作り直されます。ここのファイルを直接編集しても、
次の反映で上書きされて消えます。

## 公開前のチェックリスト

- [ ] Amazonほしい物リストのURLを差し込む（`wishlist-link` の href）
- [ ] 連絡先メールアドレスを入れる（Googleグループを用意予定。`class="mail"` の中）
- [ ] ポストカード・卓上カレンダーの写真を入れる（`good-thumb` 内）
- [ ] 会計報告の数字を入れる（表のセルの `class="ph"` を外して値を入れる）
- [ ] 公開周知が決まったら `<meta name="robots" content="noindex">` を全ページから外す
