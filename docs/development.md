# 開発者向けメモ

## モジュール構成

| モジュール | 役割 |
|---|---|
| `main.py` | エントリポイント(NiceGUI + pywebview) |
| `views.py` | メイン画面(ヘッダー・チャート領域・テーマFAB・ヘルプ) |
| `models.py` | Project / Section / Task / Member のデータモデル |
| `storage.py` | `~/.projectapp/<名前>.json` の走査・保存・読込 |
| `config.py` | テーマ設定(`config.json`) |

## コマンド

```bash
uv sync
uv run pytest --cov=projectapp
uvx ty check src
```
