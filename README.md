# Daily Trending Report

每天早上 6 点 (北京时间) 自动搜索 **前一天** 美国 TikTok Shop / Amazon / eBay / Google Trends 上
**上升最快的 10 款 20 美金以内小物品** (手环、耳环、小玩具、首饰等),
通过 Gmail 推送报告到你的邮箱, 并自动生成可浏览的 Web 历史报告.

## 实现说明

> ⚠️ **关于"上升最快"指标的说明**

TikTok Shop 和 Amazon 的"上升最快商品"数据基本只通过 **付费第三方 API** 提供
(EchoTik, Jungle Scout, Helium 10 等, 月费几十到几百美金). 本项目采用
**完全免费的多源折中方案**:

| 数据源 | 类型 | 数据 | "上升最快" 近似方式 |
|---|---|---|---|
| **Amazon** | 商品 | 多个细分类目的 Best Sellers 实时榜 | 跨日排名差 |
| **eBay** | 商品 | 公开 Deals 页面的 trending 标签 | 跨日排名差 |
| **TikTok** | 商品 | 公开 discover trending 视频描述里的 $价格 | 跨日排名差 |
| **Google Trends** | 趋势词 | 美国每日 top 20 搜索词 (免费 RSS) | 搜索词排名 (新晋即算"上升") |

效果比付费 API 粗糙, 但能跑起来. 如需更精准的数据, 可考虑接入 EchoTik 等付费 API.

## 项目结构

```
.
├── .github/workflows/
│   ├── daily.yml                   # GitHub Actions 定时 + 部署 Web UI 到 gh-pages
│   └── test.yml                    # CI 跑单元测试
├── src/
│   ├── scraper_amazon.py           # Amazon Best Sellers 爬虫
│   ├── scraper_tiktok.py           # TikTok discover 爬虫
│   ├── scraper_ebay.py             # eBay Deals 爬虫
│   ├── scraper_google_trends.py    # Google Trends RSS 抓取
│   ├── filter.py                   # 关键词/类目/价格过滤器
│   ├── ranker.py                   # 历史快照 + 上升排名计算 + 去重 + 异常检测
│   ├── anomaly.py                  # 趋势异常检测 (HOT/FLASH/STREAK/DROP...)
│   ├── charts.py                   # 极简 SVG 图表 (sparkline / bar / pie / multi-line)
│   ├── llm.py                      # LLM 中文卖点生成 (OpenAI 兼容接口)
│   ├── web.py                      # 静态 Web UI 生成器 (Chart.js 趋势图)
│   ├── exporters.py                # CSV + PDF 导出 (fpdf2 可选)
│   ├── email_sender.py             # Gmail SMTP 发送 HTML 邮件 (支持 CSV/PDF 附件)
│   └── main.py                     # 主入口
├── scripts/
│   ├── run_local.py                # 本地 dry-run (不连发邮件)
│   ├── install.sh / .bat           # 一键安装
├── tests/
│   ├── test_ranker.py              # 18 测试
│   ├── test_email.py               # 12 测试
│   ├── test_filter_and_charts.py   # 18 测试
│   ├── test_charts_full.py         # 19 测试 (bar / pie / multi-line)
│   ├── test_anomaly.py             # 20 测试 (异常检测)
│   ├── test_exporters.py           # 21 测试 (CSV + PDF 导出)
│   └── test_extensions.py          # 15 测试 (Trends, eBay, LLM, Web)
├── data/history.json               # 历史排名快照 (git 跟踪)
├── docs/index.html                 # 生成的 Web UI (部署到 GitHub Pages)
├── Makefile
├── requirements.txt
├── .env.example
└── README.md
```

## 邮件长什么样

每封报告邮件包含 **5 种 SVG 图表 + 6 种异常标签 + 详细列表**, 全部纯 SVG, 邮件客户端直接渲染 (无需联网):

