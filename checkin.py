#!/usr/bin/env python3
import os, re, asyncio, random
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

# ================= 核心业务 =================

async def run_task(context):
    page = await context.new_page()
    page.set_default_timeout(60000)
    
    try:
        print(f"  -> [{datetime.now().strftime('%H:%M:%S')}] 访问登录页...")
        await page.goto('https://www.svyun.com/plugin/86/index.htm', wait_until="commit")
        await asyncio.sleep(8) # 给够时间加载

        # 1. 登录逻辑加固
        is_login_form = await page.evaluate("() => !!document.querySelector('input')")
        if is_login_form:
            print("  -> 执行高强度 JS 登录填充...")
            await page.evaluate(f"""() => {{
                // 遍历所有 input 尝试填充
                const inputs = document.querySelectorAll('input');
                inputs.forEach(i => {{
                    if(i.type === 'password') i.value = '{SVYUN_PASS}';
                    else if(i.placeholder.includes('Email') || i.type === 'text') i.value = '{SVYUN_USER}';
                    else if(i.type === 'checkbox') i.checked = true;
                }});
                // 寻找 Login 按钮并点击
                const btns = Array.from(document.querySelectorAll('button'));
                const loginBtn = btns.find(b => b.innerText.includes('Login') || b.textContent.includes('Login'));
                if(loginBtn) loginBtn.click();
            }}""")
            await asyncio.sleep(10)

        # 2. 跳转签到页
        print("  -> 跳转签到页...")
        await page.goto('https://www.svyun.com/plugin/94/index.htm', wait_until="commit")
        await asyncio.sleep(8)

        # 3. 签到按钮扫描
        res_msg = "未找到按钮"
        for i in range(15):
            # 移除遮挡
            await page.evaluate("document.querySelectorAll('.layui-layer, .modal, .mask').forEach(el => el.remove())")
            
            content = await page.content()
            if "已签到" in content:
                return True, "今日已成功签到", await save_debug(page, "done")

            # 强点击立即签到
            clicked = await page.evaluate("""() => {
                const targets = Array.from(document.querySelectorAll('button, a, div, span'));
                const btn = targets.find(el => el.innerText.trim() === '立即签到');
                if(btn) { btn.click(); return true; }
                return false;
            }""")
            
            if clicked:
                print("  -> 签到指令已发送")
                await asyncio.sleep(5)
                if "已签到" in await page.content():
                    return True, "签到成功！", await save_debug(page, "success")
                return True, "指令已发，请核实", await save_debug(page, "sent")
            
            await asyncio.sleep(2)
            print(f"  ...等待按钮 ({i+1}/15)")

        return False, "未能识别签到按钮", await save_debug(page, "btn_error")

    except Exception as e:
        return False, f"崩溃: {str(e)[:30]}", await save_debug(page, "crash")
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024}, # 调高高度，防止按钮在视口外
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
                    await send_tg(f"❌ <b>Svyun 失败</b>\n错误: {msg}", photo=ss)
                await asyncio.sleep(30)
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
