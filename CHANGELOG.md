# Changelog

本檔記錄 schema 變動、新增來源、與重要架構調整。日期為台灣時間 (UTC+8)。

## 2026-06-22 (Phase 2 — AI 選題 / AI RADAR)

### 新增
- `scripts/digest.py`:AI 編輯 —— 讀近期 45 篇文章,歸納出固定 6 議題以外的
  新興重點主題,寫入 `data/digest.json`,每次跑都刷新(像週報)。
  - 嚴格基於提供的文章(編號引用),映射回真實文章、丟掉無效引用(防幻覺)。
- 前端新增 **AI RADAR** 分頁顯示這些主題,標「AI」、附原文連結。
- `daily_update.yml` 加 AI 選題步驟(僅在設 `OPENAI_API_KEY` 時執行,失敗不擋部署)。

## 2026-06-21 (Phase 2 — 再新增 2 來源)

### 新增
- **DNV Technical & Regulatory News** (`crawlers/dnv.py`):讀 DynamicList JSON API
  (`/api/listing/news?blockId=`),blockId 從頁面動態抓取以防改版。
- **BIMCO News** (`crawlers/bimco.py`):列表為 JS 渲染,改從 sitemap 撈 `bimco-news`
  文章(URL 帶日期),逐篇讀 og:title / og:description。
- 共 **8 個來源**啟用。

### 備註
- 旗國技術通函暫緩:各船籍網站普遍難爬(IRI 憑證問題、Liberia 無日期化列表、
  Bahamas 通告無明確日期);待確認船隊實際旗國後再做。

## 2026-06-21 (Phase 2 — 前端搜尋)

### 新增
- 前端純 JS 搜尋:`build_site.py` 產生 `search.json`(全部文章索引),首頁搜尋框即時
  過濾標題/摘要/來源/議題,支援中文(比對 AI 中文摘要)與多詞 AND。Esc 清除。

### 設計
- 確立分工:**網站只追蹤最新內容**;Gard 還原為只抓最新(移除抓取舊文的邏輯)。
  舊/背景文章未來改用 Obsidian 全歸檔保存。

## 2026-06-21 (Phase 2 — 議題 brief 頁 + 維護)

### 新增
- 每個議題產生獨立 brief 頁 `topic-<id>.html`(`templates/topic_brief.html`),
  列出該議題**全部**相關文章與 AI 摘要;HOT TOPICS 卡片新增「查看完整 brief →」連結。

### 維護
- GitHub Actions 升版:`actions/checkout@v4→v5`、`actions/setup-python@v5→v6`
  (改用 Node.js 24,清除淘汰警告)。
- 設定 `OPENAI_API_KEY` repo Secret,雲端每日排程開始自動產生新文章的中文摘要。

## 2026-06-16 (Phase 2 — 新增 3 來源)

### 新增
- **CIMAC WG7 Fuels** (`crawlers/cimac.py`):抓 WG7 燃油指南/FAQ PDF;日期解析自 "(MM/YYYY)";
  尊重頁面 `<base href=".../cms/">` 解析 PDF 連結。
- **Paris MoU** (`crawlers/paris_mou.py`):抓 Press releases 分類 (委員會、CIC、年報、Focused
  Inspection),避開個別船舶 banning 雜訊;序數日期 "2nd of June 2026" 正規化。
- **Gard Insight** (`crawlers/gard.py`):列表為 JS 渲染,改從 `sitemap insights.xml` 取最新文章,
  逐篇讀 JSON-LD (headline / datePublished / description)。
- 三者皆在 `sources.json` 設 `enabled: true` 並註冊進 `run_all_crawlers.py`。

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
