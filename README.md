# Marine Tech Intel — 海事技術情報終端

給工務部同事共用的海事技術情報彙總網站。自動從多個權威來源抓取最新通告/報告,
以靜態 HTML 呈現,部署在 GitHub Pages。一個地方看到所有更新,取代「每個人各自上 N 個網站翻」。

- **線上網址**(部署完成後)：`https://lu48ver.github.io/marine-tech-intel/`
- **目前來源**：LR FOBAS(燃油)、Tokyo MoU(PSC)、ClassNK Topics(IMO/IACS)、CIMAC WG7(燃油技術)、Paris MoU(PSC)、Gard Insight(P&I)
- **技術**：Python 爬蟲 → JSON → Jinja2 套版 → 純靜態 HTML，無資料庫、無後端、無前端框架。

---

## 目錄結構

```
marine-tech-intel/
├── crawlers/            # 爬蟲程式 (每個來源一支)
│   ├── base.py          # BaseCrawler 抽象類別 + 共用工具
│   ├── lr_fobas.py
│   ├── tokyo_mou.py
│   └── classnk.py
├── data/
│   ├── sources.json     # 來源清冊 (enabled 控制是否啟用)
│   ├── topics.json      # 議題分類 + 自動歸類關鍵字
│   └── updates/         # 各來源抓回的結果 (爬蟲產出)
├── templates/           # Jinja2 模板 (base.html + index.html)
├── static/              # style.css + main.js
├── scripts/
│   ├── run_all_crawlers.py   # 跑所有啟用的爬蟲
│   └── build_site.py         # 讀 JSON + 套模板 → build/
├── build/               # 產出的靜態網站 (gitignore,不進 repo)
└── .github/workflows/daily_update.yml   # 每日自動排程
```

---

## 一、本機怎麼跑

### 前置(只需做一次)

需要 Python 3.10+(開發用 3.10,CI 用 3.11)。在專案根目錄:

```powershell
# Windows PowerShell
python -m pip install -r requirements.txt
```

```bash
# macOS / Linux
python3 -m pip install -r requirements.txt
```

### 每次要更新資料 + 看網站

```powershell
# 1. 跑所有爬蟲 (抓最新資料,寫進 data/updates/)
python scripts/run_all_crawlers.py

# 2. (選用) AI 中文摘要 — 需先設好金鑰,見下方「AI 摘要」一節
python scripts/summarize.py

# 3. (選用) AI 選題 — 歸納近期重點主題 (AI RADAR 分頁),同樣需要金鑰
python scripts/digest.py

# 4. 產出靜態網站到 build/
python scripts/build_site.py

# 5. 本機預覽
python -m http.server 8000 --directory build/
# 瀏覽器開 http://localhost:8000
```

> 第 2、3 步是選用的。沒設金鑰就跳過,網站照樣能建置(少了 AI 摘要與近期主題)。

> 改了 CSS 卻看到舊樣式?那是瀏覽器快取。本專案已對 CSS/JS 加版本號,
> 重新 `build_site.py` 再重整即可;真的卡住就按 **Ctrl + F5** 強制重整。

### 只測單一爬蟲

```powershell
python -m crawlers.lr_fobas      # 或 tokyo_mou / classnk
```

---

## 二、怎麼部署到 GitHub Pages

部署由 GitHub Actions 自動完成。**第一次需要你到 repo 設定頁點兩個地方**:

### 步驟 1：開啟 Actions 寫入權限

1. 到 repo 頁面 → 上方 **Settings**
2. 左側選 **Actions** → **General**
3. 捲到最下面 **Workflow permissions**
4. 選 **Read and write permissions** → 按 **Save**

> 這一步讓自動排程能把抓回的資料 commit 回 main、並推到 gh-pages。

### 步驟 2：先手動觸發一次,產生 gh-pages 分支

1. 到 repo 上方 **Actions** 分頁
2. 左側點 **Daily Update**
3. 右側 **Run workflow** 按鈕 → 再按綠色 **Run workflow**
4. 等它跑完(約 1-2 分鐘,出現綠色勾)

> 這次執行會自動建立 `gh-pages` 分支並把網站放上去。

### 步驟 3：把 Pages 指向 gh-pages 分支

1. **Settings** → 左側 **Pages**
2. **Build and deployment** → **Source** 選 **Deploy from a branch**
3. **Branch** 選 **gh-pages** / **/(root)** → **Save**
4. 等約 1 分鐘,頁面頂端會出現網址:
   `https://lu48ver.github.io/marine-tech-intel/`

完成後,**之後每天台灣時間早上 8:00 會自動更新**,不用再手動做任何事。
要臨時更新就回 **Actions → Daily Update → Run workflow** 手動觸發。

---

## 三、AI 中文摘要 + 重要性分級 (選用)

把抓回來的文章 (尤其 ClassNK / Tokyo MoU 那些只有標題的 PDF) 自動摘要成繁體中文重點,
並同時評定對工務的重要性 (`importance`:須行動/須知悉/參考,供 BRIEF 排序) 與
粗分類 (`category`,供 CATEGORY 分頁瀏覽)。
摘要只根據抓回的原文,抓不到內文就跳過、不會瞎掰;結果快取在 `data/summaries.json`,
同一篇文章只摘要一次,之後每天幾乎零成本。預設模型 `gpt-4o-mini`,50 篇約 US$0.03。

