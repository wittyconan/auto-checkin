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

async def save_debug(page, name, clip_element=None):
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    path = f"{SCREENSHOT_DIR}/debug_{name}_{datetime.now().strftime('%H%M%S')}.png"
    try:
        if clip_element and await clip_element.is_visible():
            await clip_element.screenshot(path=path, timeout=5000)
        else:
            await page.screenshot(path=path, timeout=5000)
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
                await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", 
                                   json={'chat_id': TG_CHAT_ID, 'text': text, 'parse_mode': 'HTML'})
        except Exception as e: print(f"  [TG通知失败] {e}")

# ================= 核心逻辑 =================

async def run_task(context):
    page = await context.new_page()
    try:
        # 1. 访问登录页 (增加错误检测)
        response = await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        if not response or response.status >= 500:
            return False, f"网站响应异常({response.status if response else '无响应'})", await save_debug(page, "site_down")

        await asyncio.sleep(5)
        
        # 2. 登录
        user_input = page.locator('input[placeholder*="Email"]').first
        # 检查是否真的到了登录页
        if await user_input.count() == 0:
            return False, "页面加载不完整(找不到输入框)", await save_debug(page, "wrong_page")

        await user_input.fill(SVYUN_USER)
        await page.locator('input[type="password"]').fill(SVYUN_PASS)
        await page.get_by_text("Read and agree").click()
        await page.locator('button:has-text("Login")').first.click()
        
        await asyncio.sleep(10)

        # 3. 签到
        await page.goto('https://www.svyun.com/plugin/94/index.htm', wait_until="domcontentloaded")
        await asyncio.sleep(5)

        btn_sign = page.locator('button:has-text("立即签到"), .checkin-btn').first
        btn_signed = page.get_by_text("已签到")

        if await btn_signed.count() > 0:
            res_msg = "今日已签到过"
        elif await btn_sign.count() > 0:
            await btn_sign.click(force=True)
            await asyncio.sleep(3)
            res_msg = "签到成功"
        else:
            return False, "找不到签到按钮", await save_debug(page, "no_btn")

        # 4. 获取次数
        await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2')
        await asyncio.sleep(3)
        content = await page.content()
        count = re.search(r"剩余抽奖次数\s*(\d+)", content)
        suffix = f" (剩余:{count.group(1)}次)" if count else ""
        
        return True, res_msg + suffix, await save_debug(page, "final")

    except Exception as e:
        return False, f"异常: {str(e)[:20]}", await save_debug(page, "crash")
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 1024})
        
        max_retries = 3
        last_ss = None
        
        for i in range(max_retries):
            print(f"开始第 {i+1} 次尝试...")
            ok, msg, ss = await run_task(context)
            last_ss = ss
            if ok:
                await send_tg(f"✅ <b>Svyun 签到成功</b>\n结果: {msg}", photo=ss)
                break
            else:
                print(f"第 {i+1} 次失败: {msg}")
                if i == max_retries - 1:
                    await send_tg(f"❌ <b>Svyun 签到失败</b>\n最终错误: {msg}", photo=ss)
                else:
                    await asyncio.sleep(30) # 失败后等30秒再试
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
