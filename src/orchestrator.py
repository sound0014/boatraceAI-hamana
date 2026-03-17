from __future__ import annotations

"""Orchestrator: 予想実行の全パイプラインを制御する。

データ収集 → コンテキスト付与 → AI推論 → 期待値計算 の全体を担当し、
PredictionResult を生成して UIレイヤーに返す。
"""

import asyncio
import logging
import time
from datetime import date, datetime

from dotenv import load_dotenv

from src.ai.gemini_processor import GeminiProcessor
from src.annotator.context_annotator import ContextAnnotator
from src.calculator.ev_calculator import ExpectedValueCalculator
from src.exceptions import BoatRaceAIError
from src.models import PredictionResult, RaceContext
from src.repository.cache_repository import CacheRepository
from src.scraper.data_scraper import DataScraper

load_dotenv()

logger = logging.getLogger(__name__)

# パイプラインタイムアウト（秒）
_PIPELINE_TIMEOUT_SEC = 180


def _get_api_key() -> str:
    """環境変数からGemini APIキーを取得する。"""
    import os

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise BoatRaceAIError(
            "GEMINI_API_KEY が設定されていません。.env ファイルを確認してください。"
        )
    return api_key


class Orchestrator:
    """予想実行の全パイプラインを制御するオーケストレーター。

    各エンジンの呼び出し順序・タイムアウト管理・エラー伝播を担当する。
    """

    def __init__(self, venue_code: str) -> None:
        self.venue_code = venue_code
        self._scraper = DataScraper(venue_code)
        self._annotator = ContextAnnotator(venue_code)
        self._ev_calc = ExpectedValueCalculator()
        self._cache = CacheRepository()

    async def run_prediction(
        self,
        race_date: date,
        race_number: int,
        logic_file_path: str,
    ) -> PredictionResult:
        """全パイプラインを実行して予想結果を返す。

        Args:
            race_date: 開催日
            race_number: レース番号（1-12）
            logic_file_path: 評価ロジックMarkdownファイルのパス

        Returns:
            予想実行結果（期待値ランキング等を含む）

        Raises:
            BoatRaceAIError: パイプライン実行中にエラーが発生した場合
            asyncio.TimeoutError: 3分以内に処理が完了しなかった場合
        """
        start_time = time.monotonic()
        executed_at = datetime.now()

        try:
            result = await asyncio.wait_for(
                self._execute_pipeline(race_date, race_number, logic_file_path),
                timeout=_PIPELINE_TIMEOUT_SEC,
            )
        except TimeoutError:
            raise BoatRaceAIError(
                f"処理時間が上限（{_PIPELINE_TIMEOUT_SEC}秒）を超えました。"
                "ネットワーク状況を確認し、再試行してください。"
            )

        duration = time.monotonic() - start_time
        logger.info(
            "パイプライン完了: %s 第%dレース (%.1f秒)",
            race_date,
            race_number,
            duration,
        )

        context, inference, ev_list = result
        positive_ev_bets = self._ev_calc.get_positive_ev_bets(ev_list)

        return PredictionResult(
            race_context=context,
            inference=inference,
            expected_values=ev_list,
            positive_ev_bets=positive_ev_bets,
            pipeline_duration_sec=duration,
            executed_at=executed_at,
        )

    async def _execute_pipeline(
        self,
        race_date: date,
        race_number: int,
        logic_file_path: str,
    ) -> tuple:
        """実際のパイプライン処理を実行する（タイムアウト対象）。"""
        api_key = _get_api_key()

        # ステップ1: 出走表取得とオッズ取得を並列実行（キャッシュ確認含む）
        logger.info("ステップ1: データ取得開始（出走表・オッズ並列）")
        context_task = self._get_race_context(race_date, race_number)
        odds_task = self._get_odds(race_date, race_number)

        race_context, odds = await asyncio.gather(context_task, odds_task)
        logger.info("ステップ1完了: 出走艇%d艇取得", len(race_context.entries))

        # ステップ2: コンテキスト注釈（気象・潮位情報付与）
        logger.info("ステップ2: コンテキスト注釈")
        race_context = await self._annotator.annotate(race_context)

        # ステップ3: Gemini AI 推論
        logger.info("ステップ3: Gemini AI 推論")
        gemini = GeminiProcessor(
            api_key=api_key,
            venue_characteristics=self._annotator.venue_characteristics,
        )
        inference = await gemini.infer(race_context, logic_file_path)
        logger.info(
            "ステップ3完了: 1着推論結果 %s",
            {k: f"{v:.3f}" for k, v in inference.win_probabilities.items()},
        )

        # ステップ4: 期待値計算
        logger.info("ステップ4: 期待値計算")
        ev_list = self._ev_calc.calculate_all(inference, odds)
        positive_count = sum(1 for ev in ev_list if ev.is_positive_ev)
        logger.info(
            "ステップ4完了: %d件中 E>1.0 が %d件",
            len(ev_list),
            positive_count,
        )

        return race_context, inference, ev_list

    async def _get_race_context(self, race_date: date, race_number: int) -> RaceContext:  # type: ignore[return]
        """出走表を取得する（キャッシュ確認あり）。"""
        # キャッシュ確認
        cached_entries = self._cache.load_race_entries(self.venue_code, race_date, race_number)
        if cached_entries is not None:
            logger.info("出走表キャッシュヒット")
            from src.scraper.data_cleaner import build_race_context_from_scraping

            return build_race_context_from_scraping(
                venue_code=self.venue_code,
                venue_name=self._scraper._get_venue_name(),
                race_date=race_date,
                race_number=race_number,
                race_grade="一般",  # キャッシュからは grade が取れないため暫定値
                entries=cached_entries,
            )

        # スクレイピング
        context = await self._scraper.fetch_race_entries(race_date, race_number)

        # キャッシュ保存
        try:
            self._cache.save_race_entries(self.venue_code, race_date, race_number, context.entries)
        except Exception as e:
            logger.warning("出走表キャッシュ保存失敗（無視して続行）: %s", e)

        return context

    async def _get_odds(self, race_date: date, race_number: int) -> dict:  # type: ignore[return]
        """オッズを取得する（キャッシュ確認あり）。"""
        # キャッシュ確認
        cached_odds = self._cache.load_odds(self.venue_code, race_date, race_number)
        if cached_odds is not None:
            logger.info("オッズキャッシュヒット")
            return cached_odds

        # スクレイピング
        odds = await self._scraper.fetch_realtime_odds(race_date, race_number)

        # キャッシュ保存
        try:
            self._cache.save_odds(self.venue_code, race_date, race_number, odds)
        except Exception as e:
            logger.warning("オッズキャッシュ保存失敗（無視して続行）: %s", e)

        return odds
