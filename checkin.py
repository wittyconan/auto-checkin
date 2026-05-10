#!/usr/bin/env python3
import os
import re
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

# ================= 配置区域 =================
SVYUN_USER = os.getenv('SVYUN_USER', '')
SVYUN_PASS = os.getenv('SVYUN_PASS', '')
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.getenv('TG_CHAT_ID', '')
SCREENSHOT_DIR = os.getenv('SCREENSHOT_DIR', './screenshots')

async def save_debug(page, name):
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    path = f"{SCREENSHOT_DIR}/debug_{name}_{datetime.now().strftime('%H%M%S')}.png"
    try:
        await page.screenshot(path=path)
        return path
    except: return None

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
                await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", json={'chat_id': TG_CHAT_ID, 'text': text, 'parse_mode': 'HTML'})
        except: pass

# ================= 业务逻辑 =================

async def run_task(context):
    page = await context.new_page()
    try:
        # 1. 访问签到页
        print("  -> 正在加载签到中心...")
        await page.goto('https://www.svyun.com/plugin/94/index.htm', wait_until="networkidle", timeout=60000)
        
        # 2. 检查并执行登录
        if await page.locator('input[placeholder*="Email"]').first.is_visible():
            print("  -> 执行登录...")
            await page.locator('input[placeholder*="Email"]').first.fill(SVYUN_USER)
            await page.locator('input[type="password"]').fill(SVYUN_PASS)
            await page.get_by_text("Read and agree").click()
            await page.locator('button:has-text("Login")').first.click()
            await asyncio.sleep(10)
            await page.goto('https://www.svyun.com/plugin/94/index.htm')

        # 3. 【核心加固】暴力循环等待按钮出现
        print("  -> 正在扫描签到按钮 (最长等待20秒)...")
        sign_done = False
        res_msg = "未知状态"
        
        for i in range(10): # 循环10次，每次2秒
            # 自动清理可能遮挡的公告弹窗
            await page.evaluate("document.querySelectorAll('.layui-layer').forEach(el => el.remove())")
            
            # 检查是否已签到
            if await page.get_by_text("已签到").count() > 0:
                res_msg = "今日已签到过"
                sign_done = True
                break
            
            # 寻找“立即签到”按钮
            btn = page.locator('button:has-text("立即签到"), .checkin-btn').first
            if await btn.is_visible():
                print(f"  -> 第 {i+1} 次扫描发现按钮，执行强力点击...")
                # 尝试三种点击方式叠加
                try:
                    await btn.click(force=True, timeout=2000) # Playwright点击
                except:
                    await page.evaluate("document.querySelector('button:contains(\"立即签到\")')?.click()") # JS点击
                
                await asyncio.sleep(5) # 等待点击反馈
                res_msg = "签到指令发送成功"
                sign_done = True
                break
            
            await asyncio.sleep(2)
            print(f"  ...等待中 ({i+1}/10)")

        if not sign_done:
            return False, "超时未见签到按钮", await save_debug(page, "btn_timeout")

        # 4. 获取剩余抽奖次数
        await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2')
        await asyncio.sleep(5)
        content = await page.content()
        count = re.search(r"剩余抽奖次数\s*(\d+)", content)
        suffix = f" (剩余:{count.group(1)}次)" if count else ""
        
        return True, res_msg + suffix, await save_debug(page, "final")

    except Exception as e:
        return False, f"异常: {str(e)[:30]}", await save_debug(page, "crash")
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 1024})
        
        for attempt in range(2): # 两次大重试
            ok, msg, ss = await run_task(context)
            if ok:
                await send_tg(f"✅ <b>Svyun 签到报告</b>\n结果: {msg}", photo=ss)
                break
            elif attempt == 1:
                await send_tg(f"❌ <b>Svyun 最终失败</b>\n原因: {msg}", photo=ss)
            await asyncio.sleep(20)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
