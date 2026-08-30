/* ============================================================
   猫倶楽部 サイト用 Service Worker

   何をするもの？
     スマホのホーム画面から開いたときに、写真の読み込みを速くし、
     電波が弱いところでも表示できるようにするための仕組み。
     ブラウザがこのファイルを常駐させ、通信を横から受け取る。

   考え方
     ・ページ（HTML）は「まず通信、だめなら控え」。
       控えを先に使うと、更新したのに古い画面が出る事故が起きるため。
     ・写真は「まず控え、なければ通信」。
       写真は差し替えではなく追加されるので、古い控えでも困らない。
     ・ごはん板は控えを取らない。
       古い当番表を見せてしまうと、行き違いのもとになる。
     ・GAS（script.google.com）にはいっさい触らない。
       リアクションや当番の通信を邪魔しないため。

   直したときの手順
     web\ の中身を変えたら、下の VERSION を1つ上げて push する。
     （HTMLは通信優先なので、上げ忘れても古いページは出ない。
       写真だけは古い控えが残ることがある）
   ============================================================ */

var VERSION   = 'nekoclub-v10';
var CACHE_DOC = VERSION + '-page';    // ページ用
var CACHE_IMG = VERSION + '-img';     // 写真用
var CACHE_FNT = VERSION + '-font';    // 書体用
var IMG_MAX   = 400;                  // 写真の控えを持つ上限（枚）

// このファイル（sw.js）が置かれている場所。GitHub Pages では /2nyan/
var BASE = new URL('./', self.location.href).pathname;

// 控えを取ってよいページだけを並べる。ここに無いページは通信のみ。
var DOCS = ['', 'index.html', 'album.html'];

// 最初に用意しておくもの（起動を速くするため）
var PRECACHE = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon-192.png'
];

function isDoc(url) {
  if (url.pathname.indexOf(BASE) !== 0) return false;
  return DOCS.indexOf(url.pathname.slice(BASE.length)) >= 0;
}
function isImg(url) {
  return url.pathname.indexOf(BASE + 'img/') === 0;
}
function isFont(url) {
  return url.host === 'fonts.googleapis.com' || url.host === 'fonts.gstatic.com';
}

/* ---------- 導入 ---------- */
self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE_DOC)
      .then(function (c) { return c.addAll(PRECACHE); })
      .catch(function () { /* 1つでも失敗したら諦める。導入自体は止めない */ })
      .then(function () { return self.skipWaiting(); })
  );
});

/* ---------- 有効化：古い版の控えを捨てる ---------- */
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(names.map(function (n) {
        if (n.indexOf(VERSION) !== 0) return caches.delete(n);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

/* ---------- 通信の横取り ---------- */
self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;                    // 送信系はそのまま通す

  var url;
  try { url = new URL(req.url); } catch (err) { return; }

  if (isFont(url))                    return e.respondWith(cacheFirst(req, CACHE_FNT, 0));
  if (url.origin !== self.location.origin) return;     // GAS など外部はさわらない
  if (isImg(url))                     return e.respondWith(cacheFirst(req, CACHE_IMG, IMG_MAX));
  if (isDoc(url))                     return e.respondWith(networkFirst(req));
  // それ以外（ごはん板を含む）は素通し
});

/* まず通信。成功したら控えを更新する。失敗したら控えを出す。 */
function networkFirst(req) {
  return fetch(req).then(function (res) {
    if (res && res.ok) {
      var copy = res.clone();
      caches.open(CACHE_DOC).then(function (c) { c.put(req, copy); });
    }
    return res;
  }).catch(function () {
    return caches.match(req).then(function (hit) {
      return hit || caches.match('./index.html') || offline();
    });
  });
}

/* まず控え。無ければ通信して控える。max を超えたら古いものから捨てる。 */
function cacheFirst(req, name, max) {
  return caches.open(name).then(function (c) {
    return c.match(req).then(function (hit) {
      if (hit) return hit;
      return fetch(req).then(function (res) {
        if (res && (res.ok || res.type === 'opaque')) {
          c.put(req, res.clone()).then(function () { if (max) trim(c, max); });
        }
        return res;
      });
    });
  });
}

function trim(cache, max) {
  cache.keys().then(function (keys) {
    for (var i = 0; i < keys.length - max; i++) cache.delete(keys[i]);
  });
}

function offline() {
  return new Response(
    '<!doctype html><html lang="ja"><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<body style="font-family:sans-serif;background:#FBF7F0;color:#3A3129;' +
    'display:grid;place-items:center;height:100vh;margin:0;text-align:center;padding:24px">' +
    '<p>いまインターネットにつながっていないようです。<br>電波の届くところで開き直してください。</p>',
    { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
  );
}
