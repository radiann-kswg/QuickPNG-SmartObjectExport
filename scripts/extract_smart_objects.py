#!/usr/bin/env python3
"""QuickPNG-SmartObjectExport — スマートオブジェクト抽出パイプライン本体。

input-PSD/*.psd に含まれる埋め込みスマートオブジェクトを、
変形（拡縮・回転・ワープ）が適用される前のネイティブ状態でレンダリングし、
透過PNG（OUTPUT_DPI メタデータ付き、長辺 MAX_EDGE_PX 以下）として
output-PNG/ へ出力する。

- 埋め込みデータが PSD/PSB ('8BPS') → psd-tools で等倍コンポジット
- それ以外（PNG 等）→ Pillow で直接読み込み
- 同一PSD内で同じ埋め込みデータ（unique_id）を複数レイヤーが参照する場合は1回だけ出力
- 出力名: <PSDベース名>__<スマートオブジェクトレイヤー名>.png（衝突時は -2, -3…）

設定はリポジトリ直下の .env から読む（無ければ既定値）。
依存: psd-tools >= 1.9, Pillow
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

from PIL import Image
from psd_tools import PSDImage

ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "input-PSD"
OUTPUT_DIR = ROOT / "output-PNG"

# 既定値
DEFAULTS = {"OUTPUT_DPI": 350, "MAX_EDGE_PX": 512}


def load_env() -> dict:
    cfg = dict(DEFAULTS)
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([A-Z_]+)\s*=\s*([^#]*)", line)
            if m and m.group(1) in cfg:
                try:
                    cfg[m.group(1)] = int(m.group(2).strip())
                except ValueError:
                    print(f"warn: .env {m.group(1)} の値が不正、既定値を使用", file=sys.stderr)
    return cfg


def sanitize(name: str) -> str:
    """Windows で使えない文字を全角へ置換し、末尾のドット/空白を除去。"""
    table = str.maketrans('\\/:*?"<>|', "＼／：＊？”＜＞｜")
    return name.translate(table).rstrip(" .") or "unnamed"


def iter_smart_objects(layers):
    for layer in layers:
        if layer.kind == "smartobject":
            yield layer
        if layer.is_group():
            yield from iter_smart_objects(layer)


def render_native(so) -> Image.Image:
    """埋め込みデータを変形適用前のネイティブサイズでRGBAレンダリング。"""
    data = so.data
    if data[:4] == b"8BPS":  # PSD / PSB
        emb = PSDImage.open(io.BytesIO(data))
        im = emb.composite()
    else:  # PNG / JPEG など
        im = Image.open(io.BytesIO(data))
        im.load()
    return im.convert("RGBA")


def main() -> int:
    cfg = load_env()
    dpi, max_edge = cfg["OUTPUT_DPI"], cfg["MAX_EDGE_PX"]
    print(f"settings: OUTPUT_DPI={dpi} MAX_EDGE_PX={max_edge}")
    OUTPUT_DIR.mkdir(exist_ok=True)

    psds = sorted(p for p in INPUT_DIR.iterdir() if p.suffix.lower() == ".psd")
    if not psds:
        print("input-PSD/ に PSD がありません", file=sys.stderr)
        return 1

    written, skipped_dup, errors = [], 0, []
    for path in psds:
        try:
            psd = PSDImage.open(path)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{path.name}: PSDを開けない: {e}")
            continue
        seen_ids: set[str] = set()
        for layer in iter_smart_objects(psd):
            so = layer.smart_object
            if so.kind != "data":  # リンク型（外部ファイル）は対象外
                errors.append(f"{path.name} / {layer.name}: リンク型SOのため対象外")
                continue
            if so.unique_id in seen_ids:
                skipped_dup += 1
                continue
            seen_ids.add(so.unique_id)
            try:
                im = render_native(so)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{path.name} / {layer.name}: レンダリング失敗: {e}")
                continue
            if max(im.size) > max_edge:
                ratio = max_edge / max(im.size)
                im = im.resize(
                    (max(1, round(im.width * ratio)), max(1, round(im.height * ratio))),
                    Image.LANCZOS,
                )
            base = f"{path.stem}__{sanitize(layer.name)}"
            out = OUTPUT_DIR / f"{base}.png"
            n = 2
            while out.exists():
                out = OUTPUT_DIR / f"{base}-{n}.png"
                n += 1
            im.save(out, dpi=(dpi, dpi))
            written.append(out)
            print(f"ok: {out.name} ({im.width}x{im.height})")

    print(f"\ndone: {len(written)} PNG / dup-skip {skipped_dup} / error {len(errors)}")
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
