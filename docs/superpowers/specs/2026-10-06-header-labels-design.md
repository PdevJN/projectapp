# ヘッダーのラベルを 1 つの HTML 要素にまとめる 設計書

## 目的

ガントチャートの描画を軽くする。ヘッダーの日付・曜日の行(`label_row`)は、列ごとに `ui.column` と日付の `ui.label`(日次は曜日の `ui.label` も)を作り、1 列あたり 3 要素になる。NiceGUI の要素は、1 個ずつの生成が重く(`Element.__init__` が、`Classes`・`Style`・`Props` の 3 つの監視付きコレクションを作り、それぞれで `inspect.signature` を呼ぶ)、`render` の約 8 割を占める(実測: 42 列で約 135ms のうち約 100ms、429 列で約 230ms)。再描画は、タスクの編集・絞り込み・スケール切替・プレビューでも起きるので、全体に効く。

## 範囲

**含む**: `label_row` を、日付と曜日の行ぜんたいを 1 つの `ui.html` で作る形にする。テストの読み取り方の変更。

**含まない**:
- 年・月の帯(`band_row`)。要素が少ない(帯の数)ので、そのままにする。
- 格子線・縞(すでに `ui.html` 1 つ)。
- タスクの行(1 行あたり約 10 要素)の軽量化。別の機会に、効果を測ってから決める。
- ヘッダーだけを別の `refreshable` に分けること(補完的な案。今回はしない)。

## 決定事項

- 見た目は変えない。行の高さ(`HEADER_HEIGHT_PX` / `ROW_HEIGHT_PX`)、列の幅、中央揃え、`text-caption` の文字の大きさ、固定表示(`header_spacer`)は、そのまま。
- 内容は、定数と日付のみ(`Column.label` と曜日)で、利用者の入力を含まない。`stripes` と同じ前提で `sanitize=False` を使うが、念のため、各行を `html.escape` に通す。
- 1 つの `ui.html` に、列ぶんのセルを並べる。セルは、`data-col="<日付>"` を持つ。日次は、日付の行と曜日の行(`（月）`)の 2 行、週次・月次は日付の行だけ。

```html
<div style="display:flex">
  <div class="text-caption" data-col="2026-10-05"
       style="width:40px;display:flex;flex-direction:column;align-items:center">
    <div>5</div><div>（月）</div>
  </div> ...
</div>
```

- `ui.html` の要素は、`flex: none`(行の中で縮めない)にして、マーカー `label-row-cells` を付ける。左の `header_spacer("label-row-spacer")` は、そのまま。
- 個々のラベルのマーカー `col-<日付>` と `weekday-<日付>` は、なくなる(`label-row-cells` と `data-col` で、同じことを確かめる)。

## テスト

- 補助 `test/header_cells.py`: `header_cells(user)`(日付 → (日付のラベル, 曜日または None))、`should_see_column` / `should_not_see_column`(`should_see` と同じ待ち方)、`settles`(条件が成り立つまで待つ)。
- 既存のテストのうち、`col-<日付>` と `weekday-<日付>` を使う約 20 か所を、補助に置き換える。確かめる内容は変えない(日次の日付と曜日、週次・月次に曜日がないこと、期間の端、月次の見出し、ヘッダーの下罫線、格子線の位置)。
- 追加: ヘッダーの要素の数(`ui.html` 1 つ)、`html.escape`、セルの幅、日次・週次・月次の内容。
- 実機での確認(見た目: 行の高さ・中央揃え・ダークテーマの文字色・スクロールでの固定表示・エクスポートの画像)は、自動テストではできない。

## 期待する効果(実装後に測る)

- `render`: 42 列で約 135ms → 約 40ms、429 列で約 230ms → 約 60ms(推定)。
- 要素数: 429 列で約 1,370 個 → 約 300 個。更新データ(約 200KB)も減る。
- テストの全体の時間: 描画が `test_views.py` の約 4 割なので、その分が短くなる。
