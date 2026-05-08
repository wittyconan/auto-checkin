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

async def checkin_svyun(context):
    print("【svyun.com】提取抽奖详情...")
    page = await context.new_page()
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        await asyncio.sleep(5)
        # JS 注入登录
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
        await page.locator('button:has-text("Log in now"), button:has-text("Login")').first.click(force=True)
        await page.wait_for_load_state('networkidle')
        
        # 签到
        await page.locator('button:has-text("立即签到"), .checkin-btn').first.click()
        await asyncio.sleep(5)
        
        # 跳转抽奖页 (图1)
        await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2')
        await asyncio.sleep(3)
        
        # 提取页面文字次数
        draw_text = await page.inner_text("body")
        count_match = re.search(r"剩余抽奖次数\s*(\d+)\s*次", draw_text)
        count_info = f"剩余次数: {count_match.group(1)}" if count_match else "未提取到次数"
        
        # 点击“查看详情”弹出图2
        detail_btn = page.locator('text=查看详情')
        if await detail_btn.count() > 0:
            await detail_btn.click()
            await asyncio.sleep(2)
            ss = await save_debug(page, "svyun_detail") # 截取图2弹窗
        else:
            ss = await save_debug(page, "svyun_page") # 没按钮就截全屏
            
        return True, f"签到成功 | {count_info}", ss
    except Exception as e:
        return False, f"异常: {str(e)[:30]}", await save_debug(page, "svyun_err")
    finally: await page.close()

async def checkin_vps8(context):
    print("【vps8.zz.cd】处理 Turnstile 验证...")
    page = await context.new_page()
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        await asyncio.sleep(5)
        
        # 注入账号密码
        await page.evaluate(f"""() => {{
            document.querySelector('input[name="email"]').value = '{VPS8_USER}';
            document.querySelector('input[name="password"]').value = '{VPS8_PASS}';
        }}""")
        
        # 针对图3：点击 Cloudflare Turnstile 选框
        # 这种验证通常在 iframe 里，我们通过寻找包含 verify 的文本或特定选择器尝试点击
        print("  尝试勾选人机验证...")
        try:
            # 找到 Turnstile 的 iframe 并点击其主体
            cf_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            await cf_frame.locator('body').click(timeout=5000)
            await asyncio.sleep(3) # 等待验证通过
        except:
            print("  未检测到验证框或点击失败，尝试直接提交")

        await page.locator('button:has-text("登录"), button:has-text("Login")').first.click()
        await asyncio.sleep(8)
        
        # 签到
        btn = page.locator('button:has-text("签到"), #checkin')
        if await btn.count() > 0:
            await btn.first.click()
            await asyncio.sleep(2)
            ss = await save_debug(page, "vps8_success")
            return True, "完成", ss
        return False, "未见按钮", await save_debug(page, "vps8_fail")
    except Exception as e:
        return False, f"异常: {str(e)[:30]}", await save_debug(page, "vps8_err")
    finally: await page.close()

# ================= 主流程 =================

async def main():
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        report = f"🔔 <b>自动签到报告 [{datetime.now().strftime('%m-%d %H:%M')}]</b>\n\n"
        
        # 执行并汇报 Svyun
        ok1, msg1, ss1 = await checkin_svyun(context)
        report += f"{'✅' if ok1 else '❌'} <b>Svyun</b>: {msg1}\n"
        await send_tg(f"Svyun 签到报告: {msg1}", photo=ss1)
        
        # 执行并汇报 VPS8
        ok2, msg2, ss2 = await checkin_vps8(context)
        report += f"{'✅' if ok2 else '❌'} <b>VPS8</b>: {msg2}\n"
        await send_tg(f"VPS8 签到报告: {msg2}", photo=ss2)
        
        # 汇总信息发一次文字
        await send_tg(report)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
