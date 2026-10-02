# 開発者向けメモ

## モジュール構成

| モジュール | 役割 |
|---|---|
| `main.py` | エントリポイント(NiceGUI + pywebview) |
| `views.py` | メイン画面(ヘッダー・チャート領域・テーマFAB・ヘルプ) |
| `calendar.py` | 祝日の取得・キャッシュ(`holidays.json`)と日付種別の判定 |
| `timeline.py` | スケールごとの列生成、日時から位置・幅への変換(純粋関数) |
| `gantt.py` | ガントチャートの描画とスケール切替 |
| `forms.py` | タスク・セクションの追加・編集ダイアログと入力検証 |
| `models.py` | Project / Section / Task / Member のデータモデル |
| `storage.py` | `~/.projectapp/<名前>.json` の走査・保存・読込 |
| `config.py` | テーマ設定(`config.json`) |

## コマンド

```bash
uv sync
uv run pytest --cov=projectapp
uvx ty check src
```
