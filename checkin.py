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
    print("【miniduo.cn】正在尝试破解白屏...")
    page = await context.new_page()
    try:
        await page.goto('https://www.miniduo.cn/login', timeout=60000)
        await asyncio.sleep(15) 
        if len(await page.content()) < 500: return False, "白屏(IP封锁)", None
        
        # 监听式注入
        await page.wait_for_selector('input[placeholder*="邮箱"]', timeout=20000)
        await page.evaluate(f"""() => {{
            const tabs = Array.from(document.querySelectorAll('*')).find(el => el.textContent === '邮箱登录');
            if(tabs) tabs.click();
            document.querySelector('input[placeholder*="邮箱"]').value = '{MINIDUO_USER}';
            document.querySelector('input[type="password"]').value = '{MINIDUO_PASS}';
            document.querySelector('button[type="submit"], .btn-login').click();
        }}""")
        await page.wait_for_url("**/cart", timeout=20000)
        await asyncio.sleep(8)
        # 弹窗处理
        try: await page.get_by_text("我知道了").click(timeout=3000)
        except: pass
        await page.mouse.click(1160, 860) 
        return True, "签到成功", await save_debug(page, "miniduo_ok")
    except Exception as e:
        return False, f"异常: {str(e)[:20]}", await save_debug(page, "miniduo_err")
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】监听式注入启动...")
    page = await context.new_page()
    try:
        # 使用 domcontentloaded 快速切入
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000, wait_until='domcontentloaded')
        
        # 关键：显式等待输入框，无视 Loading 动画
        user_selector = 'input[name="username"]'
        await page.wait_for_selector(user_selector, state="visible", timeout=30000)
        
        print("  ✓ 检测到登录框，注入数据...")
        await page.evaluate(f"""() => {{
            const u = document.querySelector('input[name="username"]');
            const p = document.querySelector('input[name="password"]');
            const c = document.querySelector('input[type="checkbox"]');
            if(u) {{ u.value = '{SVYUN_USER}'; u.dispatchEvent(new Event('input', {{ bubbles: true }})); }}
            if(p) {{ p.value = '{SVYUN_PASS}'; p.dispatchEvent(new Event('input', {{ bubbles: true }})); }}
            if(c) c.click();
        }}""")
        
        await asyncio.sleep(1)
        await page.locator('button:has-text("Log in now"), button:has-text("Login")').first.click(force=True)
        await asyncio.sleep(8)
        
        # 点击签到
        checkin_btn = page.locator('button:has-text("立即签到"), .checkin-btn')
        if await checkin_btn.count() > 0:
            await checkin_btn.first.click()
            await asyncio.sleep(5)
            
        # 跳转抽奖页获取次数
        await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2', wait_until='domcontentloaded')
        await asyncio.sleep(5)
        content = await page.inner_text("body")
        count = re.search(r"剩余抽奖次数\s*(\d+)\s*次", content)
        msg = f"剩余:{count.group(1)}次" if count else "签到完成"
        
        # 点击查看详情弹出中奖图
        try: await page.get_by_text("查看详情").click(timeout=5000); await asyncio.sleep(2)
        except: pass
        
        return True, msg, await save_debug(page, "svyun_res")
    except Exception as e:
        return False, f"异常: {str(e)[:20]}", await save_debug(page, "svyun_err")
    finally: await page.close()

async def checkin_vps8(context):
    print("【vps8.zz.cd】处理Turnstile验证...")
    page = await context.new_page()
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        
        # 等待输入框出现
        await page.wait_for_selector('input[name="email"]', state="visible", timeout=30000)
        
        await page.evaluate(f"""() => {{
            document.querySelector('input[name="email"]').value = '{VPS8_USER}';
            document.querySelector('input[name="password"]').value = '{VPS8_PASS}';
        }}""")
        
        print("  正在探测并点击验证框...")
        # 循环探测 Turnstile iframe
        for i in range(10):
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
        return False, "未见按钮", await save_debug(page, "vps8_fail")
    except Exception as e:
        return False, f"异常: {str(e)[:20]}", await save_debug(page, "vps8_err")
    finally: await page.close()

# ================= 主流程 =================

async def main():
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 1024})
        
        results = []
        # 顺序执行，防止并发冲突
        results.append(('Miniduo', await checkin_miniduo(context)))
        await asyncio.sleep(10)
        results.append(('Svyun', await checkin_svyun(context)))
        await asyncio.sleep(10)
        results.append(('VPS8', await checkin_vps8(context)))
        
        report = f"🔔 <b>自动签到报告 [{datetime.now().strftime('%m-%d %H:%M')}]</b>\n\n"
        for name, (ok, msg, ss) in results:
            report_line = f"{'✅' if ok else '❌'} <b>{name}</b>: {msg}"
            await send_tg(report_line, photo=ss)
            report += report_line + "\n"
        
        await send_tg(report)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
