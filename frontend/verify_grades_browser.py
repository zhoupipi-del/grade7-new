"""
Playwright Browser Rendering Verification for Grade Module Vue Components

Tests three grade pages:
1. GradeDashboard.vue — macro grade overview
2. StudentRadarChart.vue — dual-modal radar (academic + behavioral)
3. HolisticProfileCard.vue — holistic profile container

Procedure:
1. Login with admin credentials (ms_admin)
2. Navigate to each grade page
3. Take screenshot + check console errors
4. Verify key UI elements are present
"""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════
BASE_URL = "http://localhost:3000/app"
LOGIN_URL = f"{BASE_URL}/login"
GRADE_PAGES = {
    "GradeDashboard": f"{BASE_URL}/grades/dashboard",
    "StudentRadarChart": f"{BASE_URL}/grades/radar",
    "HolisticProfileCard": f"{BASE_URL}/grades/profile",
}

# Test credentials (ms_admin)
USERNAME = "admin"
PASSWORD = "admin123"

SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Console error collector
console_errors: list[str] = []
console_warnings: list[str] = []


async def login(page):
    """Login to Wings 3.0 with admin credentials"""
    print(f"[1] Navigating to login page: {LOGIN_URL}")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=15000)

    # Wait for login form to appear (el-input structure)
    await page.wait_for_selector("input.el-input__inner", timeout=5000)

    # Fill credentials — el-input uses nested input structure
    inputs = page.locator("input.el-input__inner")
    username_input = inputs.first
    password_input = inputs.nth(1)

    await username_input.fill(USERNAME)
    await password_input.fill(PASSWORD)

    # Click login button — el-button with text "登 录" (has space)
    login_button = page.locator("button.el-button--primary")
    await login_button.click()

    # Wait for redirect to dashboard (or any authenticated page)
    print("[1] Waiting for post-login redirect...")
    try:
        await page.wait_for_url(f"{BASE_URL}/dashboard", timeout=10000)
        print("[1] Login successful — redirected to dashboard")
    except Exception:
        current_url = page.url
        print(f"[1] Current URL after login: {current_url}")
        if "/login" in current_url:
            print("[1] ERROR: Still on login page — login failed!")
            # Take screenshot of login failure
            await page.screenshot(path=str(SCREENSHOT_DIR / "login_failed.png"))
            return False
        print("[1] Login likely succeeded (URL changed)")

    # Take screenshot of logged-in state
    await page.screenshot(path=str(SCREENSHOT_DIR / "after_login.png"))
    return True


async def select_first_el_option(page, select_index=0):
    """Helper: select the first option from the nth el-select using keyboard"""
    select_wrapper = page.locator(".el-select").nth(select_index)
    await select_wrapper.click()
    await page.wait_for_timeout(300)
    # Use keyboard to select first visible option
    await page.keyboard.press("ArrowDown")
    await page.wait_for_timeout(200)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(800)  # wait for Vue reactivity


