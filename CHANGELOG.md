# Changelog

本檔記錄 schema 變動、新增來源、與重要架構調整。日期為台灣時間 (UTC+8)。

## 2026-06-16

### 新增
- 三個 MVP 爬蟲:LR FOBAS、Tokyo MoU、ClassNK Topics,各自實測抓到非空資料。
- `BaseCrawler` 統一介面:HTTP session、議題自動歸類、失敗時保留前一次成功 JSON。
- 靜態網站建置 (`scripts/build_site.py`)：BRIEF / SOURCES / HOT TOPICS 三分頁。
- GitHub Actions 每日排程 (`.github/workflows/daily_update.yml`)，每天 UTC 00:00 跑爬蟲並部署到 gh-pages。

### 變更
- 前端配色由深色「船橋」風改為淺色「日間港口」風 (使用者需求；與 spec §8 的深色指定相反，以使用者實際指示為準)，並調整強調色達 WCAG AA 對比。
- 靜態資源 (CSS/JS) URL 加上版本號 (`?v=<build time>`)，避免瀏覽器快取舊樣式。

### Schema
- 每個來源輸出新增 `last_success_at` 欄位 (前端「最後成功更新」與過舊標紅判斷用)。
- `topics.json` 每個議題新增 `keywords` 欄位 (爬蟲據此自動產生 `topic_ids`)。
- 收斂 `cic_2026` 議題關鍵字，移除過廣的 `psc`，避免所有 PSC 項目被誤歸。
