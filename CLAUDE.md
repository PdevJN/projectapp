# PROJECTアプリ開発

プロジェクトのタスクをガントチャートで管理し、メンバーのリソースから完了予定を算出する、NiceGUI 製のデスクトップアプリ。

**このファイルは入口。詳しい仕様は`.claude/spec/`にある。** 作業に関わる話題のファイルだけを読むこと(全部は読まない)。

## 仕様の索引(作業の前に該当するものを読む)

| 話題 | ファイル | 読むとき |
|---|---|---|
| 全体像 | [concept](.claude/spec/concept.md) | 比率・工数・完了予定・割り当て・担当・パラメータ・チーム・稼働日など、計算の考え方 |
| ガントチャート | [gantt](.claude/spec/gantt.md) | タスク・セクション・まとめ・参照・分解・警告・表示・右クリック・選択・一括編集・イベント |
| ダッシュボード | [dashboard](.claude/spec/dashboard.md) | 集計・カード・ビュー・残りの工数と必要人数・全プロジェクト |
| プロジェクトファイル | [project-files](.claude/spec/project-files.md) | 起動・基準日・保存・格納先・外部変更・元に戻す・データの保存先 |
| 取り込み・書き出し | [import-export](.claude/spec/import-export.md) | PlantUML・CSV/TSV・設定ファイル・担当者向けファイル |
| ヘッダーと git | [header-git](.claude/spec/header-git.md) | メニュー・ショートカット・コミット・プッシュ・プル・3 者マージ |
| テーマ | [theme](.claude/spec/theme.md) | テーマ・色・今日の線・画面の倍率・名前欄の幅 |
| 実装の約束 | [implementation](.claude/spec/implementation.md) | ファイル形式のバージョン・構成・描画の方針 |

## 決まりごと(要点)

- 言語は日本語。Python 3.13 以上。ライブラリは [NiceGUI](https://nicegui.io/documentation)
- 起動は`uv run projectapp`(ネイティブウィンドウ。既定)・`--mode web`(ブラウザ。`127.0.0.1`固定。認証なし)。ネイティブ専用の機能(ファイル・フォルダのダイアログ)は、Web では通知で断る
- 描画は NiceGUI の要素と CSS による自前描画(外部のガントライブラリは使わない)
- 日時から位置への変換や日程計算は、NiceGUI から切り離した純粋関数(`timeline.py`)にする
- プロジェクトは、格納先(既定`~/.projectapp`)の`<名前>.json` 1 ファイル。先頭の`version`(現在 19)で形式を管理する。古いファイルは既定値で読み、不正な値は拒否し、新しい`version`は拒否する。保存は一時ファイル経由
- 設定(テーマ・倍率・ダッシュボードのビューなど)は`~/.projectapp/config.json`、祝日は`holidays.json`
- 完了予定は保存しない(手で指定したときの入力値だけ保存し、ほかは表示のたびに算出する)。絞り込み・折りたたみ・プレビューの設定は保存しない
- 用語: 予定超過(完了予定を過ぎた)・期限超過(締切を過ぎた)・**遅れ**(両者の総称。赤)・**警告**(完了予定を過ぎそうな状態。黄)・**割り当て超過**(負荷 100% 超)。`遅延`は赤の意味では使わない

## 仕様と文書の扱い

- 仕様を変える・足すときは、該当する`.claude/spec/`のファイルを更新する(このファイルには詳細を書かない。200 行以内に保つ)
- ファイル形式を変えるときは、`version`を上げ、キーのない古いファイルを既定値で読む
- 設計の経緯は`docs/superpowers/`(その時点の記録で、後の変更は本文に反映しない)、モジュール構成とテストは`docs/development.md`、要望の一覧と実績は`docs/request-history.md`・`docs/requests.md`

## ルール

- 作業のルールは`.claude/RULE.md`、ブランチのルールは`.claude/BRANCH.md`を参照すること
- 実装の完了時: smoke(`uv run pytest -m smoke`)→ 全テスト(`uv run pytest -n auto`)→ `uvx ruff check`・`uvx ruff format src test`→ `uvx ty check src`(詳細は`RULE.md`)
- マージは利用者の指示を待つ(PR を作って止まる)
