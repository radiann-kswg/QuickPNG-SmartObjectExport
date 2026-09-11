# QuickPNG-SmartObjectExport — スマートオブジェクトPNGクイック抽出パッチ

## 目的

`input-PSD/` の各PSDに埋め込まれた**スマートオブジェクト**を、配置時の変形（拡縮・回転・ワープ）が適用される**前のネイティブ状態**でレンダリングし、**透過PNG（`OUTPUT_DPI` dpiメタデータ付き・長辺 `MAX_EDGE_PX` px以下、既定 350dpi / 512px）**として `output-PNG/` へクイック出力する。

## 返答言語

チャットでの返答は必ず日本語。

## 設定（.env）

**作業開始時に必ずリポジトリ直下の `.env` を読む**。無ければ既定値を使う。

```
OUTPUT_DPI=350   # 出力PNGへ付与するdpiメタデータ
MAX_EDGE_PX=512  # 長辺の上限px。超える場合のみアスペクト維持で縮小
```

## 実行方法（推奨パイプライン: ローカル psd-tools）

```bash
pip install "psd-tools[composite]" --break-system-packages   # 初回のみ（[composite]必須: aggdraw/scipy）
python3 scripts/extract_smart_objects.py
```

macOS では venv を使う（姉妹リポジトリと並べた親フォルダに共有 `.venv` を作ると使い回せる）:

```bash
python3 -m venv ../.venv
../.venv/bin/pip install -r requirements.txt
../.venv/bin/python scripts/extract_smart_objects.py
```

スクリプトが以下を一括で行う:

1. `input-PSD/*.psd` を走査し、スマートオブジェクトレイヤーを再帰的に列挙
2. 埋め込みデータ（`8BPS`=PSD/PSB は psd-tools コンポジット、PNG等は Pillow）を**等倍レンダリング** — これが「変形の初期化」に相当（配置行列・ワープを一切適用しない）
3. 同一PSD内で同じ埋め込みデータ（`unique_id`）を複数レイヤーが参照する場合は**1回だけ出力**
4. 長辺が `MAX_EDGE_PX` 超なら LANCZOS で縮小（拡大はしない）
5. `output-PNG/<PSDベース名>__<SOレイヤー名>.png` へ保存（`OUTPUT_DPI` メタデータ付き。名前衝突時は `-2`, `-3`…）

## なぜ抽出コアはローカル処理か（Adobeコネクタとの役割分担）

Adobe for creativity コネクタ（MCP）には**PSD内のスマートオブジェクトを個別抽出するAPIが無く**、PSDを直接渡すと白背景にフラット化されアルファが失われる（参考リポジトリ QuickPNG-To256Permill で検証済み）。そのため抽出〜PNG化は psd-tools で完結させる。Adobeコネクタは接続済みの場合に限り、出力後の追加加工（`image_crop_and_resize` 等）へ任意で利用してよい。

## 出力要件（すべて必須）

- 変形初期化: 埋め込みオリジナルの等倍レンダリング（配置bbox・ワープを反映しない）
- アルファ: RGBA透過を必ず保持
- 寸法: 長辺 ≤ `MAX_EDGE_PX`（元が小さければ等倍のまま）
- DPI: `OUTPUT_DPI` PixelsPerInch のメタデータ
- ファイル名: `<PSDベース名>__<SOレイヤー名>.png`（Windows禁止文字は全角へ置換）

## 検証チェックリスト（毎回・全件）

- PIL で `Image.open(f); im.load()` が通る（破損検出）
- `mode=RGBA`
- `max(size) <= MAX_EDGE_PX`
- DPIメタデータ ≈ `OUTPUT_DPI`
- 件数: 出力PNG数 = ユニークSO数（重複スキップ数・エラー数はスクリプトが報告）

## 既知の注意点

- リンク型スマートオブジェクト（外部ファイル参照）は埋め込みデータが無いため対象外（エラー報告のみ）
- スマートオブジェクトを含まないPSDは黙ってスキップされる（出力0件）
- psd-tools のコンポジットは一部の描画モードでPhotoshopと微差が出ることがある

## 秘匿事項

`input-PSD/`・`output-PNG/` の内容（ファイル名・画像）は**git管理外かつ、このリポジトリのドキュメント・設定・コミットに一切含めない**こと。

## ライセンス

設定・スクリプト・ドキュメントは MIT（`LICENSE` 参照）。`input-PSD/`・`output-PNG/` の画像アセットはライセンス対象外。
