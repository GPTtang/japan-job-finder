# japan-job-finder

[English](#english) | [中文](#中文) | [日本語](#日本語)

---

## English

A job-matching Skill for Claude Code. Describe your background in natural language — the skill fetches jobs from public sources, scores them against your profile, and returns a prioritized match report.

### What's special for Chinese speakers

| Signal | Score bonus |
|--------|-------------|
| Job explicitly seeks Chinese/Mandarin speakers | +0.15 |
| Bridge SE / offshore coordination role | +0.10 |
| Job from a named priority company (`priority_companies.json`) | +0.25 |
| Job from a Chinese IT 乙方 (auto-detected) | +0.20 |
| JLPT requirement exceeds your level | −0.20 |

**25 priority companies** are pre-configured across three groups:
- **Group A** — 6 user-specified Japanese firms with China offices or explicit Chinese-speaker preference (J&C, GlobalAsp, ケネス, 共達, ネットエンジン, 富士ソフト)
- **Group B** — 9 Chinese-owned IT 乙方 Japan subsidiaries (Neusoft, GienTech, ChinaSoft, Beyondsoft, iSoftStone, Rayoo, Wicresoft, 安信, SMHC)
- **Group C** — 10 major Chinese offshore IT firms with Japan operations (YIDATEC, Hundsun, DHC Software, Inspur, UFIDA, HAND, iFlytek, Digital China, Sunline, Thunisoft)

### Install

```bash
git clone https://github.com/GPTtang/japan-job-finder ~/.claude/skills/japan-job-finder
cd ~/.claude/skills/japan-job-finder
pip install -e .
cp config/sources.example.json config/sources.json
```

**Optional: headless browser support** (for JS-rendered / SPA career pages)

```bash
pip install -e ".[browser]"
playwright install chromium
```

Required for `browser_site` provider. Without it the skill falls back to static extraction with a warning.

### Use in Claude Code

Add the skill to your global Claude config:

```bash
echo '\n@~/.claude/skills/japan-job-finder/SKILL.md' >> ~/.claude/CLAUDE.md
```

Then just talk to Claude:

```
Find me backend / AI Engineer jobs in Tokyo.
I have Python, FastAPI, RAG, and 3 years of experience.
My Japanese is N2. I'm a native Chinese speaker.
```

Claude invokes the skill automatically and returns a ranked match report.

### Source config

Edit `config/sources.json` to list the companies and job boards to search.

**Supported providers:**

| Provider | Required field | Description |
|---|---|---|
| `greenhouse` | `token` | Greenhouse ATS API |
| `lever` | `company` | Lever ATS API |
| `ashby` | `board` | Ashby ATS API |
| `company_site` | `url` | Static HTML + JSON-LD extraction |
| `browser_site` | `url` | Headless Playwright — for SPA/React/Vue/Next.js pages |
| `japan_dev` | — | japan-dev.com aggregator |
| `gaijinpot` | — | GaijinPot Jobs aggregator |
| `tokyodev` | — | TokyoDev aggregator |

Use `_`-prefixed keys as human-readable separators — they are silently ignored:

```json
{ "_section": "Priority 1 — Chinese-owned firms", "_label": "Bridge SE specialists" }
```

### Priority companies config

`config/priority_companies.json` controls which companies receive a score boost and how Chinese IT 乙方 are auto-detected. Edit it to add or remove companies:

```json
{
  "_meta": { "priority_boost": 0.25, "chinese_company_boost": 0.20 },
  "named_companies": [
    {
      "id": "my_company",
      "name": "Example株式会社",
      "url_patterns": ["example.co.jp"],
      "name_patterns": ["Example", "例株式会社"]
    }
  ]
}
```

### Project layout

```
job_finder/          core package (skill.py, fetchers, parsers, matcher, formatter…)
config/
  sources.example.json      template — copy to sources.json
  sources.json              your live config (gitignored)
  priority_companies.json   priority boost rules (25 companies)
docs/
  development.md            full technical reference
SKILL.md                    Claude Code skill spec
```

---

## 中文

面向 Claude Code 的求职匹配技能。用自然语言描述你的背景，技能自动抓取公开职位、与简历匹配评分，返回优先级排序的求职报告。

### 中文母语者专属机制

| 信号 | 分数加减 |
|------|---------|
| 职位明确优先招募中文母语者 | +0.15 |
| Bridge SE / 日中离岸协调岗位 | +0.10 |
| 命中 `priority_companies.json` 指定企业 | +0.25 |
| 自动识别为中国系 IT 乙方 | +0.20 |
| 日语要求高于你的当前等级 | −0.20 |

**25 家优先企业**分三组预配置：
- **A组（用户指定6社）** — 有中国拠点或明文中文优遇的日本企业（J&C、グローバルアスピレーションズ、ケネス、共達、ネットエンジン、富士ソフト）
- **B组（中国系乙方日本法人）** — Neusoft、GienTech、中軟東京、Beyondsoft、iSoftStone、Rayoo、Wicresoft、安信、SMHC
- **C组（中国オフショア大手）** — 亿达信息、恒生電子、東華軟件、浪潮、用友、汉得、科大讯飞、神州数碼、长亮科技、华宇软件

### 安装

```bash
git clone https://github.com/GPTtang/japan-job-finder ~/.claude/skills/japan-job-finder
cd ~/.claude/skills/japan-job-finder
pip install -e .
cp config/sources.example.json config/sources.json
```

**可选：无头浏览器支持**（用于 JS 渲染 / SPA 类招聘页）

```bash
pip install -e ".[browser]"
playwright install chromium
```

启用后可使用 `browser_site` provider。未安装时自动降级为静态抓取并给出提示。

### 在 Claude Code 中使用

将技能加入全局 Claude 配置：

```bash
echo '\n@~/.claude/skills/japan-job-finder/SKILL.md' >> ~/.claude/CLAUDE.md
```

之后直接和 Claude 说话即可：

```
帮我在东京找后端 / AI 工程师职位。
我有 Python、FastAPI、RAG 经验，工作经验 3 年。
日语 N2，中文母语，希望华人友好或英语工作环境的公司。
```

Claude 会自动调用技能，返回匹配排名报告。

### 职位源配置

编辑 `config/sources.json`，填入要搜索的公司和招聘平台。

**支持的 provider：**

| Provider | 必填字段 | 说明 |
|---|---|---|
| `greenhouse` | `token` | Greenhouse ATS API |
| `lever` | `company` | Lever ATS API |
| `ashby` | `board` | Ashby ATS API |
| `company_site` | `url` | 静态 HTML + JSON-LD 提取 |
| `browser_site` | `url` | 无头浏览器（Playwright）— 适合 SPA 页面 |
| `japan_dev` | — | japan-dev.com 聚合平台 |
| `gaijinpot` | — | GaijinPot Jobs 聚合平台 |
| `tokyodev` | — | TokyoDev 聚合平台 |

以 `_` 开头的字段作为注释分隔符使用，验证器会自动跳过：

```json
{ "_section": "第一优先 — 中国系乙方", "_label": "Bridge SE 特化" }
```

### 优先企业配置

`config/priority_companies.json` 控制哪些公司加分以及如何自动识别中国系乙方。可以直接编辑添加公司：

```json
{
  "_meta": { "priority_boost": 0.25, "chinese_company_boost": 0.20 },
  "named_companies": [
    {
      "id": "my_company",
      "name": "Example株式会社",
      "url_patterns": ["example.co.jp"],
      "name_patterns": ["Example", "例株式会社"]
    }
  ]
}
```

### 技巧：让 AI 帮你生成 sources 列表

把下面这段提示词发给 Claude：

> 我是有 Python 经验、日语 N2 的后端工程师，中文母语，想在东京找对华人或英语友好的技术岗位（特别是 Bridge SE / 中国系 IT 公司）。请帮我生成 japan-job-finder 技能的 `sources.json`，包含 `gaijinpot`、`tokyodev`、`browser_site`、`company_site` 等 provider，针对 5～8 家合适的公司。

Claude 会直接输出一份针对你背景定制好的 `config/sources.json`，复制粘贴即可使用。

### 项目结构

```
job_finder/          核心包（skill.py、fetchers、parsers、matcher、formatter…）
config/
  sources.example.json      模板 — 复制为 sources.json 后编辑
  sources.json              你的配置（已加入 .gitignore）
  priority_companies.json   优先企业加分规则（25家公司）
docs/
  development.md            完整技术参考文档
SKILL.md                    Claude Code skill 规范
```

---

## 日本語

Claude Code 向けの求人マッチングスキル。自然言語で経歴を伝えると、公開求人を自動取得してプロフィールとマッチングし、優先順位付きのレポートを返します。

### 中国語話者向け加点・減点機能

| シグナル | スコア |
|---------|--------|
| 求人が中国語・中文母語者を明示優遇 | +0.15 |
| Bridge SE / 日中オフショア連携職 | +0.10 |
| `priority_companies.json` の指定企業に合致 | +0.25 |
| 中国系 IT 乙方として自動判定 | +0.20 |
| 日本語要件が候補者レベルを超える | −0.20 |

**25社の優先企業**が3グループに事前設定済み：
- **グループA（ユーザー指定6社）** — 中国拠点あり or 中国語明記優遇の日本企業（J&C、グローバルアスピレーションズ、ケネス、共達、ネットエンジン、富士ソフト）
- **グループB（中国系乙方日本法人）** — Neusoft、GienTech、中軟東京、Beyondsoft、iSoftStone、Rayoo、Wicresoft、安信、SMHC
- **グループC（中国オフショア大手）** — 亿达信息、恒生電子、東華軟件、浪潮、用友、汉得、科大訊飛、神州数碼、长亮科技、华宇软件

### インストール

```bash
git clone https://github.com/GPTtang/japan-job-finder ~/.claude/skills/japan-job-finder
cd ~/.claude/skills/japan-job-finder
pip install -e .
cp config/sources.example.json config/sources.json
```

**オプション：ヘッドレスブラウザサポート**（JS レンダリング / SPA 対応）

```bash
pip install -e ".[browser]"
playwright install chromium
```

`browser_site` プロバイダーに必要です。未インストール時は静的取得にフォールバックします。

### Claude Code での使い方

`SKILL.md` を Claude Code が読めるようグローバル設定に追加：

```bash
echo '\n@~/.claude/skills/japan-job-finder/SKILL.md' >> ~/.claude/CLAUDE.md
```

あとは Claude に話しかけるだけです：

```
東京でバックエンド・AI エンジニアの求人を探してください。
Python・FastAPI・RAG の経験が 3 年あります。
日本語は N2、中国語ネイティブ、英語環境または中国語対応の会社を希望します。
```

Claude がスキルを自動で呼び出し、マッチング結果を返します。

### 求人ソース設定

`config/sources.json` を編集して検索対象の企業や求人プラットフォームを追加します。

**対応 provider：**

| Provider | 必須フィールド | 説明 |
|---|---|---|
| `greenhouse` | `token` | Greenhouse ATS API |
| `lever` | `company` | Lever ATS API |
| `ashby` | `board` | Ashby ATS API |
| `company_site` | `url` | 静的 HTML + JSON-LD 抽出 |
| `browser_site` | `url` | ヘッドレスブラウザ（Playwright）— SPA 向け |
| `japan_dev` | — | japan-dev.com アグリゲーター |
| `gaijinpot` | — | GaijinPot Jobs アグリゲーター |
| `tokyodev` | — | TokyoDev アグリゲーター |

`_` で始まるキーはコメント用セパレーターとして扱われ、自動スキップされます：

```json
{ "_section": "第一優先 — 中国系乙方", "_label": "Bridge SE 特化" }
```

### 優先企業設定

`config/priority_companies.json` で加点対象企業と中国系 IT 乙方の自動判定ルールを管理します。企業の追加・変更はこのファイルを直接編集してください：

```json
{
  "_meta": { "priority_boost": 0.25, "chinese_company_boost": 0.20 },
  "named_companies": [
    {
      "id": "my_company",
      "name": "Example株式会社",
      "url_patterns": ["example.co.jp"],
      "name_patterns": ["Example"]
    }
  ]
}
```

### プロジェクト構成

```
job_finder/          コアパッケージ（skill.py、fetchers、parsers、matcher、formatter…）
config/
  sources.example.json      テンプレート — sources.json にコピーして編集
  sources.json              実運用設定（.gitignore 対象）
  priority_companies.json   優先企業加点ルール（25社）
docs/
  development.md            技術リファレンス
SKILL.md                    Claude Code スキル仕様
```
