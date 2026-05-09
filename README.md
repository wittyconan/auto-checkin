# 速云自动签到脚本

速云自动签到，支持 GitHub Actions 每日自动执行，支持 Telegram 机器人通知。
网址：（包含AFF）
https://www.svyun.com/recommend/Abetl6uiQauK

## 支持网站

| 网站 | 功能 |
|------|------|
| svyun.com | 签到 → 查看详情 |

## 快速开始

### 1. Fork 本仓库

点击右上角 Fork 按钮。

### 2. 配置 Secrets

进入你的仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

添加以下 Secrets：

| Secret 名称 | 说明 | 必填 |
|-------------|------|------|
| `SVYUN_USER` | svyun.com 用户名 | 否 |
| `SVYUN_PASS` | svyun.com 密码 | 否 |
| `TG_BOT_TOKEN` | Telegram Bot Token | 否 |
| `TG_CHAT_ID` | Telegram Chat ID | 否 |

> 不需要的网站可以不配置，脚本会自动跳过。

### 3. 获取 Telegram Bot Token 和 Chat ID

#### 创建 Bot
1. 在 Telegram 搜索 `@BotFather`
2. 发送 `/newbot`
3. 按提示设置 Bot 名称
4. 获得 Token（格式：`123456789:ABCdefGHIjklMNOpqrsTUVwxyz`）

#### 获取 Chat ID
1. 在 Telegram 搜索 `@userinfobot`
2. 发送任意消息
3. 它会回复你的 Chat ID（纯数字）

### 4. 启用 Actions

进入 **Actions** 标签页，点击 "I understand my workflows, go ahead and enable them"。

### 5. 手动测试

Actions → Auto Check-in → Run workflow → Run workflow

### 6. 查看结果

- 运行日志会显示签到结果
- 截图在 Artifacts 中下载（保留 7 天）
- **Telegram 会收到签到报告和截图**

## 执行时间

默认每天 UTC 0:00（北京时间 8:00）执行。

修改 `.github/workflows/checkin.yml` 中的 cron 表达式可调整时间：

```yaml
schedule:
  - cron: '0 0 * * *'  # UTC 时间
```

常用时间对照：

| cron (UTC) | 北京时间 |
|------------|----------|
| `0 0 * * *` | 08:00 |
| `0 1 * * *` | 09:00 |
| `0 16 * * *` | 00:00（次日） |

## Telegram 通知示例

```
🔔 自动签到报告
📅 时间: 2025-05-08 08:00:00

✅ svyun.com: 成功

📊 统计: 成功 1 | 失败 0 | 跳过 0
```

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 设置环境变量
export SVYUN_USER="your_username"
export SVYUN_PASS="your_password"
export TG_BOT_TOKEN="your_bot_token"
export TG_CHAT_ID="your_chat_id"
# ... 其他账号

# 运行
python checkin.py
```

## 注意事项

1. **元素选择器**：网站更新后可能导致选择器失效，需要检查并更新脚本中的 CSS 选择器。

2. **账号安全**：密码存储在 GitHub Secrets 中，相对安全，但建议使用独立密码。

## 文件结构

```
auto-checkin/
├── checkin.py              # 主脚本
├── requirements.txt        # Python 依赖
├── README.md               # 说明文档
└── .github/
    └── workflows/
        └── checkin.yml     # GitHub Actions 配置
```

## License

MIT
