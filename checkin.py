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
    return path

async def send_tg(text, photo=None):
    if not TG_BOT_TOKEN: return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        try:
            if photo and os.path.exists(photo):
                form = aiohttp.FormData()
                form.add_field('chat_id', TG_CHAT_ID)
                form.add_field('photo', open(photo, 'rb'))
                form.add_field('caption', text[:1000])
                await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto", data=form)
            else:
                await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", 
                                   json={'chat_id': TG_CHAT_ID, 'text': text, 'parse_mode': 'HTML'})
        except Exception as e: print(f"  [TG失败] {e}")

async def human_click(page, locator):
    """模拟真人轨迹点击，绕过 CF Turnstile 检测"""
    box = await locator.bounding_box()
    if box:
        x = box['x'] + box['width'] / 2
        y = box['y'] + box['height'] / 2
        await page.mouse.move(x - 5, y - 5)
        await asyncio.sleep(0.3)
        await page.mouse.click(x, y, delay=150)

# ================= 站点逻辑 =================

async def checkin_miniduo(context):
    print("【miniduo.cn】执行双重点击...")
    page = await context.new_page()
    try:
        await page.goto('https://www.miniduo.cn/login', timeout=60000)
        await page.wait_for_selector('text=邮箱登录', timeout=20000)
        await page.get_by_text("邮箱登录").click()
        await page.locator('input[placeholder*="邮箱"]').fill(MINIDUO_USER)
        await page.locator('input[type="password"]').fill(MINIDUO_PASS)
        await page.get_by_role("button", name="登录").click()
        
        await page.wait_for_url("**/cart", timeout=20000)
        await asyncio.sleep(10) # 等待公告加载
        
        # 1. 关公告
        notice = page.get_by_text("我知道了")
        if await notice.count() > 0:
            await notice.click()
            await asyncio.sleep(2)
            
        # 2. 抽奖 (先试文本，再试坐标)
        btn = page.get_by_text("开始抽奖")
        if await btn.count() > 0:
            await btn.first.click(force=True)
        else:
            await page.mouse.click(1160, 860) 
            
        await asyncio.sleep(3)
        return True, "已尝试触发", await save_debug(page, "miniduo_ok")
    except Exception as e:
        return False, f"错误:{str(e)[:15]}", await save_debug(page, "miniduo_err")
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】监听注入并抓取详情...")
    page = await context.new_page()
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        # 解决Loading死锁：显式等待登录框
        await page.wait_for_selector('input[placeholder*="Email"]', timeout=30000)
        
        await page.evaluate(f"""() => {{
            const inputs = document.querySelectorAll('input');
            const u = Array.from(inputs).find(i => i.placeholder?.includes('Email'));
            const p = Array.from(inputs).find(i => i.type === 'password');
            if(u) u.value = '{SVYUN_USER}';
            if(p) p.value = '{SVYUN_PASS}';
            document.querySelector('input[type="checkbox"]')?.click();
        }}""")
        await page.locator('button:has-text("Login")').first.click()
        await asyncio.sleep(10)
        
        # 签到
        await page.locator('button:has-text("立即签到"), .checkin-btn').first.click()
        await asyncio.sleep(5)
        
        # 抓取次数与详情
        await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2')
        await asyncio.sleep(5)
        text = await page.inner_text("body")
        count = re.search(r"剩余抽奖次数\s*(\d+)\s*次", text)
        msg = f"剩余:{count.group(1)}次" if count else "签到成功"
        
        # 点击查看详情并截图
        try:
            await page.get_by_text("查看详情").click(timeout=5000)
            await asyncio.sleep(2)
        except: pass
        
        return True, msg, await save_debug(page, "svyun_res")
    except Exception as e:
        return False, f"错误:{str(e)[:15]}", await save_debug(page, "svyun_err")
    finally: await page.close()

async def checkin_vps8(context):
    print("【vps8.zz.cd】模拟真人点击验证...")
    page = await context.new_page()
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        await page.wait_for_selector('input[name="email"]', timeout=20000)
        
        await page.evaluate(f"""() => {{
            document.querySelector('input[name="email"]').value = '{VPS8_USER}';
            document.querySelector('input[name="password"]').value = '{VPS8_PASS}';
        }}""")
        
        # 探测并模拟点击 CF 验证框
        cf_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
        if await cf_frame.locator('body').count() > 0:
            await human_click(page, cf_frame.locator('body'))
            await asyncio.sleep(5)
            
        await page.locator('button:has-text("登录")').first.click()
        await asyncio.sleep(10)
        
        btn = page.locator('button:has-text("签到"), #checkin')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "签到成功", await save_debug(page, "vps8_ok")
        return False, "未见按钮", await save_debug(page, "vps8_err")
    except Exception as e:
        return False, f"错误:{str(e)[:15]}", await save_debug(page, "vps8_err")
    finally: await page.close()

# ================= 主流程 =================

async def main():
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 1024})
        
        for name, func in [('Miniduo', checkin_miniduo), ('Svyun', checkin_svyun), ('VPS8', checkin_vps8)]:
            ok, msg, ss = await func(context)
            status = "✅" if ok else "❌"
            await send_tg(f"{status} <b>{name}</b>: {msg}", photo=ss)
            await asyncio.sleep(10)
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
