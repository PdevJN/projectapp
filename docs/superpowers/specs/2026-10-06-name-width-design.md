# 名前の欄の幅をドラッグで調整する 設計書

要望 23(2026-10-05 に受領)。

## 目的

ガントチャートの、タスクの名前の欄(左の列)と、チャート(右の領域)の境目をドラッグして、名前の欄の幅を変えられるようにする。今の幅は、`NAME_WIDTH_PX = 200` の固定で、要望 9 で名前の右に並ぶようになったチップ(ProjectCode・担当・進捗)が増えると、名前が窮屈になる。利用者が、自分で幅を合わせて、解消できるようにする。

## 範囲

**含む**:
- 名前の欄の右端のドラッグによる幅の変更(範囲 120〜480px。既定 200px)と、ダブルクリックでの既定への復元。
- 幅の保存(アプリ全体。`~/.projectapp/config.json`)と、起動時の復元。
- 描画の位置を、固定の `NAME_WIDTH_PX` から、可変の幅に追従する形にすること(CSS 変数)。
- プレビューと画像化に、保存した幅を使うこと。

**含まない**:
- プロジェクトごとの幅(ファイルには入れない)。
- 設定ダイアログからの数値入力。
- 他の列(日付の列の幅)の調整。スケールの切り替えで足りる。
- 名前の欄の中の、チップの出し方の変更(幅が変わるだけ。名前は、これまでどおり省略表示)。

## 決定事項(確認済み)

- **案 2(CSS 変数)を採る**。幅を `--name-w` に持たせ、ドラッグ中は、この変数を書き換えるだけにする(再描画なし)。離したときに、サーバーへ送って保存する。
  - 案 1(離したときに描き直す)は、ドラッグ中に表示が変わらず、約 400ms(120 タスク)かかるので採らない。
  - 案 3(名前の欄の右端を原点にする入れ子)は、行ごとに要素が増え、要望 24(要素数を増やさない)の制約に反するので採らない。
- **保存先は、アプリ全体の `config.json`**。テーマと同じ扱い。プロジェクトのデータには入れない。
- **範囲は 120〜480px、既定は 200px**。ダブルクリックで 200px に戻す。範囲外の保存値は、範囲に収めて読む。

## 描画の構造

### 幅の持ち方

- `GanttChart` が `name_width`(px、整数)を持つ。コンストラクタで受け取り、既定は `DEFAULT_NAME_WIDTH_PX`。
- `NAME_WIDTH_PX` は、`DEFAULT_NAME_WIDTH_PX`(200)へ名前を変える。`MIN_NAME_WIDTH_PX = 120`、`MAX_NAME_WIDTH_PX = 480` を足す。定義元は `config.py` に置く(`gantt.py` と `config.py` の両方が使い、`config.py` は `storage` だけに依存するので、循環しない)。
- 全体を包む `chart-content` に、`--name-w: {name_width}px` を設定する。あわせて、JS が範囲を読めるよう、`data-name-min`・`data-name-max`・`data-name-default` を持たせる(定義元は Python の定数 1 つ)。

### 位置の書き方

- ヘルパー `from_name(px: float) -> str` を `gantt.py` に置く。`calc(var(--name-w) + {px:.1f}px)` を返す。
- 現状の `NAME_WIDTH_PX` を使う `gantt.py` の 18 か所は、次のように置き換える。

| 対象 | 変更後 |
|---|---|
| 名前の欄の幅(行・セクション見出し・見出しの空白・タスク追加の行) | `width: var(--name-w)` |
| 棒・実績の棒・実績の間の点線・進捗の印・締切の ◆ の `left` | `from_name(位置)` |
| 格子線・縞の `left` | `var(--name-w)` |
| 年・月の帯のラベルの `left`(固定位置) | `var(--name-w)` |
| チャート全体の幅(`chart-content`) | `from_name(列の幅 × 列数)` |

- 格子線の先頭の列の左線は、名前の欄の右端と重なる(境目に見える縦線)。この位置は、これまでどおり保つ。
- `timeline.py` の純粋関数は、変えない。

### Python 側の計算は、境界を原点にした相対値にする

