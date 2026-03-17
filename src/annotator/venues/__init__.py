from __future__ import annotations

"""VenuePlugin レジストリ: 会場コード → VenuePlugin のマッピング。

新会場を追加する際は:
1. `venues/[venue_code].py` を作成して VenuePlugin Protocol を実装する
2. このファイルの VENUE_REGISTRY にエントリを追加する
3. `config/venues.yaml` に会場設定を追記する
"""

from src.annotator.venues.hamako import HamakoVenuePlugin

# 会場コード → VenuePlugin クラスのマッピング
VENUE_REGISTRY: dict[str, type] = {
    "06": HamakoVenuePlugin,  # 浜名湖
    # P2以降で追加:
    # "01": KiryuVenuePlugin,  # 桐生
    # "02": TodaVenuePlugin,   # 戸田
}


def get_venue_plugin(venue_code: str) -> object:
    """会場コードに対応するVenuePluginのインスタンスを返す。

    Args:
        venue_code: 会場コード（例: "06"）

    Returns:
        VenuePlugin のインスタンス

    Raises:
        KeyError: 対応するプラグインが登録されていない場合
    """
    if venue_code not in VENUE_REGISTRY:
        raise KeyError(
            f"会場コード '{venue_code}' に対応するプラグインが見つかりません。"
            f"登録済みコード: {list(VENUE_REGISTRY.keys())}"
        )
    plugin_class = VENUE_REGISTRY[venue_code]
    return plugin_class()
