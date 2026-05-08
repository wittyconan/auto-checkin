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
SCREENSHOT_DIR = os.getenv('SCREENSHOT_DIR', './screenshots')

# ================= 核心工具函数 =================
async def apply_stealth(page):
    """手动抹除浏览器指纹，对抗 CF 盾"""
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    """)

async def send_tg_report(text, photo=None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        try:
            if photo and os.path.exists(photo):
                form = aiohttp.FormData()
                form.add_field('chat_id', TG_CHAT_ID)
                form.add_field('photo', open(photo, 'rb'))
                form.add_field('caption', text[:1000], content_type='text/plain')
                await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto", data=form)
            else:
                await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", 
                                   json={'chat_id': TG_CHAT_ID, 'text': text, 'parse_mode': 'HTML'})
        except Exception as e: print(f"  [TG发送失败] {e}")

# ================= 站点签到逻辑 =================

async def checkin_miniduo(context):
    print("【miniduo.cn】执行中...")
    page = await context.new_page()
    await apply_stealth(page)
    try:
        await page.goto('https://www.miniduo.cn/login', wait_until='domcontentloaded')
        # 切换邮箱登录
        email_tab = page.get_by_text("邮箱登录")
        await email_tab.wait_for(state="visible")
        await email_tab.click()
        
        await page.locator('input[placeholder*="邮箱"]').fill(MINIDUO_USER)
        await page.locator('input[type="password"]').fill(MINIDUO_PASS)
        await page.get_by_role("button", name="登录").click()
        
        # 等待购物车/个人中心页面
        await page.wait_for_url("**/cart", timeout=15000)
        await asyncio.sleep(5) # 必须等抽奖组件加载
        
        # 查找“开始抽奖”
        lottery_btn = page.locator('button:has-text("开始抽奖"), .lottery-btn, #lottery')
        if await lottery_btn.count() > 0:
            await lottery_btn.first.click()
            await asyncio.sleep(3)
            return True, "已点击‘开始抽奖’"
        return False, "未找到抽奖按钮（可能已签过）"
    except Exception as e: return False, f"出错: {str(e)[:50]}"
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】执行中...")
    page = await context.new_page()
    await apply_stealth(page)
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', wait_until='networkidle')
        # 显式等待输入框，防止“空白登录”
        user_input = page.locator('input[name="username"]')
        await user_input.wait_for(state="visible")
        await user_input.type(SVYUN_USER, delay=100)
        await page.type('input[name="password"]', SVYUN_PASS, delay=100)
        
        # 勾选协议 (svyun 登录的死穴)
        agree_cb = page.locator('input[type="checkbox"]')
        if await agree_cb.count() > 0:
            await agree_cb.first.check()
        
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')
        
        # 跳转签到页/查找按钮
        checkin_btn = page.locator('button:has-text("立即签到"), .checkin-btn')
        if await checkin_btn.count() > 0:
            await checkin_btn.first.click()
            await asyncio.sleep(2)
            return True, "签到点击成功"
        return False, "登录成功但未找到签到按钮"
    except Exception as e: return False, f"出错: {str(e)[:50]}"
    finally: await page.close()

async def checkin_vps8(context):
    print("【vps8.zz.cd】执行中...")
    page = await context.new_page()
    await apply_stealth(page)
    try:
        # 第一道 CF 盾
        await page.goto('https://vps8.zz.cd/login', wait_until='domcontentloaded')
        await asyncio.sleep(8) # 硬等 CF Turnstile 渲染
        
        await page.type('input[name="email"]', VPS8_USER, delay=120)
        await page.type('input[name="password"]', VPS8_PASS, delay=120)
        
        # 点击登录，登录按钮往往也触发验证
        await page.get_by_role("button", name=re.compile("登录|Login")).click()
        await page.wait_for_load_state('networkidle')
        
        # 签到交互
        await asyncio.sleep(5)
        checkin_btn = page.locator('button:has-text("签到"), #checkin')
        if await checkin_btn.count() > 0:
            await checkin_btn.first.click()
            await asyncio.sleep(4) # 等待签到反馈
            return True, "签到成功"
        return False, "未找到签到按钮"
    except Exception as e: return False, f"出错: {str(e)[:50]}"
    finally: await page.close()

# ================= 主流程 =================

async def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    async with async_playwright() as p:
        # 启动参数压榨：模拟真实的窗口大小
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        results = {}
        results['miniduo'] = await checkin_miniduo(context)
        results['svyun'] = await checkin_svyun(context)
        results['vps8'] = await checkin_vps8(context)
        
        # 汇总报告
        now = datetime.now().strftime('%m-%d %H:%M')
        report = f"🤖 <b>自动签到报告 [{now}]</b>\n\n"
        for site, (ok, msg) in results.items():
            status = "✅" if ok else "❌"
            report += f"{status} <b>{site}</b>: {msg}\n"
        
        print(report)
        
        # 无论成功失败，给最后状态留个截图备查
        final_ss = f"{SCREENSHOT_DIR}/last_run.png"
        last_page = context.pages[-1] if context.pages else None
        if last_page:
            await last_page.screenshot(path=final_ss, full_page=True)
            await send_tg_report(report, photo=final_ss)
        else:
            await send_tg_report(report)
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
