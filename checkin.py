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
    await page.screenshot(path=path, full_page=True)
    print(f"  [Debug] 截图已保存: {path}")

async def send_tg(text):
    if not TG_BOT_TOKEN: return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", 
                           json={'chat_id': TG_CHAT_ID, 'text': text, 'parse_mode': 'HTML'})

# ================= 站点逻辑 =================

async def checkin_miniduo(context):
    print("【miniduo.cn】强攻执行中...")
    page = await context.new_page()
    try:
        # 针对白屏，尝试使用移动端伪装并在加载后强制等待
        await page.goto('https://www.miniduo.cn/login', timeout=60000)
        await asyncio.sleep(12) 
        
        # JS 注入登录
        await page.evaluate(f"""() => {{
            const tabs = Array.from(document.querySelectorAll('div, span, a'));
            const emailTab = tabs.find(el => el.textContent.includes('邮箱登录'));
            if(emailTab) emailTab.click();
        }}""")
        await asyncio.sleep(2)
        
        await page.evaluate(f"""() => {{
            document.querySelector('input[placeholder*="邮箱"]').value = '{MINIDUO_USER}';
            document.querySelector('input[type="password"]').value = '{MINIDUO_PASS}';
            document.querySelector('button[type="submit"], .btn-login').click();
        }}""")
        
        await page.wait_for_url("**/cart", timeout=20000)
        print("  ✓ 登录成功，正在触发转盘...")
        await asyncio.sleep(10)
        # 坐标点击保底
        await page.mouse.click(1160, 860) 
        return True, "已执行JS注入与坐标点击"
    except Exception as e:
        await save_debug(page, "miniduo_err")
        return False, f"异常: {str(e)[:30]}"
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】JS暴力注入中...")
    page = await context.new_page()
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        await asyncio.sleep(10)
        
        # 直接通过 JS 强行赋值并勾选
        print("  正在尝试 JS 注入账号密码...")
        await page.evaluate(f"""() => {{
            const user = document.querySelector('input[name="username"]');
            const pass = document.querySelector('input[name="password"]');
            const agree = document.querySelector('input[type="checkbox"]');
            if(user) user.value = '{SVYUN_USER}';
            if(pass) pass.value = '{SVYUN_PASS}';
            if(agree) agree.checked = true;
            // 触发 input 事件防止前端校验失效
            user.dispatchEvent(new Event('input', {{ bubbles: true }}));
            pass.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}""")
        
        await asyncio.sleep(2)
        await page.click('button:has-text("Login")', force=True)
        await page.wait_for_load_state('networkidle', timeout=20000)
        
        # 寻找签到按钮
        btn = page.locator('button:has-text("立即签到"), .checkin-btn')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "签到成功"
        return False, "登录完成但未见签到按钮"
    except Exception as e:
        await save_debug(page, "svyun_err")
        return False, f"异常: {str(e)[:30]}"
    finally: await page.close()

async def checkin_vps8(context):
    print("【vps8.zz.cd】等待系统恢复...")
    page = await context.new_page()
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        if "维护" in await page.content(): return False, "站点维护"
        await asyncio.sleep(15) # 给 CF 盾留出充足时间

        await page.evaluate(f"""() => {{
            document.querySelector('input[name="email"]').value = '{VPS8_USER}';
            document.querySelector('input[name="password"]').value = '{VPS8_PASS}';
        }}""")
        await page.get_by_role("button", name=re.compile("登录|Login")).click()
        await asyncio.sleep(10)
        
        btn = page.locator('button:has-text("签到"), #checkin')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "签到完成"
        return False, "未找到签到按钮"
    except Exception as e:
        await save_debug(page, "vps8_err")
        return False, f"异常: {str(e)[:30]}"
    finally: await page.close()

# ================= 主流程 =================

async def main():
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    async with async_playwright() as p:
        # 增加参数，禁用自动化控制特征
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
        
        # 统一使用移动端伪装环境（对绕过白屏和简单验证更有利）
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            viewport={'width': 390, 'height': 844},
            is_mobile=True
        )
        
        results = {}
        results['miniduo'] = await checkin_miniduo(context)
        await asyncio.sleep(10)
        results['svyun'] = await checkin_svyun(context)
        await asyncio.sleep(10)
        results['vps8'] = await checkin_vps8(context)
        
        report = f"🔔 <b>自动签到报告 [{datetime.now().strftime('%m-%d %H:%M')}]</b>\n"
        for s, (ok, msg) in results.items():
            report += f"{'✅' if ok else '❌'} {s}: {msg}\n"
        
        print(report)
        await send_tg(report)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
