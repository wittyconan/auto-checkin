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
    except Exception as e:
        print(f"  [截图跳过] {e}")
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
        except Exception as e: print(f"  [TG通知失败] {e}")

# ================= 核心业务逻辑 =================

async def checkin_svyun(context):
    print("【Svyun】开始执行自动化流程...")
    page = await context.new_page()
    
    try:
        # 1. 登录流程
        await page.goto('https://www.svyun.com/plugin/86/index.htm', wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)
        
        # 输入账号
        user_input = page.locator('input[placeholder*="Email"]').first
        await user_input.wait_for(state="visible")
        await user_input.click()
        await user_input.fill("") # 确保清空
        await user_input.type(SVYUN_USER, delay=100)
        
        # 输入密码
        pass_input = page.locator('input[type="password"]')
        await pass_input.type(SVYUN_PASS, delay=100)
        
        # 勾选协议并登录
        await page.get_by_text("Read and agree").click()
        await page.locator('button:has-text("Login")').first.click()
        
        # 等待登录跳转完成
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(8)

        # 2. 签到页处理
        print("  -> 跳转至签到中心...")
        await page.goto('https://www.svyun.com/plugin/94/index.htm', wait_until="networkidle")
        await asyncio.sleep(5)

        # [加固] 尝试关闭可能遮挡的弹窗/公告
        try:
            close_btn = page.locator('.layui-layer-close, .close, [aria-label="Close"]').first
            if await close_btn.is_visible():
                await close_btn.click()
        except: pass

        # [定位] 查找签到按钮 (多重选择器)
        # 优先寻找包含“立即签到”文字的按钮，其次寻找类名包含 checkin 的元素
        btn_sign = page.locator('button:has-text("立即签到"), .checkin-btn, .btn-checkin').first
        btn_signed = page.get_by_text("已签到")

        if await btn_signed.count() > 0:
            msg_status = "今日已签到过"
            print(f"  ✓ {msg_status}")
        elif await btn_sign.count() > 0:
            print("  -> 发现签到按钮，正在点击...")
            # 使用 force=True 穿透可能的透明遮挡层
            await btn_sign.click(force=True)
            await asyncio.sleep(5)
            msg_status = "签到动作已完成"
        else:
            return False, "未找到签到按钮", await save_debug(page, "not_found")

        # 3. 抽奖页数据获取
        print("  -> 跳转至抽奖页获取状态...")
        await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2', wait_until="networkidle")
        await asyncio.sleep(5)
        
        page_text = await page.content()
        count_match = re.search(r"剩余抽奖次数\s*(\d+)", page_text)
        draw_msg = f" | 剩余抽奖:{count_match.group(1)}" if count_match else ""
        
        # 尝试点击“查看详情”展示结果，并局部截图
        target_modal = None
        try:
            await page.get_by_text("查看详情").click(timeout=5000)
            await asyncio.sleep(2)
            # 这里的选择器根据 Layui 常见样式做了优化
            modal_loc = page.locator('.layui-layer-content, .modal-body').first
            if await modal_loc.is_visible():
                target_modal = modal_loc
        except: pass

        return True, f"{msg_status}{draw_msg}", await save_debug(page, "success", clip_element=target_modal)

    except Exception as e:
        print(f"  ❌ 运行异常: {e}")
        return False, f"错误:{str(e)[:30]}", await save_debug(page, "error")
    finally:
        await page.close()

# ================= 主入口 =================

async def main():
    async with async_playwright() as p:
        # 针对 GitHub Actions 的环境优化参数
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        # 模拟真实的浏览器环境
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        try:
            ok, msg, ss_path = await checkin_svyun(context)
            status_icon = "✅" if ok else "❌"
            report = f"🔔 <b>Svyun 自动签到结果</b>\n状态: {status_icon} {msg}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await send_tg(report, photo=ss_path)
        except Exception as fatal:
            await send_tg(f"⚠️ <b>脚本致命错误</b>\n内容: {str(fatal)[:50]}")
        finally:
            await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
