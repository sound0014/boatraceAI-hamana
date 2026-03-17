from __future__ import annotations

"""GeminiProcessor: Gemini APIを使ってレース出走表から各艇の着順確率を推論する。"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import google.generativeai as genai

from src.exceptions import GeminiAPIError, JSONParseError
from src.models import GeminiInference, RaceContext

logger = logging.getLogger(__name__)

# Gemini API のレート制限対応
_GEMINI_RETRY_WAIT_SEC = 30


class GeminiProcessor:
    """評価ロジックファイルとRaceContextをGemini APIに送信し、各艇の着順確率を推論する。

    評価ロジックファイル（Markdown）を読み込み、RaceContextと組み合わせて
    Gemini APIに送信し、確率辞書を返す。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.1-flash-lite-preview",
        venue_characteristics: str = "",
    ) -> None:
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._model_name = model
        self._venue_characteristics = venue_characteristics

    async def infer(
        self,
        context: RaceContext,
        logic_file_path: str,
    ) -> GeminiInference:
        """レースコンテキストと評価ロジックからAI推論結果を返す。

        Args:
            context: スクレイピング・コンテキスト注釈済みのレース情報
            logic_file_path: 評価ロジックMarkdownファイルのパス

        Returns:
            各艇の1着確率と推論根拠を含むGeminiInference

        Raises:
            GeminiAPIError: API呼び出し失敗またはリトライ上限に達した場合
            JSONParseError: レスポンスのJSON解析に失敗した場合
        """
        logic_content = self._load_logic_file(logic_file_path)
        logic_name = Path(logic_file_path).stem
        prompt = self._build_prompt(context, logic_content)

        # リトライ付きAPI呼び出し
        for attempt in range(2):  # 最大2回（初回 + 1回リトライ）
            try:
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._model.generate_content(prompt),
                )
                response_text = response.text

                win_probabilities, reasoning = self._parse_response(response_text)
                win_probabilities = self._normalize_probabilities(win_probabilities)

                return GeminiInference(
                    race_context=context,
                    logic_name=logic_name,
                    logic_content=logic_content,
                    win_probabilities=win_probabilities,
                    reasoning=reasoning,
                    inferred_at=datetime.now(),
                    model_version=self._model_name,
                )

            except JSONParseError:
                if attempt == 0:
                    logger.warning("Geminiレスポンスのパースに失敗。リトライします（1回目）")
                    continue
                raise
            except Exception as e:
                error_msg = str(e)
                if "quota" in error_msg.lower() or "rate" in error_msg.lower():
                    if attempt == 0:
                        logger.warning(
                            "Gemini APIレート制限。%d秒待機後リトライ",
                            _GEMINI_RETRY_WAIT_SEC,
                        )
                        await asyncio.sleep(_GEMINI_RETRY_WAIT_SEC)
                        continue
                raise GeminiAPIError(f"Gemini API呼び出しに失敗しました: {e}") from e

        raise GeminiAPIError("Gemini API のリトライ上限に達しました")

    def _load_logic_file(self, logic_file_path: str) -> str:
        """評価ロジックファイルを読み込む。

        Args:
            logic_file_path: ロジックファイルのパス

        Returns:
            ロジックファイルの内容

        Raises:
            GeminiAPIError: ファイルが見つからない場合
        """
        path = Path(logic_file_path)
        if not path.exists():
            raise GeminiAPIError(f"評価ロジックファイルが見つかりません: {logic_file_path}")
        return path.read_text(encoding="utf-8")

    def _build_prompt(self, context: RaceContext, logic_content: str) -> str:
        """Gemini APIに渡すプロンプトを組み立てる。

        Args:
            context: レースコンテキスト
            logic_content: 評価ロジックの内容

        Returns:
            組み立てられたプロンプト文字列
        """
        entries_md = self._build_entries_markdown(context)

        return f"""## システム指示
あなたはボートレース予想の専門AIです。以下の評価ロジックとレースデータから
各艇の1着確率を推論し、必ずJSON形式のみで返してください。
推論根拠も日本語で簡潔に記述してください。

## 評価ロジック（ユーザー定義）
{logic_content}

## レース情報
- 会場: {context.venue_name}（{context.venue_code}）
- 日付: {context.race_date} 第{context.race_number}レース
- レースグレード: {context.race_grade}
- 天候: {context.weather}
- 風速: {context.wind_speed}m/s ({context.wind_direction})
- 水温: {context.water_temperature}℃
- 潮位: {context.tide_level}

{self._venue_characteristics}

## 出走艇データ
{entries_md}

## 出力形式（必ずこのJSON形式のみで返答）
```json
{{
  "probabilities": {{
    "1": 0.35,
    "2": 0.20,
    "3": 0.15,
    "4": 0.15,
    "5": 0.10,
    "6": 0.05
  }},
  "reasoning": "推論根拠の説明（日本語で2〜5文程度）"
}}
```

注意:
- probabilitiesの値の合計は必ず1.0にすること
- 欠場艇の確率は0.0にすること
- reasoning は日本語で記述すること
"""

    def _build_entries_markdown(self, context: RaceContext) -> str:
        """出走艇データをMarkdown形式に変換する。"""
        lines = [
            "| 艇番 | 選手名 | 級別 | 全国勝率 | 当地勝率 | モーター2連対率 | 展示タイム | スタートタイミング | 状態 |",
            "|------|--------|------|---------|---------|----------------|-----------|-----------------|------|",
        ]
        for entry in context.entries:
            status = []
            if entry.is_absent:
                status.append("欠場")
            if entry.is_flying:
                status.append("F")
            status_str = "・".join(status) if status else "正常"

            lines.append(
                f"| {entry.boat_number} | {entry.racer_name} | {entry.grade} "
                f"| {entry.win_rate_all:.3f} | {entry.win_rate_venue:.3f} "
                f"| {entry.motor_win_rate:.3f} | {entry.exhibition_time:.2f}秒 "
                f"| {entry.start_timing:.2f}秒 | {status_str} |"
            )
        return "\n".join(lines)

    def _parse_response(self, response_text: str) -> tuple[dict[int, float], str]:
        """GeminiレスポンスからJSON解析し確率辞書と根拠を返す。

        Args:
            response_text: Geminiのレスポンステキスト

        Returns:
            (win_probabilities, reasoning): 確率辞書と根拠テキスト

        Raises:
            JSONParseError: JSON解析に失敗した場合
        """
        # コードブロックの除去
        text = response_text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        # JSON部分の抽出（テキストが混入している場合）
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise JSONParseError(f"GeminiレスポンスにJSONが見つかりません: {response_text[:200]}")

        json_text = text[start:end]
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            raise JSONParseError(
                f"Geminiレスポンスのパースに失敗: {e}\nレスポンス: {json_text[:200]}"
            ) from e

        # probabilitiesキーの確認
        if "probabilities" not in data:
            raise JSONParseError(f"Geminiレスポンスに 'probabilities' キーがありません: {data}")

        # 確率辞書を int キーに変換
        win_probabilities: dict[int, float] = {}
        for key, val in data["probabilities"].items():
            try:
                boat_num = int(key)
                probability = float(val)
                if not (0.0 <= probability <= 1.0):
                    logger.warning(
                        "%d号艇の確率値が範囲外 (%.4f)。クリップします。",
                        boat_num,
                        probability,
                    )
                    probability = max(0.0, min(1.0, probability))
                win_probabilities[boat_num] = probability
            except (ValueError, TypeError) as e:
                raise JSONParseError(f"確率値のパースに失敗: key={key}, val={val}") from e

        reasoning = str(data.get("reasoning", "推論根拠なし"))
        return win_probabilities, reasoning

    def _normalize_probabilities(
        self,
        probs: dict[int, float],
    ) -> dict[int, float]:
        """確率の合計が1.0になるよう正規化する。

        Args:
            probs: 正規化前の確率辞書

        Returns:
            正規化後の確率辞書（合計 = 1.0）
        """
        total = sum(probs.values())
        if total <= 0.0:
            # 全て0の場合は均等配分
            logger.warning("確率の合計が0.0です。均等配分にフォールバックします。")
            n = len(probs)
            return {k: 1.0 / n for k in probs} if n > 0 else probs

        if abs(total - 1.0) < 1e-6:
            return probs

        logger.warning(
            "確率の合計が1.0でないため正規化します: %.4f → 1.0",
            total,
        )
        return {k: v / total for k, v in probs.items()}
