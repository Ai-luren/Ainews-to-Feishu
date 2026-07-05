# 更新日志

本项目所有重要变更记录在此文件中。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)。

---

## [v1.3.0] - 2026-07-06

### 第三轮系统审计修复（3 agent 并行排查）

经过三个独立审计 agent 对全部代码、测试、配置的逐行交叉审计，修复 3 个 P1 + 5 个 P2 + 6 个文档/配置 FAIL，新增 45 个测试。

### P1 修复（边缘情况，影响生产行为）

- **push.py**：aihot backfill 模式不再 fallback 到最新一期，日期不匹配时返回 False（不再假成功掩盖失败）
- **push.py**：builders backfill 日期不匹配时返回 False（与 aihot/juya 行为一致）
- **builders.py**：bio 翻译改用 `_batch_translate` 并发执行（避免串行 10 条 bio × 15s = 150s 超时风险）

### P2 修复（代码质量 / 安全一致性）

- **push.py**：juya 降级告警路径的 link 经 `_safe_url` 校验（防 `javascript:` 协议）
- **aihot_card.py**：section category 经 `_escape_md` 转义（防 lark_md 排版劫持）
- **builders_card.py**：text_zh 比较改用 raw 版本（避免 escape 后的误判导致中文行错误显示/隐藏）
- **lark.py**：webhook 为 None 时防御 TypeError（`str(webhook)[:30]` 替代 `webhook[:30]`）
- **aihot.py**：响应非 dict 时 ValueError 不再被 AttributeError 掩盖（拆分 isinstance 检查）

### 文档 / 配置修复

- **README.md**：auto-routing 描述修正——下午（>= 14:00）保持 `all` 三源都推（去重跳过已推的），不再硬切到 builders
- **README.md**：Mermaid 流程图修正，反映实际的 auto-routing 逻辑
- **SKILL.md**：排障命令中的废弃 URL `imjuya.github.io` 替换为 `daily.juya.uk`
- **requirements.txt**：pytz 2024.2 → 2026.2（时区数据库过期 2 年）

### 新增测试（139 → 184）

| 测试文件 | 测试数 | 覆盖场景 |
|----------|--------|----------|
| `tests/test_aihot_api.py` | 22 | 403/401 抛 RuntimeError、404 有/无日期区分、stream + Content-Length 预检、响应非 dict 抛 ValueError、daily_date/has_content/total_items 纯函数 |
| `tests/test_builders_api.py` | 22 | fetch_feed 非 dict 抛 ValueError、_parse_date 时区转换、has_content、get_top_tweets 排序截断、_batch_translate 并发 + 超时兜底 |
| `tests/test_lark_send.py` | +1 | 响应 JSON 顶层是 list（非 dict）抛 RuntimeError |

---

## [v1.2.0] - 2026-07-05

### 第二轮 P0/P1 系统性修复（3 agent 并行）

三个 agent 并行：修复 push.py、修复 aihot/builders/rss、交叉审计。修复 4 个 P0/P1 + 6 个 P1 + 3 个配置项。

### P0 修复

- **push.py**：all 模式下午（>= 14:00）不再硬切到 builders，改为三源都推（去重跳过已推的，未推的补推）——修复上午 cron 全部失败时下午不再丢 aihot/juya

### P1 修复

- **push.py**：backfill 模式也做日期校验，防 fallback 拉到其他日期内容误推
- **push.py**：entry_date 为 None 时跳过推送，防畸形数据
- **push.py**：backfill 无内容返回 False，不再掩盖失败（退出码 1）
- **aihot.py**：403/401 抛带"不可自动恢复"明确信息的 RuntimeError
- **aihot.py**：stream=True + Content-Length 预检，防大响应 OOM
- **builders.py**：翻译改 ThreadPoolExecutor 并发（max_workers=5 + 120s 超时保护）
- **builders.py**：fetch_feed 返回非 dict 时抛 ValueError
- **rss.py**：校验 Content-Type 含 xml/rss/atom，防 HTML 错误页静默
- **rss.py**：_title_to_date 正则改 re.match 锚定开头
- **lark.py**：data 非 dict 时抛 RuntimeError 而非 AttributeError
- **push.py**：降级文本路径 link 经 `_safe_url` 校验

### 配置修复

- **workflow**：PUSH_MODE 默认值从 `morning` 改为 `all`
- **AGENTS.md**：auto-routing 描述更新
- **card_utils.py**：`_escape_md` 注释修正

