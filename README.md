# QuickPNG-SmartObjectExport

PSDに埋め込まれたスマートオブジェクトを、変形（拡縮・回転・ワープ）が初期化されたネイティブ状態の透過PNG（350dpiメタデータ・長辺512px以下）へクイック抽出する、Claude（Cowork / Claude Code）向けパイプライン設定。

姉妹リポジトリ:

- [QuickPNG-To256Permill](https://github.com/radiann-kswg/QuickPNG-To256Permill) — PSDカンバスの256‰縮小PNG出力
- [QuickPNG-Tinize4Web](https://github.com/radiann-kswg/QuickPNG-Tinize4Web) — Web公開用の高圧縮PNG変換

## 使い方

1. `input-PSD/` に対象PSDを置く
2. `.env.example` を `.env` にリネームコピーする（必要に応じてパラメータを変更）
3. Claude Desktop（Cowork）または Claude Code でこのフォルダを開き、「input-PSDのスマートオブジェクトをoutput-PNGへ抽出して」と依頼する — Claudeが `CLAUDE.md` の手順に従って処理する
4. 手動実行も可能:

   ```bash
   pip install -r requirements.txt
   # Cowork のサンドボックスなど PEP 668 管理環境では:
   #   pip install -r requirements.txt --break-system-packages
   python3 scripts/extract_smart_objects.py
   ```

   `requirements.txt` は `psd-tools[composite]` を指定している。`[composite]` はベクターシェイプ
   （aggdraw）とグラデーション（scipy）の描画に必須で、省略すると一部のスマートオブジェクトが
   正しくレンダリングされない。

5. 結果は `output-PNG/<PSDベース名>__<SOレイヤー名>.png` に出力される

## 仕様

- 埋め込みスマートオブジェクトのオリジナルデータ（PSB/PSD/PNG等）を等倍レンダリング＝**変形初期化**
- RGBA透過保持・350dpiメタデータ付与（`.env` で変更可）
- 長辺が `MAX_EDGE_PX`（既定512px）を超える場合のみアスペクト維持で縮小
- 同一PSD内の重複参照（同一 `unique_id`）は1回だけ出力
- リンク型（外部ファイル参照）スマートオブジェクトは対象外

## 構成

```
CLAUDE.md                         # Claude向けパイプライン定義（本体）
README.md                         # 本ファイル
.env.example                      # 変換パラメータのテンプレート
.env                              # 実際の変換パラメータ（git管理外・要作成）
requirements.txt                  # Python依存（psd-tools[composite] / Pillow）
scripts/extract_smart_objects.py  # 抽出スクリプト（psd-tools + Pillow）
input-PSD/                        # 入力（git管理外）
output-PNG/                       # 出力（git管理外）
```

## 設定（.env）

| 変数          | 既定値 | 意味                                       |
| ------------- | ------ | ------------------------------------------ |
| `OUTPUT_DPI`  | `350`  | 出力PNGへ付与するdpiメタデータ             |
| `MAX_EDGE_PX` | `512`  | 長辺の上限px。超える場合のみ縮小（拡大なし） |

## 出力の検証

抽出後、全件について次を確認する（詳細は `CLAUDE.md`）。

- PILで開けること（破損の検出）
- `mode=RGBA`（透過保持）
- `max(size) <= MAX_EDGE_PX`
- DPIメタデータ ≈ `OUTPUT_DPI`
- 出力PNG数 = ユニークなスマートオブジェクト数（重複スキップ数・エラー数はスクリプトが報告）

## ライセンス

設定・スクリプト・ドキュメントは [MIT License](LICENSE)。
`input-PSD/`・`output-PNG/` の画像アセットはライセンス対象外かつgit管理外。
