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

# ================= 防崩溃工具函数 =================
async def save_debug(page, name):
    path = f"{SCREENSHOT_DIR}/debug_{name}_{datetime.now().strftime('%H%M%S')}.png"
    try:
        # 【核心修复】：去掉 full_page=True，增加 5000ms 硬超时，防止截图卡死整个程序
        await page.screenshot(path=path, timeout=5000)
        return path
    except Exception as e:
        print(f"  [截图失败，忽略报错] {e}")
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
    print("【miniduo.cn】IP连通性测试 (快照版)...")
    page = await context.new_page()
    try:
        # Miniduo 已实锤封锁 Actions IP，这里改为 20 秒快速失败，不再白白浪费时间
        await page.goto('https://www.miniduo.cn/login', timeout=20000)
        await asyncio.sleep(5) 

        email_tab = page.locator('text=邮箱登录')
        if await email_tab.count() > 0:
            await email_tab.click()
            
        await page.locator('input[placeholder*="邮箱"]').fill(MINIDUO_USER)
        await page.locator('input[type="password"]').fill(MINIDUO_PASS)
        await page.get_by_role("button", name=re.compile("登录|Login")).first.click()
        
        await page.wait_for_url("**/cart", timeout=20000)
        await asyncio.sleep(10)
        
        notice1 = page.locator('text="我知道了"')
        notice2 = page.locator('text="我已了解"')
        
        if await notice1.count() > 0:
            await notice1.first.click(force=True)
            await asyncio.sleep(2)
        elif await notice2.count() > 0:
            await notice2.first.click(force=True)
            await asyncio.sleep(2)
            
        lottery_btn = page.locator('text="开始抽奖"')
        if await lottery_btn.count() > 0:
            await lottery_btn.first.click(force=True)
        else:
            await page.mouse.click(1160, 860) 
            
        await asyncio.sleep(5) 
        return True, "已触发抽奖", await save_debug(page, "miniduo_ok")
    except Exception as e:
        return False, f"错误:{str(e)[:15]} (大概率IP被封)", await save_debug(page, "miniduo_err")
    finally: await page.close()


# ⚠️ 绝对冷冻区：Svyun 内部逻辑一行未动 ⚠️
async def checkin_svyun(context):
    print("【svyun.com】物理键盘级输入法 (稳定态)...")
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
# ⚠️ 绝对冷冻区结束 ⚠️


async def checkin_vps8(context):
    print("【vps8.zz.cd】物理降维打击 CF 验证框...")
    page = await context.new_page()
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        await asyncio.sleep(5)
        
        await page.locator('input[name="email"]').press_sequentially(VPS8_USER, delay=50)
        await page.locator('input[name="password"]').press_sequentially(VPS8_PASS, delay=50)
        
        print("  正在寻找 Turnstile 验证框...")
        iframe_element = page.locator('iframe[src*="challenges.cloudflare.com"]').first
        
        try:
            await iframe_element.wait_for(state="visible", timeout=15000)
            await asyncio.sleep(5) 
            
            box = await iframe_element.bounding_box()
            if box:
                print("  ✓ 捕获盾牌物理坐标，执行强制鼠标点击...")
                click_x = box['x'] + 30
                click_y = box['y'] + (box['height'] / 2)
                
                await page.mouse.move(click_x, click_y)
                await asyncio.sleep(0.5)
                await page.mouse.click(click_x, click_y, delay=150)
                await asyncio.sleep(5) 
        except Exception as ex:
            print(f"  ! 验证框处理失败或未出现: {ex}")
            
        await page.locator('button:has-text("登录"), button:has-text("Login")').first.click(force=True)
        await asyncio.sleep(10)
        
        btn = page.locator('button:has-text("签到"), #checkin')
        if await btn.count() > 0:
            await btn.first.click(force=True)
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
        
        # 将任务包装在 try-except 中，确保绝对的隔离
        for name, func in [('Miniduo', checkin_miniduo), ('Svyun', checkin_svyun), ('VPS8', checkin_vps8)]:
            try:
                ok, msg, ss = await func(context)
                status = "✅" if ok else "❌"
                await send_tg(f"{status} <b>{name}</b>: {msg}", photo=ss)
            except Exception as global_e:
                await send_tg(f"❌ <b>{name}</b>: 发生致命崩溃 ({str(global_e)[:20]})")
            finally:
                await asyncio.sleep(5)
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
