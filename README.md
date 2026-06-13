# 橘鸦 AI 早报自动推送系统

## 项目简介

每天自动从 [juya AI 早报 RSS](https://daily.juya.uk/rss.xml) 抓取最新资讯，
解析为飞书富文本卡片并推送到指定 Feishu 群组。
**唯一调度器**：GitHub Actions `schedule`（北京时间 09:00 / 09:30 / 10:00 / 10:30）。
防重复：当天一旦推送成功，后续 cron 会直接 `[skip]`，飞书群一天只收到一张卡片。

## 架构（2026-06-14 起）

```
GitHub Actions schedule
  cron: '0,30 1,2 * * *'  # UTC 01:00/01:30/02:00/02:30 → 北京 09:00/09:30/10:00/10:30
              ↓
       push.py（GitHub 云上执行）
              ↓
  ┌──────────────────────────────┐
  │ 1. is_pushed_today 去重检查  │
  │    last_pushed_date == 今天 → [skip]
  │ 2. fetch_rss() 拉 juya feed  │
  │ 3. parse_entry_to_card() 生成卡片 │
  │ 4. 推送到 Feishu webhook     │
  │ 5. state.json 记录今天已推送  │
  └──────────────────────────────┘
              ↓
           Feishu 群组
```

> **说明**：之前的 `cron-job.org` 外部调度已删除，现在完全由 GitHub Actions 自己的 schedule 驱动。无需任何外部服务依赖。

系统由三个核心文件组成：

1. **RSS 抓取** ([`rss.py`](./rss.py)) — 从 juya 官网获取 RSS feed，解析出当天的条目；旧的 `imjuya.github.io` 已废弃，自动回退到 `https://daily.juya.uk/rss.xml`
2. **卡片生成** ([`lark_card.py`](./lark_card.py)) — 将条目 HTML 解析为 Feishu 富文本卡片，按分类输出
3. **主流程** ([`push.py`](./push.py)) — 去重检查 → 拉取 → 解析 → 推送 → 更新 state；连续失败 3 次发送运维告警

`push.py` 核心逻辑：
- 检查 `state.json` 中 `last_pushed_date`，今天已推过则 `[skip]`
- 抓取 RSS，查找今天条目（按 published 日期匹配，回退到标题日期）
- 解析为卡片并推送
- 连续失败 3 次 → 发送 ⚠️ 运维告警到飞书群
- juya 连续 3 天未更新 → 发送 ⚠️ 停更近告（已内置静默天数判断，避免误报）
- 成功/失败都更新 `state.json`

## 账号与配置清单

换公司 / 换电脑时，对照这张表找回所有配置。**只记位置，不记值。**

| 配置项 | 存在哪里 | 备注 |
|---|---|---|
| 飞书 webhook URL + secret | GitHub Secrets（仓库 → Settings → Secrets）+ 密码管理器 | 4 个：`LARK_WEBHOOK_URL/SECRET` / `LARK_OPS_WEBHOOK_URL/SECRET` |
| RSS 源地址 | GitHub Variable（仓库 → Settings → Variables） | 键名 `RSS_URL`，**建议留空**，让代码用默认源 `https://daily.juya.uk/rss.xml`；当旧的 `imjuya.github.io` 被配置时会自动回退 |
| GitHub 登录账号 | 你的邮箱 + 密码管理器 | 用于登录 GitHub 查看 Actions 日志 |

**密码管理器里要保存的**（值本身不进代码或 README）：
- 飞书 webhook URL + secret（4 个值）

## 部署步骤

> **已经 clone 了这个仓库？**
> 直接跑一键脚本：
> ```bash
> bash scripts/setup.sh
> ```
> 脚本会交互式问你"GitHub 账户、仓库名、飞书 webhook URL、signature secret"，然后自动建仓库、设 4 个 Secrets、触发首次 workflow 验证。
> **webhook/secret 不回显、不进 shell 历史、不进日志。**
> 如果是首次部署，继续看下面 3 步手动版。

### 第 1 步：在 Feishu 获取 webhook URL 和 signature secret

1. 打开 Feishu 桌面版或网页版
2. 进入目标群组（推送目标）
3. 点击右上角「⋮」→「群组机器人」
4. 点击「添加机器人」→「自定义机器人」
5. 填写机器人名称（如「AI 早报」）
6. **非常重要**：勾选「签名校验」，复制生成的 **Signature Secret**
7. 点击「完成」，复制 **Webhook URL**（格式：`https://open.larksuite.com/open-apis/bot/v2/hook/...`）

### 第 2 步：设置 GitHub Secrets

在你的 GitHub 仓库 → Settings → Secrets and variables → Actions 中，添加以下 4 个 secrets：

```bash
# 如果在本地有 gh CLI，可用命令行设置（推荐复制粘贴）：
gh secret set LARK_WEBHOOK_URL        # 粘贴上面复制的 Webhook URL
gh secret set LARK_WEBHOOK_SECRET     # 粘贴上面复制的 Signature Secret
gh secret set LARK_OPS_WEBHOOK_URL    # 粘贴同样的 Webhook URL（运维告警）
gh secret set LARK_OPS_WEBHOOK_SECRET # 粘贴同样的 Signature Secret
```

**关键说明**：
- 当前设计是**单一群组模式** — `LARK_OPS_*` 和 `LARK_*` 使用相同的值
- 早报推送和运维告警都发到同一个群
- 如果将来想分成两个群，只需改 `LARK_OPS_WEBHOOK_URL` 和 `LARK_OPS_WEBHOOK_SECRET` 为另一个群的值，**无需改代码**

### 第 3 步：触发工作流验证

推送代码到 GitHub：

```bash
git push origin master
```

然后手动触发一次工作流验证部署：

```bash
gh workflow run daily-ai-news.yml
```

或在 GitHub 网页版进入 Actions 标签，选 `daily-ai-news-push` 工作流，点「Run workflow」→「Run workflow」。
等待运行完成，检查群组是否收到早报。

## 运行时行为

| 情形 | 行为 |
|------|------|
| **已推送过今天** | 检查到 `state.json` 中 `last_pushed_date == 今天`，直接 `[skip]`（不推送、不报错） |
| **juya 还未更新** | 抓取 RSS，发现没有今天的条目，`[skip] juya not updated`，等待下一个 cron 时段 |
| **正常推送** | 解析条目为卡片，推送到群组，`state.json` 记录 `last_pushed_date` 和清零 `consecutive_failures` |
| **卡片解析降级** | 内容解析失败（卡片无文本内容），改为推送纯文本 + 原文链接，同时发送 ⚠️ 告警 |
| **推送失败（单次）** | `consecutive_failures` 加 1，等待下一个时段重试 |
| **推送失败（连续 3 次）** | 发送 ⚠️ 告警到群组，包含错误信息和 GitHub Actions run 链接，清零失败计数 |
| **juya 连续 3 天未更新** | 发送 ⚠️ 停更近告到群组（避免静默失联），仅在首次命中时发送一次 |

## 运维

### 换群

如果要改为推送到另一个群组：

```bash
# 获取新群组的 Webhook URL 和 Signature Secret，然后：
gh secret set LARK_WEBHOOK_URL --body "新的 URL"
gh secret set LARK_WEBHOOK_SECRET --body "新的 Secret"

# 如果这个新群组也要收运维告警：
gh secret set LARK_OPS_WEBHOOK_URL --body "新的 URL"
gh secret set LARK_OPS_WEBHOOK_SECRET --body "新的 Secret"
```

### 改推送时间

编辑 `.github/workflows/daily-ai-news.yml` 中的 cron 表达式：

```yaml
schedule:
  - cron: '0,30 1,2 * * *'  # <-- 这一行
```

Cron 格式：`分钟 小时 天 月 星期`（**UTC 时间**，不是北京时间）。

**时区转换提示**：
- UTC 时间 = 北京时间 - 8 小时
- 例如要改成北京时间 10:00 / 11:00：
  - 北京时间 10:00 = UTC 02:00 → cron 写 `0 2`
  - 北京时间 11:00 = UTC 03:00 → cron 写 `0 3`
- 当前配置 `'0,30 1,2 * * *'` = UTC 01:00/01:30/02:00/02:30 = 北京 09:00/09:30/10:00/10:30

修改后 push 到 GitHub，新的时间表会立即生效。

### 看日志

GitHub 仓库 → Actions 标签 → 选择 `daily-ai-news-push` 工作流 → 点击想看的 run → 展开 `push.py` 步骤，查看 stdout 输出。

关键日志：
- `[skip] already pushed today (YYYY-MM-DD)` — 今天已推过
- `[skip] juya not updated for YYYY-MM-DD` — RSS 还没有今天的条目
- `[ok] pushed YYYY-MM-DD` — 成功推送
- `[fail] push attempt failed (n/3)` — 推送失败，等待重试

### 手动触发

想立即测试或补推，用以下任一方式：

```bash
# 命令行（需要 gh CLI）：
gh workflow run daily-ai-news.yml

# 或在 GitHub 网页版：
Actions → daily-ai-news-push → Run workflow → Run workflow
```

想补发指定日期（比如昨天漏了）：
- GitHub 网页版「Run workflow」时，**可选**输入目标日期 `YYYY-MM-DD`（例如 `2026-06-13`），留空 = 今天
- 或命令行：`gh workflow run daily-ai-news.yml -f target_date=2026-06-13`

等待完成后检查群组。

### 分成两个群组

如果要把**早报推送**和**运维告警**分到两个群组：

1. 在 Feishu 创建（或选择）第二个群，添加自定义机器人，获取其 webhook URL 和 secret
2. 更新 GitHub Secrets：

```bash
# 第一个群用于早报推送
gh secret set LARK_WEBHOOK_URL --body "群 1 的 URL"
gh secret set LARK_WEBHOOK_SECRET --body "群 1 的 Secret"

# 第二个群用于运维告警
gh secret set LARK_OPS_WEBHOOK_URL --body "群 2 的 URL"
gh secret set LARK_OPS_WEBHOOK_SECRET --body "群 2 的 Secret"
```

**无需修改任何代码** — `push.py` 会自动把警告发送到 `LARK_OPS_*`，把早报发送到 `LARK_*`。

### 停止推送（暂停系统）

**不想继续收到早报时**，有三种深度：

**A. 临时暂停（保留所有配置，随时可恢复）**

在仓库里关掉 workflow：
```bash
gh workflow disable daily-ai-news.yml
```
或网页操作：仓库 → Actions → 左侧选中 `daily-ai-news-push` → 右上 `···` → Disable workflow。

Cron 从此不再触发，定时推送立刻停止。其他一切不动（代码、Secrets、飞书机器人、state.json）。

**B. 彻底下线（保留历史但完全停用）**

1. `gh workflow disable daily-ai-news.yml` — 关掉定时
2. 去飞书群设置里**删除那个自定义机器人** — webhook 从此无效，即使有人误触发 workflow 也推不出东西
3. `gh secret delete LARK_WEBHOOK_URL` + 其余 3 个 — 把密钥从 GitHub 移除
4. 仓库保留，作为"我曾经做过这件事"的存档

**C. 物理删除**（最彻底，不可恢复）

1. 执行上面 B 的 1、2 步
2. `gh repo delete <YOUR_USERNAME>/design-team-ai-daily --yes` — 删仓库（包括所有 commit 历史、state.json、workflow 日志）
3. 从本地删掉 `~/design-team-ai-daily`

**⚠️ 注意**：C 方案是**不可撤销**的。如果只是暂时不想推，用 A；如果想留档但不用了，用 B。

### 恢复推送

如果之前是 A 方案（disable）：
```bash
gh workflow enable daily-ai-news.yml
```
次日 09:00 自动恢复。

如果是 B 方案（机器人已删、Secret 已删）：重走 README "部署步骤" 第 1-3 步（建新机器人、设 Secrets、手动触发验证）。

如果是 C 方案：无法恢复。从头做一个新项目。

### 换个内容源（比如做第二个日报）

如果想 fork 这个仓库做一个**不同内容源 / 不同目标群**的日报，改 3 处即可：

1. **`rss.py`** — 把 `_RSS_URL_DEFAULT` 换成新数据源
2. **`lark_card.py`** — 改 2 样：
   - `CATEGORY_HEADER_TEMPLATE`：如果新数据源有自己的分类名，更新分类 → 颜色映射
   - `_extract_overview_groups()`：如果新数据源的 HTML 结构不同，改这个解析函数
   - `parse_entry_to_card()` 里的卡片标题 `"🤖 橘鸦 AI 早报"`
3. **`.github/workflows/daily-ai-news.yml`**（可选）—— 如果新数据源更新时间不同，改 cron（注意 UTC！北京时间减 8 小时）

改完后跑 `pytest -v` 看是否全绿（当前 72 个测试，可能要更新 fixture），然后 `bash scripts/setup.sh` 一键部署到新仓库新群。

### 跨电脑部署（换新 Mac）

推送系统跑在 GitHub 云端，和本地电脑**完全无关**——换电脑不影响推送。
但如果你想在新电脑上继续运维，只需：

```bash
# 1. 装 GitHub CLI 并登录
brew install gh && gh auth login

# 2. 克隆项目
git clone https://github.com/<YOUR_USERNAME>/design-team-ai-daily.git
```

完成。想改配置直接在 GitHub 网页上改，或者 clone 到本地编辑后 push。

## 早报没到怎么办

### 自诊步骤

1. **检查 Actions 是否运行**
   - 打开 GitHub 仓库 → Actions 标签
   - 看 `daily-ai-news-push` 最新 run 是否有绿色对勾
   - 如果有红 X，点进去看 `push.py` 的错误日志

2. **检查 juya 源是否更新**
   - 打开 RSS URL：https://daily.juya.uk/rss.xml
   - 搜索今天日期，看是否有条目
   - 如果没有，说明 juya 官网还没发布今天的早报，等下一个 cron 即可（系统每 30 分钟会重试一次）

3. **手动触发一次**
   - 运行 `gh workflow run daily-ai-news.yml`
   - 等待完成，实时查看日志

4. **检查推送历史**
   - 打开 GitHub 仓库，查看 `state.json` 的 commit 历史
   - 看 `last_pushed_date` 是哪天
   - 如果 `last_pushed_date` 是今天，说明系统认为今天已推过（可能在更早的 cron 已经推成功了）

5. **如果还是不行**
   - 检查 Secrets 是否正确：GitHub Settings → Secrets → 确认 4 个 webhook/secret 值存在且不为空
   - 检查 Feishu 群组是否收到任何告警消息（可能是解析失败或连续推送失败）

### 本地测试

如果怀疑代码有问题，可在本地运行：

```bash
# 进入项目目录
cd /path/to/design-team-ai-daily

# 创建虚拟环境（首次）
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 运行测试（验证逻辑）
pytest -v

# 本地运行 push.py（需设置环境变量）
export LARK_WEBHOOK_URL="你的 webhook URL"
export LARK_WEBHOOK_SECRET="你的 secret"
export LARK_OPS_WEBHOOK_URL="同上"
export LARK_OPS_WEBHOOK_SECRET="同上"
python push.py
```

## 开发

### 项目结构

```
.
├── push.py                      # 主推送逻辑（去重 + 拉取 + 推送 + 告警）
├── lark.py                      # Feishu webhook 通信（签名 + POST）
├── lark_card.py                 # 富文本卡片生成（分类解析 + 卡片渲染）
├── rss.py                       # RSS 抓取和解析（带废弃 URL 自动回退）
├── state.py                     # 状态管理（原子写入 + last_pushed_date / 失败计数 / juya 静默天数）
├── state.json                   # 运行时状态（由 workflow 自动提交）
├── requirements.txt             # Python 依赖
├── .github/workflows/
│   └── daily-ai-news.yml        # GitHub Actions 定时任务配置（唯一调度器）
└── tests/                       # 单元测试（当前 72 个测试，全绿为预期状态）
    ├── fixtures/
    │   └── juya_sample.xml      # 测试用样例 RSS
    ├── test_lark_card.py        # 卡片生成
    ├── test_lark_send.py        # Lark 发送
    ├── test_lark_sign.py        # Lark 签名
    ├── test_push.py             # 主流程
    ├── test_push_check_env.py   # 环境变量检查
    ├── test_rss.py              # RSS 解析
    ├── test_rss_fetch.py        # RSS 抓取
    ├── test_send_lark_card.py   # 卡片发送
    ├── test_send_lark_text.py   # 文本发送
    ├── test_state.py            # 状态读写
    └── test_state_load.py       # state.json 加载
```

### 本地开发和测试

```bash
# 安装依赖
pip install -r requirements.txt

# 运行单元测试
pytest -v

# 运行特定测试
pytest tests/test_push.py -v
```

测试框架用的是 `pytest`，HTTP 请求 mock 是 `responses`。

### 常见改动

- **改推送时间**：编辑 `.github/workflows/daily-ai-news.yml` 的 cron
- **改卡片格式**：编辑 `lark_card.py` 中的 `parse_entry_to_card()` 函数
- **改告警逻辑**：编辑 `push.py` 中的失败处理和告警发送
- **改 RSS 来源**：
  - 临时替换：`gh variable set RSS_URL --body "新地址" -R <YOUR_USERNAME>/design-team-ai-daily`，无需改代码
  - 永久替换：编辑 `rss.py` 中的 `_RSS_URL_DEFAULT`

改完后建议本地 `pytest -v` 验证，然后 push 到 GitHub，GitHub Actions 会自动运行测试。
