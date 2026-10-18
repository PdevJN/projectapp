# カテゴリ機能(ファイル形式 v3)設計書

> **状態**: 実装済み — 要望 29 — マージ PR #4(75126f7。2026-10-11)。当時の記録で、現在の仕様は [`CLAUDE.md`](../../../CLAUDE.md) を正とする。

2026-10-11。architectural。要望 29。ブランチ `feature/category`。

## 背景と目的

担当者向けの書き出し(`handoff.py`)は、タスクの ProjectCode ごとに、`todos.json` のカテゴリを自動で作っている。名前と PRJコードは同じ文字列、色は出現順の固定 10 色、`id` は `uuid5`(プロジェクト名・コード)で、利用者が管理できない。ProjectCode は自由入力の文字列なので、表記の揺れも防げない。

目的は、**カテゴリをプロジェクトで登録・管理するものにする**こと。todoapp のカテゴリ(`id`・`name`・`kind`・`expiry_date`・`color`・`prj_code`)と一対一にし、要望 5(返送の取り込み)の突き合わせに使える安定 id を持たせる。

## 決定事項

- ProjectCode をカテゴリへ昇格する。`Task.project_code` は廃止し、`Task.category_id` に置き換える。
- カテゴリは、todoapp の 6 項目すべてを持つ。
- 管理は設定ダイアログ(プロジェクト共通。URL テンプレートと同じ置き場)。
- ガントチャートは変えず、書き出しだけに反映する(名前の欄のチップは、タスクのカテゴリから作る)。
- 「未定」は保存しない擬似カテゴリ(todoapp と同じ)。タスクが選ぶと `category_id = None`。名前・種別・有効期限・色・PRJコードは設定できず、削除もできない。
- ファイル形式を version 3 に上げる。

## モデル(`models.py`)

```python
@dataclass
class Category:
    name: str                        # 最大 MAX_CATEGORY_NAME_LENGTH(30)文字。制御文字は使えない
    kind: str = ""                   # 種別(自由入力)。最大 MAX_CATEGORY_KIND_LENGTH(20)文字。制御文字は使えない
    expiry_date: date | None = None  # 有効期限日。None は期限なし
    color: str = "blue"              # categories.COLORS のどれか
    prj_code: str = ""               # PRJコード。最大 MAX_PROJECT_CODE_LENGTH(20)文字。半角英数字と - _ . だけ(空は可)
    id: str = field(default_factory=new_id, compare=False)
```

- `Project.categories: list[Category]`。順序が登録順で、書き出しの配列の順序になる。
- `Task.category_id: str | None = None`。`Task.project_code` のフィールドは消す。`MAX_PROJECT_CODE_LENGTH` は、PRJコードの上限として残す。
- `id` は、メンバー・セクションと同じ `new_id(taken)` で、既存の id と重ならないように振る。名前を変えても変わらない。
- `FORMAT_VERSION = 3`。

## ファイル形式(version 3)

```
categories: [{"id", "name", "kind", "expiry_date", "color", "prj_code"}]
tasks[].category_id: "<カテゴリid>" | null
```

- `expiry_date` は `YYYY-MM-DD` か `null`。
- 「未定」は `categories` に入れない。`category_id` が `null`(キーなしを含む)のタスクが「未定」。
- `project_code` は書かない。

### 読込のルール

version 2 以前(キーなしを含む):

- `tasks[].project_code`(空でないもの)を、`categories.migrate_legacy` で、同じコードごとにカテゴリへ移す。出現順(セクションとタスクの並び順)に、`name = コード`(制御文字は空白に替える。整えた名前が同じものは 1 つにまとめる)、`prj_code = name`(ただし、半角英数字と `-` `_` `.` 以外を含むときは空。チップは名前を出すので、見た目は変わらない)、`kind = ""`、`expiry_date = None`、`color = COLORS[出現順 % 10]`(書き出しの色の割り当てと同じ)、新しい `id` を振る。タスクはその `id` を `category_id` に持つ。
- `project_code` が空・キーなし・`null`、制御文字だけ、または「未定」のタスクは「未定」(`category_id = None`)。
- 移行で作ったカテゴリは、次に保存したときから version 3 のファイルに残る。
- 旧 `project_code` の検証(文字列・20 文字以内)は、今までどおり拒否する。

version 3:

- `categories` はキーなしなら空。配列でなければ拒否する。
- 各カテゴリ:
  - `id` はキーなし・空・文字列以外・重複を拒否する(カテゴリ同士)。
  - `name` は文字列で、前後の空白を除いて空でなく、`MAX_CATEGORY_NAME_LENGTH`(30)文字以内で、制御文字を含まず、「未定」でなく、ほかのカテゴリと重ならない。
  - `kind` は文字列(キーなし・`null` は空)。20 文字以内で、制御文字を含まない。
  - `expiry_date` は `null`・キーなし、または有効な `YYYY-MM-DD`。
  - `color` は `COLORS` のどれか(キーなしは `blue`)。
  - `prj_code` は文字列(キーなし・`null` は空)。前後の空白を除き、20 文字以内で、半角英数字と `-` `_` `.` だけ(`PRJ_CODE_FORMAT`。空は可)。
- `tasks[].category_id` は `null`・キーなし、または存在するカテゴリの `id`。存在しない `id` は拒否する。
- タスクに旧キー `project_code` があっても、version 3 では使わない(読み捨てる)。
- 不正な値は読込を拒否する(`ValueError`。「開けませんでした」)。このアプリより新しい `version` は、従来どおり拒否する。

### 保存のルール

- `categories` を登録順に保存する。保存は一時ファイル経由で、新規保存は同名のファイルを上書きしない(従来どおり)。
- チェックポイントのタスクも `category_id` を保存する(ProjectCode と同じ扱い)。

## `categories.py`(新規。NiceGUI から切り離した純粋関数)

- `UNDECIDED = "未定"`、`COLORS`(`blue indigo purple pink red orange amber green teal brown`。`handoff.CATEGORY_COLORS` から移す)。
- `validate_categories(categories)`: 上の「各カテゴリ」の検証を行う(読込・設定ダイアログの両方で使う)。
- `migrate_legacy(...)`: 旧 `project_code` からカテゴリを作る(読込のときだけ使う)。
- `next_color(categories)`: 新しい行の色。使っていない色の先頭(すべて使っていれば出現順に巡回)。
- `count_usage(project, category_id)`: そのカテゴリを選んでいるタスクの数。
- `CategoryEdit(categories, removed_ids)` と `apply_edit(project, edit)`: 一覧を置き換え、削除したカテゴリを選んでいたタスクの `category_id` を `None` に戻す。改名の引き継ぎは要らない(`id` で紐づく)。
- `chip_text(category)`: 名前の欄のチップの文字。`prj_code`、空なら名前。

## 画面

### 設定ダイアログ(`forms.open_settings_dialog`)

- URL テンプレートの節の下に「カテゴリ」の節を足す。
- 先頭に「未定」の固定行(灰色・読み取り専用・削除ボタンなし。マーカー `settings-category-undecided`)。
- 登録の行: 名前・種別・有効期限(日付入力)・色(10 色の選択。色見本つき)・PRJコード・削除ボタン。マーカーは `settings-category-<n>-name|kind|expiry|color|prj|remove`。
- 「カテゴリを追加」(`settings-category-add`)で行を足す。色は `next_color`。
- 適用時に `validate_categories` で検証し、エラーは `settings-error` に出す。
- 削除するカテゴリを使うタスクがあるときは、件数つきの確認を出す(既存の `confirm` と同じ流れ。URL テンプレートの削除の確認と並べて 1 回にまとめる)。文言: 「削除するカテゴリを使っているタスクが N 件あります。未定に戻ります。」
- 適用の通知は、`views.MainView.apply_categories`(`apply_templates` と同じ位置づけ)が受け、`apply_edit` を呼んで、ガントチャートを描き直す。

### タスクダイアログ(`task_dialog.py`)

- `ProjectCode` の入力欄(`task-project-code`)を、`ui.select`(`task-category`)に置き換える。
- 選択肢は「未定」(値 `None`)と、登録したカテゴリ名(値は `id`)。既定は「未定」。
- 編集中のタスクのカテゴリが一覧にない場合は「未定」にする。
- `forms.build_task` は `category_id` を受け取る。ProjectCode の検証(長さ)は不要になる。
- タスクのコピー(`copy`)は `category_id` を引き継ぐ。

### 名前の欄のチップ(`gantt.task_chips`)

- タスクの `category_id` から `Category` を引き、`chip_text` を出す。ツールチップはカテゴリ名。
- 「未定」のときは出さない。
- 見た目(`CODE_CHIP_STYLE`)とマーカー(`task-code-<key>-<ti>`)は変えない。
- 引き当ては、`GanttChart` が持つ `{id: Category}` の辞書で行う(再描画のたびに作る。要素数は増えない)。

