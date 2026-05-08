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
    print("【miniduo.cn】尝试绕过白屏...")
    page = await context.new_page()
    try:
        # 换回一个非常普通的 PC UA，看能不能骗过
        await page.set_extra_http_headers({"Accept-Language": "zh-CN,zh;q=0.9"})
        await page.goto('https://www.miniduo.cn/login', timeout=60000)
        await asyncio.sleep(15) 
        
        # 暴力检查白屏
        if len(await page.content()) < 500:
            print("  ! 依然白屏，IP 可能已被硬封锁。")
            return False, "白屏阻断 (IP封锁)"

        await page.evaluate(f"""() => {{
            const emailTab = Array.from(document.querySelectorAll('*')).find(el => el.textContent === '邮箱登录');
            if(emailTab) emailTab.click();
            setTimeout(() => {{
                document.querySelector('input[placeholder*="邮箱"]').value = '{MINIDUO_USER}';
                document.querySelector('input[type="password"]').value = '{MINIDUO_PASS}';
                document.querySelector('button[type="submit"], .btn-login').click();
            }}, 1000);
        }}""")
        
        await page.wait_for_url("**/cart", timeout=20000)
        await asyncio.sleep(10)
        await page.mouse.click(1160, 860) 
        return True, "尝试成功"
    except Exception as e:
        await save_debug(page, "miniduo_err")
        return False, "超时或结构改变"
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】适配移动端UI...")
    page = await context.new_page()
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        await asyncio.sleep(10)
        
        # 针对图2的移动端UI进行注入
        print("  正在向移动端输入框注入...")
        await page.evaluate(f"""() => {{
            const inputs = document.querySelectorAll('input');
            // 找到第一个文本框和第一个密码框
            const user = Array.from(inputs).find(i => i.placeholder.includes('Email') || i.type === 'text');
            const pass = Array.from(inputs).find(i => i.type === 'password');
            const agree = document.querySelector('input[type="checkbox"]');
            
            if(user) user.value = '{SVYUN_USER}';
            if(pass) pass.value = '{SVYUN_PASS}';
            if(agree) agree.click();
            
            // 触发事件
            ['input', 'change', 'blur'].forEach(ev => {{
                if(user) user.dispatchEvent(new Event(ev, {{ bubbles: true }}));
                if(pass) pass.dispatchEvent(new Event(ev, {{ bubbles: true }}));
            }});
        }}""")
        
        await asyncio.sleep(2)
        # 按钮文本从截图看是 "Log in now"
        login_btn = page.locator('button:has-text("Log in now"), button:has-text("Login")')
        await login_btn.first.click(force=True)
        
        await asyncio.sleep(10)
        # 寻找签到按钮（移动端通常也是立即签到）
        btn = page.locator('button:has-text("立即签到"), .checkin-btn, a:has-text("立即签到")')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "签到成功"
        return False, "未见签到按钮"
    except Exception as e:
        await save_debug(page, "svyun_err")
        return False, "流程中断"
    finally: await page.close()

async def checkin_vps8(context):
    print("【vps8.zz.cd】强攻执行...")
    page = await context.new_page()
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        await asyncio.sleep(15) 
        await page.evaluate(f"""() => {{
            const email = document.querySelector('input[name="email"]');
            const pass = document.querySelector('input[name="password"]');
            if(email) email.value = '{VPS8_USER}';
            if(pass) pass.value = '{VPS8_PASS}';
        }}""")
        # 模糊匹配登录按钮
        await page.locator('button:has-text("登录"), button:has-text("Login")').first.click()
        await asyncio.sleep(10)
        btn = page.locator('button:has-text("签到"), #checkin')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "完成"
        return False, "未见按钮"
    except Exception as e:
        await save_debug(page, "vps8_err")
        return False, "执行异常"
    finally: await page.close()

# ================= 主流程 =================

async def main():
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        # 核心压榨：不再全局使用移动端伪装，只在需要的 context 切换
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        # 顺序执行任务
        results = {}
        results['miniduo'] = await checkin_miniduo(context)
        await asyncio.sleep(5)
        
        # Svyun 特别处理：如果普通模式不行，可以单独给它开个移动端 context
        results['svyun'] = await checkin_svyun(context)
        
        await asyncio.sleep(5)
        results['vps8'] = await checkin_vps8(context)
        
        report = f"🔔 <b>自动签到汇总 [{datetime.now().strftime('%H:%M')}]</b>\n"
        for s, (ok, msg) in results.items():
            report += f"{'✅' if ok else '❌'} {s}: {msg}\n"
        
        print(report)
        await send_tg(report)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
