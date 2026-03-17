from __future__ import annotations

"""CacheRepository: Parquetキャッシュの読み書き。

同一レースの再実行時にスクレイピングを省略するためのキャッシュ機構。
ファイル命名規則: {venue_code}_{YYYYMMDD}_race{N}_{type}.parquet
"""

import logging
from dataclasses import asdict
from datetime import date
from pathlib import Path

import polars as pl

from src.models import RaceEntry

logger = logging.getLogger(__name__)

# キャッシュディレクトリ
_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"


class CacheRepository:
    """Parquetキャッシュの読み書きを担当するリポジトリ。"""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or _CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def save_race_entries(
        self,
        venue_code: str,
        race_date: date,
        race_number: int,
        entries: list[RaceEntry],
    ) -> None:
        """RaceEntryリストをParquetファイルに保存する。

        Args:
            venue_code: 会場コード
            race_date: 開催日
            race_number: レース番号
            entries: 保存するRaceEntryリスト
        """
        file_path = self._build_path(venue_code, race_date, race_number, "entries")
        records = [asdict(e) for e in entries]
        df = pl.DataFrame(records)
        df.write_parquet(file_path)
        logger.info("RaceEntryキャッシュ保存: %s", file_path)

    def load_race_entries(
        self,
        venue_code: str,
        race_date: date,
        race_number: int,
    ) -> list[RaceEntry] | None:
        """Parquetファイルからキャッシュ済みRaceEntryリストを読み込む。

        Args:
            venue_code: 会場コード
            race_date: 開催日
            race_number: レース番号

        Returns:
            キャッシュが存在する場合はRaceEntryリスト、存在しない場合はNone
        """
        file_path = self._build_path(venue_code, race_date, race_number, "entries")
        if not file_path.exists():
            return None

        try:
            df = pl.read_parquet(file_path)
            entries = [
                RaceEntry(
                    boat_number=row["boat_number"],
                    racer_name=row["racer_name"],
                    racer_id=row["racer_id"],
                    grade=row["grade"],
                    motor_no=row["motor_no"],
                    boat_no=row["boat_no"],
                    exhibition_time=row["exhibition_time"],
                    start_timing=row["start_timing"],
                    win_rate_all=row["win_rate_all"],
                    win_rate_venue=row["win_rate_venue"],
                    motor_win_rate=row["motor_win_rate"],
                    is_absent=row["is_absent"],
                    is_flying=row["is_flying"],
                )
                for row in df.to_dicts()
            ]
            logger.info("RaceEntryキャッシュヒット: %s", file_path)
            return entries
        except Exception as e:
            logger.warning("RaceEntryキャッシュ読み込み失敗（無視して続行）: %s", e)
            return None

    def save_odds(
        self,
        venue_code: str,
        race_date: date,
        race_number: int,
        odds: dict[str, dict[str, float]],
    ) -> None:
        """オッズデータをParquetファイルに保存する。

        Args:
            venue_code: 会場コード
            race_date: 開催日
            race_number: レース番号
            odds: {賭け式: {組み合わせ: オッズ}} の辞書
        """
        file_path = self._build_path(venue_code, race_date, race_number, "odds")
        records = []
        for bet_type, bet_odds in odds.items():
            for combo, value in bet_odds.items():
                records.append(
                    {
                        "bet_type": bet_type,
                        "combination": combo,
                        "odds": value,
                    }
                )
        df = (
            pl.DataFrame(records)
            if records
            else pl.DataFrame({"bet_type": [], "combination": [], "odds": []})
        )
        df.write_parquet(file_path)
        logger.info("オッズキャッシュ保存: %s", file_path)

    def load_odds(
        self,
        venue_code: str,
        race_date: date,
        race_number: int,
    ) -> dict[str, dict[str, float]] | None:
        """Parquetファイルからキャッシュ済みオッズデータを読み込む。

        Args:
            venue_code: 会場コード
            race_date: 開催日
            race_number: レース番号

        Returns:
            キャッシュが存在する場合はオッズ辞書、存在しない場合はNone
        """
        file_path = self._build_path(venue_code, race_date, race_number, "odds")
        if not file_path.exists():
            return None

        try:
            df = pl.read_parquet(file_path)
            odds: dict[str, dict[str, float]] = {}
            for row in df.to_dicts():
                bet_type = row["bet_type"]
                if bet_type not in odds:
                    odds[bet_type] = {}
                odds[bet_type][row["combination"]] = float(row["odds"])
            logger.info("オッズキャッシュヒット: %s", file_path)
            return odds
        except Exception as e:
            logger.warning("オッズキャッシュ読み込み失敗（無視して続行）: %s", e)
            return None

    def _build_path(
        self,
        venue_code: str,
        race_date: date,
        race_number: int,
        data_type: str,
    ) -> Path:
        """キャッシュファイルのパスを構築する。

        ファイル名形式: {venue_code}_{YYYYMMDD}_race{N}_{type}.parquet
        """
        date_str = race_date.strftime("%Y%m%d")
        filename = f"{venue_code}_{date_str}_race{race_number}_{data_type}.parquet"
        return self._cache_dir / filename
