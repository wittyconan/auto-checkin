#!/usr/bin/env python3
"""
多网站自动签到脚本
支持: miniduo.cn, svyun.com, vps8.zz.cd
支持 Telegram 机器人通报
"""

import os
import re
import asyncio
import base64
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ============================================================
# 配置区域 - 从环境变量读取
# ============================================================

# miniduo.cn 配置
MINIDUO_USER = os.getenv('MINIDUO_USER', '')
MINIDUO_PASS = os.getenv('MINIDUO_PASS', '')

# svyun.com 配置
SVYUN_USER = os.getenv('SVYUN_USER', '')
SVYUN_PASS = os.getenv('SVYUN_PASS', '')

# vps8.zz.cd 配置
VPS8_USER = os.getenv('VPS8_USER', '')
VPS8_PASS = os.getenv('VPS8_PASS', '')

# Telegram 配置
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.getenv('TG_CHAT_ID', '')

# 截图保存目录
SCREENSHOT_DIR = os.getenv('SCREENSHOT_DIR', '/tmp/checkin_screenshots')

# ============================================================
# Telegram 通知函数
# ============================================================

async def send_telegram_message(text: str, parse_mode: str = 'HTML'):
    """发送 Telegram 文本消息"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("  [TG] 未配置 Bot Token 或 Chat ID，跳过通知")
        return False
    
    import aiohttp
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={
                'chat_id': TG_CHAT_ID,
                'text': text,
                'parse_mode': parse_mode
            }) as resp:
                if resp.status == 200:
                    print("  [TG] 消息发送成功")
                    return True
                else:
                    print(f"  [TG] 消息发送失败: {await resp.text()}")
                    return False
    except Exception as e:
        print(f"  [TG] 发送异常: {e}")
        return False


async def send_telegram_photo(photo_path: str, caption: str = ""):
    """发送 Telegram 图片"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return False
    
    import aiohttp
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
    
    try:
        async with aiohttp.ClientSession() as session:
            with open(photo_path, 'rb') as f:
                form = aiohttp.FormData()
                form.add_field('chat_id', TG_CHAT_ID)
                form.add_field('photo', f, filename='screenshot.png', content_type='image/png')
                if caption:
                    form.add_field('caption', caption, content_type='text/plain')
                
                async with session.post(url, data=form) as resp:
                    if resp.status == 200:
                        print(f"  [TG] 图片发送成功: {photo_path}")
                        return True
                    else:
                        print(f"  [TG] 图片发送失败: {await resp.text()}")
                        return False
    except Exception as e:
        print(f"  [TG] 图片发送异常: {e}")
        return False


async def send_telegram_report(results: dict):
    """发送签到结果汇总报告"""
    # 构建消息
    lines = [
        "🔔 <b>自动签到报告</b>",
        f"📅 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ""
    ]
    
    success_count = 0
    fail_count = 0
    skip_count = 0
    
    site_names = {
        'miniduo': 'miniduo.cn',
        'svyun': 'svyun.com', 
        'vps8': 'vps8.zz.cd'
    }
    
    for site, result in results.items():
        name = site_names.get(site, site)
        if result is False or result is None:
            lines.append(f"⊘ {name}: 跳过（未配置）")
            skip_count += 1
        elif result.get('success'):
            balance = result.get('balance')
            if balance:
                lines.append(f"✅ {name}: 成功 | 余额 {balance} 元")
            else:
                lines.append(f"✅ {name}: 成功")
            success_count += 1
        else:
            lines.append(f"❌ {name}: 失败")
            fail_count += 1
    
    lines.extend([
        "",
        f"📊 统计: 成功 {success_count} | 失败 {fail_count} | 跳过 {skip_count}"
    ])
    
    message = "\n".join(lines)
    
    # 发送文字报告
    await send_telegram_message(message)
    
    # 发送截图
    for site, result in results.items():
        if result and result.get('screenshot') and os.path.exists(result['screenshot']):
            name = site_names.get(site, site)
            await send_telegram_photo(result['screenshot'], f"📷 {name} 签到截图")


# ============================================================
# 工具函数
# ============================================================

def ensure_screenshot_dir():
    """确保截图目录存在"""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)


async def wait_for_cf_verify(page, timeout: int = 30000):
    """等待 Cloudflare 人机验证完成"""
    print("  等待 Cloudflare 验证...")
    try:
        await page.wait_for_load_state('networkidle', timeout=timeout)
        cf_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
        try:
            await cf_frame.locator('body').wait_for(timeout=3000)
            print("  检测到 CF 验证框，等待自动完成...")
            await page.wait_for_load_state('networkidle', timeout=60000)
        except:
            pass
        print("  ✓ CF 验证完成")
        return True
    except Exception as e:
        print(f"  ! CF 验证等待超时: {e}")
        return False


