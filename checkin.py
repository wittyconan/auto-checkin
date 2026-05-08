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
    print("【miniduo.cn】执行双重点击流...")
    page = await context.new_page()
    try:
        await page.goto('https://www.miniduo.cn/login', timeout=60000)
        # 登录逻辑
        await page.get_by_text("邮箱登录").click()
        await page.locator('input[placeholder*="邮箱"]').fill(MINIDUO_USER)
        await page.locator('input[type="password"]').fill(MINIDUO_PASS)
        await page.get_by_role("button", name="登录").click()
        await page.wait_for_url("**/cart", timeout=20000)
        
        await asyncio.sleep(8) # 等待公告弹出
        
        # 第一步：点击“我知道了” (针对图1红箭头1)
        notice_btn = page.get_by_text("我知道了")
        if await notice_btn.count() > 0:
            await notice_btn.click()
            print("  ✓ 已关闭公告弹窗")
            await asyncio.sleep(2)

        # 第二步：点击“开始抽奖” (针对图1红箭头2)
        # 尝试通过文本点击，如果不行则坐标点击
        lottery_btn = page.get_by_text("开始抽奖")
        if await lottery_btn.count() > 0:
            await lottery_btn.first.click(force=True)
            print("  ✓ 成功触发抽奖按钮")
        else:
            await page.mouse.click(1160, 860) 
            print("  ! 尝试坐标点击抽奖")
            
        await asyncio.sleep(3)
        ss = await save_debug(page, "miniduo_final")
        return True, "签到成功", ss
    except Exception as e:
        return False, f"异常: {str(e)[:30]}", await save_debug(page, "miniduo_err")
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】优化跳转逻辑...")
    page = await context.new_page()
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        # 注入登录 (同前)
        await page.evaluate(f"window.login_info = {{u:'{SVYUN_USER}', p:'{SVYUN_PASS}'}}")
        await page.evaluate("""() => {
            const inputs = document.querySelectorAll('input');
            const user = Array.from(inputs).find(i => i.placeholder?.includes('Email') || i.type === 'text');
            const pass = Array.from(inputs).find(i => i.type === 'password');
            if(user) user.value = window.login_info.u;
            if(pass) pass.value = window.login_info.p;
            document.querySelector('input[type="checkbox"]').click();
        }""")
        await page.locator('button:has-text("Log in now"), button:has-text("Login")').first.click()
        await page.wait_for_load_state('networkidle')
        
        # 签到
        await page.locator('button:has-text("立即签到"), .checkin-btn').first.click()
        await asyncio.sleep(5)
        
        # 优化跳转抽奖页，不再死等图片加载
        await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2', wait_until='domcontentloaded')
        await asyncio.sleep(5)
        
        # 提取文字
        content = await page.inner_text("body")
        count = re.search(r"剩余抽奖次数\s*(\d+)\s*次", content)
        msg = f"剩余:{count.group(1)}次" if count else "已完成签到"
        
        # 尝试点击查看详情 (图2)
        try:
            await page.get_by_text("查看详情").click(timeout=5000)
            await asyncio.sleep(2)
        except: pass
        
        ss = await save_debug(page, "svyun_res")
        return True, msg, ss
    except Exception as e:
        return False, f"异常: {str(e)[:30]}", await save_debug(page, "svyun_err")
    finally: await page.close()

async def checkin_vps8(context):
    print("【vps8.zz.cd】强制探测Turnstile...")
    page = await context.new_page()
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        # 先输账号密码
        await page.evaluate(f"document.querySelector('input[name=\"email\"]').value='{VPS8_USER}'")
        await page.evaluate(f"document.querySelector('input[name=\"password\"]').value='{VPS8_PASS}'")
        
        # 强制探测验证框 (图3)
        print("  正在探测 CF 验证框...")
        for i in range(10): # 循环探测 10 次
            cf_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            if await cf_frame.locator('body').count() > 0:
                await cf_frame.locator('body').click()
                print(f"  ✓ 探测到并点击验证框 (第{i+1}秒)")
                break
            await asyncio.sleep(1)
        
        await page.locator('button:has-text("登录"), button:has-text("Login")').first.click()
        await asyncio.sleep(8)
        
        # 签到
        btn = page.locator('button:has-text("签到"), #checkin')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "签到成功", await save_debug(page, "vps8_ok")
        return False, "未见签到按钮", await save_debug(page, "vps8_fail")
    except Exception as e:
        return False, str(e)[:30], await save_debug(page, "vps8_err")
    finally: await page.close()

# ================= 主流程 =================

async def main():
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 1024})
        
        # 执行顺序压榨
        sites = [('Miniduo', checkin_miniduo), ('Svyun', checkin_svyun), ('VPS8', checkin_vps8)]
        for name, func in sites:
            ok, msg, ss = await func(context)
            await send_tg(f"<b>{name}</b>: {msg}", photo=ss)
            await asyncio.sleep(5)
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
