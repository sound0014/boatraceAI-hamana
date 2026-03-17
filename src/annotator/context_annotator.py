from __future__ import annotations

"""ContextAnnotator: 会場固有のコンテキスト情報をRaceContextに注釈として付与する。"""

import logging
from dataclasses import replace

from src.annotator.venues import get_venue_plugin
from src.models import RaceContext

logger = logging.getLogger(__name__)


class ContextAnnotator:
    """会場固有のコンテキスト情報（気象・潮位・水面特性）をRaceContextに付与する。

    会場プラグインパターンを採用し、浜名湖以外の会場への拡張をプラグイン追加のみで対応できる。
    """

    def __init__(self, venue_code: str) -> None:
        self.venue_code = venue_code
        self._plugin = get_venue_plugin(venue_code)

    async def annotate(self, context: RaceContext) -> RaceContext:
        """気象・潮位情報を取得してRaceContextを更新する。

        Args:
            context: 基本情報（出走艇・レース情報）が設定済みのRaceContext

        Returns:
            気象・潮位情報が追加されたRaceContext
        """
        try:
            weather_data = await self._plugin.fetch_weather(context.race_date)  # type: ignore[attr-defined]
            tide_data = await self._plugin.fetch_tide(context.race_date)  # type: ignore[attr-defined]

            # dataclassのreplaceで新しいインスタンスを生成（イミュータブルパターン）
            return replace(
                context,
                wind_speed=float(weather_data.get("wind_speed", 0.0)),
                wind_direction=str(weather_data.get("wind_direction", "不明")),
                water_temperature=float(weather_data.get("water_temperature", 0.0)),
                weather=str(weather_data.get("weather", "不明")),
                tide_level=str(tide_data.get("tide_level", "中間")),
            )

        except Exception as e:
            logger.warning(
                "コンテキスト注釈の取得に失敗しました（処理を継続します）: %s",
                e,
            )
            return context

    @property
    def venue_characteristics(self) -> str:
        """会場固有の特性テキストを返す（Geminiプロンプトへの注入用）。"""
        return str(self._plugin.venue_characteristics)  # type: ignore[attr-defined]
