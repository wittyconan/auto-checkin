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
    await page.screenshot(path=path)
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
                form.add_field('caption', text[:1000], content_type='text/plain')
                await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto", data=form)
            else:
                await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", 
                                   json={'chat_id': TG_CHAT_ID, 'text': text, 'parse_mode': 'HTML'})
        except Exception as e: print(f"  [TG发送失败] {e}")

# ================= 站点逻辑 =================

async def checkin_miniduo(context):
    print("【miniduo.cn】正在执行极致兼容登录...")
    page = await context.new_page()
    try:
        await page.goto('https://www.miniduo.cn/login', timeout=60000)
        # 根据图1，点击“邮箱登录”标签
        email_tab = page.locator('text=邮箱登录')
        await email_tab.wait_for(state="visible", timeout=20000)
        await email_tab.click()
        
        # 填充账号
        await page.type('input[placeholder*="邮箱"]', MINIDUO_USER, delay=100)
        await page.type('input[type="password"]', MINIDUO_PASS, delay=100)
        await page.get_by_role("button", name="登录").click()
        
        await page.wait_for_url("**/cart", timeout=20000)
        await asyncio.sleep(8)
        # 处理弹窗和转盘
        try: await page.get_by_text("我知道了").click(timeout=5000)
        except: pass
        await page.mouse.click(1160, 860) 
        return True, "已尝试触发签到", await save_debug(page, "miniduo_ok")
    except Exception as e:
        return False, f"异常: {str(e)[:20]}", await save_debug(page, "miniduo_err")
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】正在处理登录...")
    page = await context.new_page()
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        # 根据图2，这里的输入框可能没有 name，使用 placeholder 匹配
        user_input = page.locator('input[placeholder*="Email"], input[type="text"]')
        await user_input.wait_for(state="visible", timeout=20000)
        
        await user_input.type(SVYUN_USER, delay=100)
        await page.locator('input[type="password"]').type(SVYUN_PASS, delay=100)
        
        # 勾选协议 (根据图2，点击文字部分)
        await page.get_by_text("Read and agree").click()
        await page.locator('button:has-text("Login")').click()
        
        await asyncio.sleep(8)
        btn = page.locator('button:has-text("立即签到"), .checkin-btn')
        if await btn.count() > 0:
            await btn.first.click()
            await asyncio.sleep(5)
            # 跳转获取次数
            await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2')
            await asyncio.sleep(3)
            return True, "签到成功", await save_debug(page, "svyun_res")
        return False, "未见签到按钮", await save_debug(page, "svyun_fail")
    except Exception as e:
        return False, f"异常: {str(e)[:20]}", await save_debug(page, "svyun_err")
    finally: await page.close()

async def checkin_vps8(context):
    print("【vps8.zz.cd】处理人机验证...")
    page = await context.new_page()
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        # 根据图3，填入信息
        await page.locator('input[name="email"]').type(VPS8_USER, delay=100)
        await page.locator('input[name="password"]').type(VPS8_PASS, delay=100)
        
        # 处理 Turnstile 验证
        print("  正在尝试点击 CF 验证...")
        for i in range(15):
            cf_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            if await cf_frame.locator('body').count() > 0:
                await cf_frame.locator('body').click()
                print(f"  ✓ 已点击验证框 (第{i+1}秒)")
                break
            await asyncio.sleep(1)
            
        await page.locator('button:has-text("登录"), button:has-text("Login")').first.click()
        await asyncio.sleep(10)
        
        btn = page.locator('button:has-text("签到"), #checkin')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "签到成功", await save_debug(page, "vps8_ok")
        return False, "未见签到按钮", await save_debug(page, "vps8_fail")
    except Exception as e:
        return False, f"异常: {str(e)[:20]}", await save_debug(page, "vps8_err")
    finally: await page.close()

# ================= 主流程 =================

async def main():
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 1024})
        
        # 执行
        results = [
            ('Miniduo', await checkin_miniduo(context)),
            ('Svyun', await checkin_svyun(context)),
            ('VPS8', await checkin_vps8(context))
        ]
        
        report = f"🔔 <b>自动签到报告 [{datetime.now().strftime('%H:%M')}]</b>\n\n"
        for name, (ok, msg, ss) in results:
            status = "✅" if ok else "❌"
            await send_tg(f"{status} <b>{name}</b>: {msg}", photo=ss)
            report += f"{status} {name}: {msg}\n"
        
        await send_tg(report)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
