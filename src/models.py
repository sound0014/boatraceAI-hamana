from __future__ import annotations

"""システム全体で共有するデータモデル定義。

他の src/ モジュールには依存しない（循環依存防止）。
内部処理には @dataclass を使用し、システム境界バリデーションには Pydantic を使用する。
"""

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class RaceEntry:
    """1レースに出場する1艇の情報。"""

    boat_number: int  # 艇番（1-6）
    racer_name: str  # 選手名
    racer_id: str  # 登録番号
    grade: str  # 級別（A1/A2/B1/B2）
    motor_no: int  # モーター番号
    boat_no: int  # ボート番号
    exhibition_time: float  # 展示タイム（秒）
    start_timing: float  # 展示スタートタイミング（秒、マイナスはフライング）
    win_rate_all: float  # 全国勝率
    win_rate_venue: float  # 当地勝率
    motor_win_rate: float  # モーター2連対率
    is_absent: bool = False  # 欠場フラグ
    is_flying: bool = False  # フライング（F）フラグ


@dataclass
class RaceContext:
    """1レースの全情報（出走艇6艇 + 気象・潮位等の環境情報）。"""

    venue_code: str  # 会場コード（例: "06" = 浜名湖）
    venue_name: str  # 会場名（例: "浜名湖"）
    race_date: date  # 開催日
    race_number: int  # レース番号（1-12）
    race_grade: str  # レースグレード（SG/G1/G2/G3/一般）
    wind_speed: float  # 風速（m/s）
    wind_direction: str  # 風向き（例: "追い風"/"向かい風"/"横風"）
    water_temperature: float  # 水温（℃）
    tide_level: str  # 潮位状況（例: "満潮"/"干潮"/"中間"）
    weather: str  # 天候（晴/曇/雨）
    entries: list[RaceEntry] = field(default_factory=list)  # 出走艇リスト（6艇）


@dataclass
class GeminiInference:
    """Gemini APIの推論結果を格納するデータモデル。"""

    race_context: RaceContext  # 対象レース
    logic_name: str  # 使用した評価ロジック名
    logic_content: str  # 評価ロジック本文
    win_probabilities: dict[int, float]  # {艇番: 1着確率} 合計1.0
    reasoning: str  # 推論根拠（Geminiの説明文）
    inferred_at: datetime  # 推論実行日時
    model_version: str  # 使用Geminiモデルバージョン


@dataclass
class ExpectedValue:
    """特定の買い目の期待値計算結果。"""

    race_context: RaceContext
    bet_type: str  # 賭け式（"単勝"/"複勝"/"2連単"/"2連複"/"3連単"/"3連複"）
    boat_combination: tuple[int, ...]  # 艇番の組み合わせ（例: (1, 2, 3)）
    probability: float  # Gemini推論確率
    odds: float  # リアルタイムオッズ
    expected_value: float  # 期待値（probability × odds）
    is_positive_ev: bool  # 期待値 > 1.0 フラグ
    calculated_at: datetime  # 計算日時


@dataclass
class RaceResult:
    """1レースの確定結果（着順・払戻金）。"""

    venue_code: str
    race_date: date
    race_number: int
    finishing_order: list[int]  # 着順別艇番（[1着艇番, 2着艇番, ...]）
    payouts: dict[str, dict[str, int]]  # {賭け式: {組み合わせ: 払戻金}}
    recorded_at: datetime


@dataclass
class PredictionResult:
    """Orchestratorが予想パイプライン実行後に返す集約型。

    UIレイヤー（app.py）に渡す唯一の戻り値。
    """

    race_context: RaceContext  # 環境情報込みのレースコンテキスト
    inference: GeminiInference  # AI推論結果（確率・根拠）
    expected_values: list[ExpectedValue]  # 全買い目の期待値リスト
    positive_ev_bets: list[ExpectedValue]  # E>1.0の買い目（EV降順）
    pipeline_duration_sec: float  # パイプライン処理時間（秒）
    executed_at: datetime  # 予想実行日時