# ============================================================
# 签到函数
# ============================================================

async def checkin_miniduo(browser):
    """miniduo.cn 签到"""
    print("\n" + "="*50)
    print("【miniduo.cn】开始签到")
    print("="*50)
    
    if not MINIDUO_USER or not MINIDUO_PASS:
        print("  ✗ 未配置账号密码，跳过")
        return False
    
    page = await browser.new_page()
    results = {'success': False, 'balance': None, 'screenshot': None, 'message': ''}
    
    try:
        print("  步骤1: 访问网站...")
        await page.goto('https://www.miniduo.cn/cart', wait_until='networkidle', timeout=30000)
        
        if '登录' in await page.content() or 'login' in page.url:
            print("  步骤2: 执行登录...")
            await page.fill('input[name="username"], input[type="text"], input[placeholder*="用户"], input[placeholder*="账号"]', MINIDUO_USER, timeout=5000)
            await page.fill('input[name="password"], input[type="password"]', MINIDUO_PASS, timeout=5000)
            await page.click('button[type="submit"], input[type="submit"], button:has-text("登录"), .login-btn', timeout=5000)
            await page.wait_for_load_state('networkidle', timeout=15000)
            print("  ✓ 登录完成")
        else:
            print("  步骤2: 已登录状态")
        
        print("  步骤3: 查找抽奖按钮...")
        lottery_selectors = ['button:has-text("抽奖")', 'a:has-text("抽奖")', '.lottery-btn', '#lottery', '[class*="lottery"]', '[class*="draw"]', 'button:has-text("签到")']
        clicked = False
        for selector in lottery_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    await page.click(selector)
                    print(f"  ✓ 点击抽奖按钮")
                    clicked = True
                    await asyncio.sleep(2)
                    break
            except:
                continue
        if not clicked:
            print("  ! 未找到抽奖按钮，可能已签到")
        
        print("  步骤4: 跳转余额页面...")
        await page.goto('https://www.miniduo.cn/addfund', wait_until='networkidle', timeout=30000)
        
        print("  步骤5: 获取余额信息...")
        content = await page.content()
        balance_match = re.search(r'(\d+(?:\.\d+)?)\s*元', content)
        if balance_match:
            results['balance'] = balance_match.group(1)
            print(f"  ✓ 当前余额: {results['balance']} 元")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = f"{SCREENSHOT_DIR}/miniduo_{timestamp}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        results['screenshot'] = screenshot_path
        print(f"  ✓ 截图已保存")
        
        results['success'] = True
        results['message'] = f"签到成功，余额: {results['balance']} 元" if results['balance'] else "签到成功"
        
    except Exception as e:
        print(f"  ✗ 签到失败: {e}")
        results['message'] = f"签到失败: {e}"
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        await page.screenshot(path=f"{SCREENSHOT_DIR}/miniduo_error_{timestamp}.png")
    finally:
        await page.close()
    
    return results


async def checkin_svyun(browser):
    """svyun.com 签到"""
    print("\n" + "="*50)
    print("【svyun.com】开始签到")
    print("="*50)
    
    if not SVYUN_USER or not SVYUN_PASS:
        print("  ✗ 未配置账号密码，跳过")
        return False
    
    page = await browser.new_page()
    results = {'success': False, 'screenshot': None, 'message': ''}
    
    try:
        print("  步骤1: 访问网站...")
        await page.goto('https://www.svyun.com/plugin/86/index.htm', wait_until='networkidle', timeout=30000)
        
        print("  步骤2: 执行登录...")
        await page.fill('input[name="username"], input[name="user"], input[type="text"]', SVYUN_USER, timeout=5000)
        await page.fill('input[name="password"], input[type="password"]', SVYUN_PASS, timeout=5000)
        
        for selector in ['input[type="checkbox"][name*="agree"]', 'input[type="checkbox"][id*="agree"]', '.agree-checkbox', 'input[type="checkbox"]']:
            try:
                if await page.locator(selector).count() > 0:
                    await page.check(selector)
                    print(f"  ✓ 勾选同意协议")
                    break
            except:
                continue
        
        await page.click('button[type="submit"], input[type="submit"], button:has-text("登录"), .login-btn', timeout=5000)
        await page.wait_for_load_state('networkidle', timeout=15000)
        print("  ✓ 登录完成")
        
        print("  步骤3: 查找签到按钮...")
        checkin_selectors = ['button:has-text("立即签到")', 'a:has-text("立即签到")', 'button:has-text("签到")', '.checkin-btn', '#checkin', '[class*="checkin"]']
        clicked = False
        for selector in checkin_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    await page.click(selector)
                    print(f"  ✓ 点击签到按钮")
                    clicked = True
                    await asyncio.sleep(2)
                    break
            except:
                continue
        if not clicked:
            print("  ! 未找到签到按钮，可能已签到")
        
        print("  步骤4: 跳转抽奖页面...")
        await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2', wait_until='networkidle', timeout=30000)
        
        print("  步骤5: 查找查看详情...")
        for selector in ['button:has-text("查看详情")', 'a:has-text("查看详情")', '.detail-btn', '[class*="detail"]']:
            try:
                if await page.locator(selector).count() > 0:
                    await page.click(selector)
                    print(f"  ✓ 点击查看详情")
                    await asyncio.sleep(1)
                    break
            except:
                continue
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = f"{SCREENSHOT_DIR}/svyun_{timestamp}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        results['screenshot'] = screenshot_path
        print(f"  ✓ 截图已保存")
        
        results['success'] = True
        results['message'] = "签到成功"
        
    except Exception as e:
        print(f"  ✗ 签到失败: {e}")
        results['message'] = f"签到失败: {e}"
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        await page.screenshot(path=f"{SCREENSHOT_DIR}/svyun_error_{timestamp}.png")
    finally:
        await page.close()
    
    return results


