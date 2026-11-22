from projectapp.assign_drag import ASSIGN_DRAG_CSS, ASSIGN_DRAG_JS, ASSIGN_DROP_EVENT


def test_the_drag_js_uses_its_own_data_transfer_type_and_event() -> None:
    assert "application/x-assign-member" in ASSIGN_DRAG_JS
    assert "application/x-dashboard-card" not in ASSIGN_DRAG_JS
    assert f'emitEvent("{ASSIGN_DROP_EVENT}"' in ASSIGN_DRAG_JS
    assert (
        "data-assign-member" in ASSIGN_DRAG_JS and "data-assign-cell" in ASSIGN_DRAG_JS
    )


def test_the_drag_js_installs_only_once_and_ignores_foreign_drags() -> None:
    assert "__assignDragInstalled" in ASSIGN_DRAG_JS
    assert "isOurs" in ASSIGN_DRAG_JS


def test_the_css_marks_the_cell_under_the_pointer() -> None:
    assert ".assign-drop-over" in ASSIGN_DRAG_CSS
