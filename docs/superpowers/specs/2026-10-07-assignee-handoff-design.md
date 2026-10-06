# 担当者向けファイルの書き出し 設計書

要望 4(2026-10-04 に受領)。

## 目的

管理者が、メンバーを 1 人選び、その担当のタスクを todoapp のファイル形式(`todos.json`)で書き出す。担当者は、todoapp(別の NiceGUI アプリ)でそのファイルを開き、実行の記録(開始時刻・終了時刻)を付ける。記録を返してもらう取り込みは、要望 5 の範囲とし、今回は含めない。

todoapp の形式は、`file-format.md`(利用者が配置。git 管理外)に従う。

## 範囲

**含む**:
- メイン画面から、担当者を選んで、未終了のタスクを todoapp 形式の JSON として書き出すこと。
- projectapp のタスクから todoapp の `items` / `records` / `categories` への変換(純粋関数)。
- 保存先の選択(ネイティブの保存ダイアログ)と、一時ファイル経由の書き込み。

**含まない**:
- 担当者からの返送の取り込み(要望 5)。todoapp の `records` を projectapp の実績へ戻す対応は、そちらで設計する。
- メール送信など、ファイルの受け渡し。書き出して終わり。
- todoapp 側の変更。todoapp は、`file-format.md` の形式のまま読めること。
- todoapp にない情報(状態・進捗度・優先度・締切・他の担当者のタスク・メンバーの比率・添付ファイル)。書き出さない。

## 決定事項(確認済み)

- 受け取る側は todoapp。形式は、todoapp のものをそのまま使う(独自のキーは足さない)。
- 対象は、選んだ担当のタスクのうち、状態が「終了」以外のもの。
- 複数日にわたるタスクは `daily`、1 日のタスクは `one_time`。
- 工数は、基準の人の時間なので、担当者自身の時間にするには、相対比率で割る。割り当て率では割らない(割り当て率は、1 日の時間の配分であって、作業量ではない)。

## 変換

対象のタスクを `all_tasks()` の順に並べ、次のように変える。

| todoapp | 値 |
|---|---|
| `version` | `1` |
| `items[].id` | 決定的な uuid(下記)の hex 32 文字 |
| `items[].name` | `Task.name` |
| `items[].schedule_type` | 完了予定の日が開始予定の日と同じなら `one_time`、後の日なら `daily`(判定は下記)。開始予定がないときは `one_time` |
| `items[].anchor_date` | 開始予定の日。開始予定がなければ `project.base_date` |
| `items[].estimate_hours` | `effort_hours ÷ メンバーの相対比率`(小数第 2 位に丸める。工数がなければ `0.0`) |
| `items[].category_id` | ProjectCode があれば、そのコードのカテゴリの id。なければ `null` |
| `items[].done_date` | `null` |
| `categories[]` | ProjectCode の初出順に 1 件ずつ。`name` と `prj_code` は同じコード、`kind` は空文字、`expiry_date` は `null`、`color` は todoapp の色名を順に割り当てる(`blue` から。10 色で一巡) |
| `records[]` | タスクの `actuals`(1 区間 = 1 件)。`item_id`・`item_name` はそのタスク、`start_time`・`end_time` は ISO 8601(秒まで。`end` がなければ `null`) |

- **期間の判定**: 工数がなく、手入力の完了予定も締切もないタスクは、完了予定が「開始予定の 1 日後」という既定値になるだけで、期間の情報がない。このときは `one_time` にする。それ以外は、`effective_end` の日を、開始予定の日と比べる。完了予定が 0 時ちょうどのときは、前日の終わりとして数える(`end - 1 秒` の日)。
- メンバーが見つからない場合(担当者名がメンバーにいない)は、比率 100% で数える。ファイルの読込が、メンバーを補うので、通常は起きない。
- **決定的な id**: `uuid5(NAMESPACE, f"{project.name}\n{task_key}")`。`task_key` は、タスク名に、同じ名前のタスクの出現順の番号(2 件目以降のみ。`name#2`)を足したもの。カテゴリは `uuid5(NAMESPACE, f"{project.name}\ncategory\n{code}")`。記録は `uuid5(NAMESPACE, f"{item_id}\n{start}")`。同じ内容を書き出し直すと、同じ id になる。`NAMESPACE` は、固定の定数。
- **実行中の記録は 1 件だけ**: todoapp は、実行中(`end_time` が `null`)を同時に 1 件までとする。実行中の区間が複数あるときは、開始が最も新しいものだけを `null` のまま残し、ほかは書き出さない。書き出さなかった件数は、通知に出す。

