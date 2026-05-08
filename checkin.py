#!/usr/bin/env python3
"""
多网站自动签到脚本
支持: miniduo.cn, svyun.com, vps8.zz.cd
"""

import os
import asyncio
import base64
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ============================================================
# 配置区域 - 从环境变量读取账号密码
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

# 截图保存目录
SCREENSHOT_DIR = os.getenv('SCREENSHOT_DIR', '/tmp/checkin_screenshots')

# ============================================================
# 工具函数
# ============================================================

def ensure_screenshot_dir():
    """确保截图目录存在"""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def save_screenshot(page, name: str) -> str:
    """保存截图并返回路径"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{name}_{timestamp}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    asyncio.get_event_loop().run_until_complete(page.screenshot(path=filepath))
    return filepath

async def wait_and_click(page, selector: str, timeout: int = 10000, desc: str = ""):
    """等待元素出现并点击"""
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        await page.click(selector)
        print(f"  ✓ 点击: {desc or selector}")
        return True
    except PlaywrightTimeout:
        print(f"  ✗ 未找到元素: {desc or selector}")
        return False
    except Exception as e:
        print(f"  ✗ 点击失败: {desc or selector} - {e}")
        return False

async def wait_for_cf_verify(page, timeout: int = 30000):
    """等待 Cloudflare 人机验证完成"""
    print("  等待 Cloudflare 验证...")
    try:
        # CF 验证通常会在几秒内完成，等待页面跳转或验证框消失
        await page.wait_for_load_state('networkidle', timeout=timeout)
        # 检查是否还有 CF 验证框
        cf_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
        try:
            await cf_frame.locator('body').wait_for(timeout=3000)
            print("  检测到 CF 验证框，请手动完成验证（或使用 Turnstile 自动化）")
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
    """
    miniduo.cn 签到
    1. 登录 https://www.miniduo.cn/cart
    2. 找抽奖按钮点击
    3. 跳转 https://www.miniduo.cn/addfund
    4. 截取余额信息
    """
    print("\n" + "="*50)
    print("【miniduo.cn】开始签到")
    print("="*50)
    
    if not MINIDUO_USER or not MINIDUO_PASS:
        print("  ✗ 未配置账号密码，跳过")
        return False
    
    page = await browser.new_page()
    results = {'success': False, 'balance': None, 'screenshot': None}
    
    try:
        # 1. 访问登录页面
        print("  步骤1: 访问网站...")
        await page.goto('https://www.miniduo.cn/cart', wait_until='networkidle', timeout=30000)
        
        # 2. 检查是否需要登录
        if '登录' in await page.content() or 'login' in page.url:
            print("  步骤2: 执行登录...")
            # 尝试查找登录表单
            await page.fill('input[name="username"], input[type="text"], input[placeholder*="用户"], input[placeholder*="账号"]', MINIDUO_USER, timeout=5000)
            await page.fill('input[name="password"], input[type="password"]', MINIDUO_PASS, timeout=5000)
            await page.click('button[type="submit"], input[type="submit"], button:has-text("登录"), .login-btn', timeout=5000)
            await page.wait_for_load_state('networkidle', timeout=15000)
            print("  ✓ 登录完成")
        else:
            print("  步骤2: 已登录状态")
        
        # 3. 查找抽奖按钮
        print("  步骤3: 查找抽奖按钮...")
        lottery_selectors = [
            'button:has-text("抽奖")',
            'a:has-text("抽奖")',
            '.lottery-btn',
            '#lottery',
            '[class*="lottery"]',
            '[class*="draw"]',
            'button:has-text("签到")',
        ]
        clicked = False
        for selector in lottery_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    await page.click(selector)
                    print(f"  ✓ 点击抽奖按钮: {selector}")
                    clicked = True
                    await asyncio.sleep(2)
                    break
            except:
                continue
        
        if not clicked:
            print("  ! 未找到抽奖按钮，可能已签到")
        
        # 4. 跳转到余额页面
        print("  步骤4: 跳转余额页面...")
        await page.goto('https://www.miniduo.cn/addfund', wait_until='networkidle', timeout=30000)
        
        # 5. 获取余额信息
        print("  步骤5: 获取余额信息...")
        content = await page.content()
        import re
        balance_match = re.search(r'(\d+(?:\.\d+)?)\s*元', content)
        if balance_match:
            results['balance'] = balance_match.group(1)
            print(f"  ✓ 当前余额: {results['balance']} 元")
        else:
            print("  ! 未找到余额信息")
        
        # 6. 截图
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = f"{SCREENSHOT_DIR}/miniduo_{timestamp}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        results['screenshot'] = screenshot_path
        print(f"  ✓ 截图已保存: {screenshot_path}")
        
        results['success'] = True
        
    except Exception as e:
        print(f"  ✗ 签到失败: {e}")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        await page.screenshot(path=f"{SCREENSHOT_DIR}/miniduo_error_{timestamp}.png")
    
    finally:
        await page.close()
    
    return results


async def checkin_svyun(browser):
    """
    svyun.com 签到
    1. 登录 https://www.svyun.com/plugin/86/index.htm（需勾选同意协议）
    2. 点击立即签到
    3. 跳转 https://www.svyun.com/plugin/94/draw.htm?id=2
    4. 点击查看详情，截图弹出页面
    """
    print("\n" + "="*50)
    print("【svyun.com】开始签到")
    print("="*50)
    
    if not SVYUN_USER or not SVYUN_PASS:
        print("  ✗ 未配置账号密码，跳过")
        return False
    
    page = await browser.new_page()
    results = {'success': False, 'screenshot': None}
    
    try:
        # 1. 访问登录页面
        print("  步骤1: 访问网站...")
        await page.goto('https://www.svyun.com/plugin/86/index.htm', wait_until='networkidle', timeout=30000)
        
        # 2. 登录
        print("  步骤2: 执行登录...")
        await page.fill('input[name="username"], input[name="user"], input[type="text"]', SVYUN_USER, timeout=5000)
        await page.fill('input[name="password"], input[type="password"]', SVYUN_PASS, timeout=5000)
        
        # 勾选同意协议
        agree_selectors = [
            'input[type="checkbox"][name*="agree"]',
            'input[type="checkbox"][id*="agree"]',
            '.agree-checkbox',
            'input[type="checkbox"]',
        ]
        for selector in agree_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    await page.check(selector)
                    print(f"  ✓ 勾选同意协议: {selector}")
                    break
            except:
                continue
        
        # 点击登录
        await page.click('button[type="submit"], input[type="submit"], button:has-text("登录"), .login-btn', timeout=5000)
        await page.wait_for_load_state('networkidle', timeout=15000)
        print("  ✓ 登录完成")
        
        # 3. 点击签到按钮
        print("  步骤3: 查找签到按钮...")
        checkin_selectors = [
            'button:has-text("立即签到")',
            'a:has-text("立即签到")',
            'button:has-text("签到")',
            '.checkin-btn',
            '#checkin',
            '[class*="checkin"]',
        ]
        clicked = False
        for selector in checkin_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    await page.click(selector)
                    print(f"  ✓ 点击签到按钮: {selector}")
                    clicked = True
                    await asyncio.sleep(2)
                    break
            except:
                continue
        
        if not clicked:
            print("  ! 未找到签到按钮，可能已签到")
        
        # 4. 跳转到抽奖页面
        print("  步骤4: 跳转抽奖页面...")
        await page.goto('https://www.svyun.com/plugin/94/draw.htm?id=2', wait_until='networkidle', timeout=30000)
        
        # 5. 点击查看详情
        print("  步骤5: 查找查看详情...")
        detail_selectors = [
            'button:has-text("查看详情")',
            'a:has-text("查看详情")',
            '.detail-btn',
            '[class*="detail"]',
        ]
        for selector in detail_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    await page.click(selector)
                    print(f"  ✓ 点击查看详情: {selector}")
                    await asyncio.sleep(1)
                    break
            except:
                continue
        
        # 6. 截图
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = f"{SCREENSHOT_DIR}/svyun_{timestamp}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        results['screenshot'] = screenshot_path
        print(f"  ✓ 截图已保存: {screenshot_path}")
        
        results['success'] = True
        
    except Exception as e:
        print(f"  ✗ 签到失败: {e}")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        await page.screenshot(path=f"{SCREENSHOT_DIR}/svyun_error_{timestamp}.png")
    
    finally:
        await page.close()
    
    return results


async def checkin_vps8(browser):
    """
    vps8.zz.cd 签到
    1. 登录 https://vps8.zz.cd/login
    2. 勾选 CF Verify you are human
    3. 找签到按钮点击
    4. 再次勾选 CF Verify you are human
    5. 签到完成截图
    """
    print("\n" + "="*50)
    print("【vps8.zz.cd】开始签到")
    print("="*50)
    
    if not VPS8_USER or not VPS8_PASS:
        print("  ✗ 未配置账号密码，跳过")
        return False
    
    page = await browser.new_page()
    results = {'success': False, 'screenshot': None}
    
    try:
        # 1. 访问登录页面
        print("  步骤1: 访问网站...")
        await page.goto('https://vps8.zz.cd/login', wait_until='networkidle', timeout=30000)
        
        # 2. 等待 CF 验证
        await wait_for_cf_verify(page)
        
        # 3. 登录
        print("  步骤2: 执行登录...")
        await page.fill('input[name="email"], input[name="username"], input[type="text"], input[type="email"]', VPS8_USER, timeout=5000)
        await page.fill('input[name="password"], input[type="password"]', VPS8_PASS, timeout=5000)
        
        # CF Turnstile 验证 - 通常会自动完成
        print("  步骤3: 等待 CF Turnstile 验证...")
        await asyncio.sleep(3)  # 给 Turnstile 一些时间自动完成
        await wait_for_cf_verify(page, timeout=15000)
        
        # 点击登录
        await page.click('button[type="submit"], input[type="submit"], button:has-text("登录"), button:has-text("Login")', timeout=5000)
        await page.wait_for_load_state('networkidle', timeout=15000)
        print("  ✓ 登录完成")
        
        # 4. 查找签到按钮
        print("  步骤4: 查找签到按钮...")
        checkin_selectors = [
            'button:has-text("签到")',
            'a:has-text("签到")',
            '.checkin-btn',
            '#checkin',
            '[class*="checkin"]',
            'button:has-text("Check")',
        ]
        clicked = False
        for selector in checkin_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    await page.click(selector)
                    print(f"  ✓ 点击签到按钮: {selector}")
                    clicked = True
                    await asyncio.sleep(2)
                    break
            except:
                continue
        
        if not clicked:
            print("  ! 未找到签到按钮，可能已签到")
        
        # 5. 再次等待 CF 验证
        print("  步骤5: 等待签到后的 CF 验证...")
        await wait_for_cf_verify(page, timeout=15000)
        
        # 6. 截图
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = f"{SCREENSHOT_DIR}/vps8_{timestamp}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        results['screenshot'] = screenshot_path
        print(f"  ✓ 截图已保存: {screenshot_path}")
        
        results['success'] = True
        
    except Exception as e:
        print(f"  ✗ 签到失败: {e}")
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
        # 启动浏览器（headless 模式）
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        results = {}
        
        # 执行签到
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
    
    return results


if __name__ == '__main__':
    asyncio.run(main())