## 書き出し(`handoff.build_todos`)

- `categories` は `project.categories` を登録順にそのまま書き出す(タスクが 1 件もないカテゴリも含む。以前は使われたコードだけだった)。`id` は `category.id`。`expiry_date` は ISO 形式の日付か `null`。
- 項目の `category_id` は、タスクの `category_id`。「未定」は `null`。
- `_uuid(project.name, "category", ...)` と `CATEGORY_COLORS` の割り当ては廃止する。
- todoapp の形式(`version: 1`)は変えず、独自のキーも足さない。
- 要望 5(返送の取り込み)では、`category_id` が `null` または存在しない `id` のものを「未定」として読む。ここでは実装しない。

- 制御文字は Unicode の `Cc`(改行・タブ・NUL・DEL・C1)。名前と種別に共通で、前後の空白(改行を含む)を除いてから検査する。PRJコードは制御文字を含む半角英数字と `-` `_` `.` 以外すべてを拒否する(日本語・全角・空白・記号も不可)。設定ダイアログの入力欄には `maxlength` を付ける。

## タスク名の上限(同じブランチで行う)

- タスク名は 50 文字以内(`MAX_TASK_NAME_LENGTH`)で、制御文字(Unicode の `Cc`)を含まない。
- 入力(`forms.build_task`)は、前後の空白を除いてから検査し、超過・制御文字を拒否する。チェックポイントにも適用する。名前の入力欄には `maxlength` を付ける。
- 読込は拒否せず、`models.tidy_task_name` で整える(制御文字は空白に替え、前後の空白を除き、50 文字を超える分は切り詰める。version を問わない)。整えた結果が空でも開ける。名前が文字列でないファイルは拒否する。
- タスクのコピー(`arrange.copy_task`)は、「(コピー)」を足した名前が上限を超えないよう、元の名前を切り詰める。
- セクション・メンバー・パラメータ等の名前は変えない。

## 範囲外

- ガントチャート上のカテゴリの色分けと、カテゴリでの絞り込み。
- カテゴリの並べ替え(設定ダイアログの行の順序は登録順。入れ替えは後続)。
- 有効期限切れの扱い(todoapp 側が判定する。このアプリは値を持つだけ)。
- `handoff.py` のタスク `id`(`uuid5`)の見直し(要望 5)。
- ダッシュボード、プレビュー、PNG の書き出しの変更。

## テスト

- `test_categories.py`(新規): 検証(空・重複・「未定」・色・日付・長さ)、`migrate_legacy`(出現順・色・同じコードを 1 つにまとめる)、`next_color`、`count_usage`、`apply_edit`(削除したカテゴリのタスクが未定に戻る)、`chip_text`。
- `test_storage.py`: version 2 の旧ファイル(ProjectCode あり・なし)が移行されること、version 3 の往復、不正な値の拒否(存在しない `category_id`、重複 `id`、不正な色・日付、「未定」という名前)、`version` が 3 であること。
- `test_forms.py`・設定ダイアログ: カテゴリの追加・変更・削除、確認ダイアログ、「未定」の行が編集できないこと、エラー表示。
- `test_task_dialog.py`: 選択肢(先頭が未定)、保存で `category_id`、一覧にないカテゴリは未定。
- `test_gantt.py`: チップの文字(PRJコード・空なら名前・未定は出ない)、ツールチップ。
- `test_handoff.py`: 登録したカテゴリがすべて書き出される(未使用も)、`category_id`、「未定」が `null`、`id` が `category.id`、旧テスト(ProjectCode からの自動生成)の書き換え。
- 既存の ProjectCode のテスト(`test_forms.py`・`test_task_dialog.py`・`test_views.py`・`test_gantt.py`・`test_arrange.py`)を、カテゴリのテストに書き換える。

## 影響するドキュメント

- `CLAUDE.md`(`projectapp/`): ProjectCode の記述を、カテゴリに合わせて直す。担当者向けファイルの節の「ProjectCode はカテゴリ(`prj_code`)にする」も直す。データの保存先の節に、カテゴリを加える。
- `docs/development.md`: モジュール構成に `categories.py` を足し、ファイル形式の注意に version 3 を書く。
- `.claude/MEMORY.md`: 要望 29 の状況。
