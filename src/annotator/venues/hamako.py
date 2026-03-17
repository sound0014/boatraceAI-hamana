from __future__ import annotations

"""HamakoVenuePlugin: 浜名湖（会場コード: 06）固有の実装。

P0フェーズでは気象・潮位 API 未接続のスタブ。
P1フェーズで実際の API 接続に置き換える。
"""

import logging
from datetime import date

logger = logging.getLogger(__name__)


class HamakoVenuePlugin:
    """浜名湖（会場コード: 06）固有のコンテキスト情報を提供するプラグイン。

    P0: 気象・潮位情報はデフォルト値を返すスタブ実装。
    P1: 実際の気象・潮位 API に接続して情報を取得する。
    """

    venue_characteristics = """
## 浜名湖（会場コード: 06）の特徴

### 水面特性
- 海水面のため潮位（満潮・干潮）の影響を受ける
- 塩分を含む海水のため浮力がやや高く、タイムが出やすい傾向

### 風の影響
- 追い風時は1コース（イン）が有利になりやすい
- 向かい風が強い場合（5m/s以上）は差し・まくりが決まりやすい
- 横風（浜松方面からの西風）はターンが難しく波乱になりやすい

### 潮位の影響
- 満潮時: 波が立ちやすく外コースが有利になることがある
- 干潮時: 水面が安定し、インコースがより有利になる
- 中間: 標準的なコース有利不利が働く

### コース傾向
- 1コース（イン）勝率: 約55%（全国平均に近い）
- 向かい風強時: 3〜4コースのまくりが多くなる
"""

    async def fetch_weather(self, race_date: date) -> dict[str, float | str]:
        """気象情報を取得する。

        P0フェーズ: スタブ（デフォルト値を返す）
        P1フェーズ: 浜名湖周辺の気象APIを呼び出す実装に置き換える

        Returns:
            気象情報の辞書
        """
        logger.info(
            "HamakoVenuePlugin: P0スタブのため気象情報はデフォルト値を返します（%s）",
            race_date,
        )
        return {
            "wind_speed": 0.0,
            "wind_direction": "不明（P0スタブ）",
            "water_temperature": 0.0,
            "weather": "不明（P0スタブ）",
        }

    async def fetch_tide(self, race_date: date) -> dict[str, str]:
        """潮位情報を取得する。

        P0フェーズ: スタブ（デフォルト値を返す）
        P1フェーズ: 国土交通省潮位APIを呼び出す実装に置き換える

        Returns:
            潮位情報の辞書
        """
        logger.info(
            "HamakoVenuePlugin: P0スタブのため潮位情報はデフォルト値を返します（%s）",
            race_date,
        )
        return {
            "tide_level": "中間（P0スタブ）",
        }
