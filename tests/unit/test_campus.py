"""輔大地標判別（backend/shared/campus.py）的單元測試。"""
from __future__ import annotations

from backend.shared.campus import resolve_campus_location


def test_inside_library_returns_label() -> None:
    # 總圖書館（校正後座標）附近應判別為總圖
    assert resolve_campus_location(25.036230, 121.434509) == "輔大總圖書館"
    assert resolve_campus_location(25.036100, 121.434400) == "輔大總圖書館"


def test_measured_zhongmeitang_returns_label() -> None:
    # 2026-10 實地 GPS 校正點：站在中美堂發事件應正確判別
    assert resolve_campus_location(25.0381, 121.4319) == "中美堂"


def test_grass_areas_return_labels() -> None:
    # 草地/開放空間實測點
    assert resolve_campus_location(25.035425, 121.432454) == "維也納森林"
    assert resolve_campus_location(25.034496, 121.432927) == "小巴黎"
    assert resolve_campus_location(25.036363, 121.433590) == "文學院荷花池"
    assert resolve_campus_location(25.036024, 121.433667) == "文學院前草地"


def test_measured_songyan_returns_label() -> None:
    # 實測點：站在聖言樓前發事件應正確判別
    assert resolve_campus_location(25.035496, 121.431612) == "SF 聖言樓"


def test_outside_campus_returns_none() -> None:
    # 台北市中心：不在輔大 bounding box，不判別地標
    assert resolve_campus_location(25.0173, 121.5397) is None
    # 校園 bounding box 內但離所有已校準地標都遠（未校準區域）：寧可不標
    assert resolve_campus_location(25.0330, 121.4280) is None
