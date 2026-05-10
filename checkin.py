#!/usr/bin/env python3
import os, re, asyncio
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
        print(f"  -> [{datetime.now().strftime('%H:%M:%S')}] 访问登录页...")
        await page.goto('https://www.svyun.com/plugin/86/index.htm', wait_until="networkidle")
        await asyncio.sleep(3)

        # 1. 纯净的物理模拟登录
        email_input = page.locator('input[placeholder*="Email"]').first
        if await email_input.is_visible():
            print("  -> 正在填写账号密码...")
            # 使用最稳妥的 fill，它能完美触发 Vue/React 的 input 事件
            await email_input.fill(SVYUN_USER)
            
            pwd_input = page.locator('input[type="password"]').first
            await pwd_input.fill(SVYUN_PASS)
            
            print("  -> 正在物理点击同意协议...")
            # 放弃 JS，直接点击页面上显示的文字标签
            agree_text = page.locator('text="Read and agree"').first
            await agree_text.click()
            await asyncio.sleep(1) # 停顿一下，让动画和状态反应过来
            
            print("  -> 点击登录按钮...")
            login_btn = page.locator('button:has-text("Login")').first
            await login_btn.click()
            
            # 等待网络请求完成（登录请求）
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(5)
            
        # 2. 进入签到页
        print("  -> 跳转签到页...")
        await page.goto('https://www.svyun.com/plugin/94/index.htm', wait_until="networkidle")
        await asyncio.sleep(5)

        # 3. 扫描并签到
        print("  -> 检查签到状态...")
        print(f"  -> 当前URL: {page.url}")
        print(f"  -> 页面标题: {await page.title()}")
        
        content = await page.content()
        
        # 先检查是否已经签到过
        if "已签到" in content:
            return True, "今日已成功签到", await save_debug(page, "final_done")
        
        # 保存调试截图
        await save_debug(page, "before_checkin")
        
        # 尝试多种定位方式
        print("  -> 尝试定位签到按钮...")
        
        # 尝试各种可能的按钮选择器
        button_selectors = [
            'button:has-text("立即签到")',
            'a:has-text("立即签到")',
            '.btn:has-text("立即签到")',
            'button:has-text("签到")',
            'a:has-text("签到")',
            '[class*="sign"]',
            '[class*="checkin"]',
        ]
        
        sign_btn = None
        for sel in button_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible():
                    sign_btn = btn
                    print(f"  -> 使用选择器找到按钮: {sel}")
                    break
            except:
                continue
        
        if sign_btn:
            print("  -> 找到签到按钮，正在点击...")
            await sign_btn.click(force=True)
            await asyncio.sleep(5)
            
            # 检查是否跳转到抽奖页面
            if "抽奖" in await page.title() or "/plugin/95/" in page.url:
                print("  -> 页面跳转到抽奖页，返回签到页验证...")
                await page.goto('https://www.svyun.com/plugin/94/index.htm', wait_until="networkidle")
                await asyncio.sleep(5)
            
            # 再次验证签到状态
            content = await page.content()
            if "已签到" in content:
                return True, "签到动作成功执行！", await save_debug(page, "success")
            return True, "按钮已点击，请看截图确认", await save_debug(page, "clicked")
        else:
            print("  -> 所有选择器都未找到按钮！")
            await save_debug(page, "no_button")
            return False, "未能找到签到按钮", await save_debug(page, "fail_btn")

    except Exception as e:
        return False, f"流程崩溃: {str(e)[:30]}", await save_debug(page, "crash")
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
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
                await asyncio.sleep(20)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
