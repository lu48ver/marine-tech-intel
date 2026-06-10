# Marine Tech Intel — 專案規格書

## 1. 專案目標

建立一個給工務部同事共用的海事技術情報彙總網站,自動從多個權威來源抓取最新通告/報告/技術文章,以靜態 HTML 呈現,部署在 GitHub Pages。

**使用者**: 海運公司工務部監督、輪機長、輪機員 (3-10 人小團隊)
**核心價值**: 取代「每個人各自上 N 個網站翻」的低效率,一個地方看到所有更新

## 2. 技術選型 (固定,不要更動)

- **爬蟲**: Python 3.11+ / requests / BeautifulSoup4 / lxml
- **PDF 解析**: pdfplumber (備用 pypdf)
- **資料儲存**: JSON 檔 (放在 repo `/data/` 資料夾,不用資料庫)
- **前端**: 純 HTML + CSS + Vanilla JavaScript (不用 React/Vue/框架)
- **建置**: Python 腳本讀 JSON、套 Jinja2 template、輸出靜態 HTML
- **CI/CD**: GitHub Actions cron 排程
- **部署**: GitHub Pages (gh-pages branch)
- **字型**: 用 Google Fonts CDN 載入 (JetBrains Mono / Fraunces / Noto Sans TC)

**不要做的事**:
- 不要架資料庫 (SQLite/Postgres 都不要)
- 不要用前端框架
- 不要做使用者登入系統
- 不要寫複雜的後端 API

## 3. 資料夾結構 (建議,可微調)

```
marine-tech-intel/
├── crawlers/                    # 爬蟲程式
│   ├── __init__.py
│   ├── base.py                  # BaseCrawler 抽象類別
│   ├── lr_fobas.py
│   ├── tokyo_mou.py
│   ├── classnk.py
│   ├── cimac.py
│   └── ... (其他來源)
├── data/                        # 抓回來的資料 (JSON)
│   ├── sources.json             # 來源清冊
│   ├── topics.json              # 議題分類
│   └── updates/                 # 各來源最新通告
│       ├── lr_fobas.json
│       ├── tokyo_mou.json
│       └── ...
├── templates/                   # Jinja2 模板
│   ├── base.html
│   ├── brief.html
│   ├── sources.html
│   └── topic_brief.html
├── static/                      # CSS, JS, 圖片
│   ├── style.css
│   └── main.js
├── build/                       # 產出的靜態網站 (gitignore)
├── scripts/
│   ├── run_all_crawlers.py      # 跑所有爬蟲
│   └── build_site.py            # 用 JSON + template 產出 HTML
├── .github/workflows/
│   └── daily_update.yml         # GitHub Actions 排程
├── requirements.txt
├── README.md
└── CHANGELOG.md
```

## 4. 資料來源清冊 (MVP 階段先做標 ★ 的三個)

| 來源 | 類型 | 更新頻率 | URL | 抓取目標 | MVP |
|---|---|---|---|---|---|
| **LR FOBAS** ★ | 燃油 | 月度 | https://www.lr.org/en/knowledge/press-room/ | 含關鍵字 "FOBAS" 的新聞稿 | ✅ |
| **Tokyo MoU** ★ | PSC | 滾動 | https://www.tokyo-mou.org/publications/ | Press Releases / Safety Bulletin / CIC Results | ✅ |
| **ClassNK Topics** ★ | Class | 每月 | https://www.classnk.com/hp/en/info_service/imo_and_iacs/index.html | IMO/IACS 相關通告 | ✅ |
| CIMAC WG7 | Tech | 季度 | https://www.cimac.com/working-groups/wg7-fuels/index.html | Latest Publications | Phase 2 |
| Paris MoU | PSC | 滾動 | https://parismou.org/inspections-risk/library-faq/cic | CIC 公告 | Phase 2 |
| Gard Insight | P&I | 每月 | https://www.gard.no/ | 文章 | Phase 2 |
| IMO MEPC/MSC | IMO | 每次會議 | https://www.imo.org/ | (用 ClassNK 整理替代) | 跳過 |

## 5. 每個爬蟲必須輸出的 JSON 格式 (Schema)

每個爬蟲跑完,輸出到 `data/updates/{source_id}.json`,格式統一為:

```json
{
  "source_id": "lr_fobas",
  "source_name": "LR FOBAS",
  "source_url": "https://www.lr.org/en/knowledge/press-room/",
  "last_crawled_at": "2026-05-13T14:30:00+08:00",
  "crawl_status": "success",
  "items": [
    {
      "title": "FOBAS H2 2025 Fuel Quality Report",
      "url": "https://www.lr.org/en/knowledge/press-room/press-listing/press-release/2026/...",
      "published_at": "2026-02-12",
      "summary": "報告摘要,中英都可,優先英文原文摘要 200 字內",
      "tags": ["fuel", "bunker", "biofuel"],
      "topic_ids": ["bio_fuel", "fuel_quality"]
    }
  ]
}
```

**重要規則**:
- `published_at` 用 ISO 8601 (`YYYY-MM-DD`)
- `tags` 是該文章的關鍵字 (自由)
- `topic_ids` 對應 `data/topics.json` 中定義的議題,讓前端可以反向索引
- 若抓不到,`crawl_status` 設為 `error` 並加 `error_message` 欄

## 6. 議題分類 (data/topics.json)

預設 6 個議題,每個議題對應前端「Hot Topics」分頁的展開卡片:

