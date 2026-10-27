from projectapp.dashboard_drag import DASHBOARD_DRAG_CSS, DASHBOARD_DRAG_JS


def test_the_js_emits_the_move_event_and_uses_its_own_drag_type() -> None:
    assert 'emitEvent("dashboard_move_card"' in DASHBOARD_DRAG_JS
    assert "application/x-dashboard-card" in DASHBOARD_DRAG_JS  # ガントチャートの drag と見分ける
    assert "data-dash-handle" in DASHBOARD_DRAG_JS and "data-dash-card" in DASHBOARD_DRAG_JS
    assert "__dashboardDragInstalled" in DASHBOARD_DRAG_JS  # 二重に入れない


def test_the_css_marks_the_drop_position() -> None:
    assert ".dash-drop-before" in DASHBOARD_DRAG_CSS
