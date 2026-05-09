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

# ================= 工具函数 =================
async def save_debug(page, name):
    path = f"{SCREENSHOT_DIR}/debug_{name}_{datetime.now().strftime('%H%M%S')}.png"
    try:
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

# ================= 站点逻辑 =================

async def checkin_miniduo(context):
    print("【miniduo.cn】快照探测 (GitHub IP大概率已死)...")
    page = await context.new_page()
    try:
        # 15秒快速探测，不行直接报错跳过，不浪费生命
        await page.goto('https://www.miniduo.cn/login', timeout=15000)
        await asyncio.sleep(3)
        if len(await page.content()) < 500:
            return False, "IP已被完全封锁 (白屏)", None
            
        # 如果奇迹般地进去了，执行历史成功逻辑
        await page.get_by_text("邮箱登录").click()
        await page.locator('input[placeholder*="邮箱"]').fill(MINIDUO_USER)
        await page.locator('input[type="password"]').fill(MINIDUO_PASS)
        await page.get_by_role("button", name=re.compile("登录|Login")).first.click()
        
        await page.wait_for_url("**/cart", timeout=20000)
        await asyncio.sleep(8)
        
        for notice in ['我知道了', '我已了解']:
            el = page.locator(f'text="{notice}"')
            if await el.count() > 0:
                await el.first.click(force=True)
                await asyncio.sleep(2)
                break
                
        lottery = page.locator('text="开始抽奖"')
        if await lottery.count() > 0:
            await lottery.first.click(force=True)
        else:
            await page.mouse.click(1160, 860) 
            
        await asyncio.sleep(5) 
        return True, "已触发抽奖", await save_debug(page, "miniduo_ok")
    except Exception as e:
        return False, f"超时/墙拦截 ({str(e)[:15]})", await save_debug(page, "miniduo_err")
    finally: await page.close()


# 🌟 Svyun：拨乱反正！恢复你历史成功的原版 JS 注入 🌟
async def checkin_svyun(context):
    print("【svyun.com】使用历史 100% 成功 JS 注入版...")
    page = await context.new_page()
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        await asyncio.sleep(8)
        
        # 核心：这就是你当年唯一成功的那套注入代码，原封不动！
        await page.evaluate(f"""() => {{
            const inputs = document.querySelectorAll('input');
            const user = Array.from(inputs).find(i => i.placeholder?.includes('Email') || i.type === 'text');
            const pass = Array.from(inputs).find(i => i.type === 'password');
            const agree = document.querySelector('input[type="checkbox"]');
            if(user) user.value = '{SVYUN_USER}';
            if(pass) pass.value = '{SVYUN_PASS}';
            if(agree) agree.click();
            ['input', 'change', 'blur'].forEach(ev => {{
                if(user) user.dispatchEvent(new Event(ev, {{ bubbles: true }}));
                if(pass) pass.dispatchEvent(new Event(ev, {{ bubbles: true }}));
            }});
        }}""")
        await asyncio.sleep(2)
        await page.locator('button:has-text("Log in now"), button:has-text("Login")').first.click(force=True)
        
        await asyncio.sleep(10)
        # 签到
        btn = page.locator('button:has-text("立即签到"), .checkin-btn')
        if await btn.count() > 0:
            await btn.first.click()
            await asyncio.sleep(5)
            
            # 抓取次数与详情弹窗
            await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2')
            await asyncio.sleep(5)
            text = await page.inner_text("body")
            count = re.search(r"剩余抽奖次数\s*(\d+)\s*次", text)
            msg = f"剩余:{count.group(1)}次" if count else "签到成功"
            
            try: await page.get_by_text("查看详情").click(timeout=5000); await asyncio.sleep(2)
            except: pass
            
            return True, msg, await save_debug(page, "svyun_res")
        return False, "未见签到按钮", await save_debug(page, "svyun_fail")
    except Exception as e:
        return False, f"错误:{str(e)[:15]}", await save_debug(page, "svyun_err")
    finally: await page.close()


async def checkin_vps8(context):
    print("【vps8.zz.cd】强攻 CF Turnstile...")
    page = await context.new_page()
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        await asyncio.sleep(5)
        
        await page.locator('input[name="email"]').fill(VPS8_USER)
        await page.locator('input[name="password"]').fill(VPS8_PASS)
        
        print("  正在尝试物理点击 CF 盾...")
        cf_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]').first
        if await cf_iframe.count() > 0:
            box = await cf_iframe.bounding_box()
            if box:
                # 点击偏左侧 30 像素位置，正中复选框靶心
                click_x = box['x'] + 30
                click_y = box['y'] + (box['height'] / 2)
                await page.mouse.click(click_x, click_y, delay=200)
                await asyncio.sleep(5) 
                
        # 不管点没点中，强制发起登录
        await page.locator('button:has-text("登录"), button:has-text("Login")').first.click(force=True)
        await asyncio.sleep(10)
        
        btn = page.locator('button:has-text("签到"), #checkin')
        if await btn.count() > 0:
            await btn.first.click(force=True)
            return True, "签到成功", await save_debug(page, "vps8_ok")
        return False, "未见签到按钮", await save_debug(page, "vps8_err")
    except Exception as e:
        return False, f"错误:{str(e)[:15]}", await save_debug(page, "vps8_err")
    finally: await page.close()

# ================= 主流程 =================

async def main():
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 1024})
        
        for name, func in [('Miniduo', checkin_miniduo), ('Svyun', checkin_svyun), ('VPS8', checkin_vps8)]:
            try:
                ok, msg, ss = await func(context)
                status = "✅" if ok else "❌"
                await send_tg(f"{status} <b>{name}</b>: {msg}", photo=ss)
            except Exception as global_e:
                await send_tg(f"❌ <b>{name}</b>: 发生致命崩溃")
            finally:
                await asyncio.sleep(5)
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
