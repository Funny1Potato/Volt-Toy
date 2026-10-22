"""展示用的格式化。数值一律两位小数，省得在文案里出现 0.30000000000000004。"""

from __future__ import annotations


def kwh_text(value: float) -> str:
    return f"{value:.2f}"


def ah_text(value: float) -> str:
    return f"{value:.2f}"


def fee_text(value: float) -> str:
    return f"{value:.2f}"


def span_text(seconds: float) -> tuple[int, int]:
    remain = max(0, int(round(seconds)))
    minutes, secs = divmod(remain, 60)
    return minutes, secs
