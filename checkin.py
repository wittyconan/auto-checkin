#!/usr/bin/env python3
import os
import re
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

# ================= 配置区域 (已清理无用变量) =================
SVYUN_USER = os.getenv('SVYUN_USER', '')
SVYUN_PASS = os.getenv('SVYUN_PASS', '')
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.getenv('TG_CHAT_ID', '')
SCREENSHOT_DIR = os.getenv('SCREENSHOT_DIR', './screenshots')

# ================= 工具函数 =================
async def save_debug(page, name, clip_element=None):
    """
    智能截图函数：
    如果有 clip_element (局部元素)，则只截取该元素；
    否则截取当前屏幕可是范围，不使用 full_page 防止卡死。
    """
    path = f"{SCREENSHOT_DIR}/debug_{name}_{datetime.now().strftime('%H%M%S')}.png"
    try:
        if clip_element and await clip_element.is_visible():
            await clip_element.screenshot(path=path, timeout=5000)
        else:
            await page.screenshot(path=path, timeout=5000)
        return path
    except Exception as e:
        print(f"  [截图超时忽略] {e}")
        return None

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

# ================= Svyun 独尊版 =================

async def checkin_svyun(context):
    print("【svyun.com】物理键盘级输入法 (稳定态，绝不修改)...")
    page = await context.new_page()
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        await asyncio.sleep(10)
        
        # 1. 物理点击并清空填入账号
        user_input = page.locator('input[placeholder*="Email"]').first
        await user_input.wait_for(state="visible")
        await user_input.click()
        await user_input.clear()
        await user_input.press_sequentially(SVYUN_USER, delay=100)
        
        # 2. 物理点击并清空填入密码
        pass_input = page.locator('input[type="password"]')
        await pass_input.click()
        await pass_input.clear()
        await pass_input.press_sequentially(SVYUN_PASS, delay=100)
        
        # 3. 勾选并登录
        await page.get_by_text("Read and agree").click()
        await asyncio.sleep(1)
        await page.locator('button:has-text("Login")').first.click()
        
        await asyncio.sleep(10)
        # 4. 签到逻辑
        btn = page.locator('button:has-text("立即签到"), .checkin-btn')
        if await btn.count() > 0:
            await btn.first.click()
            await asyncio.sleep(5)
            
            # 5. 跳转抽奖页获取次数
            await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2')
            await asyncio.sleep(5)
            text = await page.inner_text("body")
            count = re.search(r"剩余抽奖次数\s*(\d+)\s*次", text)
            msg = f"剩余:{count.group(1)}次" if count else "签到成功"
            
            # 6. 点击详情并准备局部截图
            target_modal = None
            try: 
                await page.get_by_text("查看详情").click(timeout=5000)
                await asyncio.sleep(2)
                # 尝试捕捉弹出的详情面板（覆盖常见前端框架的模态框 class）
                dialogs = page.locator('.layui-layer, .el-dialog, .modal-content, [role="dialog"]')
                if await dialogs.count() > 0:
                    target_modal = dialogs.first
            except: pass
            
            return True, msg, await save_debug(page, "svyun_res", clip_element=target_modal)
        
        return False, "未见签到按钮", await save_debug(page, "svyun_fail")
    except Exception as e:
        return False, f"错误:{str(e)[:15]}", await save_debug(page, "svyun_err")
    finally: await page.close()

# ================= 主流程 =================

async def main():
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 1024})
        
        try:
            ok, msg, ss = await checkin_svyun(context)
            status = "✅" if ok else "❌"
            report = f"🔔 <b>自动签到报告</b>\n{status} <b>Svyun</b>: {msg}\n时间: {datetime.now().strftime('%m-%d %H:%M')}"
            await send_tg(report, photo=ss)
        except Exception as global_e:
            await send_tg(f"❌ <b>Svyun</b>: 发生致命崩溃 ({str(global_e)[:20]})")
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
