# BoatRaceAI-Hamana ⛵

浜名湖特化型・共創AI予想プラットフォーム

## 概要

浜名湖ボートレースのデータ収集・AI推論・期待値計算を自動化し、
日本語で書いた評価ロジックをそのままGemini AIが解釈して期待値を算出するシステム。

### 特徴

- **ノーコード予想**: 日本語のロジックファイルを変更するだけでAIの推論方針が変わる
- **期待値ベース**: `E = P × O`（確率 × オッズ）でE > 1.0の買い目を自動抽出
- **会場拡張可能**: 浜名湖特化のMVPだが、プラグインパターンで他会場にも対応できる設計

## セットアップ

### 必要なもの

- Python 3.12+
- Google Gemini API キー（[AI Studio](https://aistudio.google.com/app/apikey) で取得）

### インストール

```bash
# 1. リポジトリのクローン
git clone <repository-url>
cd BoatRaceAI-Hamana

# 2. 環境変数の設定
cp .env.example .env
# .env に GEMINI_API_KEY を設定

# 3. 依存関係のインストール
pip install -r requirements.txt

# 4. Playwright ブラウザのインストール
playwright install chromium

# 5. アプリ起動
streamlit run src/app.py
```

ブラウザで `http://localhost:8501` を開いてください。

## 使い方

1. **「予想実行」タブ** を開く
2. 会場（浜名湖）・開催日・レース番号を選択
3. 評価ロジックを選択（`logics/default_logic.md`）
4. 「🚀 予想実行」をクリック
5. 期待値ランキングを確認（緑色: E≥1.5、黄色: 1.0≤E<1.5）

### 評価ロジックのカスタマイズ

1. **「ロジック編集」タブ** を開く
2. 評価ロジックを日本語で編集
3. 「💾 保存」をクリック
4. 「予想実行」タブで結果を確認

## 開発

```bash
# 開発依存関係のインストール
pip install -r requirements-dev.txt

# テスト実行
pytest tests/unit/ -v

# リント・フォーマット
ruff check src/ tests/
ruff format src/ tests/

# 型チェック
mypy src/
```

## アーキテクチャ

```
UIレイヤー     : src/app.py （Streamlit）
         ↓
サービスレイヤー: src/orchestrator.py
         ↓
         ├── src/scraper/     (DataScraper + DataCleaner)
         ├── src/annotator/   (ContextAnnotator + VenuePlugin)
         ├── src/ai/          (GeminiProcessor)
         └── src/calculator/  (ExpectedValueCalculator)
         ↓
データレイヤー  : src/repository/ (CacheRepository → Parquet)
```

## ライセンス

MIT

---

**注意**: ボートレースへの投票は自己責任で行ってください。
このシステムの使用による損失に対して開発者は責任を負いません。
