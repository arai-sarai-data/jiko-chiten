# 事故が集まる地点

同じ場所で、人身事故がくり返し起きている。警察庁の事故1件ごとの記録から、全国の「事故が集まる地点」を地図にしました。

公開ページ：https://arai-sarai-data.github.io/jiko-chiten/

## 仕組み

- `fetch.py` が公式の公開データを取得・検証・集計し、`docs/data/` に JSON を書き出します。
- GitHub Actions（`.github/workflows/update.yml`）が毎月2日に自動で実行し、GitHub Pages に公開します。
- 元データの形式が想定と違うときは **数字を推測で埋めずに停止** します（前回の正しいデータが表示され続けます）。停止した理由は Actions のログに `データ検証で停止しました` として出ます。

## 最初の設定（1回だけ）

1. このフォルダの中身を `arai-sarai-data/jiko-chiten` リポジトリ（Public）に置く。
2. Settings → Pages → Build and deployment の Source を **GitHub Actions** にする。
3. Settings → Actions → General → Workflow permissions を **Read and write permissions** にする。
4. Actions タブ → `update` → **Run workflow** で初回のデータ取得を実行する。

## 出典

- 警察庁が公開している人身事故1件ごとの記録（緯度経度付き）を、約50m四方のマス目で数え、事故が集中している地点を示します

各データの利用条件に従い、出典を明記して加工・公開しています（`docs/about.html`）。