```json
[
  { "id": "bio_fuel", "name": "BIO FUEL Bunkering", "priority": "high", "summary": "..." },
  { "id": "cic_2026", "name": "PSC CIC 2026 — Cargo Securing", "priority": "high", "summary": "..." },
  { "id": "oil_sampling", "name": "Oil Sampling Point", "priority": "watch", "summary": "..." },
  { "id": "biofouling", "name": "Biofouling Management Plan", "priority": "watch", "summary": "..." },
  { "id": "gas_detector", "name": "Gas Detector Requirement", "priority": "watch", "summary": "..." },
  { "id": "cii_ets", "name": "CII / SEEMP / Net-Zero Framework", "priority": "reg", "summary": "..." }
]
```

## 7. BaseCrawler 設計 (crawlers/base.py)

所有爬蟲都繼承此類別,確保介面統一:

```python
from abc import ABC, abstractmethod
from datetime import datetime
import json

class BaseCrawler(ABC):
    source_id: str
    source_name: str
    source_url: str

    @abstractmethod
    def fetch(self) -> list[dict]:
        """回傳 items list,格式如 spec.md 第 5 節"""
        pass

    def run(self) -> dict:
        """執行爬蟲、組裝最終 JSON、寫檔"""
        try:
            items = self.fetch()
            result = {
                "source_id": self.source_id,
                "source_name": self.source_name,
                "source_url": self.source_url,
                "last_crawled_at": datetime.now().isoformat(),
                "crawl_status": "success",
                "items": items
            }
        except Exception as e:
            result = {
                "source_id": self.source_id,
                "crawl_status": "error",
                "error_message": str(e),
                "last_crawled_at": datetime.now().isoformat()
            }
        # 寫到 data/updates/{source_id}.json
        ...
        return result
```

## 8. 前端設計需求

**視覺風格**: 深色背景的「海事技術終端」風格,類似船橋儀表板的感覺。
**色票** (CSS 變數):
- `--bg-0: #0a0e0c` (主背景)
- `--bg-1: #111714` (卡片背景)
- `--accent: #7fd1a8` (強調綠 — 航海綠)
- `--warn: #e8a04a` (警示橘)
- `--crit: #e85a3c` (嚴重紅)
- `--info: #6fb8d4` (資訊藍)

**字型**:
- 中文內文: Noto Sans TC
- 英文標題: Fraunces (襯線)
- 程式碼/數據: JetBrains Mono

**頁面結構** (最小可用版本):
1. **BRIEF** — 首頁,顯示最近 10 條跨來源更新 (依日期排序)
2. **SOURCES** — 所有來源清冊,每個來源顯示最近 5 條
3. **HOT TOPICS** — 可展開的議題卡片,每個議題顯示對應的最新文章

**互動需求**:
- Tabs 切換 (純 JS,不需路由)
- Topic 卡片可展開/收合
- 每個項目的連結都用 `target="_blank" rel="noopener"`

## 9. 自動化流程

### 本機測試流程
```bash
# 1. 跑單一爬蟲測試
python -m crawlers.lr_fobas

# 2. 跑所有爬蟲
python scripts/run_all_crawlers.py

# 3. 產出靜態網站
python scripts/build_site.py

# 4. 本機預覽
python -m http.server 8000 --directory build/
```

### GitHub Actions (.github/workflows/daily_update.yml)
- 觸發: `cron: '0 0 * * *'` (每日 UTC 00:00 = 台灣早上 8:00)
- 也支援手動觸發 `workflow_dispatch`
- 步驟:
  1. checkout code
  2. setup python 3.11
  3. install requirements
  4. run crawlers
  5. build site
  6. commit data/ 變動回 main branch
  7. push build/ 內容到 gh-pages branch

## 10. 失敗處理原則

- **單一爬蟲掛掉不能整個流程掛掉** — 用 try/except 包住每個爬蟲
- **資料保留** — 若新爬取失敗,保留前一次成功的 JSON 不要覆蓋
- **錯誤可見** — 前端要顯示「某來源最後更新時間」,過舊就標紅
- **CHANGELOG** — 每次有 schema 變動或新增爬蟲,寫進 `CHANGELOG.md`

## 11. 程式風格規範

- Python: 遵循 PEP 8,函式有 type hints
- 程式碼註解用英文,使用者面對的字串用繁體中文
- 每個爬蟲檔案 < 200 行,複雜的解析邏輯抽出來
- 不要用 print 除錯,用 logging
- requirements.txt 鎖版本 (`requests==2.31.0` 而不是 `requests>=2.31`)

## 12. MVP 完成定義 (Definition of Done)

打勾代表完成:
- [ ] 3 個 MVP 爬蟲都能在本機跑出非空 JSON
- [ ] `python scripts/build_site.py` 能產出 `build/index.html`
- [ ] 本機 `python -m http.server` 開啟看到完整網站
- [ ] GitHub Actions workflow 至少手動觸發過一次成功
- [ ] GitHub Pages 已部署、有可公開瀏覽的 URL
- [ ] README.md 有完整本機跑/部署/新增來源指引
- [ ] 任一爬蟲掛掉時,其他來源仍能正常顯示

## 13. Phase 2 路線 (MVP 完成後)

- 加 4 個次要來源 (CIMAC、Paris MoU、Gard、IMO 透過 ClassNK)
- 加每個熱門議題的獨立 brief 頁面 (像 oil_sampling_point_brief.html)
- 加 RSS 輸出 (`/feed.xml`),讓同事可以用 RSS reader 訂閱
- 加搜尋功能 (純前端,讀全部 JSON 做 fuzzy search)
- 接入 LLM,把抓回來的文章自動摘要成中文
