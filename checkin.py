#!/usr/bin/env python3
import os, re, asyncio
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
    await page.screenshot(path=path)
    return path

async def send_tg(text, photo=None):
    if not TG_BOT_TOKEN: return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        try:
            form = aiohttp.FormData()
            form.add_field('chat_id', TG_CHAT_ID)
            if photo: form.add_field('photo', open(photo, 'rb'))
            form.add_field( 'caption' if photo else 'text', text)
            await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/{'sendPhoto' if photo else 'sendMessage'}", data=form)
        except: pass

# ================= 核心逻辑 =================

async def run_task(context):
    page = await context.new_page()
    try:
        # 1. 强制进入登录页
        print("  -> 正在登录...")
        await page.goto('https://www.svyun.com/plugin/86/index.htm', wait_until="domcontentloaded")
        
        # 只有在看到输入框时才登录
        if await page.locator('input[placeholder*="Email"]').is_visible():
            await page.locator('input[placeholder*="Email"]').fill(SVYUN_USER)
            await page.locator('input[type="password"]').fill(SVYUN_PASS)
            await page.get_by_text("Read and agree").click()
            await page.locator('button:has-text("Login")').click()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(5)

        # 2. 【核心修改】模拟点击侧边栏的“每日签到”
        # 这样做是为了触发页面内部的 Ajax 加载，防止直接跳转 URL 导致的按钮不渲染
        print("  -> 正在通过侧边栏进入签到页...")
        await page.locator('li:has-text("活动优惠")').click() # 先展开菜单
        await asyncio.sleep(1)
        await page.locator('a:has-text("每日签到")').click() # 点击签到项
        await asyncio.sleep(5)

        # 3. 循环等待并强力点击
        res_msg = "失败"
        for i in range(15): # 延长到30秒总计
            # 自动移除任何可能遮挡的 Layui 弹窗
            await page.evaluate("document.querySelectorAll('.layui-layer').forEach(el => el.remove())")
            
            # 检查是否已签到
            if await page.get_by_text("已签到").count() > 0 or await page.locator('.checkin-btn-done').is_visible():
                res_msg = "今日已签到过"
                return True, res_msg, await save_debug(page, "already_done")

            # 定位立即签到按钮
            btn = page.get_by_role("button", name=re.compile("立即签到"))
            if await btn.is_visible():
                print("  -> 发现按钮，执行 JavaScript 强制点击...")
                # 使用 evaluate 绕过一切 UI 遮挡
                await page.evaluate("Array.from(document.querySelectorAll('button')).find(el => el.textContent.includes('立即签到')).click()")
                await asyncio.sleep(3)
                return True, "签到成功", await save_debug(page, "success")
            
            print(f"  ...扫描中 ({i+1}/15)")
            await asyncio.sleep(2)

        return False, "超时未见按钮", await save_debug(page, "timeout_fail")

    except Exception as e:
        return False, f"异常: {str(e)[:30]}", await save_debug(page, "error")
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        ok, msg, ss = await run_task(context)
        status = "✅" if ok else "❌"
        await send_tg(f"{status} <b>Svyun 签到报告</b>\n结果: {msg}", photo=ss)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
