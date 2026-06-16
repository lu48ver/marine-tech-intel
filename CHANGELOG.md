# Changelog

本檔記錄 schema 變動、新增來源、與重要架構調整。日期為台灣時間 (UTC+8)。

## 2026-06-16 (Phase 2 — AI 摘要)

### 新增
- `scripts/summarize.py`:用 OpenAI (預設 `gpt-4o-mini`) 把抓回的文章摘要成繁體中文重點。
  - 依 content-type / 檔頭判斷 PDF 或 HTML 抓取原文 (Tokyo MoU 部分公告是 PDF 但網址非 .pdf)。
  - 嚴格基於原文,抓不到內文則跳過,不從標題瞎掰 (防幻覺)。
  - 摘要快取於 `data/summaries.json` (以 URL 為 key),同一篇只摘要一次。
  - 金鑰來源:環境變數 `OPENAI_API_KEY` 或本機 `.openai_key` 檔 (兩者皆不進 repo)。
- 前端 BRIEF 與議題展開處顯示 AI 摘要,並加「AI」標記區隔機器產生內容。
- `daily_update.yml` 新增摘要步驟 (僅在設定 `OPENAI_API_KEY` Secret 時執行,失敗不擋部署)。

### Schema
- 每個 item 新增選用欄位 `summary_zh` (AI 產生的中文摘要)。

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
