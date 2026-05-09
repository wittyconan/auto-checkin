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

# ================= 站点逻辑 =================

async def checkin_miniduo(context):
    print("【miniduo.cn】测试 IP 连通性...")
    page = await context.new_page()
    try:
        # 缩短超时时间，因为如果是白屏，等再久也没用
        response = await page.goto('https://www.miniduo.cn/login', timeout=20000)
        await asyncio.sleep(5)
        
        if len(await page.content()) < 500:
            return False, "IP被墙(纯白屏)", await save_debug(page, "miniduo_block")

        await page.get_by_text("邮箱登录").click()
        await page.locator('input[placeholder*="邮箱"]').fill(MINIDUO_USER)
        await page.locator('input[type="password"]').fill(MINIDUO_PASS)
        await page.get_by_role("button", name="登录").click()
        
        await page.wait_for_url("**/cart", timeout=15000)
        await asyncio.sleep(8) 
        try: await page.get_by_text("我知道了").click(timeout=3000)
        except: pass
        await page.mouse.click(1160, 860) 
        return True, "已尝试触发", await save_debug(page, "miniduo_ok")
    except Exception as e:
        return False, f"错误:{str(e)[:15]}", await save_debug(page, "miniduo_err")
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】物理键盘级输入法...")
    page = await context.new_page()
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        # 等待页面上的 Loading 完全消失
        await asyncio.sleep(10)
        
        # 1. 点击账号框 -> 模拟真实敲击
        user_input = page.locator('input[placeholder*="Email"]').first
        await user_input.wait_for(state="visible")
        await user_input.click()
        await user_input.clear()
        await user_input.press_sequentially(SVYUN_USER, delay=100) # 延迟100ms敲一个字
        
        # 2. 点击密码框 -> 模拟真实敲击
        pass_input = page.locator('input[type="password"]')
        await pass_input.click()
        await pass_input.clear()
        await pass_input.press_sequentially(SVYUN_PASS, delay=100)
        
        # 3. 勾选并登录
        await page.get_by_text("Read and agree").click()
        await asyncio.sleep(1)
        await page.locator('button:has-text("Login")').first.click()
        
        await asyncio.sleep(10)
        # 签到逻辑
        btn = page.locator('button:has-text("立即签到"), .checkin-btn')
        if await btn.count() > 0:
            await btn.first.click()
            await asyncio.sleep(5)
            
            # 抓取次数
            await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2')
            await asyncio.sleep(5)
            text = await page.inner_text("body")
            count = re.search(r"剩余抽奖次数\s*(\d+)\s*次", text)
            msg = f"剩余:{count.group(1)}次" if count else "签到成功"
            
            try: await page.get_by_text("查看详情").click(timeout=5000); await asyncio.sleep(2)
            except: pass
            
            return True, msg, await save_debug(page, "svyun_res")
        return False, "未见签到按钮", await save_debug(page, "svyun_fail")
    except Exception as e:
        return False, f"错误:{str(e)[:15]}", await save_debug(page, "svyun_err")
    finally: await page.close()

async def checkin_vps8(context):
    print("【vps8.zz.cd】精准狙击 CF 验证框...")
    page = await context.new_page()
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        await asyncio.sleep(5)
        
        # 同样使用真实敲击
        await page.locator('input[name="email"]').press_sequentially(VPS8_USER, delay=50)
        await page.locator('input[name="password"]').press_sequentially(VPS8_PASS, delay=50)
        
        print("  正在寻找 Turnstile 验证框...")
        # 等待 iframe 出现
        await page.wait_for_selector('iframe[src*="challenges.cloudflare.com"]', state="attached", timeout=15000)
        cf_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
        
        # 给 CF 盾一点时间加载内部的复选框
        await asyncio.sleep(5)
        
        # 强行点击 iframe 内部偏左的位置（通常是那个小方框的所在处）
        target = cf_frame.locator('body')
        if await target.count() > 0:
            print("  ✓ 找到盾牌，执行偏移点击...")
            # x:20, y:20 通常能精准点到那个框
            await target.click(position={"x": 20, "y": 20}, delay=200)
            await asyncio.sleep(5) # 等绿圈转完
            
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
            await asyncio.sleep(5)
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
