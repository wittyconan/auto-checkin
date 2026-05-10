#!/usr/bin/env python3
import os, re, asyncio, random
from datetime import datetime
from playwright.async_api import async_playwright

SVYUN_USER = os.getenv('SVYUN_USER', '')
SVYUN_PASS = os.getenv('SVYUN_PASS', '')
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.getenv('TG_CHAT_ID', '')
SCREENSHOT_DIR = os.getenv('SCREENSHOT_DIR', './screenshots')

async def save_debug(page, name):
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    path = f"{SCREENSHOT_DIR}/debug_{name}_{datetime.now().strftime('%H%M%S')}.png"
    try:
        await page.screenshot(path=path, timeout=5000)
        return path
    except: return None

async def send_tg(text, photo=None):
    if not TG_BOT_TOKEN: return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        try:
            form = aiohttp.FormData()
            form.add_field('chat_id', TG_CHAT_ID)
            if photo: form.add_field('photo', open(photo, 'rb'))
            form.add_field('caption' if photo else 'text', text)
            await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/{'sendPhoto' if photo else 'sendMessage'}", data=form)
        except: pass

async def run_task(context):
    page = await context.new_page()
    page.set_default_timeout(60000)
    
    try:
        print(f"  -> [{datetime.now().strftime('%H:%M:%S')}] 访问首页...")
        # 尝试直接去签到页，如果被拦截会自动跳登录
        await page.goto('https://www.svyun.com/plugin/94/index.htm', wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # 1. 登录逻辑：改用物理模拟填充
        email_input = page.locator('input[placeholder*="Email"]').first
        if await email_input.is_visible():
            print("  -> 发现登录框，执行物理级模拟输入...")
            # 物理点击并输入 (触发 Vue/React 的内部监听)
            await email_input.click()
            await email_input.fill("") # 先清空
            await email_input.type(SVYUN_USER, delay=100)
            
            pwd_input = page.locator('input[type="password"]').first
            await pwd_input.click()
            await pwd_input.type(SVYUN_PASS, delay=100)
            
            # 强行勾选协议 (JS 暴力勾选)
            await page.evaluate("document.querySelectorAll('input[type=\"checkbox\"]').forEach(i => i.checked = true)")
            
            # 点击登录
            login_btn = page.locator('button:has-text("Login")').first
            await login_btn.click()
            print("  -> 已点击登录按钮，等待跳转...")
            await asyncio.sleep(10)
            
            # 登录完再次确保进入签到页
            await page.goto('https://www.svyun.com/plugin/94/index.htm')
            await asyncio.sleep(5)

        # 2. 签到按钮扫描：增加 DOM 重新加载检测
        for i in range(15):
            # 强制刷新页面数据状态 (JS 注入)
            await page.evaluate("document.querySelectorAll('.layui-layer').forEach(el => el.remove())")
            
            content = await page.content()
            if "已签到" in content:
                return True, "今日已成功签到", await save_debug(page, "final_done")

            # 寻找按钮并执行 JS 点击 (因为物理点击在 Headless 模式下容易偏离)
            clicked = await page.evaluate("""() => {
                const b = Array.from(document.querySelectorAll('button, a, div')).find(el => el.innerText.trim() === '立即签到');
                if(b) { b.click(); return true; }
                return false;
            }""")
            
            if clicked:
                print("  -> 发现按钮并发送 JS 点击指令")
                await asyncio.sleep(5)
                if "已签到" in await page.content():
                    return True, "签到成功！", await save_debug(page, "success")
                return True, "签到动作已触发", await save_debug(page, "triggered")
            
            print(f"  ...等待按钮加载 ({i+1}/15)")
            await asyncio.sleep(2)

        return False, "页面已加载但未能点击成功", await save_debug(page, "fail_btn")

    except Exception as e:
        return False, f"流程异常: {str(e)[:30]}", await save_debug(page, "crash")
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        # 特别注意：针对 GitHub 环境关闭某些可能导致渲染失败的参数
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        for attempt in range(3):
            print(f"\n--- 尝试 {attempt + 1} ---")
            ok, msg, ss = await run_task(context)
            if ok:
                await send_tg(f"✅ <b>Svyun 签到</b>\n结果: {msg}", photo=ss)
                break
            else:
                if attempt == 2:
                    await send_tg(f"❌ <b>Svyun 彻底失败</b>\n原因: {msg}", photo=ss)
                await asyncio.sleep(30)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
