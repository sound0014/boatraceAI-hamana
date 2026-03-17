from __future__ import annotations

"""DataScraper: Playwrightによるボートレース公式サイトの非同期スクレイピング。"""

import asyncio
import logging
import re
from datetime import date

from playwright.async_api import async_playwright

from src.exceptions import ScrapingError
from src.models import RaceContext, RaceResult
from src.scraper.data_cleaner import DataCleaner, build_race_context_from_scraping

logger = logging.getLogger(__name__)

# ボートレース公式サイトのURLテンプレート
_BASE = "https://www.boatrace.jp/owpc/pc/race"
_URL_RACELIST = f"{_BASE}/racelist"
_URL_BEFOREINFO = f"{_BASE}/beforeinfo"
_URL_ODDS3T = f"{_BASE}/odds3t"
_URL_ODDS2TF = f"{_BASE}/odds2tf"
_URL_ODDSTF = f"{_BASE}/oddstf"
_URL_RACERESULT = f"{_BASE}/raceresult"


def _build_url(base: str, venue_code: str, race_date: date, race_number: int) -> str:
    """ボートレース公式サイトのURLを組み立てる。"""
    hd = race_date.strftime("%Y%m%d")
    return f"{base}?rno={race_number}&jcd={venue_code}&hd={hd}"