- `marker_left` は、印の位置を、境界からの距離で返す(今は名前の幅を足した値)。締切の ◆ との重なりの判定も、相対値で行う。
- 期間の右端の外へ出さない判定(`mark_left <= total - MARK_WIDTH_PX`)は、相対値(`列の幅 × 列数 - MARK_WIDTH_PX`)で比べる。
- 結果が名前の幅に依存しないので、幅が変わっても、Python 側の再計算は要らない。
- `content_width()` は、`name_width + 列の幅 × 列数`(画像の幅)。

## ドラッグ操作

### 掴む場所(要素数を増やさない)

- 名前の欄の右端 6px(`RESIZE_EDGE_PX`)を、掴み場所にする。CSS の疑似要素(`::after`。`position: absolute; right: 0; top: 0; bottom: 0; width: 6px; cursor: col-resize`)で、カーソルだけを出す。要素は増えない。
- 対象は、名前の欄の 4 種類(タスクの行・セクション見出し・見出しの空白・タスク追加の行)。クラス `gantt-name-resizable` を付ける。
- 名前の欄は、横スクロールで左に固定されるので、掴み場所も固定された右端に付いてくる。格子線の側には置かない(スクロールで流れるため)。
- 読み取り専用(プレビュー)では、`gantt-name-resizable` を付けない(掴めない)。

### JS(`gantt_drag.py` の `CHART_DRAG_JS` に足す)

既存のドラッグ用 JS と同じく、`document` に委譲する(`render` で作り直されるため)。

- `pointerdown`: 対象が、`.gantt-name-resizable` の中で、ポインタが右端 6px 以内なら、ドラッグを始める。`setPointerCapture` し、開始位置と開始の幅(`--name-w` の現在値)を記録する。ドラッグ中は、`document.body` に、カーソル `col-resize` と `user-select: none` を付ける。
- `pointermove`: 幅 = 開始の幅 + 移動量 を、`data-name-min`〜`data-name-max` に収め、整数に丸めて、`chart-content` の `--name-w` に設定する。
- `pointerup`: `emitEvent("chart_name_width", {width})` を送る。
- `dblclick`(右端): `--name-w` を `data-name-default` に戻し、同じイベントを送る。
- 既存の操作との衝突を避ける。
  - 右端では、行の移動(HTML5 の drag)を始めない(`dragstart` で、ドラッグ中の印があれば `preventDefault`)。
  - 離したあとの `click` が、編集ダイアログを開かないよう、ドラッグの直後の 1 回を、捕捉して止める。
- ドラッグでの幅の変更中も、バーの横移動(pointer イベントの `transform`)には、干渉しない(対象の要素が違う)。

### Python 側

- `ui.on("chart_name_width", ...)` で、`handle_name_width(args)` を呼ぶ。`chart_move` と同じ形。
- 検証は、純粋関数 `parse_name_width(value) -> int | None`(`config.py`)。次を満たすときだけ通す。
  - 整数または、整数とみなせる有限の数(真偽値・NaN・無限大・文字列は拒否して `None`)。
  - 範囲外は、範囲に収める。
- `None` のときは、何もしない。それ以外は、`self.name_width` を更新し、`actions.set_name_width(width)` を呼ぶ。**再描画はしない**(ブラウザ側の変数が、すでに同じ値)。
- `GanttActions` に `set_name_width: Callable[[int], object]` を足す。

## 保存と復元

- `config.py` に、`load_name_width(base_dir) -> int` と `save_name_width(width, base_dir)` を足す。
  - ファイルや、キー `name_width` がなければ、既定(200)。値が不正(整数でない)なら、既定。範囲外は、範囲に収める。
- **現状の `save_theme` は、ファイル全体を `{"theme": ...}` で上書きする**。幅を足すと、お互いの値を消すので、「読み込んで、そのキーだけを更新して、書く」形に直す(`save_theme` と `save_name_width` で共通の内部関数)。ファイルの読み込みに失敗する(不正な JSON)ときの挙動は、現状(`load_theme` の例外)から変えない。
- `MainView` が、起動時に `load_name_width` で読み、`GanttChart(name_width=...)` に渡す。`set_name_width` のコールバックで、`save_name_width` を呼ぶ。プロジェクトを切り替えても、幅は変わらない。

