# projectapp

メンバーのリソースの管理もできるネイティブアプリ。詳細な機能仕様は [CLAUDE.md](./CLAUDE.md) を参照。

## セットアップ

```bash
uv sync
```

## 起動

```bash
uv run projectapp
```

pywebviewによるネイティブウィンドウが起動する。

## 主な機能


## データの保存先

| ファイル | 内容 |
|---|---|
| `~/.projectapp/project.json` | アイテム・実行記録・カテゴリ |
| `~/.projectapp/config.json` | テーマ・週の開始曜日 |
| `~/.projectapp/holidays.json` | 祝日データのキャッシュ(内閣府CSV。カレンダー画面のボタンで更新) |

## キーボード操作

| キー / 操作 | 機能 |
|---|---|

メインパネル右上のFABからテーマ(自動/ライト/ダーク)を切り替えられる。設定は`~/.projectapp/config.json`に保存され、次回起動時に復元される。右下の「？」ボタンからは、上記キー操作の一覧をいつでも確認できる。

アイテムの実行中は、画面下部に半透明のフローティング表示で「アイテム名」と「残り時間」(見積り未設定の場合は「-」)が表示される。

## 開発

開発者向けの情報(テスト・型チェック・モジュール構成)は [docs/development.md](./docs/development.md) を参照。

## ライセンス

[MIT License](./LICENSE)
