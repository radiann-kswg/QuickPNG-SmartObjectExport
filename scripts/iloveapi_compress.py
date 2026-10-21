#!/usr/bin/env python3
"""iLoveAPI (iLoveIMG) の compressimage で、出力フォルダ内の PNG をさらに圧縮する後段処理。

使い方: python3 scripts/iloveapi_compress.py [出力フォルダ]
  省略時はリポジトリ直下の output-TinyPNG/ または output-PNG/（サブフォルダも再帰）。
  各変換スクリプトの末尾から自動で呼ばれる。.env で無効なら何もせず終了する。

.env:
  ILOVEAPI_COMPRESS=1              # 1=後段圧縮を行う / 0=行わない
  ILOVEAPI_PUBLIC_KEY=project_public_xxx   # https://www.iloveapi.com/ で発行（無料枠 月2,500クレジット）
  ILOVEAPI_LEVEL=recommended       # low / recommended / extreme

動作（1ファイルずつ）: auth → start/compressimage → upload → process → download。
  戻りが PNG で、寸法が同じ・透過が保たれ・元より小さいときだけ置き換える。
  元にあった pHYs(DPI) チャンクは引き継ぐ（Tinize4Web のように元に無ければ付けない）。
  API へ送るファイル名は常に "image.png"（実ファイル名を外部へ出さない）。
依存: 標準ライブラリのみ。  自己診断: python3 scripts/iloveapi_compress.py --selftest
"""
from __future__ import annotations

import json
import struct
import sys
import urllib.error
import urllib.request
import uuid
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.ilovepdf.com/v1"
PNG_SIG = b"\x89PNG\r\n\x1a\n"


def load_env() -> dict:
    cfg = {"ILOVEAPI_COMPRESS": "0", "ILOVEAPI_PUBLIC_KEY": "", "ILOVEAPI_LEVEL": "recommended"}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


def req(url: str, headers: dict | None = None, data: dict | None = None,
        multipart: dict | None = None):
    headers = dict(headers or {})
    body = None
    if multipart:
        b = uuid.uuid4().hex
        parts = []
        for k, v in multipart.items():
            if isinstance(v, tuple):  # (filename, bytes)
                parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; '
                             f'filename="{v[0]}"\r\nContent-Type: application/octet-stream\r\n\r\n'
                             .encode() + v[1] + b"\r\n")
            else:
                parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        body = b"".join(parts) + f"--{b}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={b}"
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=180) as r:
        raw, ctype = r.read(), r.headers.get_content_type()
    return json.loads(raw) if ctype == "application/json" else raw


def compress_bytes(png: bytes, token: str, level: str) -> tuple[bytes, object]:
    h = {"Authorization": f"Bearer {token}"}
    st = req(f"{API}/start/compressimage", h)
    server, task = st["server"], st["task"]
    up = req(f"https://{server}/v1/upload", h, multipart={"task": task, "file": ("image.png", png)})
    req(f"https://{server}/v1/process", h, data={
        "task": task, "tool": "compressimage", "compression_level": level,
        "files": [{"server_filename": up["server_filename"], "filename": "image.png"}]})
    return req(f"https://{server}/v1/download/{task}", h), st.get("remaining_credits")


# --- PNG チャンク操作（Pillow 無しで寸法・透過・pHYs を扱う）
def chunks(png: bytes):
    pos = 8
    while pos + 12 <= len(png):
        ln = struct.unpack(">I", png[pos:pos + 4])[0]
        yield png[pos + 4:pos + 8], png[pos + 8:pos + 8 + ln], pos + 12 + ln
        pos += 12 + ln


def info(png: bytes) -> tuple[int, int, bool]:
    """(幅, 高さ, 透過あり)"""
    types = [t for t, _, _ in chunks(png)]
    ihdr = next(d for t, d, _ in chunks(png) if t == b"IHDR")
    w, h, _, ct = struct.unpack(">IIBB", ihdr[:10])
    return w, h, ct in (4, 6) or (ct == 3 and b"tRNS" in types)


