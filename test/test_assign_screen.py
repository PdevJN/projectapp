import inspect
from datetime import date, datetime

from nicegui import ui
from nicegui.testing import User

from projectapp.assign_drag import ASSIGN_DRAG_CSS
from projectapp.assign_load import member_color
from projectapp.assign_screen import (
    ROW_HEIGHT_PX,
    AssignScreen,
    row_height,
    select_on_active,
)
from projectapp.assign_trial import AssignTrial, is_dirty
from projectapp.gantt import GanttActions, GanttChart
from projectapp.models import Project, Task
from projectapp.timeline import Scale


def noop_actions() -> GanttActions:
    return GanttActions(
        add_section=lambda: None,
        add_task=lambda path: None,
        add_top_task=lambda: None,
        edit_task=lambda path, ti: None,
        move_task=lambda src, dst, copy: None,
        shift_task=lambda path, ti, days: None,
        set_name_width=lambda width: None,
    )


def one_task_project() -> Project:
    return Project(
        "demo",
        base_date=date(2026, 10, 5),
        tasks=[
            Task(
                "設計",
                id="a",
                planned_start=datetime(2026, 10, 6, 9),
                planned_end=datetime(2026, 10, 9, 12),
            )
        ],
    )


async def test_embedded_chart_draws_the_bar_without_a_second_toolbar(
    user: User,
) -> None:
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        main = GanttChart(one_task_project(), {}, noop_actions())
        main.build()
        embedded = GanttChart(one_task_project(), {}, noop_actions())
        embedded.build_embedded()
        charts.extend([main, embedded])

    await user.open("/")
    main, embedded = charts
    assert embedded.toolbar is None and embedded.splitter is None
    assert embedded.options.read_only is True
    assert len(embedded.task_rows) == 1
    embedded.set_scale(Scale.WEEK)  # ツールバーがなくても切り替えられる
    assert embedded.scale is Scale.WEEK
    assert main.scale is Scale.DAY  # メインには影響しない


def mount_screen(confirmed: list[AssignTrial], screens: list[AssignScreen]) -> None:
    @ui.page("/")
    def index() -> None:
        main = GanttChart(one_task_project(), {}, noop_actions())
        main.build()
        project = one_task_project()
        screen = AssignScreen(
            project, project.tasks[0], {}, on_confirm=confirmed.append
        )
        screens.append(screen)
        ui.button("open", on_click=screen.open).mark("open-screen")


