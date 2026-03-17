from __future__ import annotations

"""Streamlit Web UI のエントリポイント。

起動コマンド: streamlit run src/app.py
"""

import asyncio
import logging
import os
from datetime import date
from pathlib import Path

import subprocess

import streamlit as st

from src.exceptions import BoatRaceAIError
from src.models import PredictionResult


@st.cache_resource(show_spinner="Playwright Chromium を初期化中...")
def _ensure_playwright_chromium() -> bool:
    """Playwright Chromium バイナリを確認し、未インストールなら自動インストールする。

    Streamlit Community Cloud では pip install playwright 後にバイナリが存在しないため、
    アプリ起動時に一度だけ playwright install chromium を実行する。
    @st.cache_resource により複数リクエストでも1回のみ実行される。

    Returns:
        インストール成功なら True
    """
    result = subprocess.run(
        ["playwright", "install", "chromium"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("playwright install chromium 失敗: %s", result.stderr)
        return False
    logger.info("playwright install chromium 完了")
    return True

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 設定
_LOGICS_DIR = Path(__file__).parent.parent / "logics"
_DEFAULT_LOGIC = "default_logic.md"
_VENUE_OPTIONS = {"浜名湖 (06)": "06"}  # 将来拡張用


def render_prediction_page() -> None:
    """予想実行ページを描画する。"""
    st.header("🏁 予想実行")

    with st.form("prediction_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            venue_label = st.selectbox("会場", list(_VENUE_OPTIONS.keys()))
        with col2:
            race_date = st.date_input("開催日", value=date.today())
        with col3:
            race_number = st.number_input("レース番号", min_value=1, max_value=12, value=1, step=1)

        # 評価ロジックファイル選択
        logic_files = sorted(_LOGICS_DIR.glob("*.md"))
        logic_options = [f.name for f in logic_files]
        if not logic_options:
            st.warning("logics/ ディレクトリにロジックファイルがありません。")
            logic_options = [_DEFAULT_LOGIC]

        selected_logic = st.selectbox("評価ロジック", logic_options)
        submitted = st.form_submit_button("🚀 予想実行", use_container_width=True)

    if submitted:
        venue_code = _VENUE_OPTIONS[venue_label]
        logic_path = str(_LOGICS_DIR / selected_logic)
        _run_prediction(venue_code, race_date, race_number, logic_path)

    # セッション結果の表示
    if "prediction_result" in st.session_state and st.session_state.prediction_result:
        _display_result(st.session_state.prediction_result)


def _run_prediction(
    venue_code: str,
    race_date: date,
    race_number: int,
    logic_path: str,
) -> None:
    """予想を実行してsession_stateに結果を保存する。"""
    from src.orchestrator import Orchestrator

    with st.spinner("⏳ データ収集・AI推論・期待値計算中...（最大3分）"):
        try:
            orchestrator = Orchestrator(venue_code)
            result = asyncio.run(orchestrator.run_prediction(race_date, race_number, logic_path))
            st.session_state.prediction_result = result
            st.success(f"✅ 予想完了！処理時間: {result.pipeline_duration_sec:.1f}秒")
        except BoatRaceAIError as e:
            st.error(f"❌ {e}")
            logger.error("予想実行エラー: %s", e)
        except Exception as e:
            st.error(f"❌ 予期しないエラーが発生しました: {e}\n開発者に報告してください。")
            logger.exception("予期しないエラー")


def _display_result(result: PredictionResult) -> None:
    """予想結果を表示する。"""
    st.divider()
    context = result.race_context
    inference = result.inference

    # メタ情報
    st.subheader(f"📊 {context.venue_name} {context.race_date} 第{context.race_number}レース")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("E>1.0 買い目数", f"{len(result.positive_ev_bets)}件")
    with col2:
        top_ev = result.positive_ev_bets[0].expected_value if result.positive_ev_bets else 0
        st.metric("最高期待値", f"{top_ev:.2f}")
    with col3:
        st.metric("処理時間", f"{result.pipeline_duration_sec:.1f}秒")

    # 推論根拠
    with st.expander("🤖 Gemini 推論根拠"):
        st.markdown(inference.reasoning)

        st.markdown("**各艇の1着確率（Gemini推論）**")
        prob_data = {
            "艇番": list(inference.win_probabilities.keys()),
            "1着確率": [f"{v:.1%}" for v in inference.win_probabilities.values()],
        }
        st.table(prob_data)

    # 期待値テーブル
    st.subheader("💰 期待値ランキング（E > 1.0 の買い目）")
    if not result.positive_ev_bets:
        st.info("E > 1.0 の買い目がありませんでした。評価ロジックを見直してください。")
    else:
        import pandas as pd

        rows = []
        for ev in result.positive_ev_bets:
            combo_str = "-".join(str(b) for b in ev.boat_combination)
            rows.append(
                {
                    "賭け式": ev.bet_type,
                    "買い目": combo_str,
                    "確率": f"{ev.probability:.1%}",
                    "オッズ": f"{ev.odds:.1f}",
                    "期待値": ev.expected_value,
                }
            )

        df = pd.DataFrame(rows)

        # カラーコーディング
        def color_ev(val: float) -> str:
            if val >= 1.5:
                return "background-color: #c6efce; color: #276221"  # 緑
            elif val >= 1.0:
                return "background-color: #ffeb9c; color: #9c6500"  # 黄
            return ""

        styled = df.style.applymap(color_ev, subset=["期待値"]).format({"期待値": "{:.4f}"})
        st.dataframe(styled, use_container_width=True)

        # CSVダウンロード
        csv_buf = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "📥 CSV ダウンロード",
            data=csv_buf,
            file_name=f"ev_{context.race_date}_{context.venue_code}_R{context.race_number}.csv",
            mime="text/csv",
        )

    # 全買い目（展開表示）
    with st.expander("全買い目を表示（E < 1.0 含む）"):
        if result.expected_values:
            import pandas as pd

            all_rows = []
            for ev in result.expected_values:
                combo_str = "-".join(str(b) for b in ev.boat_combination)
                all_rows.append(
                    {
                        "賭け式": ev.bet_type,
                        "買い目": combo_str,
                        "確率": f"{ev.probability:.1%}",
                        "オッズ": f"{ev.odds:.1f}",
                        "期待値": f"{ev.expected_value:.4f}",
                        "推奨": "○" if ev.is_positive_ev else "×",
                    }
                )
            st.dataframe(pd.DataFrame(all_rows), use_container_width=True)


def render_logic_edit_page() -> None:
    """ロジック編集ページを描画する。"""
    st.header("✏️ 評価ロジック編集")

    logic_files = sorted(_LOGICS_DIR.glob("*.md"))
    logic_options = [f.name for f in logic_files]
    if not logic_options:
        logic_options = [_DEFAULT_LOGIC]

    selected = st.selectbox("編集するロジックファイル", logic_options)
    logic_path = _LOGICS_DIR / selected

    # 現在の内容を読み込む
    current_content = ""
    if logic_path.exists():
        current_content = logic_path.read_text(encoding="utf-8")
    else:
        current_content = "# 新しい評価ロジック\n\n## 重視する要素\n1. \n"

    edited = st.text_area(
        f"{selected} の内容",
        value=current_content,
        height=400,
        help="日本語でロジックを記述してください。Markdown形式で書けます。",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("💾 保存", use_container_width=True):
            try:
                _LOGICS_DIR.mkdir(parents=True, exist_ok=True)
                logic_path.write_text(edited, encoding="utf-8")
                st.success("✅ 保存しました！")
            except Exception as e:
                st.error(f"❌ 保存に失敗しました: {e}")
    with col2:
        if st.button("↩️ デフォルトに戻す", use_container_width=True):
            default_path = _LOGICS_DIR / _DEFAULT_LOGIC
            if default_path.exists():
                logic_path.write_text(default_path.read_text(encoding="utf-8"), encoding="utf-8")
                st.success("デフォルトロジックに戻しました。ページをリロードしてください。")


def render_help_page() -> None:
    """使い方ページを描画する。"""
    st.header("📖 使い方")
    st.markdown("""
## 基本操作

### 1. 予想を実行する
1. **「予想実行」タブ** を選択
2. 会場・開催日・レース番号を選択
3. 使用したい評価ロジックを選択
4. **「🚀 予想実行」** ボタンをクリック
5. 結果の **期待値ランキング** を確認

### 2. 評価ロジックを変更する
1. **「ロジック編集」タブ** を選択
2. 編集したいロジックファイルを選択
3. テキストエリアで内容を日本語で編集
4. **「💾 保存」** ボタンをクリック

### 3. 結果をエクスポートする
- 期待値ランキング表示後、**「📥 CSV ダウンロード」** をクリック

---

## 期待値の見方

| 期待値 | 表示 | 意味 |
|--------|------|------|
| **≥ 1.5** | 🟢 緑 | 強く推奨（長期的に利益が見込める） |
| **1.0 〜 1.5** | 🟡 黄 | 推奨（理論上プラス） |
| **< 1.0** | グレー | 非推奨（デフォルト非表示） |

---

## セットアップ

```bash
# 1. 環境変数の設定
cp .env.example .env
# .env に GEMINI_API_KEY を設定

# 2. 依存関係のインストール
pip install -r requirements.txt

# 3. Playwright ブラウザのインストール
playwright install chromium

# 4. アプリ起動
streamlit run src/app.py
```
""")


def main() -> None:
    """Streamlitアプリのメイン関数。"""
    # Playwright Chromium バイナリの確認・自動インストール（初回のみ）
    _ensure_playwright_chromium()

    st.set_page_config(
        page_title="BoatRaceAI-Hamana",
        page_icon="⛵",
        layout="wide",
    )

    st.title("⛵ BoatRaceAI-Hamana")
    st.caption("浜名湖特化型・共創AI予想プラットフォーム")

    tab1, tab2, tab3 = st.tabs(["🏁 予想実行", "✏️ ロジック編集", "📖 使い方"])

    with tab1:
        render_prediction_page()

    with tab2:
        render_logic_edit_page()

    with tab3:
        render_help_page()


if __name__ == "__main__":
    main()
