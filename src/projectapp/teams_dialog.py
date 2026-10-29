"""チームのタブ(`メンバーとパラメータ`のダイアログの 3 つ目)。"""

from collections.abc import Callable, Collection
from copy import deepcopy
from dataclasses import dataclass

from nicegui import ui

from projectapp.models import Membership, Team
from projectapp.teams import TeamRow, build_teams, even_split, settle_memberships


@dataclass
class TeamsPanel:
    """チームのタブの操作。dirty は未適用の編集があるか、apply は適用(続きの処理は、適用できたときだけ呼ぶ)。"""

    dirty: Callable[[], bool]
    apply: Callable[[Callable[[], None] | None], None]


def teams_panel(
    get_teams: Callable[[], list[Team]],
    impacts: Callable[[list[Team]], list[str]],
    on_apply: Callable[[list[Team]], object],
    on_applied: Callable[[set[str]], object],
    get_taken: Callable[[], Collection[str]],
) -> TeamsPanel:
    """チームの登録(タブの中身)。削除で所属が外れるメンバーがいるときは、適用の前に確認する。
    適用してもダイアログは閉じず、プロジェクトの今のチームから行を作り直す。`on_applied` には、削除したチームの id を渡す。"""

    def to_rows() -> list[TeamRow]:
        return [TeamRow(t.id, t.name) for t in get_teams()]

    rows = to_rows()
    baseline = deepcopy(rows)
    ui.label("メンバーを所属させて、担当の割り当てと絞り込み・集計に使います").classes("text-caption text-grey")

    @ui.refreshable
    def table() -> None:
        with ui.column().classes("w-full gap-1"):
            if not rows:
                ui.label("チームがありません").classes("text-grey")
            for index, row in enumerate(rows):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    ui.input(
                        "チーム名",
                        value=row.name,
                        on_change=lambda e, r=row: setattr(r, "name", e.value or ""),
                    ).classes("flex-1").mark(f"team-name-{index}")
                    ui.button(icon="delete", on_click=lambda _e, r=row: remove(r)).props(
                        "flat dense round color=negative"
                    ).mark(f"team-delete-{index}")

    def add() -> None:
        rows.append(TeamRow(None, ""))
        table.refresh()

    def remove(row: TeamRow) -> None:
        rows.remove(row)
        table.refresh()

    table()
    ui.button("チームを追加", icon="add", on_click=add).props("flat").mark("team-add")
    error = ui.label("").classes("text-negative").mark("team-error")
    pending: dict[str, list[Team]] = {}
    after: dict[str, Callable[[], None] | None] = {"then": None}
    with ui.dialog() as confirm, ui.card():
        confirm_text = ui.label("").style("white-space: pre-line")
        with ui.row():
            ui.button("キャンセル", on_click=confirm.close).props("flat").mark("team-delete-cancel")
            ui.button("削除する", on_click=lambda: confirm_apply()).props("color=negative").mark("team-delete-confirm")

    def commit(teams: list[Team], then: Callable[[], None] | None) -> None:
        removed = {t.id for t in get_teams()} - {t.id for t in teams}
        on_apply(teams)
        on_applied(removed)
        rows[:] = to_rows()
        baseline[:] = deepcopy(rows)
        table.refresh()
        if then is not None:
            then()

    def confirm_apply() -> None:
        confirm.close()
        commit(pending["teams"], after["then"])

    def apply(then: Callable[[], None] | None = None) -> None:
        error.set_text("")
        try:
            teams = build_teams(rows, get_taken())
        except ValueError as exc:
            error.set_text(str(exc))
            return
        affected = impacts(teams)
        if affected:
            pending["teams"] = teams
            after["then"] = then
            confirm_text.set_text("\n".join(affected) + "\n削除すると、その所属は外れます(残りの割合は 100% に揃えます)")
            confirm.open()
            return
        commit(teams, then)

    ui.button("適用", on_click=lambda: apply()).mark("team-apply")
    return TeamsPanel(dirty=lambda: rows != baseline, apply=apply)


def open_member_teams_dialog(
    name: str,
    teams: list[Team],
    current: list[Membership],
    on_save: Callable[[list[Membership]], object],
) -> None:
    """メンバー 1 人の所属を決める小さなダイアログ。チームごとにチェックを入れ、2 つ以上のときだけ割合(合計 100)を入れる。"""
    percents = {m.team_id: m.percent for m in current}
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label(f"{name or '(名前なし)'} の所属チーム").classes("text-subtitle1")
        ui.label("兼務のときは、割合の合計を 100% にします").classes("text-caption text-grey")
        checks: list[ui.checkbox] = []
        inputs: list[ui.number] = []
        for index, team in enumerate(teams):
            with ui.row().classes("w-full items-center no-wrap gap-3"):
                check = ui.checkbox(team.name, value=team.id in percents).classes("flex-1").mark(f"mteam-check-{index}")
                number = ui.number("割合(%)", value=percents.get(team.id), min=1, max=100, step=5).classes("w-28")
                number.mark(f"mteam-percent-{index}")
            checks.append(check)
            inputs.append(number)
        error = ui.label("").classes("text-negative").mark("mteam-error")

        def checked() -> list[int]:
            return [i for i, check in enumerate(checks) if check.value]

        def show() -> None:
            picked = checked()
            for i, number in enumerate(inputs):
                number.set_visibility(i in picked and len(picked) >= 2)

        def on_check() -> None:
            picked = checked()
            if len(picked) >= 2:  # 選び直したら、均等割りから始める
                for i, share in zip(picked, even_split(len(picked))):
                    inputs[i].set_value(share)
            show()

        for check in checks:
            check.on_value_change(lambda _e: on_check())
        show()

        def save() -> None:
            rows = [(teams[i].id, inputs[i].value) for i in checked()]
            try:
                chosen = settle_memberships(rows, {t.id for t in teams})
            except ValueError as exc:
                error.set_text(str(exc))
                return
            dialog.close()
            on_save(chosen)

        with ui.row():
            ui.button("キャンセル", on_click=dialog.close).props("flat").mark("mteam-cancel")
            ui.button("決定", on_click=save).mark("mteam-save")
    dialog.on("hide", dialog.delete)
    dialog.open()
