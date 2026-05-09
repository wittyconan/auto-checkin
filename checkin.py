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
                form.add_field('caption', text[:1000])
                await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto", data=form)
            else:
                await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", 
                                   json={'chat_id': TG_CHAT_ID, 'text': text, 'parse_mode': 'HTML'})
        except Exception as e: print(f"  [TG失败] {e}")

# ================= 站点逻辑 =================

async def checkin_miniduo(context):
    print("【miniduo.cn】使用历史稳定基准版...")
    page = await context.new_page()
    try:
        # 恢复 60 秒长等待，不再提前掐断
        await page.goto('https://www.miniduo.cn/login', timeout=60000)
        await asyncio.sleep(5) # 给页面充足的渲染时间

        # 原始成功版的登录逻辑
        email_tab = page.locator('text=邮箱登录')
        if await email_tab.count() > 0:
            await email_tab.click()
            
        await page.locator('input[placeholder*="邮箱"]').fill(MINIDUO_USER)
        await page.locator('input[type="password"]').fill(MINIDUO_PASS)
        await page.get_by_role("button", name=re.compile("登录|Login")).first.click()
        
        # 稳定等待购物车页面
        await page.wait_for_url("**/cart", timeout=30000)
        print("  ✓ 登录成功，等待弹窗与转盘...")
        await asyncio.sleep(10) # 必须死等10秒，让那个公告弹窗出来
        
        # 处理弹窗：兼容“我知道了”和“我已了解”
        notice1 = page.locator('text="我知道了"')
        notice2 = page.locator('text="我已了解"')
        
        if await notice1.count() > 0:
            await notice1.first.click()
            print("  ✓ 关闭 [我知道了] 弹窗")
            await asyncio.sleep(2)
        elif await notice2.count() > 0:
            await notice2.first.click()
            print("  ✓ 关闭 [我已了解] 弹窗")
            await asyncio.sleep(2)
            
        # 抽奖点击
        lottery_btn = page.locator('text="开始抽奖"')
        if await lottery_btn.count() > 0:
            await lottery_btn.first.click(force=True)
            print("  ✓ 文本点击 [开始抽奖]")
        else:
            await page.mouse.click(1160, 860) 
            print("  ✓ 坐标点击 [开始抽奖]")
            
        await asyncio.sleep(5) # 等转盘转完
        return True, "已触发抽奖", await save_debug(page, "miniduo_ok")
    except Exception as e:
        return False, f"错误:{str(e)[:20]}", await save_debug(page, "miniduo_err")
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】物理键盘级输入法 (稳定态，不作更改)...")
    page = await context.new_page()
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        await asyncio.sleep(10)
        
        user_input = page.locator('input[placeholder*="Email"]').first
        await user_input.wait_for(state="visible")
        await user_input.click()
        await user_input.clear()
        await user_input.press_sequentially(SVYUN_USER, delay=100)
        
        pass_input = page.locator('input[type="password"]')
        await pass_input.click()
        await pass_input.clear()
        await pass_input.press_sequentially(SVYUN_PASS, delay=100)
        
        await page.get_by_text("Read and agree").click()
        await asyncio.sleep(1)
        await page.locator('button:has-text("Login")').first.click()
        
        await asyncio.sleep(10)
        btn = page.locator('button:has-text("立即签到"), .checkin-btn')
        if await btn.count() > 0:
            await btn.first.click()
            await asyncio.sleep(5)
            
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
    print("【vps8.zz.cd】网络重试与精准狙击...")
    page = await context.new_page()
    try:
        # 加入网络层面的重试机制，应对 net: 错误
        for attempt in range(2):
            try:
                await page.goto('https://vps8.zz.cd/login', timeout=60000)
                break # 成功则跳出循环
            except Exception as e:
                if "net::" in str(e) and attempt == 0:
                    print("  ! 网络连接被阻断，重试中...")
                    await asyncio.sleep(5)
                else: raise e
                
        await asyncio.sleep(5)
        await page.locator('input[name="email"]').press_sequentially(VPS8_USER, delay=50)
        await page.locator('input[name="password"]').press_sequentially(VPS8_PASS, delay=50)
        
        print("  正在寻找 Turnstile 验证框...")
        try:
            await page.wait_for_selector('iframe[src*="challenges.cloudflare.com"]', state="attached", timeout=15000)
            cf_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            await asyncio.sleep(5)
            target = cf_frame.locator('body')
            if await target.count() > 0:
                print("  ✓ 找到盾牌，执行偏移点击...")
                await target.click(position={"x": 20, "y": 20}, delay=200)
                await asyncio.sleep(5) 
        except: pass # 如果没出验证码就算了，继续往下走
            
        await page.locator('button:has-text("登录")').first.click()
        await asyncio.sleep(10)
        
        btn = page.locator('button:has-text("签到"), #checkin')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "签到成功", await save_debug(page, "vps8_ok")
        return False, "未见按钮", await save_debug(page, "vps8_err")
    except Exception as e:
        return False, f"错误:{str(e)[:20]}", await save_debug(page, "vps8_err")
    finally: await page.close()

# ================= 主流程 =================

async def main():
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 1024})
        
        for name, func in [('Miniduo', checkin_miniduo), ('Svyun', checkin_svyun), ('VPS8', checkin_vps8)]:
            ok, msg, ss = await func(context)
            status = "✅" if ok else "❌"
            await send_tg(f"{status} <b>{name}</b>: {msg}", photo=ss)
            await asyncio.sleep(5)
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