def carry_phys(src: bytes, dst: bytes) -> bytes:
    phys = next((d for t, d, _ in chunks(src) if t == b"pHYs"), None)
    if phys is None or any(t == b"pHYs" for t, _, _ in chunks(dst)):
        return dst
    end = next(e for t, _, e in chunks(dst) if t == b"IHDR")
    body = b"pHYs" + phys
    chunk = struct.pack(">I", len(phys)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    return dst[:end] + chunk + dst[end:]


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    cfg = load_env()
    if cfg["ILOVEAPI_COMPRESS"] != "1":
        return 0
    if not cfg["ILOVEAPI_PUBLIC_KEY"]:
        print("warn: ILOVEAPI_COMPRESS=1 ですが ILOVEAPI_PUBLIC_KEY が未設定のためスキップ", file=sys.stderr)
        return 0
    out_dir = Path(argv[1]) if len(argv) > 1 else next(
        (ROOT / d for d in ("output-TinyPNG", "output-PNG") if (ROOT / d).is_dir()), None)
    if out_dir is None or not out_dir.is_dir():
        print(f"warn: 出力フォルダが見つかりません: {out_dir}", file=sys.stderr)
        return 0
    files = sorted(p for p in out_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".png")
    if not files:
        return 0
    try:
        token = req(f"{API}/auth", data={"public_key": cfg["ILOVEAPI_PUBLIC_KEY"]})["token"]
    except (urllib.error.URLError, OSError) as e:
        print(f"warn: iLoveAPI 認証失敗、後段圧縮をスキップ: {e}", file=sys.stderr)
        return 0
    print(f"iLoveAPI compressimage ({cfg['ILOVEAPI_LEVEL']}): {len(files)} file(s)")
    total_in = total_out = 0
    credits = None
    for p in files:
        src = p.read_bytes()
        try:
            dst, credits = compress_bytes(src, token, cfg["ILOVEAPI_LEVEL"])
        except urllib.error.HTTPError as e:
            print(f"  ERR  {p.name}: HTTP {e.code} {e.read()[:200]!r}", file=sys.stderr)
            continue
        except (urllib.error.URLError, OSError, KeyError) as e:
            print(f"  ERR  {p.name}: {e}", file=sys.stderr)
            continue
        if dst[:8] != PNG_SIG:
            print(f"  skip {p.name}: 戻りが PNG ではない", file=sys.stderr)
            continue
        dst = carry_phys(src, dst)
        si, di = info(src), info(dst)
        if si[:2] != di[:2] or (si[2] and not di[2]):
            print(f"  skip {p.name}: 寸法/透過が変わった {si} -> {di}", file=sys.stderr)
            continue
        total_in += len(src)
        if len(dst) >= len(src):
            total_out += len(src)
            print(f"  keep {p.name}: {len(src) / 1024:.1f}KB（縮まず）")
            continue
        p.write_bytes(dst)
        total_out += len(dst)
        print(f"  OK   {p.name}: {len(src) / 1024:.1f}KB -> {len(dst) / 1024:.1f}KB "
              f"({100 * len(dst) / len(src):.0f}%)")
    if total_in:
        print(f"done: {total_in / 1024:.1f}KB -> {total_out / 1024:.1f}KB "
              f"({100 * total_out / total_in:.1f}%)  remaining_credits={credits}")
    return 0


def _png(w: int, h: int, ct: int, extra: list[bytes] = ()) -> bytes:
    def ch(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    bpp = {2: 3, 3: 1, 6: 4}[ct]
    raw = b"".join(b"\x00" + b"\x80" * (w * bpp) for _ in range(h))
    body = [ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ct, 0, 0, 0))] + list(extra)
    return PNG_SIG + b"".join(body + [ch(b"IDAT", zlib.compress(raw)), ch(b"IEND", b"")])


def selftest() -> int:
    def ch(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    phys = ch(b"pHYs", struct.pack(">IIB", 13780, 13780, 1))  # 350dpi
    src = _png(4, 3, 6, [phys])
    dst = _png(4, 3, 3, [ch(b"PLTE", b"\x80\x80\x80"), ch(b"tRNS", b"\x00")])
    assert info(src) == (4, 3, True) and info(dst) == (4, 3, True)
    assert info(_png(4, 3, 2)) == (4, 3, False)
    merged = carry_phys(src, dst)
    assert [t for t, _, _ in chunks(merged)] == [b"IHDR", b"pHYs", b"PLTE", b"tRNS", b"IDAT", b"IEND"]
    assert carry_phys(src, merged) == merged and carry_phys(dst, src) == src
    assert all(zlib.crc32(t + d) & 0xFFFFFFFF == struct.unpack(">I", merged[e - 4:e])[0]
               for t, d, e in chunks(merged))
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