- **顶部统计卡片** — 均价、价格区间、新晋商品数、来源分布
- **💰 价格对比条形图** — Top N 商品价格水平柱状图
- **📊 来源分布饼图** — Amazon / eBay / TikTok / Google Trends 各占多少
- **📈 排名趋势多线图** — Top 8 商品过去 N 天的排名变化曲线 (有历史时)
- **🏆 Top 10 详细列表** — 每行商品可能带以下异常标签 (按 severity 倒序):
  - ⚡ **FLASH** — 一夜爆款 (50+ 名直接冲到前 10)
  - 🔥 **HOT** — 排名飙升 (单日上升 ≥ 30 名)
  - 🚀 **LAUNCH** — 新晋爆款 (首次上榜 + 有价格)
  - 📈 **STREAK** — 连续上升 (连续 3+ 天排名都在上升)
  - 💸 **DROP** — 大幅降价 (比历史最低价低 30%+)
  - 💰 **HIKE** — 大幅涨价
  - 📉 **DOWN** — 排名大跌 (单日下降 ≥ 20 名)
  - 每行右侧 **sparkline** (排名 + 价格迷你折线)
  - 每行下方 **LLM 中文卖点** callout
- **告警机制** — 抓取全部失败 / 过滤后无商品 / 主流程崩溃时, 自动发告警邮件 (高优先级)

## 异常检测规则

`src/anomaly.py` 里集中维护, 阈值常量:

```python
HOT_RISE_THRESHOLD = 30    # 排名上升 ≥ 30 名
BIG_DROP_THRESHOLD = -20   # 排名下降 ≥ 20 名
STREAK_DAYS = 3            # 连续 3+ 天都上升
PRICE_DROP_PCT = 0.30      # 比历史最低价低 30%+
PRICE_HIKE_PCT = 0.30      # 比历史最高价高 30%+
FLASH_FROM = 50, FLASH_TO = 10  # 一夜爆款阈值
```

按需改这些常量, 重新 push 即可. severity 1-3 用于排序, 越大越靠前.

## Web 历史报告

每天跑完后会自动生成 `docs/index.html`, 并通过 GitHub Actions 部署到 GitHub Pages.

启用方法 (在 GitHub 仓库页面):

1. `Settings` → `Pages` → `Build and deployment` → Source 选 **GitHub Actions**
2. 第二次 workflow 跑完就会自动部署, 访问 `https://<用户名>.github.io/<仓库名>/` 即可
3. Web UI 内容:
   - 顶部 4 个统计卡片 (记录数 / 日期范围 / 生成时间)
   - 筛选器: 按来源 / 类目 / 标题关键词过滤
   - 历史商品表格 (按日期倒序)
   - 颜色区分不同来源 (Amazon 黄色, TikTok 粉色, eBay 蓝色, Trends 绿色)

## 自定义过滤

`src/filter.py` 里有 3 个可调的列表/常量:

- `DEFAULT_BLOCK_KEYWORDS` — 黑名单关键词, 命中直接过滤 (默认屏蔽成人/武器/烟酒/医疗/政治/大件等)
- `DEFAULT_FLAG_KEYWORDS` — 灰名单关键词, 命中保留但标题前加 `[!关键词]` 标记 (例如 `vintage`, `replica`)
- `ALLOWED_CATEGORY_HINTS` — 类目白名单片段, 不匹配的类目直接过滤, 防止爬到不相关细类

修改后直接 push 即可, 下次 GitHub Actions 跑就用新规则.

## 配置步骤

### 1. 创建 GitHub 仓库并推送代码

```bash
cd daily-trending-report
git init
git add .
git commit -m "init: daily trending report"
# 在 GitHub 上创建一个新仓库 (建议设为 private), 然后:
git remote add origin git@github.com:<你的用户名>/<仓库名>.git
git branch -M main
git push -u origin main
```

### 2. 配置 Gmail App Password