class DataScraper:
    """ボートレース公式サイトから出走表・展示情報・オッズ・結果を取得する。

    会場コードをパラメータとして受け取り、浜名湖以外への拡張に対応する。
    """

    SCRAPING_INTERVAL_SEC = 1.0
    TIMEOUT_MS = 30_000  # 30秒（ミリ秒単位）
    MAX_RETRIES = 3

    def __init__(self, venue_code: str) -> None:
        self.venue_code = venue_code
        self._cleaner = DataCleaner()

    async def fetch_race_entries(
        self,
        race_date: date,
        race_number: int,
    ) -> RaceContext:
        """出走表と直前情報を取得してRaceContextを返す。

        Args:
            race_date: 開催日
            race_number: レース番号（1-12）

        Returns:
            出走艇情報と基本レース情報を含むRaceContext

        Raises:
            ScrapingError: スクレイピングが失敗した場合
        """
        racelist_url = _build_url(_URL_RACELIST, self.venue_code, race_date, race_number)
        beforeinfo_url = _build_url(_URL_BEFOREINFO, self.venue_code, race_date, race_number)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = await context.new_page()

                # 出走表の取得
                raw_entries = await self._fetch_racelist(page, racelist_url)
                await asyncio.sleep(self.SCRAPING_INTERVAL_SEC)

                # 直前情報（展示タイム・スタートタイミング）の取得
                await self._fetch_beforeinfo(page, beforeinfo_url, raw_entries)

            finally:
                await browser.close()

        entries = self._cleaner.clean_entries(raw_entries)

        # 会場名をvenue_codeから取得（簡易実装）
        venue_name = self._get_venue_name()
        race_grade = raw_entries[0].get("race_grade", "一般") if raw_entries else "一般"

        return build_race_context_from_scraping(
            venue_code=self.venue_code,
            venue_name=venue_name,
            race_date=race_date,
            race_number=race_number,
            race_grade=race_grade,
            entries=entries,
        )

    async def fetch_realtime_odds(
        self,
        race_date: date,
        race_number: int,
    ) -> dict[str, dict[str, float]]:
        """リアルタイムオッズを取得して {賭け式: {組み合わせ: オッズ}} を返す。

        Args:
            race_date: 開催日
            race_number: レース番号（1-12）

        Returns:
            賭け式→組み合わせ→オッズの辞書

        Raises:
            ScrapingError: スクレイピングが失敗した場合
        """
        odds: dict[str, dict[str, float]] = {}

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = await context.new_page()

                # 単勝オッズ
                win_url = _build_url(_URL_ODDSTF, self.venue_code, race_date, race_number)
                win_odds = await self._fetch_win_odds(page, win_url)
                odds["単勝"] = win_odds
                await asyncio.sleep(self.SCRAPING_INTERVAL_SEC)

                # 2連単オッズ
                exacta_url = _build_url(_URL_ODDS2TF, self.venue_code, race_date, race_number)
                exacta_odds = await self._fetch_exacta_odds(page, exacta_url)
                odds["2連単"] = exacta_odds
                await asyncio.sleep(self.SCRAPING_INTERVAL_SEC)

                # 3連単オッズ
                trifecta_url = _build_url(_URL_ODDS3T, self.venue_code, race_date, race_number)
                trifecta_odds = await self._fetch_trifecta_odds(page, trifecta_url)
                odds["3連単"] = trifecta_odds

            finally:
                await browser.close()

        return odds

    async def fetch_race_result(
        self,
        race_date: date,
        race_number: int,
    ) -> RaceResult:
        """レース結果・払戻金を取得して返す。

        Args:
            race_date: 開催日
            race_number: レース番号（1-12）

        Returns:
            レース結果データ

        Raises:
            ScrapingError: スクレイピングが失敗した場合
        """
        from datetime import datetime

        url = _build_url(_URL_RACERESULT, self.venue_code, race_date, race_number)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = await context.new_page()
                finishing_order, payouts = await self._fetch_result_page(page, url)
            finally:
                await browser.close()

        return RaceResult(
            venue_code=self.venue_code,
            race_date=race_date,
            race_number=race_number,
            finishing_order=finishing_order,
            payouts=payouts,
            recorded_at=datetime.now(),
        )

    # -----------------------------------------------------------------------
    # 内部メソッド: 出走表
    # -----------------------------------------------------------------------

    async def _fetch_racelist(self, page: object, url: str) -> list[dict]:
        """出走表ページをスクレイピングして生データリストを返す。"""
        await self._navigate_with_retry(page, url)  # type: ignore[arg-type]

        raw_entries: list[dict] = []
        try:
            # 出走表テーブルの行を取得
            rows = await page.query_selector_all("table.is-w748 tbody tr.is-fs12")  # type: ignore[attr-defined]
            if not rows:
                # テーブルセレクタが変わっている可能性あり
                rows = await page.query_selector_all(".table1 tbody tr")  # type: ignore[attr-defined]

            race_grade = await self._extract_race_grade(page)  # type: ignore[arg-type]

            for i, row in enumerate(rows[:6]):
                entry_data = await self._parse_racelist_row(row, i + 1)
                entry_data["race_grade"] = race_grade
                raw_entries.append(entry_data)

        except Exception as e:
            raise ScrapingError(
                self.venue_code,
                f"出走表の解析に失敗しました: {e}",
            ) from e

        return raw_entries

    async def _fetch_beforeinfo(
        self,
        page: object,
        url: str,
        raw_entries: list[dict],
    ) -> None:
        """直前情報ページから展示タイム・スタートタイミングを取得してraw_entriesを更新する。"""
        await self._navigate_with_retry(page, url)  # type: ignore[arg-type]

        try:
            rows = await page.query_selector_all("table.is-w748 tbody tr.is-fs12")  # type: ignore[attr-defined]
            if not rows:
                rows = await page.query_selector_all(".table1 tbody tr")  # type: ignore[attr-defined]

            for i, row in enumerate(rows[:6]):
                if i < len(raw_entries):
                    before_data = await self._parse_beforeinfo_row(row)
                    raw_entries[i].update(before_data)

        except Exception as e:
            # 直前情報取得失敗は警告のみ（出走表は使える）
            logger.warning(
                "直前情報の取得に失敗しました（%d号艇以降）: %s",
                len(raw_entries) + 1,
                e,
            )

    async def _parse_racelist_row(self, row: object, boat_number: int) -> dict:
        """出走表の1行をパースして辞書を返す。"""
        try:
            cells = await row.query_selector_all("td")  # type: ignore[attr-defined]
            if len(cells) < 5:
                return self._default_entry(boat_number)

            # テキスト取得
            texts = []
            for cell in cells:
                text = await cell.inner_text()  # type: ignore[attr-defined]
                texts.append(text.strip())

            # セルの位置はサイト構造に依存（基本的な取得）
            racer_name = texts[3] if len(texts) > 3 else ""
            racer_id = texts[2] if len(texts) > 2 else ""
            grade = texts[4] if len(texts) > 4 else "B1"

            # 勝率のパース（"6.50" などの文字列）
            win_rate_all = self._parse_float(texts[5] if len(texts) > 5 else "0")
            win_rate_venue = self._parse_float(texts[6] if len(texts) > 6 else "0")
            motor_win_rate = self._parse_float(texts[8] if len(texts) > 8 else "0")

            return {
                "boat_number": boat_number,
                "racer_name": racer_name,
                "racer_id": racer_id,
                "grade": grade[:2] if len(grade) >= 2 else grade,
                "motor_no": int(self._parse_float(texts[9] if len(texts) > 9 else "0")),
                "boat_no": int(self._parse_float(texts[10] if len(texts) > 10 else "0")),
                "exhibition_time": 0.0,  # 直前情報で更新
                "start_timing": 0.0,  # 直前情報で更新
                "win_rate_all": min(win_rate_all / 100 if win_rate_all > 1 else win_rate_all, 1.0),
                "win_rate_venue": min(
                    win_rate_venue / 100 if win_rate_venue > 1 else win_rate_venue, 1.0
                ),
                "motor_win_rate": min(
                    motor_win_rate / 100 if motor_win_rate > 1 else motor_win_rate, 1.0
                ),
                "is_absent": False,
            }
        except Exception as e:
            logger.warning("%d号艇の出走表パースに失敗: %s", boat_number, e)
            return self._default_entry(boat_number)

    async def _parse_beforeinfo_row(self, row: object) -> dict:
        """直前情報の1行から展示タイム・スタートタイミングを取得する。"""
        try:
            cells = await row.query_selector_all("td")  # type: ignore[attr-defined]
            if not cells:
                return {"exhibition_time": 0.0, "start_timing": 0.0}

            texts = []
            for cell in cells:
                text = await cell.inner_text()  # type: ignore[attr-defined]
                texts.append(text.strip())

            # 展示タイムとスタートタイミングの位置（サイト構造に依存）
            exhibition_time = self._parse_float(texts[4] if len(texts) > 4 else "0")
            start_timing = self._parse_start_timing(texts[5] if len(texts) > 5 else "0.00")

            return {
                "exhibition_time": exhibition_time,
                "start_timing": start_timing,
            }
        except Exception:
            return {"exhibition_time": 0.0, "start_timing": 0.0}

    async def _extract_race_grade(self, page: object) -> str:
        """レースグレードを抽出する。"""
        try:
            grade_el = await page.query_selector(".is-raceGrade1")  # type: ignore[attr-defined]
            if grade_el:
                text = await grade_el.inner_text()  # type: ignore[attr-defined]
                if "SG" in text:
                    return "SG"
                if "G1" in text:
                    return "G1"
                if "G2" in text:
                    return "G2"
                if "G3" in text:
                    return "G3"
        except Exception:
            pass
        return "一般"

    # -----------------------------------------------------------------------
    # 内部メソッド: オッズ
    # -----------------------------------------------------------------------

    async def _fetch_win_odds(self, page: object, url: str) -> dict[str, float]:
        """単勝オッズを取得する。"""
        await self._navigate_with_retry(page, url)  # type: ignore[arg-type]
        odds: dict[str, float] = {}
        try:
            cells = await page.query_selector_all(".oddsPoint")  # type: ignore[attr-defined]
            for i, cell in enumerate(cells[:6]):
                text = await cell.inner_text()  # type: ignore[attr-defined]
                odds[str(i + 1)] = self._parse_float(text)
        except Exception as e:
            logger.warning("単勝オッズ取得に失敗: %s", e)
        return odds

    async def _fetch_exacta_odds(self, page: object, url: str) -> dict[str, float]:
        """2連単オッズを取得する。"""
        await self._navigate_with_retry(page, url)  # type: ignore[arg-type]
        odds: dict[str, float] = {}
        try:
            # 2連単オッズテーブルのセルを取得
            rows = await page.query_selector_all("table.is-w748 tbody tr")  # type: ignore[attr-defined]
            for row in rows:
                cells = await row.query_selector_all("td")  # type: ignore[attr-defined]
                if len(cells) >= 2:
                    combo = await cells[0].inner_text()  # type: ignore[attr-defined]
                    odds_val = await cells[1].inner_text()  # type: ignore[attr-defined]
                    combo = combo.strip().replace("-", "")
                    if re.match(r"^\d{2}$", combo):
                        odds[f"{combo[0]}-{combo[1]}"] = self._parse_float(odds_val)
        except Exception as e:
            logger.warning("2連単オッズ取得に失敗: %s", e)
        return odds

    async def _fetch_trifecta_odds(self, page: object, url: str) -> dict[str, float]:
        """3連単オッズを取得する。"""
        await self._navigate_with_retry(page, url)  # type: ignore[arg-type]
        odds: dict[str, float] = {}
        try:
            rows = await page.query_selector_all("table.is-w748 tbody tr")  # type: ignore[attr-defined]
            for row in rows:
                cells = await row.query_selector_all("td")  # type: ignore[attr-defined]
                if len(cells) >= 2:
                    combo = await cells[0].inner_text()  # type: ignore[attr-defined]
                    odds_val = await cells[1].inner_text()  # type: ignore[attr-defined]
                    combo = combo.strip().replace("-", "")
                    if re.match(r"^\d{3}$", combo):
                        odds[f"{combo[0]}-{combo[1]}-{combo[2]}"] = self._parse_float(odds_val)
        except Exception as e:
            logger.warning("3連単オッズ取得に失敗: %s", e)
        return odds

    # -----------------------------------------------------------------------
    # 内部メソッド: レース結果
    # -----------------------------------------------------------------------

    async def _fetch_result_page(
        self,
        page: object,
        url: str,
    ) -> tuple[list[int], dict[str, dict[str, int]]]:
        """レース結果ページから着順と払戻金を取得する。"""
        await self._navigate_with_retry(page, url)  # type: ignore[arg-type]
        finishing_order: list[int] = []
        payouts: dict[str, dict[str, int]] = {}

        try:
            # 着順の取得
            result_rows = await page.query_selector_all(".table1 tbody tr")  # type: ignore[attr-defined]
            for row in result_rows[:3]:
                cells = await row.query_selector_all("td")  # type: ignore[attr-defined]
                if cells:
                    text = await cells[0].inner_text()  # type: ignore[attr-defined]
                    boat_no = int(self._parse_float(text.strip()))
                    finishing_order.append(boat_no)
        except Exception as e:
            logger.warning("レース結果取得に失敗: %s", e)

        return finishing_order, payouts

    # -----------------------------------------------------------------------
    # ユーティリティメソッド
    # -----------------------------------------------------------------------

    async def _navigate_with_retry(self, page: object, url: str) -> None:
        """指定URLにリトライ付きでアクセスする。

        Args:
            page: Playwrightのページオブジェクト
            url: アクセスするURL

        Raises:
            ScrapingError: 最大リトライ回数を超えた場合
        """
        last_error: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                await page.goto(url, timeout=self.TIMEOUT_MS)  # type: ignore[attr-defined]
                return
            except Exception as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    wait = 2**attempt  # 指数バックオフ: 1秒, 2秒, 4秒
                    logger.warning(
                        "スクレイピング失敗（%d回目）。%d秒後にリトライ: %s",
                        attempt + 1,
                        wait,
                        url,
                    )
                    await asyncio.sleep(wait)

        raise ScrapingError(
            self.venue_code,
            f"最大リトライ回数（{self.MAX_RETRIES}回）に達しました: {url} - {last_error}",
        )

    def _get_venue_name(self) -> str:
        """会場コードから会場名を返す（簡易実装）。"""
        venue_map = {
            "01": "桐生",
            "02": "戸田",
            "03": "江戸川",
            "04": "平和島",
            "05": "多摩川",
            "06": "浜名湖",
            "07": "蒲郡",
            "08": "常滑",
            "09": "津",
            "10": "三国",
            "11": "びわこ",
            "12": "住之江",
            "13": "尼崎",
            "14": "鳴門",
            "15": "丸亀",
            "16": "児島",
            "17": "宮島",
            "18": "徳山",
            "19": "下関",
            "20": "若松",
            "21": "芦屋",
            "22": "福岡",
            "23": "唐津",
            "24": "大村",
        }
        return venue_map.get(self.venue_code, f"会場{self.venue_code}")

    @staticmethod
    def _parse_float(text: str) -> float:
        """テキストから浮動小数点数をパースする（パース失敗時は0.0）。"""
        try:
            cleaned = re.sub(r"[^\d.]", "", text.strip())
            return float(cleaned) if cleaned else 0.0
        except (ValueError, AttributeError):
            return 0.0

    @staticmethod
    def _parse_start_timing(text: str) -> float:
        """スタートタイミングをパースする（F表記対応）。"""
        text = text.strip()
        if "F" in text.upper():
            # Fの後の数値を取得してマイナスにする
            match = re.search(r"(\d+\.\d+)", text)
            if match:
                return -float(match.group(1))
            return -0.01  # Fだが数値不明の場合
        try:
            cleaned = re.sub(r"[^\d.]", "", text)
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    def _default_entry(boat_number: int) -> dict:
        """デフォルト値のエントリ辞書を返す。"""
        return {
            "boat_number": boat_number,
            "racer_name": f"{boat_number}号艇選手",
            "racer_id": "",
            "grade": "B1",
            "motor_no": 0,
            "boat_no": 0,
            "exhibition_time": 6.80,
            "start_timing": 0.15,
            "win_rate_all": 0.05,
            "win_rate_venue": 0.05,
            "motor_win_rate": 0.30,
            "is_absent": False,
            "race_grade": "一般",
        }
