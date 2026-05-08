#!/usr/bin/env python3
import os
import re
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

# ================= 配置区域 =================
MINIDUO_USER = os.getenv('MINIDUO_USER', '')
MINIDUO_PASS = os.getenv('MINIDUO_PASS', '')
SVYUN_USER = os.getenv('SVYUN_USER', '')
SVYUN_PASS = os.getenv('SVYUN_PASS', '')
VPS8_USER = os.getenv('VPS8_USER', '')
VPS8_PASS = os.getenv('VPS8_PASS', '')
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.getenv('TG_CHAT_ID', '')
SCREENSHOT_DIR = os.getenv('SCREENSHOT_DIR', './screenshots')

# ================= 工具函数 =================
async def save_debug(page, name):
    path = f"{SCREENSHOT_DIR}/debug_{name}_{datetime.now().strftime('%H%M%S')}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [Debug] 截图已保存: {path}")

async def apply_stealth(page):
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = { runtime: {} };
    """)

async def send_tg(text):
    if not TG_BOT_TOKEN: return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", 
                           json={'chat_id': TG_CHAT_ID, 'text': text, 'parse_mode': 'HTML'})

# ================= 站点逻辑 =================

async def checkin_miniduo(context):
    print("【miniduo.cn】执行中...")
    page = await context.new_page()
    await apply_stealth(page)
    try:
        await page.goto('https://www.miniduo.cn/login', timeout=60000)
        await asyncio.sleep(8) # 硬等页面渲染
        
        # 处理可能的白屏：检查内容长度
        content = await page.content()
        if len(content) < 500:
            print("  ! 检测到页面内容过少，尝试刷新...")
            await page.reload()
            await asyncio.sleep(10)

        # 切换邮箱登录并输入
        await page.get_by_text("邮箱登录").click()
        await page.locator('input[placeholder*="邮箱"]').click()
        await page.type('input[placeholder*="邮箱"]', MINIDUO_USER, delay=100)
        await page.type('input[type="password"]', MINIDUO_PASS, delay=100)
        await page.get_by_role("button", name="登录").click()
        
        await page.wait_for_url("**/cart", timeout=20000)
        print("  ✓ 登录成功，等待转盘加载...")
        await asyncio.sleep(12) 
        
        # 精准点击转盘中心
        await page.mouse.click(1160, 860) 
        await asyncio.sleep(3)
        return True, "已尝试触发坐标点击"
    except Exception as e:
        await save_debug(page, "miniduo_err")
        return False, str(e)[:30]
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】执行中...")
    page = await context.new_page()
    await apply_stealth(page)
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        await asyncio.sleep(8)
        
        # 拟人化输入账号
        user_box = page.locator('input[name="username"]')
        await user_box.wait_for(state="visible")
        await user_box.click() # 先点一下激活
        await user_box.type(SVYUN_USER, delay=120)
        
        # 拟人化输入密码
        pwd_box = page.locator('input[name="password"]')
        await pwd_box.click()
        await pwd_box.type(SVYUN_PASS, delay=120)
        
        # 勾选协议：直接点击文字部分
        print("  尝试勾选协议...")
        agree_text = page.get_by_text("Read and agree")
        if await agree_text.count() > 0:
            await agree_text.click()
        
        await asyncio.sleep(1)
        await page.click('button:has-text("Login")')
        await page.wait_for_load_state('networkidle', timeout=20000)
        
        # 点击签到
        btn = page.locator('button:has-text("立即签到"), .checkin-btn')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "签到点击成功"
        return False, "未找到签到按钮"
    except Exception as e:
        await save_debug(page, "svyun_err")
        return False, str(e)[:30]
    finally: await page.close()

async def checkin_vps8(context):
    print("【vps8.zz.cd】执行中...")
    page = await context.new_page()
    await apply_stealth(page)
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        if "维护" in await page.content(): return False, "站点维护"

        # 处理 CF 盾
        for _ in range(5):
            if "Just a moment" in await page.title():
                print("  等待 CF 验证中...")
                await asyncio.sleep(10)
            else: break
        
        await page.locator('input[name="email"]').type(VPS8_USER, delay=100)
        await page.type('input[name="password"]', VPS8_PASS, delay=100)
        await page.get_by_role("button", name=re.compile("登录|Login")).click()
        
        await asyncio.sleep(10)
        btn = page.locator('button:has-text("签到"), #checkin')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "签到完成"
        return False, "未找到按钮"
    except Exception as e:
        await save_debug(page, "vps8_err")
        return False, str(e)[:30]
    finally: await page.close()

# ================= 主入口 =================

async def main():
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        # 统一设置视口分辨率，保证坐标点击的一致性
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        results = {}
        # 改为顺序执行，每个任务之间留出呼吸时间
        results['miniduo'] = await checkin_miniduo(context)
        await asyncio.sleep(10)
        results['svyun'] = await checkin_svyun(context)
        await asyncio.sleep(10)
        results['vps8'] = await checkin_vps8(context)
        
        report = f"🔔 <b>自动签到报告 [{datetime.now().strftime('%m-%d %H:%M')}]</b>\n"
        for s, (ok, msg) in results.items():
            report += f"{'✅' if ok else '❌'} {s}: {msg}\n"
        
        print(report)
        await send_tg(report)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
