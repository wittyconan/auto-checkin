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
    print("【miniduo.cn】开始...")
    page = await context.new_page()
    await apply_stealth(page)
    try:
        await page.goto('https://www.miniduo.cn/login', timeout=60000)
        await page.get_by_text("邮箱登录").click()
        await page.locator('input[placeholder*="邮箱"]').fill(MINIDUO_USER)
        await page.locator('input[type="password"]').fill(MINIDUO_PASS)
        await page.get_by_role("button", name="登录").click()
        
        # 登录后跳转购物车页面
        await page.wait_for_url("**/cart", timeout=20000)
        print("  ✓ 登录成功，等待转盘加载...")
        await asyncio.sleep(10) # 关键：给悬浮转盘充足加载时间
        
        # 尝试点击转盘中心的“开始抽奖”
        lottery_btn = page.get_by_text("开始抽奖")
        if await lottery_btn.count() > 0:
            await lottery_btn.first.click(force=True)
            print("  ✓ 文本点击‘开始抽奖’成功")
        else:
            # 备选：根据你的截图分辨率 (1280x800)，模拟右下角坐标点击
            print("  ! 未找到文本，尝试坐标点击 (1160, 860)...")
            await page.mouse.click(1160, 860) 
            
        await asyncio.sleep(3)
        return True, "已尝试触发抽奖"
    except Exception as e:
        await save_debug(page, "miniduo_err")
        return False, str(e)[:30]
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】开始...")
    page = await context.new_page()
    await apply_stealth(page)
    try:
        # 增加 Referer 伪装，应对 504 屏蔽
        await page.goto('https://www.svyun.com/plugin/86/index.htm', 
                        timeout=60000, 
                        referer="https://www.google.com/")
        await asyncio.sleep(5)
        
        if "504" in await page.title() or "Gateway Timeout" in await page.content():
            return False, "站点 504 (GitHub IP被禁)"

        await page.locator('input[name="username"]').fill(SVYUN_USER)
        await page.fill('input[name="password"]', SVYUN_PASS)
        cb = page.locator('input[type="checkbox"]')
        if await cb.count() > 0: await cb.first.check()
        await page.click('button[type="submit"]')
        await asyncio.sleep(5)
        
        btn = page.locator('button:has-text("立即签到"), .checkin-btn')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "签到成功"
        return False, "未找到签到按钮"
    except Exception as e:
        await save_debug(page, "svyun_err")
        return False, str(e)[:30]
    finally: await page.close()

async def checkin_vps8(context):
    print("【vps8.zz.cd】开始...")
    page = await context.new_page()
    await apply_stealth(page)
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        
        # 识别维护页面
        if "维护" in await page.content():
            return False, "站点维护中"

        # 硬等 CF 验证
        for _ in range(3):
            if "Just a moment" in await page.title():
                await asyncio.sleep(10)
            else: break
        
        await page.locator('input[name="email"]').wait_for(state="visible", timeout=20000)
        await page.type('input[name="email"]', VPS8_USER, delay=100)
        await page.type('input[name="password"]', VPS8_PASS, delay=100)
        await page.get_by_role("button", name=re.compile("登录|Login")).click()
        await asyncio.sleep(8)
        
        btn = page.locator('button:has-text("签到"), #checkin')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "签到成功"
        return False, "未找到按钮"
    except Exception as e:
        await save_debug(page, "vps8_err")
        return False, str(e)[:30]
    finally: await page.close()

# ================= 主流程 =================

async def main():
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800}, # 必须固定分辨率以保证坐标点击准确
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        results = {}
        # 顺序执行
        results['miniduo'] = await checkin_miniduo(context)
        await asyncio.sleep(5)
        results['svyun'] = await checkin_svyun(context)
        await asyncio.sleep(5)
        results['vps8'] = await checkin_vps8(context)
        
        report = f"🔔 <b>自动签到报告 [{datetime.now().strftime('%H:%M')}]</b>\n"
        for s, (ok, msg) in results.items():
            report += f"{'✅' if ok else '❌'} {s}: {msg}\n"
        
        print(report)
        await send_tg(report)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
