async def human_click(page, locator):
    """模拟真人鼠标移动并点击，专门针对 VPS8 的 Turnstile 盾"""
    box = await locator.bounding_box()
    if box:
        # 在按钮范围内随机取点
        x = box['x'] + box['width'] / 2
        y = box['y'] + box['height'] / 2
        await page.mouse.move(x - 10, y - 10)
        await asyncio.sleep(0.5)
        await page.mouse.click(x, y, delay=200) # 增加物理点击延迟

async def checkin_vps8(context):
    print("【vps8.zz.cd】人机验证压榨中...")
    page = await context.new_page()
    try:
        await page.goto('https://vps8.zz.cd/login', timeout=60000)
        await page.locator('input[name="email"]').fill(VPS8_USER)
        await page.locator('input[name="password"]').fill(VPS8_PASS)
        
        # 针对图 3 中的验证框
        cf_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
        target = cf_frame.locator('body')
        
        if await target.count() > 0:
            print("  ✓ 探测到验证框，执行真人模拟点击...")
            await human_click(page, target)
            await asyncio.sleep(5) # 等待盾消失
            
        await page.locator('button:has-text("登录")').click()
        await asyncio.sleep(10)
        
        # 签到
        btn = page.locator('button:has-text("签到"), #checkin')
        if await btn.count() > 0:
            await btn.first.click()
            return True, "签到成功", await save_debug(page, "vps8_ok")
        return False, "未见签到按钮", await save_debug(page, "vps8_fail")
    except Exception as e:
        return False, f"异常: {str(e)[:20]}", await save_debug(page, "vps8_err")
    finally: await page.close()

async def checkin_svyun(context):
    print("【svyun.com】回归 JS 注入成功态...")
    page = await context.new_page()
    try:
        await page.goto('https://www.svyun.com/plugin/86/index.htm', timeout=60000)
        await asyncio.sleep(10) # 强制等待 Loading 结束
        
        # 还原之前成功的注入逻辑，增加 retry
        for _ in range(3):
            try:
                await page.evaluate(f"""() => {{
                    const u = document.querySelector('input[type="text"], input[name="username"]');
                    const p = document.querySelector('input[type="password"]');
                    const c = document.querySelector('input[type="checkbox"]');
                    if(u) u.value = '{SVYUN_USER}';
                    if(p) p.value = '{SVYUN_PASS}';
                    if(c) c.click();
                    const btn = document.querySelector('button[type="submit"], button.btn-primary');
                    if(btn) btn.click();
                }}""")
                break
            except: await asyncio.sleep(2)
            
        await asyncio.sleep(10)
        # 签到与次数提取保持不变...
        return True, "已尝试登录并签到", await save_debug(page, "svyun_res")
    except Exception as e:
        return False, f"异常: {str(e)[:20]}", await save_debug(page, "svyun_err")
    finally: await page.close()