async def checkin_vps8(browser):
    """vps8.zz.cd 签到"""
    print("\n" + "="*50)
    print("【vps8.zz.cd】开始签到")
    print("="*50)
    
    if not VPS8_USER or not VPS8_PASS:
        print("  ✗ 未配置账号密码，跳过")
        return False
    
    page = await browser.new_page()
    results = {'success': False, 'screenshot': None, 'message': ''}
    
    try:
        print("  步骤1: 访问网站...")
        await page.goto('https://vps8.zz.cd/login', wait_until='networkidle', timeout=30000)
        
        await wait_for_cf_verify(page)
        
        print("  步骤2: 执行登录...")
        await page.fill('input[name="email"], input[name="username"], input[type="text"], input[type="email"]', VPS8_USER, timeout=5000)
        await page.fill('input[name="password"], input[type="password"]', VPS8_PASS, timeout=5000)
        
        print("  步骤3: 等待 CF Turnstile 验证...")
        await asyncio.sleep(3)
        await wait_for_cf_verify(page, timeout=15000)
        
        await page.click('button[type="submit"], input[type="submit"], button:has-text("登录"), button:has-text("Login")', timeout=5000)
        await page.wait_for_load_state('networkidle', timeout=15000)
        print("  ✓ 登录完成")
        
        print("  步骤4: 查找签到按钮...")
        checkin_selectors = ['button:has-text("签到")', 'a:has-text("签到")', '.checkin-btn', '#checkin', '[class*="checkin"]', 'button:has-text("Check")']
        clicked = False
        for selector in checkin_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    await page.click(selector)
                    print(f"  ✓ 点击签到按钮")
                    clicked = True
                    await asyncio.sleep(2)
                    break
            except:
                continue
        if not clicked:
            print("  ! 未找到签到按钮，可能已签到")
        
        print("  步骤5: 等待签到后的 CF 验证...")
        await wait_for_cf_verify(page, timeout=15000)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = f"{SCREENSHOT_DIR}/vps8_{timestamp}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        results['screenshot'] = screenshot_path
        print(f"  ✓ 截图已保存")
        
        results['success'] = True
        results['message'] = "签到成功"
        
    except Exception as e:
        print(f"  ✗ 签到失败: {e}")
        results['message'] = f"签到失败: {e}"
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        await page.screenshot(path=f"{SCREENSHOT_DIR}/vps8_error_{timestamp}.png")
    finally:
        await page.close()
    
    return results


# ============================================================
# 主函数
# ============================================================

async def main():
    """主函数"""
    print("="*60)
    print(f"自动签到脚本 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    ensure_screenshot_dir()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        results = {}
        results['miniduo'] = await checkin_miniduo(context)
        results['svyun'] = await checkin_svyun(context)
        results['vps8'] = await checkin_vps8(context)
        
        await browser.close()
    
    # 输出汇总
    print("\n" + "="*60)
    print("签到结果汇总")
    print("="*60)
    for site, result in results.items():
        if result:
            status = "✓ 成功" if result.get('success') else "✗ 失败"
            balance = f" | 余额: {result.get('balance')}元" if result.get('balance') else ""
            print(f"  {site}: {status}{balance}")
        else:
            print(f"  {site}: ⊘ 跳过")
    
    # 发送 Telegram 通知
    print("\n" + "="*60)
    print("发送 Telegram 通知")
    print("="*60)
    await send_telegram_report(results)
    
    return results


if __name__ == '__main__':
    asyncio.run(main())