async def test_open_shows_the_title_and_the_chart(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-screen")
    await user.should_see(marker="assign-task-title")
    assert screens[0].chart is not None and len(screens[0].chart.task_rows) == 1


async def test_scale_toggle_changes_only_the_embedded_chart(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-scale")
    screens[0].set_scale(Scale.MONTH)
    assert screens[0].chart is not None and screens[0].chart.scale is Scale.MONTH


async def test_confirm_calls_back_with_the_trial_and_closes(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-confirm")
    screens[0].trial.task.name = "詳細設計"
    user.find(marker="assign-confirm").click()
    assert [t.task.name for t in confirmed] == ["詳細設計"]
    assert screens[0].dialog is not None and screens[0].dialog.value is False


async def test_cancel_without_changes_closes_without_asking(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-cancel")
    user.find(marker="assign-cancel").click()
    assert screens[0].dialog is not None and screens[0].dialog.value is False
    assert confirmed == []


async def test_cancel_with_changes_asks_and_keeps_the_screen_on_no(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-cancel")
    screens[0].trial.task.name = "変更"
    user.find(marker="assign-cancel").click()
    await user.should_see(marker="assign-discard-no")
    user.find(marker="assign-discard-no").click()
    assert (
        screens[0].dialog is not None and screens[0].dialog.value is True
    )  # 画面に戻る
    user.find(marker="assign-discard-yes").click()
    assert screens[0].dialog.value is False
    assert confirmed == []


async def test_escape_key_cancels_like_the_cancel_button(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-cancel")
    dialog = screens[0].dialog
    assert dialog is not None
    [listener] = [ev for ev in dialog._event_listeners.values() if "escape" in ev.type]
    listener.handler(None)  # 変更がないので、確認なしで閉じる
    assert dialog.value is False
    assert confirmed == []


async def test_embedded_scroll_box_is_separate_from_the_main_chart(user: User) -> None:
    charts: list[GanttChart] = []

    @ui.page("/")
    def index() -> None:
        main = GanttChart(one_task_project(), {}, noop_actions())
        main.build()
        embedded = GanttChart(one_task_project(), {}, noop_actions())
        embedded.build_embedded()
        charts.extend([main, embedded])

    await user.open("/")
    main, embedded = charts
    assert embedded.scroll_selector != main.scroll_selector
    assert embedded.scroll_box is not None
    assert "data-assign-scroll" in embedded.scroll_box.props
    sent: list[str] = []
    assert embedded.client is not None
    embedded.client.run_javascript = lambda js, **kw: sent.append(js)  # type: ignore[method-assign]
    embedded.scroll_to_left()
    assert sent and all("data-assign-scroll" in js for js in sent)
    assert not any("data-chart-scroll" in js for js in sent)


def team_project() -> Project:
    from projectapp.models import Assignee, Member, Membership, Team

    task = Task(
        "設計",
        id="a",
        planned_start=datetime(2026, 11, 16, 9),
        planned_end=datetime(2026, 11, 30, 17),
        effort_hours=40,
        assignees=[Assignee("田中")],
    )
    return Project(
        "p",
        base_date=date(2026, 11, 16),
        members=[
            Member("田中", 1.0, teams=[Membership("t1")]),
            Member("鈴木", 1.0, teams=[Membership("t1")]),
            Member("佐藤", 1.0),
        ],
        teams=[Team("開発", id="t1")],
        tasks=[task],
    )


def mount_team_screen(
    confirmed: list[AssignTrial], screens: list[AssignScreen]
) -> None:
    @ui.page("/")
    def index() -> None:
        main = GanttChart(team_project(), {}, noop_actions())
        main.build()
        project = team_project()
        screen = AssignScreen(
            project, project.tasks[0], {}, on_confirm=confirmed.append
        )
        screens.append(screen)
        ui.button("open", on_click=screen.open).mark("open-screen")


async def open_team_screen(user: User) -> tuple[AssignScreen, list[AssignTrial]]:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_team_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-members")
    return screens[0], confirmed


async def test_member_list_shows_teams_and_marks_the_tasks_assignees(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    await user.should_see(marker="assign-team-開発")
    await user.should_see(marker="assign-team-チームなし")
    for name in ("田中", "鈴木", "佐藤"):
        await user.should_see(marker=f"assign-member-{name}")
    await user.should_see(marker="assign-member-assigned-田中")
    await user.should_not_see(marker="assign-member-assigned-鈴木")


async def test_dropping_a_member_on_a_week_cell_adds_only_that_week(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    crews = [[a.name for a in w] for w in screen.trial.task.weekly_crew]
    assert crews[1] == ["田中", "鈴木"] and crews[0] == ["田中"]
    await user.should_see(marker="assign-chip-1-鈴木")
    await user.should_not_see(marker="assign-chip-0-鈴木")


async def test_dropping_a_duplicate_is_rejected_with_a_notice(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    before = [list(w) for w in screen.trial.task.weekly_crew]
    screen.drop_member("鈴木", 1, None)
    assert screen.trial.task.weekly_crew == before
    await user.should_see("すでに割り当てています")


async def test_the_remove_button_removes_but_not_the_last_member(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.remove_member_at("鈴木", 1, None)
    assert [a.name for a in screen.trial.task.weekly_crew[1]] == ["田中"]
    screen.remove_member_at("田中", 1, None)  # 最後の 1 人
    assert [a.name for a in screen.trial.task.weekly_crew[1]] == ["田中"]
    await user.should_see("最後の 1 人は外せません")


async def test_a_week_can_be_split_into_days_and_back(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 0, None)
    screen.toggle_daily(0)
    assert 0 in screen.trial.task.daily_crew
    await user.should_see(marker="assign-cell-0-3")
    screen.drop_member("佐藤", 0, 3)
    assert [a.name for a in screen.trial.task.daily_crew[0][3]] == [
        "田中",
        "鈴木",
        "佐藤",
    ]
    screen.toggle_daily(0)
    assert 0 not in screen.trial.task.daily_crew


async def test_a_task_without_a_start_date_shows_no_cells(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []

    @ui.page("/")
    def index() -> None:
        main = GanttChart(team_project(), {}, noop_actions())
        main.build()
        project = team_project()
        project.tasks[0].planned_start = None
        project.tasks[0].planned_end = None
        screen = AssignScreen(
            project, project.tasks[0], {}, on_confirm=confirmed.append
        )
        screens.append(screen)
        ui.button("open", on_click=screen.open).mark("open-screen")

    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-no-start")
    await user.should_see(marker="assign-members")  # 一覧は出す
    assert screens[0].plan is None


async def test_the_chart_updates_after_a_drop(user: User) -> None:
    screen, _ = await open_team_screen(user)
    assert screen.chart is not None
    before = screen.chart.project.tasks[0].weekly_crew
    screen.drop_member("鈴木", 1, None)
    assert screen.chart.project.tasks[0].weekly_crew != before  # 複製が作り直されている


async def test_confirm_returns_the_changed_trial(user: User) -> None:
    screen, confirmed = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    user.find(marker="assign-confirm").click()
    assert [a.name for a in confirmed[0].task.weekly_crew[1]] == ["田中", "鈴木"]


async def test_the_screen_without_members_says_so(user: User) -> None:
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_screen(confirmed, screens)  # one_task_project はメンバーがいない
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-no-members")


async def test_the_assignment_row_draws_at_every_scale(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    for scale in (Scale.WEEK, Scale.MONTH, Scale.DAY):
        screen.set_scale(scale)
        await user.should_see(marker="assign-cell-0")
        await user.should_see(marker="assign-chip-1-鈴木")


async def test_the_drag_script_is_run_not_inserted_as_html(
    user: User, monkeypatch
) -> None:
    from projectapp import assign_screen

    ran: list[str] = []
    monkeypatch.setattr(
        assign_screen.ui, "run_javascript", lambda js, **kw: ran.append(js)
    )
    confirmed: list[AssignTrial] = []
    screens: list[AssignScreen] = []
    mount_team_screen(confirmed, screens)
    await user.open("/")
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-members")
    from projectapp.assign_drag import ASSIGN_DRAG_JS

    assert (
        ASSIGN_DRAG_JS in ran
    )  # 画面を開いたあとの add_head_html は実行されないので、直接実行する


async def test_reopening_screens_registers_the_drop_handler_once_and_targets_the_latest(
    user: User,
) -> None:
    from nicegui import context

    from projectapp.assign_drag import ASSIGN_DROP_EVENT

    screens: list[AssignScreen] = []
    clients: list = []

    @ui.page("/")
    def index() -> None:
        clients.append(context.client)
        main = GanttChart(team_project(), {}, noop_actions())
        main.build()

        def open_new() -> None:
            project = team_project()
            screen = AssignScreen(
                project, project.tasks[0], {}, on_confirm=lambda t: None
            )
            screens.append(screen)
            screen.open()

        ui.button("open", on_click=open_new).mark("open-screen")

    await user.open("/")
    user.find(marker="open-screen").click()
    user.find(marker="open-screen").click()
    await user.should_see(marker="assign-members")
    listeners = [
        ev
        for ev in clients[0].layout._event_listeners.values()
        if ev.type == ASSIGN_DROP_EVENT
    ]
    assert len(listeners) == 1
    listeners[0].handler(
        type("E", (), {"args": {"name": "鈴木", "week": 1, "day": None}})()
    )
    assert screens[-1].trial.task.weekly_crew  # 最新の画面だけが受ける
    assert not screens[0].trial.task.weekly_crew


async def test_daily_toggle_works_on_a_plain_task_and_is_hidden_without_assignees(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    assert not screen.trial.task.weekly_crew
    screen.toggle_daily(0)  # 週ごとでない最初の状態から、週ごと+日ごとにできる
    assert (
        0 in screen.trial.task.daily_crew
        and len(screen.trial.task.weekly_crew) == screen.plan.weeks
    )


async def test_the_remove_button_works_in_a_week_beyond_the_defined_ones(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 0, None)  # 週 0 だけに足した週ごとのタスク
    screen.remove_member_at("田中", 0, None)  # 先に田中を外す(鈴木が残る)
    assert [a.name for a in screen.trial.task.weekly_crew[0]] == ["鈴木"]


async def test_the_member_frames_follow_the_trial_after_a_drop_and_a_remove(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    await user.should_not_see(marker="assign-member-assigned-鈴木")
    screen.drop_member("鈴木", 1, None)
    await user.should_see(marker="assign-member-assigned-鈴木")
    screen.remove_member_at("鈴木", 1, None)
    await user.should_not_see(marker="assign-member-assigned-鈴木")


async def test_chips_are_icon_only_and_the_remove_button_shows_on_hover(
    user: User,
) -> None:
    from projectapp.assign_drag import ASSIGN_DRAG_CSS

    screen, _ = await open_team_screen(user)
    chip = user.find(marker="assign-chip-0-田中").elements.pop()
    labels = [e for e in chip.descendants() if isinstance(e, ui.label)]
    assert all(
        label.text != "田中" for label in labels
    )  # 名前の文字は出さない(頭文字のアイコンだけ。名前はツールチップ)
    assert ".assign-chip:hover .assign-remove" in ASSIGN_DRAG_CSS
    assert (
        "assign-remove"
        in user.find(marker="assign-remove-0-田中").elements.pop().classes
    )


async def test_a_daily_cell_wraps_its_icons_and_the_row_grows_with_the_crew(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 0, None)
    screen.toggle_daily(0)
    screen.drop_member(
        "佐藤", 0, 3
    )  # 3 日目だけ 3 人(1 日 40px のセルには 1 段に 1 つしか入らない)
    await user.should_see(marker="assign-cell-0-3")  # 再描画を待つ
    # シミュレーションでは古い行も残ることがあるので、いちばん高い行(=最新)を見る
    heights = [
        int(str(row._style["height"]).removesuffix("px"))
        for row in user.find(marker="assign-row").elements
    ]
    assert max(heights) == row_height(3) > row_height(2) > ROW_HEIGHT_PX
    cell = user.find(marker="assign-cell-0-3").elements.pop()
    assert "wrap" in str(cell._style.get("flex-wrap", "")) or "flex-wrap: wrap" in str(
        cell._style
    )


def fire(number: ui.number, kind: str) -> None:
    """数値欄の`kind`のイベントを、登録順にすべて呼ぶ(`ui.number`自身のリスナーも含めて、実際と同じにする)。"""
    for listener in [e for e in number._event_listeners.values() if e.type == kind]:
        handler = listener.handler
        if inspect.signature(handler).parameters:
            handler(None)
        else:
            handler()


def rate_of(screen: AssignScreen, week: int, name: str) -> float:
    crew = screen.trial.task.weekly_crew[week]
    return next(a.allocation for a in crew if a.name == name)


async def test_clicking_a_chip_icon_opens_the_rate_popup_for_that_cell(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    await user.should_see(marker="assign-open-rate-1-鈴木")
    user.find(marker="assign-open-rate-1-鈴木").click()
    assert screen.rate_target == ("鈴木", 1, None)
    assert screen.rate_dialog is not None and screen.rate_dialog.value is True
    assert screen.rate_slider is not None and screen.rate_slider.value == 100
    assert screen.rate_number is not None and screen.rate_number.value == 100
    assert screen.rate_title is not None and screen.rate_title.text == "鈴木 第 2 週"


async def test_the_popup_title_names_the_day_of_a_daily_week(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 0, None)
    screen.toggle_daily(0)
    screen.open_rate("鈴木", 0, 3)
    assert screen.rate_title is not None
    assert screen.rate_title.text == "鈴木 第 1 週 4 日目"


async def test_applying_a_rate_changes_only_that_cell_and_shows_a_badge(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    await user.should_not_see(marker="assign-rate-badge-1-鈴木")  # 100% は出さない
    screen.open_rate("鈴木", 1, None)
    screen.apply_rate(60)
    assert rate_of(screen, 1, "鈴木") == 0.6
    assert rate_of(screen, 1, "田中") == 1.0
    assert rate_of(screen, 0, "田中") == 1.0
    assert screen.rate_slider is not None and screen.rate_slider.value == 60
    assert screen.rate_number is not None and screen.rate_number.value == 60
    await user.should_see(marker="assign-rate-badge-1-鈴木")


async def test_the_popup_stays_open_after_the_chart_is_redrawn(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    dialog = screen.rate_dialog
    screen.apply_rate(70)
    assert screen.rate_dialog is dialog and dialog is not None and dialog.value is True


async def test_a_rate_outside_the_range_changes_nothing(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    before = screen.trial.task
    for bad in (0, 150, -5, float("nan"), None, "x"):
        screen.apply_rate(bad)
        assert screen.trial.task == before
    assert screen.rate_number is not None and screen.rate_number.value == 100


async def test_setting_the_rate_back_to_100_removes_the_badge(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    screen.apply_rate(50)
    await user.should_see(marker="assign-rate-badge-1-鈴木")
    screen.apply_rate(100)
    assert rate_of(screen, 1, "鈴木") == 1.0
    assert screen.rate_number is not None and screen.rate_number.value == 100


async def test_apply_to_all_weeks_changes_that_member_everywhere(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 0, None)
    screen.drop_member("鈴木", 2, None)
    screen.open_rate("鈴木", 0, None)
    assert screen.rate_number is not None
    screen.rate_number.value = 40
    screen.apply_rate_all()
    assert rate_of(screen, 0, "鈴木") == 0.4 and rate_of(screen, 2, "鈴木") == 0.4
    assert rate_of(screen, 0, "田中") == 1.0


async def test_the_slider_and_the_number_field_apply_through_their_events(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    assert screen.rate_slider is not None and screen.rate_number is not None
    screen.rate_slider.set_value(75)  # ドラッグ中: 数値欄だけ合わせ、試算は変えない
    assert screen.rate_number.value == 75 and rate_of(screen, 1, "鈴木") == 1.0
    screen.rate_slider._on_release(None)  # 離したとき
    assert rate_of(screen, 1, "鈴木") == 0.75
    for kind in ("blur", "keydown.enter"):
        screen.rate_number.value = 30
        fire(screen.rate_number, kind)
        assert rate_of(screen, 1, "鈴木") == 0.3
        screen.rate_number.value = 100
        fire(screen.rate_number, kind)
        assert rate_of(screen, 1, "鈴木") == 1.0


async def test_blurring_an_out_of_range_number_is_refused_not_clamped(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    screen.apply_rate(50)
    assert screen.rate_number is not None
    for bad in (150, 0, -5):
        screen.rate_number.value = bad
        fire(screen.rate_number, "blur")
        assert rate_of(screen, 1, "鈴木") == 0.5  # 100% や 1% に丸めて反映しない
        assert screen.rate_number.value == 50  # 直前の値に戻る


async def test_a_fractional_rate_is_rounded_to_a_whole_percent(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    screen.apply_rate(33.4)
    assert rate_of(screen, 1, "鈴木") == 0.33
    screen.apply_rate(99.6)  # 100% に丸まる
    assert rate_of(screen, 1, "鈴木") == 1.0
    screen.apply_rate(0.4)  # 0% に丸まるので範囲外
    assert rate_of(screen, 1, "鈴木") == 1.0


async def test_lowering_the_last_week_adds_cells_for_the_weeks_it_stretches_into(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    assert screen.plan is not None
    before = screen.plan.weeks
    screen.open_rate("田中", before - 1, None)
    screen.apply_rate(20)  # 率を下げると完了予定が後ろへ伸びる
    assert screen.plan is not None and screen.plan.weeks > before


async def test_the_remove_button_does_not_open_the_popup(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    await user.should_see(marker="assign-remove-1-鈴木")
    user.find(marker="assign-remove-1-鈴木").click()
    assert screen.rate_dialog is not None and screen.rate_dialog.value is False
    assert screen.rate_target is None


async def test_the_popup_closes_when_its_member_is_gone(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    screen.remove_member_at("鈴木", 1, None)
    screen.show_rate()
    assert screen.rate_dialog is not None and screen.rate_dialog.value is False


async def test_a_confirmed_rate_is_written_back_and_cancel_discards_it(
    user: User,
) -> None:
    screen, confirmed = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.open_rate("鈴木", 1, None)
    screen.apply_rate(60)
    assert is_dirty(screen.trial)
    user.find(marker="assign-confirm").click()
    assert (
        confirmed
        and next(
            a.allocation for a in confirmed[0].task.weekly_crew[1] if a.name == "鈴木"
        )
        == 0.6
    )


def test_the_badge_css_exists() -> None:
    assert ".assign-rate-badge" in ASSIGN_DRAG_CSS


async def test_selecting_a_range_marks_its_cells_and_shows_the_clear_button(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.select_range((0, None), (0, None))
    assert screen.selection == ((0, None), (0, None))
    await user.should_see(marker="assign-selection-clear")
    assert any(
        "assign-selected" in e.classes
        for e in user.find(marker="assign-cell-0").elements
    )


async def test_the_selection_is_ordered_whatever_the_swipe_direction(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.select_range((2, None), (1, None))
    assert screen.selection == ((1, None), (2, None))


async def test_dropping_inside_the_selection_adds_to_every_cell_in_it(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.select_range((1, None), (2, None))
    screen.drop_member("鈴木", 2, None)
    crews = [[a.name for a in w] for w in screen.trial.task.weekly_crew]
    assert crews[0] == ["田中"]
    # 最後の週(1)の担当は以降も続くので、週 2 は増やさなくても鈴木が入る
    assert crews == [["田中"], ["田中", "鈴木"]]
    assert screen.selection is None  # 足したら選択を外す


async def test_dropping_outside_the_selection_adds_only_that_cell(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.select_range((1, None), (2, None))
    screen.drop_member("鈴木", 0, None)
    crews = [[a.name for a in w] for w in screen.trial.task.weekly_crew]
    assert crews[0] == ["田中", "鈴木"]
    assert all("鈴木" not in c for c in crews[1:])
    assert screen.selection == ((1, None), (2, None))  # 範囲の外なので選択は残る


async def test_dropping_when_everyone_is_already_in_the_range_changes_nothing(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.drop_member("鈴木", 2, None)
    before = screen.trial.task
    screen.select_range((1, None), (2, None))
    screen.drop_member("鈴木", 1, None)
    assert screen.trial.task == before
    assert screen.selection == ((1, None), (2, None))


async def test_the_clear_button_and_daily_toggle_remove_the_selection(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.select_range((0, None), (1, None))
    await user.should_see(marker="assign-selection-clear")
    user.find(marker="assign-selection-clear").click()
    assert screen.selection is None
    screen.select_range((0, None), (1, None))
    screen.toggle_daily(0)  # セルの並びが変わるので外す
    assert screen.selection is None


async def test_a_selection_without_a_start_date_is_ignored(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.plan = None
    screen.select_range((0, None), (1, None))
    assert screen.selection is None


async def test_the_select_event_is_routed_to_the_active_screen(user: User) -> None:
    screen, _ = await open_team_screen(user)
    select_on_active(
        screen.client_id,
        {"first": {"week": 0, "day": None}, "last": {"week": 1, "day": None}},
    )
    assert screen.selection == ((0, None), (1, None))
    select_on_active(
        "other", {"first": {"week": 0, "day": None}, "last": {"week": 2, "day": None}}
    )
    assert screen.selection == ((0, None), (1, None))  # 知らないクライアントは無視


async def test_a_range_selection_does_not_make_the_screen_dirty(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.select_range((0, None), (1, None))
    assert not is_dirty(screen.trial)


async def test_the_load_panel_shows_a_toggle_and_a_row_for_each_assignee(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    await user.should_see(marker="assign-load")
    await user.should_see(marker="assign-load-toggle-田中")
    await user.should_see(marker="assign-load-row-田中")
    summary = user.find(marker="assign-load-summary-田中").elements.pop()
    assert summary.text.startswith("最大 ")


async def test_each_member_has_a_stable_color_by_project_member_order(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    names = [m.name for m in screen.project.members]
    assert [screen.load_color(n) for n in names] == [
        member_color(i) for i in range(len(names))
    ]
    assert screen.load_color("いない人") == member_color(0)


async def test_the_load_can_be_switched_to_one_overlaid_histogram(user: User) -> None:
    screen, _ = await open_team_screen(user)
    await user.should_see(marker="assign-load-row-田中")
    screen.set_load_overlay(True)
    await user.should_see(marker="assign-load-overlay")
    await user.should_not_see(marker="assign-load-row-田中")
    await user.should_see(marker="assign-load-toggle-田中")  # トグルは両方で使う
    summary = user.find(marker="assign-load-overlay-summary").elements.pop()
    assert "最大" in summary.text
    screen.set_load_overlay(False)
    await user.should_see(marker="assign-load-row-田中")
    await user.should_not_see(marker="assign-load-overlay")


async def test_tapping_a_toggle_hides_and_shows_the_row(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.toggle_load("田中")
    assert screen.load_hidden == {"田中"}
    await user.should_not_see(marker="assign-load-row-田中")
    await user.should_see(marker="assign-load-toggle-田中")  # トグルは残る
    screen.toggle_load("田中")
    assert screen.load_hidden == set()
    await user.should_see(marker="assign-load-row-田中")


async def test_dropping_a_member_adds_a_row_for_that_member(user: User) -> None:
    screen, _ = await open_team_screen(user)
    await user.should_not_see(marker="assign-load-row-鈴木")
    screen.drop_member("鈴木", 1, None)
    await user.should_see(marker="assign-load-row-鈴木")
    await user.should_see(marker="assign-load-toggle-鈴木")


async def test_the_load_uses_the_trial_task_without_touching_the_original(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    loaded = screen.load_project()
    names = {a.name for task in loaded.all_tasks() for a in task.assignees}
    assert "鈴木" in names
    original = {a.name for task in screen.project.all_tasks() for a in task.assignees}
    assert "鈴木" not in original


async def test_a_removed_assignee_loses_the_toggle_and_the_hidden_mark(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.drop_member("鈴木", 1, None)
    screen.toggle_load("鈴木")
    assert "鈴木" in screen.load_hidden
    screen.remove_member_at("鈴木", 1, None)
    screen.render_load()
    assert "鈴木" not in screen.load_hidden


async def test_no_start_date_says_the_load_cannot_be_shown(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.plan = None
    screen.render_load()
    await user.should_see(marker="assign-load-none")


async def test_a_closed_panel_is_not_drawn_until_it_is_opened(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.on_load_toggle(False)
    screen.drop_member("鈴木", 1, None)
    await user.should_not_see(marker="assign-load-row-鈴木")
    screen.on_load_toggle(True)
    await user.should_see(marker="assign-load-row-鈴木")


async def test_the_load_display_does_not_make_the_screen_dirty(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.toggle_load("田中")
    screen.on_load_toggle(False)
    assert not is_dirty(screen.trial)


def label_text(user: User, marker: str) -> str:
    return user.find(marker=marker).elements.pop().text


async def test_without_a_deadline_the_shortage_row_says_why(user: User) -> None:
    await open_team_screen(user)
    await user.should_see(marker="assign-shortage")
    assert "基準日" in label_text(user, "assign-shortage")


async def test_the_shortage_row_follows_the_assignment(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.trial.task.deadline = datetime(
        2026, 11, 20, 17
    )  # 11/16 月〜20 金: 5 日 × 6.5h
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see("あと 7.5h 足りません")
    screen.drop_member("鈴木", 0, None)  # 週 0 に 鈴木 を足す(100%)
    await user.should_see("余裕")
    text = label_text(user, "assign-shortage")
    assert text.startswith("余裕 25.0h")


async def test_the_shortage_row_hint_names_the_due(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.trial.task.deadline = datetime(2026, 11, 20, 17)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see("あと 7.5h 足りません")
    label = user.find(marker="assign-shortage").elements.pop()
    assert "11/20 17:00 まで。締切" in str(label.props.get("title", ""))


async def test_the_shortage_row_does_not_make_the_screen_dirty(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.trial.task.deadline = None
    screen.refresh()
    assert not is_dirty(screen.trial)


async def test_switching_from_a_shortage_to_a_reason_clears_the_warning_look(
    user: User,
) -> None:
    screen, _ = await open_team_screen(user)
    screen.trial.task.deadline = datetime(2026, 11, 20, 17)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see("あと 7.5h 足りません")
    label = user.find(marker="assign-shortage").elements.pop()
    assert "--warning" in str(label._style)
    screen.now = lambda: datetime(2026, 11, 25, 9)  # 締切を過ぎた
    screen.refresh()
    await user.should_see("基準日を過ぎています")
    assert "--warning" not in str(label._style)
    assert "title" not in label.props


async def test_the_burn_row_shows_each_weeks_burn(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see("消化 32.5h / 残り 7.5h")
    assert label_text(user, "assign-burn-0") == "消化 32.5h / 残り 7.5h"
    assert label_text(user, "assign-burn-1") == "消化 7.5h / 完了"
    await user.should_not_see(marker="assign-burn-2")  # セルは 2 週ぶんだけ


async def test_the_burn_row_follows_the_assignment(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.drop_member("鈴木", 0, None)  # 週 0 だけ 2 人(65h)
    await user.should_see("消化 40.0h / 完了")
    assert label_text(user, "assign-burn-0") == "消化 40.0h / 完了"
    assert label_text(user, "assign-burn-1") == "—"


async def test_the_burn_row_needs_no_deadline(user: User) -> None:
    screen, _ = await open_team_screen(user)
    assert screen.trial.task.deadline is None
    await user.should_see(marker="assign-burn-0")


async def test_the_burn_hint_names_the_week(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    await user.should_see("消化 32.5h / 残り 7.5h")
    label = user.find(marker="assign-burn-0").elements.pop()
    assert "11/16〜11/22 の稼働 32.5h" in str(label.props.get("title", ""))


async def test_the_burn_row_is_not_drawn_without_a_start_date(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.trial.task.planned_start = None
    screen.refresh()
    await user.should_not_see(marker="assign-burn-row")


async def test_the_burn_row_does_not_make_the_screen_dirty(user: User) -> None:
    screen, _ = await open_team_screen(user)
    screen.now = lambda: datetime(2026, 11, 16, 9)
    screen.refresh()
    assert not is_dirty(screen.trial)