async def verify_grade_page(page, name, url):
    """Navigate to a grade page, take screenshot, check for errors"""
    print(f"\n[2.{name}] Navigating to: {url}")
    await page.goto(url, wait_until="networkidle", timeout=15000)

    # Wait 2s for data loading and rendering
    await page.wait_for_timeout(2000)

    # Interactive pages require class/student selection to render charts
    if name == "StudentRadarChart":
        print(f"[2.{name}] Selecting class + student to trigger chart rendering...")
        try:
            # First el-select = class
            await select_first_el_option(page, 0)
            # Second el-select = student
            await select_first_el_option(page, 1)
            await page.wait_for_timeout(1500)
        except Exception as e:
            print(f"[2.{name}] Interaction failed: {e}")

    elif name == "HolisticProfileCard":
        print(f"[2.{name}] Clicking Demo data button to trigger full rendering...")
        try:
            demo_btn = page.locator("button:has-text('Demo数据')")
            if await demo_btn.count() > 0:
                await demo_btn.click()
                await page.wait_for_timeout(1500)
            else:
                print(f"[2.{name}] Demo button not found, fallback to manual selection")
                await select_first_el_option(page, 0)  # class
                await select_first_el_option(page, 1)  # student
                await select_first_el_option(page, 2)  # exam
                await page.wait_for_timeout(1500)
        except Exception as e:
            print(f"[2.{name}] Interaction failed: {e}")

    # Take screenshot
    screenshot_path = SCREENSHOT_DIR / f"{name}.png"
    await page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"[2.{name}] Screenshot saved: {screenshot_path}")

    # Check for ECharts canvas (chart rendering indicator)
    echarts_canvases = await page.locator("canvas").count()
    print(f"[2.{name}] ECharts canvases found: {echarts_canvases}")

    # Check for Element Plus components
    el_cards = await page.locator(".el-card").count()
    el_selects = await page.locator(".el-select").count()
    el_tables = await page.locator(".el-table").count()
    print(f"[2.{name}] Element Plus: {el_cards} cards, {el_selects} selects, {el_tables} tables")

    # Check for empty/loading states
    empty_text = await page.locator(".el-empty, .empty-state").count()
    loading_spinners = await page.locator(".el-loading-mask, .is-loading").count()
    print(f"[2.{name}] Empty states: {empty_text}, Loading: {loading_spinners}")

    # Check page title
    title = await page.title()
    print(f"[2.{name}] Page title: {title}")

    # Get visible text content (sample)
    body_text = await page.locator("body").inner_text()
    # Truncate to first 500 chars for summary
    text_preview = body_text[:500].replace("\n", " | ")
    print(f"[2.{name}] Text preview: {text_preview}")

    return {
        "name": name,
        "url": url,
        "echarts_canvases": echarts_canvases,
        "el_cards": el_cards,
        "el_selects": el_selects,
        "el_tables": el_tables,
        "empty_states": empty_text,
        "loading": loading_spinners,
        "title": title,
    }


async def main():
    global console_errors, console_warnings

    print("╔════════════════════════════════════════════════════════╗")
    print("║  Grade Module Browser Rendering Verification          ║")
    print("╚════════════════════════════════════════════════════════╝")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = await context.new_page()

        # Collect console messages
        page.on("console", lambda msg: (
            console_errors.append(f"[{msg.type}] {msg.text}")
            if msg.type == "error"
            else console_warnings.append(f"[{msg.type}] {msg.text}")
            if msg.type == "warning"
            else None
        ))

        # Step 1: Login
        login_ok = await login(page)
        if not login_ok:
            print("\n❌ Login failed — cannot proceed with page verification")
            await browser.close()
            return

        # Step 2: Verify each grade page
        results = []
        for name, url in GRADE_PAGES.items():
            result = await verify_grade_page(page, name, url)
            results.append(result)

        # Step 3: Summary
        print("\n╔════════════════════════════════════════════════════════╗")
        print("║  Verification Summary                                 ║")
        print("╚════════════════════════════════════════════════════════╝")

        for r in results:
            status = "✅" if r["echarts_canvases"] > 0 or r["el_cards"] > 0 else "⚠️"
            print(f"  {status} {r['name']}: canvases={r['echarts_canvases']}, cards={r['el_cards']}, selects={r['el_selects']}")

        if console_errors:
            print(f"\n❌ Console Errors ({len(console_errors)}):")
            for err in console_errors[:10]:
                print(f"  {err}")
        else:
            print("\n✅ No console errors detected")

        if console_warnings:
            print(f"\n⚠️ Console Warnings ({len(console_warnings)}):")
            for w in console_warnings[:5]:
                print(f"  {w}")

        # Save detailed results as JSON
        report = {
            "login_success": login_ok,
            "pages": results,
            "console_errors": console_errors,
            "console_warnings": console_warnings[:20],
        }
        report_path = SCREENSHOT_DIR / "verification_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n📄 Full report saved: {report_path}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
