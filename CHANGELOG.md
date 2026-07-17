# Changelog

本檔記錄 schema 變動、新增來源、與重要架構調整。日期為台灣時間 (UTC+8)。

## 2026-07-07 (排程改為每 3 天)

- 自動更新從每日改為**每 3 天**(cron `0 0 */3 * *`,每月 1、4、7…31 日
  台灣時間 08:00);海事消息時效性不需每日。手動觸發不受影響。
- NEW 徽章窗口配合調整 48→**72 小時**,確保兩次更新之間徽章不會提前消失。

## 2026-07-07 (資訊架構重構:四分頁 + 議題升級)

### 分頁架構
- 五分頁收斂為四分頁,每頁回答一個問題:**BRIEF**(今天看什麼)/
  **追蹤議題**(我追的事進展如何,原 HOT TOPICS + AI RADAR 併入為底部
  「AI 雷達」區塊)/ **全部瀏覽**(找東西,原 CATEGORY 改名)/ **SOURCES**。
  舊 hash `#radar`→`#topics`、`#category`→`#browse` 自動導向。

### Schema 變動
- item 與 summaries 快取新增 **`watch_topics`**:AI 依 topics.json 的議題
  **定義**(非關鍵字)歸入追蹤議題,取代 substring 比對成為主要歸類方式
  (關鍵字保留為 AI 未跑時的 fallback)。cii_ets 從 9 篇雜訊降到 3 篇正中。
- `digest.json` 新增 **`topic_status`**:AI 每日依各議題近期文章寫 2-3 句
  現況,議題卡描述從靜態文字變成活的 mini-brief(無現況時退回靜態)。

### 議題盤點
- 退役 `oil_sampling`、`biofouling`(近 12 個月 0 篇);`cic_2026` 改為
  不綁年度主題的 `psc_cic`「PSC 集中檢查 (CIC)」;`cii_ets` 關鍵字收緊
  (移除裸 mepc/ghg/decarboni 等大網)。

## 2026-07-06 (Obsidian 全歸檔 TechNews)

### 新增
- `scripts/export_obsidian.py`:每篇文章一個 .md(frontmatter + AI 摘要 +
  原文連結)歸檔到 vault repo `wei_obsidian` 的 `marine engineer/TechNews/`,
  只進不出、以 URL 去重(索引 `.archive_index.json`)。已回填現有 116 篇。
- 每日 workflow 加歸檔步驟:sparse clone vault repo → 匯出新文章 → 推回
  (rebase 重試 3 次,與裝置端 obsidian-git 的推送共存)。用 `VAULT_DEPLOY_KEY`
  Secret(限 wei_obsidian 的寫入 deploy key);沒設自動跳過、失敗不擋部署。

## 2026-07-06 (營運面:失敗通知 + NEW 徽章 + 測試)

### Schema 變動
- item 新增 **`first_seen_at`**(第一次被爬到的時間),`BaseCrawler.run()` 自動
  維護:同 URL 重爬保留原時間戳;舊資料(欄位出現前)回退用 `published_at`,
  不會整批閃 NEW。既有 116 篇已回填。

### 新增
- **爬蟲健康檢查** `scripts/check_crawler_health.py`:每日 workflow 最後一步
  (部署後執行,永不擋部署),任一來源失敗就讓 run 變紅並觸發 GitHub 通知信,
  同時在 run summary 輸出各來源狀態表。上線當下即抓到 DNV 自 6/23 起 403 的
  無聲故障。
- **NEW 徽章**:48 小時內新收錄的文章在 BRIEF/SOURCES/HOT TOPICS/CATEGORY/
  議題 brief 頁標綠色 NEW。
- **測試** `tests/`(25 條):BRIEF 排序/時間窗/議題比對/NEW 判定/BaseCrawler
  first_seen 保留與失敗處理 + build_site 煙霧測試;CI 裝完依賴先跑測試,
  失敗不爬取、不部署。`requirements.txt` 加 `pytest`。

## 2026-07-06 (Phase 2 — AI 粗分類 + CATEGORY 分頁)

### Schema 變動
- item 與 `data/summaries.json` 快取新增 **`category`** 欄位,AI 給每篇文章唯一
  粗分類:`regulation` 法規環保 / `fuel` 燃油 / `psc` PSC 檢查 / `machinery`
  輪機設備 / `safety` 安全保安 / `industry` 產業商務。與 `importance` 同一次
  呼叫產出;舊快取由 classify-only 補分類。

### 內容邏輯
- 前端新增 **CATEGORY** 分頁:近 12 個月**所有**文章依分類分組(每篇一類,
  涵蓋固定議題漏接的 58% 內容),組內「須行動」優先、同級依日期。
  未分類文章集中在「未分類」桶,全部分類完成時該桶自動隱藏。
- 議題卡(HOT TOPICS)與分類項目同步顯示「須行動」徽章。

## 2026-07-06 (Phase 2 — 編輯判斷層:重要性分級 + BRIEF 排序邏輯)

### Schema 變動
- item 與 `data/summaries.json` 快取新增 **`importance`** 欄位
  (`action` 須行動 / `notice` 須知悉 / `reference` 參考),由 AI 針對工務監督
  視角評定;`summarize.py` 同一次呼叫產出摘要+分級,舊快取用低成本
  classify-only 呼叫補分級(不重抓原文)。

### 內容邏輯
- **BRIEF 從「最新 10 條」改為「近 60 天的重點」**:排除 `reference`(商務/公關
  噪音)、每來源最多 3 條(防多產來源洗版)、「須行動」優先、同級內依日期排序。
  全部被過濾時退回舊行為,BRIEF 永不空白。
- **議題卡與搜尋索引加 12 個月時間窗**:慢更新來源「最新 20 篇」裡的十年舊文
  不再出現在議題卡/搜尋(貫徹「網站只看最新切片」原則);議題空著=近期沒動靜。
- **AI 選題 prompt 強化**:why 必須引用文章內具體事實(生效日、法規名、數字),
  禁止「愈加重要/構成挑戰」等空話,編號只准出現在 articles 陣列。

### 前端
- BRIEF 與搜尋結果對 `action` 級文章顯示紅色「須行動」徽章(hover 註明 AI 判定)。

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
