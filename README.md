# 自动签到脚本

多网站自动签到，支持 GitHub Actions 每日自动执行。

## 支持网站

| 网站 | 功能 |
|------|------|
| miniduo.cn | 抽奖 → 获取余额 |
| svyun.com | 签到 → 查看详情 |
| vps8.zz.cd | 签到（含 CF 验证） |

## 快速开始

### 1. Fork 本仓库

点击右上角 Fork 按钮。

### 2. 配置 Secrets

进入你的仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

添加以下 Secrets：

| Secret 名称 | 说明 |
|-------------|------|
| `MINIDUO_USER` | miniduo.cn 用户名 |
| `MINIDUO_PASS` | miniduo.cn 密码 |
| `SVYUN_USER` | svyun.com 用户名 |
| `SVYUN_PASS` | svyun.com 密码 |
| `VPS8_USER` | vps8.zz.cd 用户名 |
| `VPS8_PASS` | vps8.zz.cd 密码 |

> 不需要的网站可以不配置，脚本会自动跳过。

### 3. 启用 Actions

进入 **Actions** 标签页，点击 "I understand my workflows, go ahead and enable them"。

### 4. 手动测试

Actions → Auto Check-in → Run workflow → Run workflow

### 5. 查看结果

- 运行日志会显示签到结果
- 截图在 Artifacts 中下载（保留 7 天）

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

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 设置环境变量
export MINIDUO_USER="your_username"
export MINIDUO_PASS="your_password"
# ... 其他账号

# 运行
python checkin.py
```

## 注意事项

1. **Cloudflare 验证**：vps8.zz.cd 使用 CF Turnstile，headless 模式下可能无法自动通过。如遇问题，可尝试：
   - 使用 `headless=False` 本地调试
   - 或考虑使用第三方 CF 绕过服务

2. **元素选择器**：网站更新后可能导致选择器失效，需要检查并更新脚本中的 CSS 选择器。

3. **账号安全**：密码存储在 GitHub Secrets 中，相对安全，但建议使用独立密码。

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