## プレビューと画像化

- プレビュー(`ViewOptions.read_only`)は、保存した幅で表示する(掴めない)。画像の幅も、同じ幅から決まる(見たままが、保存される)。
- `preview.fit_scale` は、`NAME_WIDTH_PX` の代わりに、引数 `name_width` を受け取る。`MainView` が、`self.gantt.name_width` を渡す。
- 画像化(html-to-image)は、`data-chart-content` の要素を対象にする。`calc(var(--name-w) + ...)` が、複製された要素で、正しく解決されるか(変数は `chart-content` 自身に設定してあるので、解決される見込み)は、実機で確認する。

## テスト

自動テスト:
- `parse_name_width`: 整数・範囲内・範囲外(収める)・真偽値・NaN・無限大・文字列・浮動小数。
- `config`: 幅の読み書き、キーなし・不正値・範囲外、**テーマと幅が互いを消さない**こと、新規のファイル。
- `GanttChart`: `chart-content` の `--name-w`・`data-name-*`、名前の欄の幅、棒の `left` が `calc(var(--name-w) + ...)` であること、`content_width()`、`gantt-name-resizable` が通常のときだけ付くこと(読み取り専用では付かない)。
- `handle_name_width`: 正常・範囲外を収める・不正値を無視・`set_name_width` が呼ばれる・再描画しないこと。
- `marker_left` と期間の右端の判定が、幅に依存しないこと(幅を変えても、境界からの相対位置が同じ)。
- `preview.fit_scale`: 幅を引数にすること。
- 既存テストのうち、名前の幅や位置の文字列(`200`・`220.0px` など)に依存する約 25 か所(`test_gantt.py` 約 23 か所、`test_preview.py` 2 か所)を、変数・`calc` の形に直す。確かめる内容は変えない。
- `Recorder`(`GanttActions` の記録)に、`set_name_width` を足す。

自動テストではできない(NiceGUI の `User` が、ポインタ操作を扱えない)ので、実機で確認する項目:
- 名前の欄の右端で、カーソルが `col-resize` になり、ドラッグで幅が追従すること(棒・格子線・帯・ヘッダーが、一緒に動く)。
- 範囲(120・480)で止まること。ダブルクリックで 200 に戻ること。
- ドラッグしたあと、編集ダイアログが開かないこと。行の移動(drag)が始まらないこと。
- 横スクロール中も、右端の掴み場所が、名前の欄に付いてくること。
- 離したあとと、アプリの再起動後に、幅が保たれること。テーマの設定も保たれること。
- 長い名前が省略表示されること(120px)。チップが隠れないこと。
- プレビューで掴めないこと。幅が反映されること。画像で保存した幅と、見た目が同じこと(ダークテーマを含む)。

## 要望 24(描画の高速化)との整合

- 要素数は増えない(掴み場所は疑似要素)。NiceGUI の内部関数の差し替えも、`title` 属性への置換もしない。
- 幅の変更は、再描画を起こさない(約 400ms の描き直しを、ドラッグのたびに入れない)。

## 変更するファイル

| ファイル | 変更 |
|---|---|
| `config.py` | 幅の定数・`parse_name_width`・`load_name_width`・`save_name_width`。`save_theme` を、読んで更新する形に |
| `gantt.py` | `name_width`・`from_name`・位置の置き換え(18 か所)・`handle_name_width`・`GanttActions.set_name_width`・`gantt-name-resizable`・`chart_name_width` の受け取り |
| `gantt_drag.py` | 疑似要素の CSS と、ドラッグ・ダブルクリックの JS |
| `views.py` | 読み込み・保存・`GanttChart` への受け渡し・`fit_scale` への幅の受け渡し |
| `preview.py` | `fit_scale` が、幅を引数で受け取る |
| `docs/development.md`・`CLAUDE.md` | 仕様の追記(幅の調整・保存先) |
| `test/*` | 上のとおり |