### 新增测试（138 → 139）

---

## [v1.1.0] - 2026-07-05

### 第一轮系统性修复 + CDN cache-busting

三个并行审计 agent 发现并修复 5 个 P0 + 7 个 P1 + 2 个 P2，测试从 90 增加到 138。

### P0 修复

- **state.py**：`fcntl.flock` 排他锁防并发 read-modify-write 丢失更新（所有写操作包裹在 `_state_lock` 中）
- **push.py**：`record_entry_date` 移到推送成功后调用（防推送失败时 dead_alert 失效）
- **lark.py**：code 字段默认值从 0 改为 -1（防畸形响应静默通过）
- **aihot.py**：无日期请求 404 视为 API 异常抛错（不再静默返回 None 导致 3 天才告警）
- **push.py**：backfill 也调用 `mark_pushed_today`（防重复 backfill 同一天）

### P1 修复

- **card_utils.py**：`_escape_md` 补全 `*` `` ` `` `>` `~` `_` 转义（防 lark_md 排版劫持）
- **push.py**：backfill 历史日期去重
- **builders.py**：`_parse_date` 转换为北京时间（防日期偏移）
- **builders.py**：`fetch_feed` 添加 `?t={timestamp}` 绕过 GitHub raw CDN 缓存
- **lark.py**：添加飞书 webhook 频率限制重试（code=11232，30 秒等待，最多 2 次）
- **README.md**：cron 表达式统一为 `*/30 8-15 * * *`
- **README.md**：cron-job.org Body 包含 `push_mode=all`

### P2 修复

- **.gitignore**：删除 state.json（已 tracked，注释误导）
- **README.md**：删除不存在的"15:00 GitHub Actions 兜底"描述

### 代码重构

- **card_utils.py**：提取共享 `_s`、`_safe_url`、`_escape_md`、`_truncate` 函数
- **state.py**：`_Source` 类重构，减少 27 个包装函数为 3 个实例 + 别名
- **push.py**：提取 `_handle_failure()` 和 `_handle_dead_alert()` 公共函数
- **builders_card.py**：删除死代码（build_card_payload、parse_entry_to_card）

### 新增测试（90 → 138）

| 测试文件 | 测试数 | 覆盖场景 |
|----------|--------|----------|
| `tests/test_builders_card.py` | 20 | 卡片渲染边界（双语、bio 回退、互动数据、URL 拦截、markdown 注入、截断） |
| `tests/test_aihot_card.py` | 19 | 卡片渲染边界（结构、日期、template、section、快讯、URL 拦截、截断） |
| `tests/test_lark_rate_limit.py` | 3 | 飞书 11232 频率限制重试（成功/耗尽/非 11232） |
| `tests/test_push_routing.py` | 4 | all 模式 13:59/14:00 自动路由边界 |
| `tests/test_push_backfill_dedup.py` | 2 | backfill 历史日期去重 |

### 依赖更新

- requests 2.32.3 → 2.33.0（Dependabot PR #1）
- pytest 8.3.3 → 9.0.3（Dependabot PR #2）

---

## [v1.0.0] - 2026-06-22

### 开源版本

- 重写 README 为开源版本，添加对话式部署引导
- 开源前敏感信息清理
- 添加 CodeQL 安全扫描（push/PR + 每周一定时）
- 启用 Dependabot 安全更新

---

## [v0.4.0] - 2026-06-20

### 最终兜底 + 重试窗口

- juya 降级模式不再标记已推送，允许后续 cron 重试
- 11:00 后仍降级则发带链接的文本兜底（有总比没有好）
- 降级告警一天一次去重
- 修复 juya RSS 解析，支持 feedparser 的 content 字段格式

---

## [v0.3.0] - 2026-06-15

### 双源推送 + cron-job.org

- 双源推送（juya + aihot），各自独立去重/告警
- 主调度改为 cron-job.org，GitHub schedule 保留兜底
- 推送顺序改为 aihot 先、juya 后
- 精简代码，添加 Mermaid 流程图
- 补充 aihot 状态测试 + 端到端模拟测试

---

## [v0.2.0] - 2026-06-15

### 初始版本

- juya AI 早报 RSS 解析 + 飞书卡片推送
- state.json 去重机制
- 失败计数 + 运维告警