## 構成

### `handoff.py`(新規。NiceGUI に依存しない)

- `build_todos(project, member_name, holidays) -> Handoff`
  - `Handoff` は、`data: dict`(todoapp 形式)、`task_count: int`、`skipped_records: int`。
  - 未終了で、`assignee == member_name` のタスクだけを対象にする。
- `tasks_for(project, member_name) -> list[Task]`: 対象の絞り込み(ダイアログの件数の表示にも使う)。
- `default_filename(project_name, member_name) -> str`: `todos-<メンバー名>.json`(ファイル名に使えない文字は `_` へ)。todoapp は `~/.todoapp/todos.json` を読むため、担当者が名前を直して置く前提。
- `write_json(path, data) -> Path`: UTF-8・インデント 2 の整形 JSON(`ensure_ascii=False`)。拡張子がなければ `.json` を付ける。一時ファイル経由で、失敗したら何も残さない(`export.write_png` と同じ作り)。

### 画面(`views.py`)

- ヘッダーに、「担当者へ書き出し」ボタン(`icon="upload_file"`、マーカー `export-handoff`)を、「エクスポート」の隣に置く。プレビュー中は出さない(ヘッダーごと別の画面になる)。
- 押すとダイアログを開く。担当者の選択(メンバー名。メンバーがいなければ、押したときに「メンバーが登録されていません」と通知して開かない)、対象の件数の表示、「書き出す」・「キャンセル」。
- 件数が 0 のときは、「書き出す」を無効にして、「終了以外のタスクがありません」と表示する。
- 「書き出す」で、保存ダイアログ(`ask_path`)を開き、パスを選んだら、`write_json` で書く。成功したら「N 件を書き出しました」と通知(書き出さなかった記録があれば、その件数も)。キャンセルしたら何もしない。失敗(`OSError`)は、通知して、ダイアログを閉じない。
- 保存はしない。プロジェクトの変更にもならない(編集中の判定に入れない)。

### 保存ダイアログ(`export.py`)

- `ImageExporter.ask_path(filename)` は PNG の種類に固定されている。`file_types` を引数に足し(既定は、今の PNG)、JSON の保存にも使う。テストの偽物も、同じ引数を受ける。

## エラーと注意

- 担当者のタスクの開始予定が、`MIN_YEAR`〜`MAX_YEAR` の範囲外でも、そのまま書き出す(読込がすでに検査している)。
- 書き出したファイルは、todoapp の `version` の検査を通る必要がある。`version` は、常に `1`。
- ファイルに、他の担当者の名前・比率は入らない(`assignee` のキーを出さない)。

## テスト

- `build_todos`: 終了の除外、他の担当者の除外、`one_time` / `daily` の判定(1 日・複数日・工数も完了予定も締切もない・開始予定なし・完了予定が 0 時ちょうど)、`anchor_date` の既定、工数の換算(比率 50%・100%・工数なし)、カテゴリ(ProjectCode の有無・重複・色の巡回)、実績の変換(終了あり・実行中)、実行中が複数のときの絞り込み、同名タスクの id、書き出し直しで id が変わらないこと。
- 出力が `file-format.md` の必須キー・型・`version == 1` を満たすこと(キーの集合と型を検査するテスト)。
- `write_json`: 拡張子の補完、一時ファイルが残らないこと、日本語がエスケープされないこと。
- 画面: メンバーがいないときの通知、件数 0 のときの無効化、書き出しの成功(偽の保存先)、保存ダイアログのキャンセル、書き込み失敗の通知、プロジェクトの変更扱いにならないこと。

## ドキュメント

- `CLAUDE.md`(プロジェクト): 「プロジェクトファイル」または新しい節に、担当者向けファイルの書き出しを足す。
- `docs/development.md`: `handoff.py` を、モジュール構成に足す(todoapp 形式との対応の表を含む)。
- `.claude/MEMORY.md`: 要望 4 の状況を更新する。
