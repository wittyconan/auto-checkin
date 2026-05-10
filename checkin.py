#!/usr/bin/env python3
import os
import re
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

# ================= 配置区域 =================
SVYUN_USER = os.getenv('SVYUN_USER', '')
SVYUN_PASS = os.getenv('SVYUN_PASS', '')
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.getenv('TG_CHAT_ID', '')
SCREENSHOT_DIR = os.getenv('SCREENSHOT_DIR', './screenshots')

# ================= 工具函数 =================
async def save_debug(page, name, clip_element=None):
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    path = f"{SCREENSHOT_DIR}/debug_{name}_{datetime.now().strftime('%H%M%S')}.png"
    try:
        if clip_element and await clip_element.is_visible():
            await clip_element.screenshot(path=path, timeout=5000)
        else:
            await page.screenshot(path=path, timeout=5000)
        return path
    except:
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
        except Exception as e: 
            print(f"  [TG通知失败] {e}")

# ================= 核心业务逻辑 =================

async def run_task(context):
    page = await context.new_page()
    # 设置较长的默认超时
    page.set_default_timeout(30000)
    
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在访问签到页面...")
        # 直接访问签到页，利用已有的 Session
        response = await page.goto('https://www.svyun.com/plugin/94/index.htm', wait_until="domcontentloaded")
        
        if response and response.status >= 500:
            return False, f"服务器错误({response.status})", await save_debug(page, "50x_error")
        
        await asyncio.sleep(5)

        # 1. 登录态自适应检查
        login_input = page.locator('input[placeholder*="Email"]').first
        if await login_input.is_visible():
            print("  -> 检测到未登录，执行登录流程...")
            await login_input.fill(SVYUN_USER)
            await page.locator('input[type="password"]').fill(SVYUN_PASS)
            await page.get_by_text("Read and agree").click()
            await page.locator('button:has-text("Login")').first.click()
            
            # 等待登录跳转
            await asyncio.sleep(10)
            # 重新回到签到页
            await page.goto('https://www.svyun.com/plugin/94/index.htm')
            await asyncio.sleep(5)
        else:
            print("  -> 检测到已登录，直接进入签到流程。")

        # 2. 执行签到动作
        # 兼容定位：文字匹配 + 类名匹配
        btn_sign = page.locator('button:has-text("立即签到"), .layui-btn:has-text("立即签到"), .checkin-btn').first
        btn_signed = page.locator('text="已签到", button:has-text("已签到")').first

        if await btn_signed.is_visible():
            res_msg = "今日已签到过"
            print(f"  ✓ {res_msg}")
        elif await btn_sign.is_visible():
            print("  -> 发现签到按钮，尝试点击...")
            await btn_sign.click(force=True)
            await asyncio.sleep(5)
            res_msg = "签到动作成功"
        else:
            # 这种情况通常是页面加载了但由于某些 UI 遮挡找不到元素
            return False, "未能识别签到按钮状态", await save_debug(page, "btn_error")

        # 3. 抽奖页数据采集
        print("  -> 正在获取剩余次数...")
        await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2')
        await asyncio.sleep(5)
        
        content = await page.content()
        count_match = re.search(r"剩余抽奖次数\s*(\d+)", content)
        draw_info = f" | 剩余抽奖: {count_match.group(1)}次" if count_match else ""
        
        # 尝试截图详情
        target_ss = await save_debug(page, "success_detail")
        return True, res_msg + draw_info, target_ss

    except Exception as e:
        error_str = str(e).replace('\n', ' ')[:50]
        print(f"  ❌ 运行异常: {error_str}")
        return False, f"异常: {error_str}", await save_debug(page, "crash")
    finally:
        await page.close()

# ================= 主流程 (含自动重试) =================

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        # 模拟真实浏览器
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        max_retries = 3
        for attempt in range(max_retries):
            print(f"\n--- 第 {attempt + 1} 次尝试 ---")
            ok, msg, ss_path = await run_task(context)
            
            if ok:
                await send_tg(f"✅ <b>Svyun 签到报告</b>\n结果: {msg}\n时间: {datetime.now().strftime('%m-%d %H:%M')}", photo=ss_path)
                break
            else:
                if attempt < max_retries - 1:
                    print(f"  等待 30 秒后重试...")
                    await asyncio.sleep(30)
                else:
                    await send_tg(f"❌ <b>Svyun 签到失败</b>\n原因: {msg}", photo=ss_path)
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
