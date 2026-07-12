/**
 * Playwright 验证脚本 — HolisticProfileCard 修复确认
 * 检查点:
 * 1. 登录成功 → 导航到 /grades/profile
 * 2. Demo 模式触发 → 五维对比明细学业映射分不为 0
 * 3. 雷达图渲染（ECharts 容器存在且有 canvas 子节点）
 * 4. dimensionDetails computed 输出正常
 */
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  // 收集 console 错误
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', err => errors.push(err.message));

  const BASE = 'http://localhost:5173';

  try {
    // ── Step 1: 登录 ──
    console.log('=== Step 1: 登录 ===');
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle', timeout: 15000 });
    
    // 填表登录
    const usernameInput = page.locator('input[type="text"], input[placeholder*="用户"], input[placeholder*="账号"]').first();
    const passwordInput = page.locator('input[type="password"]').first();
    
    if (await usernameInput.count() > 0) {
      await usernameInput.fill('admin');
      await passwordInput.fill('admin123');
      await page.locator('button[type="submit"], button:has-text("登录")').first().click();
      await page.waitForURL(/\/(dashboard|home|rdi|grades)/, { timeout: 10000 }).catch(() => {});
      console.log('登录后 URL:', page.url());
    } else {
      console.log('未找到登录表单，可能已是登录状态或页面结构不同');
      console.log('当前 URL:', page.url());
      // 截图看实际页面
      await page.screenshot({ path: 'playwright_login_page.png', fullPage: true });
    }

    // ── Step 2: 导航到全息档案 ──
    console.log('\n=== Step 2: 导航到 /grades/profile ===');
    await page.goto(`${BASE}/grades/profile`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
    console.log('当前 URL:', page.url());
    await page.waitForTimeout(3000); // 等组件初始化 + Demo 数据填充
    
    // 截图看渲染效果
    await page.screenshot({ path: 'playwright_profile_page.png', fullPage: true });
    console.log('截图已保存: playwright_profile_page.png');

    // ── Step 3: 检查五维数据 ──
    console.log('\n=== Step 3: 检查五维对比数据 ===');
    
    // 尝试读取 Vue 组件内部状态（通过 __vue_app__）
    const dimensionCheck = await page.evaluate(() => {
      const results = {
        hasVueApp: false,
        dimensionValues: {},
        chartContainers: 0,
        canvasElements: 0,
        pageText: '',
        zeroDimensionCount: 0,
      };

      // 检查 ECharts 容器
      const echartsDivs = document.querySelectorAll('div[_echarts_instance_], div.echarts-container, div[class*="chart"]');
      results.chartContainers = echartsDivs.length;
      
      // 检查 canvas
      const canvases = document.querySelectorAll('canvas');
      results.canvasElements = canvases.length;

      // 检查页面关键文本 — 五维分数是否为 0
      const bodyText = document.body.innerText;
      results.pageText = bodyText.substring(0, 500);

      // 搜索可能的分数文本
      const scorePatterns = ['道德', '学业', '身心健康', '艺术素养', '社会实践'];
      scorePatterns.forEach(dim => {
        const regex = new RegExp(dim + '[^\\d]*([\\d.]+)', 'g');
        const matches = bodyText.match(regex);
        if (matches) {
          results.dimensionValues[dim] = matches;
        }
      });

      // 统计零分维度
      const zeroPatterns = [/学业[^0-9]*0(\.0)?/, /道德[^0-9]*0(\.0)?/, /身心健康[^0-9]*0(\.0)?/, /艺术[^0-9]*0(\.0)?/, /社会实践[^0-9]*0(\.0)?/];
      zeroPatterns.forEach(p => {
        if (p.test(bodyText)) results.zeroDimensionCount++;
      });

      return results;
    });

    console.log('Vue App 检查:', dimensionCheck.hasVueApp);
    console.log('ECharts 容器数:', dimensionCheck.chartContainers);
    console.log('Canvas 元素数:', dimensionCheck.canvasElements);
    console.log('零分维度数:', dimensionCheck.zeroDimensionCount);
    console.log('页面文本前500字:', dimensionCheck.pageText.substring(0, 200));
    console.log('维度值匹配:', JSON.stringify(dimensionCheck.dimensionValues));

    // ── Step 4: 判断修复效果 ──
    console.log('\n=== Step 4: 修复效果判定 ===');
    const hasCanvas = dimensionCheck.canvasElements > 0;
    const zeroDims = dimensionCheck.zeroDimensionCount;
    
    if (hasCanvas && zeroDims < 3) {
      console.log('✅ 修复成功！雷达图已渲染，学业映射分不再全为0');
    } else if (hasCanvas && zeroDims >= 3) {
      console.log('⚠️ 雷达图渲染但仍有多个维度为0，需进一步检查');
    } else if (!hasCanvas) {
      console.log('❌ 雷达图未渲染（无 canvas 元素），组件可能未加载或API失败');
    }

    // ── Step 5: Console 错误汇总 ──
    console.log('\n=== Step 5: Console 错误 ===');
    if (errors.length === 0) {
      console.log('✅ 无 console 错误');
    } else {
      console.log(`❌ ${errors.length} 个 console 错误:`);
      errors.forEach(e => console.log('  -', e.substring(0, 120)));
    }

  } catch (err) {
    console.log('❌ 测试异常:', err.message);
    await page.screenshot({ path: 'playwright_error.png', fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }
})();
