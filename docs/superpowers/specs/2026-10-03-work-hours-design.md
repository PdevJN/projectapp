# 稼働時間の設定画面 設計書

## 目的

プロジェクトごとに、1日の稼働可能時間と始業時刻を、画面から変更できるようにする。変更した値で、終了日時の自動算出と、すでに自動算出されたタスクの終了日時が更新される。日程計算(`2026-10-03-schedule-calc-design.md`)と、プロジェクトの保存 UI(`2026-10-03-project-save-design.md`)の次の段階。

いまは `Project.daily_hours`(既定 6.5h)と `Project.work_start`(既定 9:00)を画面から変える手段がなく、常に既定値で算出される。

## 範囲

**含む**: 設定ダイアログ(稼働可能時間・始業時刻)、入力の検証、変更時の再計算、自動算出された終了を区別する印(`Task.end_auto`)、その保存・読込。

**含まない**(後続のサブプロジェクト、または対象外):
- 昼休みの設定、曜日ごとの稼働時間、メンバーごとの稼働時間、祝日の編集
- 設定の取り消しボタン(値を戻して適用すれば、自動算出分は元に戻る)
- 見積もりのバッファ換算、リソース割り当て比率
- 実績の入力、ドラッグ&ドロップほか

## 決定事項

- 設定はプロジェクトごと。値はプロジェクトのファイル(`~/.projectapp/<名前>.json`)に保存される(既存の `daily_hours`、`work_start`)。
- 設定を変えたときは、**自動算出された終了だけ**を再計算する。手で入力した終了は変えない。
- 自動算出かどうかは、`Task.end_auto` で区別する。古いファイル(印がない)は手入力として扱う。
- 適用は確認なしで、すぐ再計算する。再計算の結果は、開始・工数・稼働時間から一意に決まるので、値を戻して適用すれば元に戻る。
- 適用しても、保存は自動では行わない。変更は「編集中」の判定に入る。

## データ

- `Task.end_auto: bool = False`。`True` は、「終了が自動算出で、利用者が書き換えていない」ことを表す。
- 保存は `asdict` による。読込は `raw.get("end_auto", False)`。
- `fill_end` は、終了を補完したときに `end_auto=True` を付ける。
- `build_task` は、編集ダイアログの終了が、編集前の終了(新規は `None`)と**違えば** `end_auto=False` にする(手入力、空にした場合、新規の手入力)。**同じなら**、編集前の `end_auto` を引き継ぐ。空にして保存して、再び算出できたときは、`fill_end` が `True` に戻す。
- 編集で開始や工数だけを変えても、終了は動かない(既存のルール)。印も変わらない。次に設定を変えて再計算するか、終了を空にして保存したときに、新しい値が反映される。

## 再計算

`timeline.recalc_ends(project, holidays) -> int`(純粋関数。NiceGUI に依存しない):
- セクション内と、セクションなしのタスクのうち、`end_auto` が `True` で開始があるものだけを対象にする。
- `calc_end(start, effort_hours, project.daily_hours, project.work_start, holidays)` で再計算し、結果が現在の終了と違えば、終了を入れ替える。
- `calc_end` が `None` を返すとき(工数が不正など)は、終了をそのままにする。
- 終了を入れ替えた件数を返す。

## 設定ダイアログ

- ヘッダーの「開く」「保存」の隣に「設定」ボタン(マーカー `open-settings`)を置く。押すと `forms.open_settings_dialog(daily_hours, work_start, on_apply)` が開く。
- 入力欄は「1日の稼働可能時間(h)」(マーカー `settings-hours`)と「始業時刻」(`HH:MM`、マーカー `settings-start`)。現在の値を入れておく。「適用」(マーカー `settings-apply`)と「キャンセル」。
- `forms.build_work_settings(hours, start) -> tuple[float, time]` が検証する。エラーは `ValueError` で、ダイアログ内(マーカー `settings-error`)に出し、閉じない。
  - 稼働時間は、有限の数で、0 より大きく 24 以下。未入力は拒否する。
  - 始業時刻は `HH:MM` の形式。
  - **始業時刻 + 稼働時間が 24:00 を超える組み合わせは拒否する**(例: 20:00 と 6.5h)。稼働枠が日をまたぐと算出が曖昧になる。

## 適用

`MainView.apply_settings(hours, start)`:
- 現在の値と同じなら、何もしない(通知も出さない)。
- 違えば、`project.daily_hours` と `project.work_start` を更新し、`recalc_ends(project, self.holidays)` を呼び、チャートを描き直す。「稼働時間を変更しました(N件の終了を再計算)」と通知する。
- 保存は自動では行わない。変更は編集中の判定(`is_dirty`)に入るので、「保存」で保存され、保存せずに別のプロジェクトを開こうとすると確認が出る。

## 構成

| ファイル | 変更 |
|---|---|
| `models.py` | `Task.end_auto: bool = False` を追加 |
| `storage.py` | `end_auto` を復元(ないファイルは `False`) |
| `timeline.py` | `fill_end` が `end_auto=True` を付ける。`recalc_ends` を追加 |
| `forms.py` | `build_task` が `end_auto` を更新する。`build_work_settings`、`open_settings_dialog` を追加 |
| `views.py` | 「設定」ボタン、`apply_settings` を追加 |
| `gantt.py` | 変更なし(`set_project` で描き直す) |

## エラー処理

- 入力の不正は、ダイアログ内にエラー文を出し、値を変えず、閉じない。
- 再計算できないタスク(`calc_end` が `None`)は、終了を変えず、件数に数えない。

## テスト

- `timeline`: `recalc_ends`(自動算出分だけが変わる、手入力は変わらない、開始なしは変わらない、算出できないタスクはそのまま、件数、セクションなしのタスクを含む、稼働時間・始業時刻・祝日が結果に効く)。`fill_end` が `end_auto=True` を付ける。
- `forms`: `build_task` の `end_auto`(手入力で `False`、変えなければ引き継ぐ、空にして `False`)。`build_work_settings`(範囲の境界、NaN・inf、未入力、形式、始業時刻 + 稼働時間が 24:00 ちょうど・超過)。ダイアログ(不正なら閉じない、正しければ `on_apply` を呼ぶ)。
- `storage`: `end_auto` の保存・読込、`end_auto` のない古いファイルの読込。
- `views`: 適用で再計算と通知が出る、同じ値なら何もしない、適用すると編集中になる、保存して開き直しても設定と `end_auto` が残る。
