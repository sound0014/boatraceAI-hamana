from __future__ import annotations

"""VenuePlugin Protocol: 会場固有のコンテキスト情報を提供するプラグインインターフェース。"""

from datetime import date
from typing import Protocol, runtime_checkable


@runtime_checkable
class VenuePlugin(Protocol):
    """会場固有のコンテキスト情報を提供するプラグインのインターフェース。

    新会場を追加する際は、このProtocolを実装するクラスを作成し、
    venues/__init__.py のレジストリに登録する。
    """

    @property
    def venue_characteristics(self) -> str:
        """水面特性・特徴の説明文（Geminiプロンプトに注釈として挿入）。"""
        ...

    async def fetch_weather(self, race_date: date) -> dict[str, float | str]:
        """会場の気象情報を取得する。

        Returns:
            {
                "wind_speed": float,       # 風速 (m/s)
                "wind_direction": str,     # 風向き
                "water_temperature": float, # 水温 (℃)
                "weather": str,            # 天候
            }
        """
        ...

    async def fetch_tide(self, race_date: date) -> dict[str, str]:
        """潮位情報を取得する（対応する会場のみ）。

        Returns:
            {
                "tide_level": str,  # 潮位状況（例: "満潮"/"干潮"/"中間"）
            }
        """
        ...
