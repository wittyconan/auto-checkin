#!/usr/bin/env python3
import os
import re
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ================= 配置区域 =================
MINIDUO_USER = os.getenv('MINIDUO_USER', '')
MINIDUO_PASS = os.getenv('MINIDUO_PASS', '')
SVYUN_USER = os.getenv('SVYUN_USER', '')
SVYUN_PASS = os.getenv('SVYUN_PASS', '')
VPS8_USER = os.getenv('VPS8_USER', '')
VPS8_PASS = os.getenv('VPS8_PASS', '')
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.getenv('TG_CHAT_ID', '')
SCREENSHOT_DIR = os.getenv('SCREENSHOT_DIR', '/tmp/checkin_screenshots')

# ================= 工具函数 =================
async def send_tg_report(text, photo=None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        if photo:
            form = aiohttp.FormData()
            form.add_field('chat_id', TG_CHAT_ID)
            form.add_field('photo', open(photo, 'rb'), filename='res.png')
            form.add_field('caption', text, content_type='text/plain')
            await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto", data=form)
        else:
            await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", 
                               json={'chat_id': TG_CHAT_ID, 'text': text, 'parse_mode': 'HTML'})

async def handle_cf(page):
    """尝试等待并穿透 CF 验证"""
    try:
        await asyncio.sleep(5) # 基础静默期
        await page.wait_for_load_state('networkidle', timeout=10000)
    except: pass

# ================= 签到主逻辑 =================

async def checkin_miniduo(context):
    print("【miniduo.cn】执行中...")
    page = await context.new_page()
    try:
        await page.goto('https://www.miniduo.cn/login', wait_until='domcontentloaded')
        # 强制等待切换到邮箱登录
        email_tab = page.get_by_text("邮箱登录")
        await email_tab.wait_for(state="visible")
        await email_tab.click()
        
        await page.locator('input[placeholder*="邮箱"]').fill(MINIDUO_USER)
        await page.locator('input[type="password"]').fill(MINIDUO_PASS)
        await page.get_by_role("button", name="登录").click()
        await page.wait_for_url("**/cart", timeout=10000)
        
        # 核心：点“开始抽奖”按钮
        print("  寻找抽奖按钮...")
        # 该站点的抽奖按钮往往是动态生成的
        await asyncio.sleep(3)
        lottery_btn = page.locator('button:has-text("开始抽奖"), .lottery-btn')
        if await lottery_btn.count() > 0:
            await lottery_btn.first.click()
            await asyncio.sleep(2)
            return True, "已点击抽奖"
        return False, "未找到抽奖按钮"
    except Exception as e: return False, str(e)
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】执行中...")
    page = await context.new_page()
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm')
        # 确保输入框加载
        user_input = page.locator('input[name="username"]')
        await user_input.wait_for(state="visible")
        await user_input.fill(SVYUN_USER)
        await page.fill('input[name="password"]', SVYUN_PASS)
        
        # 勾选协议：这是 svyun 登录失败的主因
        check_box = page.locator('input[type="checkbox"]')
        if await check_box.count() > 0:
            await check_box.first.check()
        
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')
        
        # 点击签到
        checkin_btn = page.locator('button:has-text("立即签到"), .checkin-btn')
        if await checkin_btn.count() > 0:
            await checkin_btn.first.click()
            await asyncio.sleep(2)
            return True, "签到成功"
        return False, "已登录但未找到签到按钮"
    except Exception as e: return False, str(e)
    finally: await page.close()

async def checkin_vps8(context):
    print("【vps8.zz.cd】执行中...")
    page = await context.new_page()
    try:
        # 第一重 CF 盾
        await page.goto('https://vps8.zz.cd/login')
        await handle_cf(page)
        
        # 拟人化输入
        await page.type('input[name="email"]', VPS8_USER, delay=50)
        await page.type('input[name="password"]', VPS8_PASS, delay=50)
        
        # 这里通常有 Turnstile 验证，硬等几秒让 Token 生成
        await asyncio.sleep(5)
        await page.get_by_role("button", name=re.compile("登录|Login")).click()
        
        # 第二重：登录后的签到按钮
        await page.wait_for_load_state('domcontentloaded')
        await handle_cf(page)
        
        checkin_btn = page.locator('button:has-text("签到"), #checkin')
        if await checkin_btn.count() > 0:
            await checkin_btn.first.click()
            await asyncio.sleep(3) # 再次等 CF 验证
            return True, "签到成功"
        return False, "登录成功但未找到签到按钮"
    except Exception as e: return False, str(e)
    finally: await page.close()

# ================= 主入口 =================

async def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    async with async_playwright() as p:
        # 增加隐身参数
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        # 执行任务
        results = {}
        results['miniduo'] = await checkin_miniduo(context)
        results['svyun'] = await checkin_svyun(context)
        results['vps8'] = await checkin_vps8(context)
        
        # 汇总并发送通知
        report = "🔔 <b>自动签到汇总</b>\n"
        for site, (res, msg) in results.items():
            icon = "✅" if res else "❌"
            report += f"{icon} {site}: {msg}\n"
        
        print(report)
        await send_tg_report(report)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
