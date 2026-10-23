"""輔大地標判別（backend/shared/campus.py）的單元測試。"""
from __future__ import annotations

from backend.shared.campus import resolve_campus_location


def test_inside_library_returns_label() -> None:
    # 總圖書館（校正後座標）附近應判別為總圖
    assert resolve_campus_location(25.0393, 121.4314) == "輔大總圖書館"
    assert resolve_campus_location(25.0391, 121.4312) == "輔大總圖書館"


def test_measured_zhongmeitang_returns_label() -> None:
    # 2026-10 實地 GPS 校正點：站在中美堂發事件應正確判別
    assert resolve_campus_location(25.0381, 121.4319) == "中美堂"


def test_outside_campus_returns_none() -> None:
    # 台北市中心：不在輔大 bounding box，不判別地標
    assert resolve_campus_location(25.0173, 121.5397) is None
    # 校園 bounding box 內但遠離所有地標（西北側空地）：同樣 None
    assert resolve_campus_location(25.0415, 121.4215) is None


def test_nearest_poi_wins() -> None:
    # 中美堂與總圖之間偏中美堂的點，應判給較近的中美堂而非總圖
    label = resolve_campus_location(25.0384, 121.4318)
    assert label == "中美堂"
