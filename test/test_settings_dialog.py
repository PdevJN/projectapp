from nicegui import ui
from nicegui.testing import User

from projectapp.settings_dialog import open_import_dialog
from projectapp.settings_io import ImportPlan, ProjectChange, SectionPlan

PLAN = ImportPlan(
    sections=(
        SectionPlan("members", ("鈴木",), ("田中", "佐藤"), True),
        SectionPlan("events", (), ("2026-10-10〜2026-10-12 合宿",), False),
    ),
    project_changes=(ProjectChange("稼働可能時間", "6.5h", "7h"),),
)


def mount(calls: list[tuple]) -> None:
    @ui.page("/")
    def index() -> None:
        open_import_dialog(PLAN, lambda sections, overwrite: calls.append((sections, overwrite)))


def element(user: User, marker: str) -> ui.element:
    return next(iter(user.find(marker=marker).elements))


async def test_the_dialog_lists_the_sections_and_the_project_changes(user: User) -> None:
    mount([])
    await user.open("/")
    await user.should_see("メンバー(追加 1 件・重複 2 件)")
    await user.should_see("稼働可能時間: 6.5h → 7h")
    await user.should_see("追加: 鈴木")
    await user.should_see("重複(取り込みません): 2026-10-10〜2026-10-12 合宿")
    assert element(user, "import-section-project").value
    assert element(user, "import-section-members").value
    assert not element(user, "import-overwrite-members-0").value  # 既定はスキップ


async def test_apply_passes_the_checked_sections_and_overwrites(user: User) -> None:
    calls: list[tuple] = []
    mount(calls)
    await user.open("/")
    user.find(marker="import-section-events").click()  # events を外す
    user.find(marker="import-overwrite-members-1").click()  # 佐藤を上書き
    user.find(marker="import-apply").click()
    assert calls == [({"project", "members"}, {("members", "佐藤")})]


async def test_cancel_calls_nothing(user: User) -> None:
    calls: list[tuple] = []
    mount(calls)
    await user.open("/")
    user.find(marker="import-cancel").click()
    assert calls == []
