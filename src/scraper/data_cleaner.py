from __future__ import annotations

"""DataCleaner: スクレイピング生データのクレンジングとバリデーション。"""

import logging
from datetime import date

from src.exceptions import DataValidationError
from src.models import RaceContext, RaceEntry

logger = logging.getLogger(__name__)


class DataCleaner:
    """スクレイピングで取得した生データをクレンジングしてデータモデルに変換する。

    F（フライング）・欠場・異常値を検出し、フラグを設定する。
    """

    # 展示タイム異常値閾値
    EXHIBITION_TIME_MIN = 6.00
    EXHIBITION_TIME_MAX = 7.50

    # スタートタイミング閾値
    START_TIMING_FLYING_THRESHOLD = 0.0  # この値未満はフライング
    START_TIMING_LATE_WARN = 1.0  # この値超は遅れスタート警告

    # 最低出走艇数（6艇中2艇以上欠場でエラー: 実質4艇以上必要）
    MIN_ENTRY_COUNT = 4

    def clean_entries(self, raw_entries: list[dict]) -> list[RaceEntry]:
        """生データをクレンジングしてRaceEntryリストを返す。

        Args:
            raw_entries: スクレイピングで取得した生データのリスト

        Returns:
            クレンジング済みのRaceEntryリスト

        Raises:
            DataValidationError: 出走艇数が不正な場合
        """
        active_entries = [e for e in raw_entries if not e.get("is_absent", False)]
        if len(active_entries) < self.MIN_ENTRY_COUNT:
            raise DataValidationError(
                "entries",
                f"出走艇数が不足しています: {len(active_entries)}艇（最低{self.MIN_ENTRY_COUNT}艇必要）",
            )

        entries = []
        for raw in raw_entries:
            entry = self._build_entry(raw)
            entries.append(entry)
        return entries

    def validate_race_context(
        self,
        context: RaceContext,
    ) -> tuple[bool, list[str]]:
        """レースコンテキストのバリデーション結果と警告リストを返す。

        Args:
            context: バリデーション対象のレースコンテキスト

        Returns:
            (is_valid, warnings): バリデーション結果と警告メッセージリスト
        """
        warnings: list[str] = []
        is_valid = True

        # 出走艇数チェック
        active_entries = [e for e in context.entries if not e.is_absent]
        if len(active_entries) < self.MIN_ENTRY_COUNT:
            is_valid = False
            warnings.append(
                f"出走艇数が不足: {len(active_entries)}艇（最低{self.MIN_ENTRY_COUNT}艇）"
            )

        # 各艇のデータチェック
        for entry in context.entries:
            if entry.is_absent:
                continue
            entry_warnings = self._validate_entry(entry)
            warnings.extend(entry_warnings)

        return is_valid, warnings

    def _build_entry(self, raw: dict) -> RaceEntry:
        """生データからRaceEntryを構築する。"""
        boat_number = int(raw.get("boat_number", 0))
        start_timing = float(raw.get("start_timing", 0.0))
        exhibition_time = float(raw.get("exhibition_time", 0.0))
        is_absent = bool(raw.get("is_absent", False))

        # F（フライング）判定
        is_flying = start_timing < self.START_TIMING_FLYING_THRESHOLD and not is_absent

        entry = RaceEntry(
            boat_number=boat_number,
            racer_name=str(raw.get("racer_name", "")),
            racer_id=str(raw.get("racer_id", "")),
            grade=str(raw.get("grade", "B1")),
            motor_no=int(raw.get("motor_no", 0)),
            boat_no=int(raw.get("boat_no", 0)),
            exhibition_time=exhibition_time,
            start_timing=start_timing,
            win_rate_all=float(raw.get("win_rate_all", 0.0)),
            win_rate_venue=float(raw.get("win_rate_venue", 0.0)),
            motor_win_rate=float(raw.get("motor_win_rate", 0.0)),
            is_absent=is_absent,
            is_flying=is_flying,
        )

        # 異常値の警告ログ（値は保持）
        if not is_absent:
            self._log_anomalies(entry)

        return entry

    def _validate_entry(self, entry: RaceEntry) -> list[str]:
        """単一エントリのバリデーション警告を返す。"""
        warnings: list[str] = []

        if not (0.0 <= entry.win_rate_all <= 1.0):
            warnings.append(f"{entry.boat_number}号艇: 全国勝率が範囲外 ({entry.win_rate_all})")

        if not (0.0 <= entry.win_rate_venue <= 1.0):
            warnings.append(f"{entry.boat_number}号艇: 当地勝率が範囲外 ({entry.win_rate_venue})")

        return warnings

    def _log_anomalies(self, entry: RaceEntry) -> None:
        """異常値を検出した場合に警告ログを出力する（値は保持）。"""
        if entry.exhibition_time > 0 and not (
            self.EXHIBITION_TIME_MIN <= entry.exhibition_time <= self.EXHIBITION_TIME_MAX
        ):
            logger.warning(
                "%d号艇: 展示タイム異常値 %.2f秒（基準: %.2f〜%.2f）",
                entry.boat_number,
                entry.exhibition_time,
                self.EXHIBITION_TIME_MIN,
                self.EXHIBITION_TIME_MAX,
            )

        if entry.start_timing > self.START_TIMING_LATE_WARN:
            logger.warning(
                "%d号艇: スタートタイミング遅延 %.2f秒（警告閾値: %.2f）",
                entry.boat_number,
                entry.start_timing,
                self.START_TIMING_LATE_WARN,
            )


def build_race_context_from_scraping(
    venue_code: str,
    venue_name: str,
    race_date: date,
    race_number: int,
    race_grade: str,
    entries: list[RaceEntry],
) -> RaceContext:
    """スクレイピング結果から基本のRaceContextを構築する。

    気象・潮位情報はContextAnnotatorが後から付与するため、デフォルト値を設定する。
    """
    return RaceContext(
        venue_code=venue_code,
        venue_name=venue_name,
        race_date=race_date,
        race_number=race_number,
        race_grade=race_grade,
        wind_speed=0.0,
        wind_direction="不明",
        water_temperature=0.0,
        tide_level="中間",
        weather="不明",
        entries=entries,
    )