1. 登录 Gmail 账号, 开启 [两步验证](https://myaccount.google.com/security)
2. 访问 [App Passwords](https://myaccount.google.com/apppasswords)
3. 应用选 "Mail", 设备选 "Other (Custom name)" 输入 `DailyTrending`
4. 点生成, 会得到一个 **16 位密码** (形如 `abcd efgh ijkl mnop`)

### 3. 配置 GitHub Secrets

进入仓库 `Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`,
依次添加:

**必需 (3 个):**

| Secret 名 | 值 |
|---|---|
| `GMAIL_ADDRESS` | 你的 Gmail 地址, 例如 `yourname@gmail.com` |
| `GMAIL_APP_PASSWORD` | 第 2 步得到的 16 位 App Password (空格可保留也可去掉) |
| `RECIPIENT_EMAIL` | 收件邮箱, 可以和发件同一个, 也可以是其他邮箱 (多个用英文逗号分隔) |

**可选 (LLM 卖点增强):**

| Secret 名 | 值 | 说明 |
|---|---|---|
| `LLM_API_KEY` | 你的 LLM API Key | 不填则跳过 LLM 卖点生成, 邮件里不会有蓝色 callout |
| `LLM_BASE_URL` | 默认 `https://api.openai.com/v1` | 想用 DeepSeek / 智谱 / Moonshot 等兼容服务时改这里 |
| `LLM_MODEL` | 默认 `gpt-4o-mini` | 模型名, 例如 `deepseek-chat` / `glm-4-flash` |

> 兼容示例: DeepSeek 填 `https://api.deepseek.com/v1` + `deepseek-chat`; 智谱填 `https://open.bigmodel.cn/api/paas/v4/` + `glm-4-flash`. 报告里会展示 `LLM_API_KEY` 状态日志.

### 4. 手动测试一次

1. 进入仓库的 `Actions` 标签页
2. 左侧选 `Daily Trending Report`
3. 右侧点 `Run workflow` -> `Run workflow`
4. 等 1-3 分钟, 看是否成功并收到邮件
5. 第一次没历史数据, 所有商品会显示为 `NEW` (这是正常的)
6. 也可以勾上 `dry_run = true` 跑一次, 跳过邮件但仍生成历史和 Web UI

### 5. 启用 GitHub Pages (Web UI)

1. 仓库 `Settings` → `Pages` → `Build and deployment`
2. Source 选 **GitHub Actions**
3. 第二次 workflow 跑完就会自动部署
4. 访问 `https://<你的用户名>.github.io/<仓库名>/` 看历史报告

### 6. 第二天验证

- 历史已经在 `data/history.json` 累积, 第二天开始就能看到真实的排名变化
- 之后每天北京时间早上 6 点自动跑 (cron `0 22 * * *` UTC)

## 本地运行 (可选)

### 一键安装 (推荐)

```bash
# Unix/macOS
bash scripts/install.sh

# Windows
scripts\install.bat
```

会自动装依赖 + 跑测试. Windows 用户也可以直接用 `make` (装了 MinGW/Git Bash 的话).

### 手动安装

```bash
# 1. 安装依赖
pip install -r requirements.txt
pip install pytest        # 跑测试用

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 Gmail 凭证, 或者直接 export:

# Unix:
export GMAIL_ADDRESS="yourname@gmail.com"
export GMAIL_APP_PASSWORD="abcdefghijklmnop"
export RECIPIENT_EMAIL="yourname@qq.com"

# Windows PowerShell:
$env:GMAIL_ADDRESS="yourname@gmail.com"
$env:GMAIL_APP_PASSWORD="abcdefghijklmnop"
$env:RECIPIENT_EMAIL="yourname@qq.com"

# 3. 跑 (发邮件)
python -m src.main

# 或者只渲染邮件 HTML 到本地看效果 (不发邮件, 也不需要 Gmail 凭证):
python scripts/run_local.py
# 打开 output/preview.html 看效果
```

### 常用 Makefile 命令

```bash
make help      # 看所有命令
make install   # 装依赖
make test      # 跑测试
make preview   # 渲染邮件 HTML 到 output/preview.html
make run       # 跑抓取 + 发邮件
make clean     # 清理缓存
```

## 常见问题

**Q: 为什么没收到邮件?**
A: 检查 Actions 运行日志. 90% 是 `GMAIL_APP_PASSWORD` 配错了 — 必须用 App Password,
不能用 Gmail 登录密码. 也检查垃圾邮件箱.

**Q: Amazon 抓不到东西 / 数量很少?**
A: Amazon 有反爬, 偶尔会返回空. 隔天重试, 或减少 `scraper_amazon.py` 中
`CATEGORIES` 的类目数, 降低被 ban 风险.

**Q: TikTok 部分经常为空?**
A: 正常. TikTok 的内容主要是 JS 渲染, 纯 requests 抓不全. Amazon 部分
已经能提供主要数据. 想要更好的 TikTok 数据请考虑付费 API (EchoTik 等).

**Q: 想改时间 / 改价格阈值 / 改类目?**
- 时间: 编辑 `.github/workflows/daily.yml` 的 `cron` 字段
- 价格阈值: `scraper_amazon.py` 里 `if price is not None and price > 20.0`
- 类目: `CATEGORIES` / `DISCOVER_CATEGORIES` 字典

**Q: GitHub Actions 免费额度够用吗?**
A: 每天跑 1 次, 每次 < 5 分钟, 月消耗约 150 分钟. 免费额度 2000 分钟/月,
完全够用. 注意开启 `data/history.json` 的 commit 步骤不会消耗额外额度.

**Q: 怎么先看邮件长什么样, 不发邮件?**
A: `python scripts/run_local.py`, 会渲染邮件 HTML 到 `output/preview.html`,
浏览器打开看效果.

**Q: 同一商品在多个类目 (Earrings, Bracelets, Watches) 都出现了怎么办?**
A: 已经自动去重了. `ranker.dedupe_products` 会按 asin/url 去重,
保留排名最高的那个, 并把所有出现过的类目合并显示 (例如 "Bracelets · Earrings").

**Q: 邮件进垃圾箱了怎么办?**
A: 已加了 `List-Unsubscribe` / `Precedence: bulk` / `X-Mailer` 等反垃圾邮件 headers.
如果仍进垃圾箱, 把它从垃圾箱标记为"非垃圾邮件"几次, Gmail 会学习.
也可以在 `src/email_sender.py::send_report` 里调整 subject 的语气 (去掉 emoji 等).

**Q: 怎么屏蔽不想看的类目 (例如成人用品)?**
A: 编辑 `src/filter.py` 里的 `DEFAULT_BLOCK_KEYWORDS` 列表, 加你不想看到的关键词,
push 即可. 也可以扩展 `ALLOWED_CATEGORY_HINTS` 来更严格地控制.

**Q: Web UI 部署到哪儿了?**
A: 通过 GitHub Actions 部署到 GitHub Pages, 路径 `https://<用户名>.github.io/<仓库名>/`.
需要先在仓库 Settings → Pages → Source 选 GitHub Actions.

**Q: LLM 没配 / 配错了会怎样?**
A: 自动静默跳过, 邮件里不会有蓝色卖点 callout, 其他一切照常. 不会有崩溃.

**Q: 想用其他 LLM (DeepSeek / 智谱 / Ollama)?**
A: 设 `LLM_BASE_URL` 为兼容接口地址, `LLM_MODEL` 为对应模型名即可. 项目用 OpenAI Python SDK 的标准 `chat.completions.create` 接口, 任何兼容服务都通.

## CSV / PDF 附件导出

邮件自动附带 **CSV 附件** (每次都有, 零依赖), 可选 **PDF 附件** (需安装 fpdf2).

### CSV 附件
- 文件名: `trending_YYYY-MM-DD.csv`
- 编码: UTF-8 with BOM (Excel 直接打开不乱码)
- 字段: rank, title, price_usd, source, category, rank_change, is_new, url, asin, badges, selling_point
- 用 Excel / Google Sheets 打开后可排序、筛选、做透视表

### PDF 附件 (可选)
- 文件名: `trending_YYYY-MM-DD.pdf`
- 内容: 标题 + 日期 + Top N 商品表格 + 异常标签图例
- 需要安装 fpdf2: `pip install fpdf2`
- 没安装时自动跳过, 邮件里没有 PDF 附件, 其他一切照常

### 安装 fpdf2
```bash
pip install fpdf2          # 单独安装
pip install -r requirements.txt  # 如果已取消注释 fpdf2 行
```

### 本地测试导出
```python
from src.exporters import csv_bytes, export_pdf
from src.ranker import RankedItem

items = [RankedItem(...)]  # 你的商品列表
csv_data = csv_bytes(items, "2026-06-05")
pdf_data = export_pdf(items, "2026-06-05")  # None if fpdf2 not installed
```
