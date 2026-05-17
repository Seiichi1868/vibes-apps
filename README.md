# 音読判定アプリ（Flask）

英語の音読をブラウザで録音し、流暢さスコアを返す Web アプリの土台です。  
現時点の評価ロジックはダミー実装で、後から Whisper や LLM 評価に置き換えやすい構成にしています。

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 起動

```bash
python app.py
```

ブラウザで `http://127.0.0.1:5000` を開いてください。

## 現在の機能

- テキスト入力（読み上げる英文）
- ブラウザ録音（MediaRecorder）
- Flask API への音声アップロード
- 流暢さスコアの返却と表示（ダミーAI）

## 次の拡張ポイント

- Whisper で音声認識し、原文との一致率を算出
- GPT 系モデルで発音/リズム/自然さのコメント生成
- ユーザー別の履歴保存（SQLite + SQLAlchemy）
