from __future__ import annotations

"""プロジェクト固有のカスタム例外クラス。

標準ライブラリのみに依存し、他の src/ モジュールは一切インポートしない。
"""


class BoatRaceAIError(Exception):
    """BoatRaceAI-Hamana プロジェクト固有の全例外の基底クラス。

    `except BoatRaceAIError` で本システム起因のエラーを一括捕捉できる。
    """


class ScrapingError(BoatRaceAIError):
    """Playwrightによるスクレイピングが失敗した場合の例外。

    タイムアウト・サイト仕様変更・ネットワーク障害等で発生する。
    """

    def __init__(self, venue_code: str, message: str) -> None:
        super().__init__(f"[{venue_code}] {message}")
        self.venue_code = venue_code


class GeminiAPIError(BoatRaceAIError):
    """Gemini APIの呼び出しが失敗した場合の例外。

    レート制限・タイムアウト・認証エラー等で発生する。
    """


class JSONParseError(BoatRaceAIError):
    """GeminiのレスポンスがJSON形式でない、または確率辞書として解析できない場合の例外。"""


class DataValidationError(BoatRaceAIError):
    """スクレイピングで取得したデータが不正な値を含む場合の例外。

    出走艇数が6未満、勝率が0〜1の範囲外等で発生する。
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"[{field}] {message}")
        self.field = field
