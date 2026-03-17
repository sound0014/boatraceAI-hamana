from __future__ import annotations

"""ExpectedValueCalculator: GeminiInferenceとオッズから全買い目の期待値を算出する。"""

import csv
import itertools
import logging
from datetime import datetime
from pathlib import Path

from src.models import ExpectedValue, GeminiInference

logger = logging.getLogger(__name__)

# ゼロ除算ガード用の最小値
_PROB_MIN = 1e-9


class ExpectedValueCalculator:
    """GeminiInferenceとリアルタイムオッズから全買い目の期待値を算出する。

    計算式: E = P × O
    - P: Gemini が推論した着順確率
    - O: リアルタイムオッズ
    """

    def calculate_all(
        self,
        inference: GeminiInference,
        odds: dict[str, dict[str, float]],
    ) -> list[ExpectedValue]:
        """全賭け式・全組み合わせの期待値リストを返す。

        Args:
            inference: Gemini API の推論結果
            odds: {賭け式: {組み合わせ文字列: オッズ}}

        Returns:
            全買い目の期待値リスト（EVの降順）
        """
        probs = inference.win_probabilities
        results: list[ExpectedValue] = []
        now = datetime.now()

        # 出走艇番（欠場除外）
        active_boats = [e.boat_number for e in inference.race_context.entries if not e.is_absent]

        # 単勝
        if "単勝" in odds:
            for boat in active_boats:
                key = str(boat)
                if key in odds["単勝"]:
                    p = probs.get(boat, 0.0)
                    o = odds["単勝"][key]
                    if o > 0:
                        ev_val = p * o
                        results.append(
                            ExpectedValue(
                                race_context=inference.race_context,
                                bet_type="単勝",
                                boat_combination=(boat,),
                                probability=p,
                                odds=o,
                                expected_value=ev_val,
                                is_positive_ev=ev_val > 1.0,
                                calculated_at=now,
                            )
                        )

        # 2連単
        if "2連単" in odds:
            for i, j in itertools.permutations(active_boats, 2):
                key = f"{i}-{j}"
                if key in odds["2連単"]:
                    p = self._calc_exacta_prob(probs, i, j)
                    o = odds["2連単"][key]
                    if o > 0:
                        ev_val = p * o
                        results.append(
                            ExpectedValue(
                                race_context=inference.race_context,
                                bet_type="2連単",
                                boat_combination=(i, j),
                                probability=p,
                                odds=o,
                                expected_value=ev_val,
                                is_positive_ev=ev_val > 1.0,
                                calculated_at=now,
                            )
                        )

        # 3連単
        if "3連単" in odds:
            for i, j, k in itertools.permutations(active_boats, 3):
                key = f"{i}-{j}-{k}"
                if key in odds["3連単"]:
                    p = self._calc_trifecta_prob(probs, i, j, k)
                    o = odds["3連単"][key]
                    if o > 0:
                        ev_val = p * o
                        results.append(
                            ExpectedValue(
                                race_context=inference.race_context,
                                bet_type="3連単",
                                boat_combination=(i, j, k),
                                probability=p,
                                odds=o,
                                expected_value=ev_val,
                                is_positive_ev=ev_val > 1.0,
                                calculated_at=now,
                            )
                        )

        # EV降順でソート
        results.sort(key=lambda x: x.expected_value, reverse=True)
        return results

    def get_positive_ev_bets(
        self,
        ev_list: list[ExpectedValue],
        threshold: float = 1.0,
    ) -> list[ExpectedValue]:
        """期待値 > threshold の買い目をEV降順で返す。

        Args:
            ev_list: 全買い目の期待値リスト
            threshold: フィルタリング閾値（デフォルト: 1.0）

        Returns:
            threshold を超える買い目リスト（EV降順）
        """
        return [ev for ev in ev_list if ev.expected_value > threshold]

    def export_csv(
        self,
        ev_list: list[ExpectedValue],
        file_path: str,
    ) -> None:
        """期待値リストをCSVに出力する。

        Args:
            ev_list: 出力する期待値リスト
            file_path: 出力先CSVファイルパス
        """
        output_path = Path(file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "賭け式",
                    "買い目",
                    "確率",
                    "オッズ",
                    "期待値",
                    "正の期待値",
                    "計算日時",
                ],
            )
            writer.writeheader()
            for ev in ev_list:
                combo_str = "-".join(str(b) for b in ev.boat_combination)
                writer.writerow(
                    {
                        "賭け式": ev.bet_type,
                        "買い目": combo_str,
                        "確率": f"{ev.probability:.4f}",
                        "オッズ": f"{ev.odds:.1f}",
                        "期待値": f"{ev.expected_value:.4f}",
                        "正の期待値": "○" if ev.is_positive_ev else "×",
                        "計算日時": ev.calculated_at.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

        logger.info("CSVエクスポート完了: %s (%d件)", file_path, len(ev_list))

    # -----------------------------------------------------------------------
    # 確率計算メソッド
    # -----------------------------------------------------------------------

    def _calc_exacta_prob(
        self,
        probs: dict[int, float],
        first: int,
        second: int,
    ) -> float:
        """2連単（1着→2着）の確率を計算する。

        P(i→j) = P1(i) × P1(j) / (1 - P1(i))

        Args:
            probs: 1着確率辞書
            first: 1着艇番
            second: 2着艇番

        Returns:
            2連単の確率
        """
        p_first = probs.get(first, 0.0)
        p_second = probs.get(second, 0.0)

        denominator = 1.0 - p_first
        if denominator < _PROB_MIN:
            return 0.0

        return p_first * (p_second / denominator)

    def _calc_trifecta_prob(
        self,
        probs: dict[int, float],
        first: int,
        second: int,
        third: int,
    ) -> float:
        """3連単（1着→2着→3着）の確率を計算する。

        P(i→j→k) = P1(i) × P1(j)/(1-P1(i)) × P1(k)/(1-P1(i)-P1(j))

        Args:
            probs: 1着確率辞書
            first: 1着艇番
            second: 2着艇番
            third: 3着艇番

        Returns:
            3連単の確率
        """
        p_first = probs.get(first, 0.0)
        p_second = probs.get(second, 0.0)
        p_third = probs.get(third, 0.0)

        denom_2nd = 1.0 - p_first
        if denom_2nd < _PROB_MIN:
            return 0.0

        denom_3rd = 1.0 - p_first - p_second
        if denom_3rd < _PROB_MIN:
            return 0.0

        return p_first * (p_second / denom_2nd) * (p_third / denom_3rd)
