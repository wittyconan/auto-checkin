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
            form.add_field('caption' if photo else 'text', text)
            await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/{'sendPhoto' if photo else 'sendMessage'}", data=form)
        except: pass

# ================= 业务流程 =================

async def run_task(context):
    page = await context.new_page()
    # 强制增加超时容忍
    page.set_default_timeout(45000)
    
    try:
        # 1. 直接强攻登录
        print("  -> 访问登录页...")
        await page.goto('https://www.svyun.com/plugin/86/index.htm', wait_until="networkidle")
        
        # 检查是否在登录页
        if await page.locator('input[placeholder*="Email"]').is_visible():
            print("  -> 使用 JS 注入方式进行强制登录...")
            # 暴力 JS 注入：填充账号密码、强制勾选、强制点击登录按钮
            await page.evaluate(f"""() => {{
                document.querySelector('input[placeholder*="Email"]').value = '{SVYUN_USER}';
                document.querySelector('input[type="password"]').value = '{SVYUN_PASS}';
                // 暴力寻找并点击所有可能的 Checkbox
                document.querySelectorAll('input[type="checkbox"]').forEach(i => i.checked = true);
                // 暴力寻找并触发登录按钮
                const loginBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Login'));
                if(loginBtn) loginBtn.click();
            }}""")
            await asyncio.sleep(10)
        
        # 2. 模拟进入签到模块
        print("  -> 跳转签到路径...")
        await page.goto('https://www.svyun.com/plugin/94/index.htm', wait_until="networkidle")
        await asyncio.sleep(5)

        # 3. 强力扫描签到按钮
        res_msg = "操作失败"
        for i in range(10):
            # 自动移除遮挡层
            await page.evaluate("document.querySelectorAll('.layui-layer, .modal-backdrop').forEach(el => el.remove())")
            
            # 检查已签到状态
            content = await page.content()
            if "已签到" in content:
                return True, "今日已签到过", await save_debug(page, "done")
            
            # 暴力执行 JS 签到点击
            btn_found = await page.evaluate("""() => {
                const btn = Array.from(document.querySelectorAll('button, a')).find(el => el.innerText.includes('立即签到'));
                if(btn) {
                    btn.click();
                    return true;
                }
                return false;
            }""")
            
            if btn_found:
                print("  -> JS 指令执行成功")
                await asyncio.sleep(5)
                return True, "签到指令已发送", await save_debug(page, "success")
            
            print(f"  ...等待按钮加载 ({i+1}/10)")
            await asyncio.sleep(3)

        return False, "超时未能触发签到按钮", await save_debug(page, "timeout")

    except Exception as e:
        return False, f"流程异常: {str(e)[:30]}", await save_debug(page, "crash")
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        
        # 增加一次全局重试
        for attempt in range(2):
            ok, msg, ss = await run_task(context)
            if ok:
                await send_tg(f"✅ <b>Svyun 签到报告</b>\n结果: {msg}", photo=ss)
                break
            elif attempt == 1:
                await send_tg(f"❌ <b>Svyun 签到失败</b>\n原因: {msg}", photo=ss)
            await asyncio.sleep(10)
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
