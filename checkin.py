#!/usr/bin/env python3
import os, re, asyncio, random
from datetime import datetime
from playwright.async_api import async_playwright

# ================= 配置区域 =================
SVYUN_USER = os.getenv('SVYUN_USER', '')
SVYUN_PASS = os.getenv('SVYUN_PASS', '')
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.getenv('TG_CHAT_ID', '')
SCREENSHOT_DIR = os.getenv('SCREENSHOT_DIR', './screenshots')

async def save_debug(page, name):
    if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)
    path = f"{SCREENSHOT_DIR}/debug_{name}_{datetime.now().strftime('%H%M%S')}.png"
    try:
        await page.screenshot(path=path, timeout=5000)
        return path
    except: return None

async def send_tg(text, photo=None):
    if not TG_BOT_TOKEN: return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        try:
            form = aiohttp.FormData()
            form.add_field('chat_id', TG_CHAT_ID)
            if photo: form.add_field('photo', open(photo, 'rb'))
            form.add_field('caption' if photo else 'text', text)
            await session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/{'sendPhoto' if photo else 'sendMessage'}", data=form)
        except: pass

# ================= 核心业务 =================

async def run_task(context):
    page = await context.new_page()
    # 增加默认超时到 60 秒，应对 504 延迟
    page.set_default_timeout(60000)
    
    try:
        print(f"  -> [{datetime.now().strftime('%H:%M:%S')}] 尝试访问网站...")
        # 优化 1：使用 'commit' 级别，只要服务器开始吐数据就介入，不等图片加载
        try:
            resp = await page.goto('https://www.svyun.com/plugin/86/index.htm', wait_until="commit")
            if resp and resp.status >= 500:
                return False, f"服务器错误({resp.status})", await save_debug(page, "server_error")
        except Exception as e:
            return False, f"网络超时: {str(e)[:15]}", await save_debug(page, "network_timeout")

        await asyncio.sleep(5)

        # 优化 2：强力 JS 登录注入
        # 哪怕页面还在转圈，只要 DOM 出来了就强行填
        is_login = await page.evaluate("() => !!document.querySelector('input[placeholder*=\"Email\"]')")
        if is_login:
            print("  -> 检测到登录页，执行暴力登录注入...")
            await page.evaluate(f"""() => {{
                const u = document.querySelector('input[placeholder*="Email"]');
                const p = document.querySelector('input[type="password"]');
                if(u && p) {{
                    u.value = '{SVYUN_USER}';
                    p.value = '{SVYUN_PASS}';
                    document.querySelectorAll('input[type="checkbox"]').forEach(i => i.checked = true);
                    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Login'));
                    if(btn) btn.click();
                }}
            }}""")
            await asyncio.sleep(10)

        # 优化 3：暴力跳转签到页
        await page.goto('https://www.svyun.com/plugin/94/index.htm', wait_until="commit")
        await asyncio.sleep(8)

        # 优化 4：循环扫描并强行触发签到
        msg = "未命中逻辑"
        for i in range(12): # 扫描 12 次，每次 3 秒
            # 清除可能挡路的公告弹窗
            await page.evaluate("document.querySelectorAll('.layui-layer, .modal, .mask').forEach(el => el.remove())")
            
            # 检查是否已签到
            page_content = await page.content()
            if "已签到" in page_content:
                return True, "今日已成功签到 (或已签)", await save_debug(page, "checked_in")

            # 强行点击“立即签到”
            clicked = await page.evaluate("""() => {
                const btn = Array.from(document.querySelectorAll('button, a, div')).find(el => 
                    el.innerText.trim() === '立即签到' || el.className.includes('checkin-btn')
                );
                if(btn) { btn.click(); return true; }
                return false;
            }""")
            
            if clicked:
                print("  -> 发现按钮并发送点击指令...")
                await asyncio.sleep(5)
                # 点击后验证一下
                if "已签到" in await page.content():
                    return True, "签到成功！", await save_debug(page, "success")
                return True, "签到指令已发 (请看截图)", await save_debug(page, "sent")
            
            print(f"  ...等待按钮加载 ({i+1}/12)")
            await asyncio.sleep(3)

        return False, "页面已加载但未见按钮", await save_debug(page, "no_btn_error")

    except Exception as e:
        return False, f"运行时崩溃: {str(e)[:30]}", await save_debug(page, "crash")
    finally:
        await page.close()

# ================= 主入口 =================

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
        # 伪装成普通 Chrome，减少被 504 拦截的概率
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        # 增加随机延迟重试，对抗服务器波动
        max_attempts = 3
        for attempt in range(max_attempts):
            print(f"\n--- 尝试第 {attempt + 1} 次 ---")
            ok, msg, ss = await run_task(context)
            if ok:
                await send_tg(f"✅ <b>Svyun 签到</b>\n结果: {msg}", photo=ss)
                break
            else:
                if attempt < max_attempts - 1:
                    wait_time = random.randint(30, 90)
                    print(f"  失败原因: {msg}，等待 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    await send_tg(f"❌ <b>Svyun 最终失败</b>\n最终错误: {msg}", photo=ss)
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