### 本機測試

在專案根目錄建立 `.openai_key`,裡面只放一行 OpenAI 金鑰 (此檔已 gitignore,不會上傳):

```powershell
Set-Content -Path .openai_key -Value "sk-你的金鑰" -NoNewline -Encoding ascii
python scripts/summarize.py --dry-run   # 先看會摘要哪些,不花錢
python scripts/summarize.py             # 實際摘要
```

可用 `--limit 3` 只摘要 3 篇試水溫,或 `OPENAI_MODEL` 環境變數換模型。

### 讓 GitHub 每天自動摘要

把金鑰放進 repo 的加密 Secret (不會出現在程式碼裡):

1. **Settings** → 左側 **Secrets and variables** → **Actions**
2. **New repository secret**
3. **Name** 填 `OPENAI_API_KEY`,**Secret** 貼你的金鑰 → **Add secret**

設好後,每天的自動排程就會在抓完資料後自動產生摘要。**沒設這個 Secret 也沒關係** ——
摘要步驟會自動跳過,網站照常部署,只是沒有 AI 摘要。

> 想停用 AI 摘要:把這個 Secret 刪掉即可。

---

## 四、怎麼新增一個來源

以新增來源 `example` 為例:

### 1. 寫爬蟲 `crawlers/example.py`

繼承 `BaseCrawler`,只需實作 `fetch()`,回傳符合下方 schema 的 items list:

```python
from crawlers.base import BaseCrawler, run_from_cli

class ExampleCrawler(BaseCrawler):
    source_id = "example"
    source_name = "Example Source"
    source_url = "https://example.com/news"

    def fetch(self) -> list[dict]:
        soup = self.get_soup(self.source_url)
        items = []
        for row in soup.select(".news-item"):
            items.append({
                "title": row.select_one("a").get_text(strip=True),
                "url": row.select_one("a")["href"],
                "published_at": "2026-06-16",   # 必須 ISO 格式 YYYY-MM-DD
                "summary": "",
                "tags": ["example"],
            })
        return items

if __name__ == "__main__":
    run_from_cli(ExampleCrawler)
```

`topic_ids` 不用自己填 —— `BaseCrawler` 會用 `topics.json` 的關鍵字自動歸類。

### 2. 在 `data/sources.json` 加一筆

```json
{
  "source_id": "example",
  "source_name": "Example Source",
  "source_url": "https://example.com/news",
  "category": "Tech",
  "update_frequency": "每週",
  "enabled": true,
  "phase": "phase2"
}
```

### 3. 在 `scripts/run_all_crawlers.py` 註冊

```python
from crawlers.example import ExampleCrawler
CRAWLER_CLASSES = {
    ...
    "example": ExampleCrawler,
}
```

### 4. 測試

```powershell
python -m crawlers.example          # 確認抓到非空資料
python scripts/run_all_crawlers.py  # 確認沒影響其他來源
python scripts/build_site.py        # 確認網站能建置
```

> 把 schema 變動或新增來源寫進 `CHANGELOG.md`。

---

## 每個項目的 JSON 格式 (schema)

每支爬蟲輸出到 `data/updates/{source_id}.json`:

```json
{
  "source_id": "lr_fobas",
  "source_name": "LR FOBAS",
  "source_url": "https://www.lr.org/en/knowledge/press-room/",
  "last_crawled_at": "2026-06-16T08:00:00+08:00",
  "last_success_at": "2026-06-16T08:00:00+08:00",
  "crawl_status": "success",
  "items": [
    {
      "title": "文章標題",
      "url": "https://...",
      "published_at": "2026-02-12",
      "summary": "摘要,200 字內",
      "tags": ["fuel", "biofuel"],
      "topic_ids": ["bio_fuel"],
      "summary_zh": "AI 中文摘要 (summarize.py 產生,選用)",
      "importance": "action | notice | reference (AI 重要性分級,選用)",
      "category": "regulation | fuel | psc | machinery | safety | industry (AI 粗分類,選用)"
    }
  ]
}
```

`importance` 是 AI 以工務監督視角評定的重要性:`action` 須行動(新規生效、
PSC/CIC 檢查、須備文件設備)、`notice` 須知悉(技術/法規動態)、`reference`
參考(商務/公關/船員新聞)。BRIEF 依此排序並排除 `reference`;沒跑 AI 摘要時
一律視為 `notice`,網站照常運作。

`category` 是 AI 給每篇文章的唯一粗分類(法規環保/燃油/PSC 檢查/輪機設備/
安全保安/產業商務),供前端 **CATEGORY** 分頁瀏覽 —— 固定議題只涵蓋部分內容,
分類視角則涵蓋近 12 個月的全部文章;未分類的文章會集中在「未分類」桶。

失敗處理:單一爬蟲掛掉不影響其他來源;抓取失敗時保留前一次成功的資料,
`crawl_status` 設為 `error`,前端會在該來源卡片標示「抓取失敗」並顯示資料過舊。

---

## 路線圖

- **MVP(已完成)**：3 個爬蟲 + 靜態網站 + 每日自動部署。
- **Phase 2**:接入 Claude API 自動產生中文重點摘要 → AI 主動補抓漏掉的新聞 →
  議題獨立 brief 頁 → RSS 訂閱 → 前端搜尋。詳見 `files/spec.md` 第 13 節。
