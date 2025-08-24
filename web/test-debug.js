import { chromium } from 'playwright';

(async () => {
  console.log('='.repeat(80));
  console.log('Testing Web Interface at http://192.168.1.219:1985/');
  console.log('='.repeat(80));

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Collect console messages
  const consoleMessages = [];
  page.on('console', msg => {
    consoleMessages.push({
      type: msg.type(),
      text: msg.text(),
      location: msg.location()
    });
  });

  // Collect API requests
  const apiRequests = [];
  page.on('request', request => {
    if (request.url().includes('/api/')) {
      apiRequests.push({
        url: request.url(),
        method: request.method()
      });
    }
  });

  // Collect API responses
  const apiResponses = [];
  page.on('response', response => {
    if (response.url().includes('/api/')) {
      apiResponses.push({
        url: response.url(),
        status: response.status(),
        ok: response.ok()
      });
    }
  });

  console.log('\n1. Loading main page...');
  await page.goto('http://192.168.1.219:1985/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);

  const title = await page.title();
  console.log(`   Page title: ${title}`);

  console.log('\n2. Checking for key UI elements...');
  
  // Check navigation
  const navItems = await page.$$('nav a');
  console.log(`   Navigation items found: ${navItems.length}`);
  for (const item of navItems) {
    const text = await item.innerText();
    const href = await item.getAttribute('href');
    console.log(`      - ${text}: ${href}`);
  }

  // Check main content
  const mainContent = await page.$('main');
  if (mainContent) {
    console.log('   Main content area: Found');
    const contentText = await mainContent.innerText();
    console.log(`   Content length: ${contentText.length} characters`);
    if (contentText.length < 500) {
      console.log(`   Content preview: ${contentText.substring(0, 200)}`);
    }
  } else {
    console.log('   Main content area: NOT FOUND');
  }

  console.log('\n3. Checking Overview page elements...');
  
  // Check for dashboard header
  const dashboardHeader = await page.$('h1');
  if (dashboardHeader) {
    const headerText = await dashboardHeader.innerText();
    console.log(`   Dashboard header: ${headerText}`);
  }

  // Look for statistics cards
  const statCards = await page.$$('.bg-white.rounded-lg.shadow, .bg-gray-800.rounded-lg.shadow');
  console.log(`   Statistics cards found: ${statCards.length}`);

  // Check for loading spinner
  const spinner = await page.$('.animate-spin');
  if (spinner) {
    console.log('   ⚠️ Loading spinner is still visible!');
  }

  // Check for error messages
  const errorDivs = await page.$$('.bg-red-50, .bg-red-900');
  if (errorDivs.length > 0) {
    console.log(`   ⚠️ Error messages found: ${errorDivs.length}`);
    for (const err of errorDivs) {
      const errText = await err.innerText();
      console.log(`      - ${errText}`);
    }
  }

  console.log('\n4. Console Messages:');
  console.log(`   Total console messages: ${consoleMessages.length}`);
  
  // Show last 20 messages
  const lastMessages = consoleMessages.slice(-20);
  for (const msg of lastMessages) {
    if (msg.text.includes('logger.js') || msg.text.includes('Overview') || msg.text.includes('API')) {
      console.log(`   [${msg.type}] ${msg.text.substring(0, 200)}`);
    }
  }

  console.log('\n5. API Requests Made:');
  console.log(`   Total API requests: ${apiRequests.length}`);
  for (const req of apiRequests) {
    console.log(`   - ${req.method} ${req.url}`);
  }

  console.log('\n6. API Responses:');
  console.log(`   Total API responses: ${apiResponses.length}`);
  for (const resp of apiResponses) {
    const statusIcon = resp.ok ? '✓' : '✗';
    console.log(`   ${statusIcon} ${resp.status} ${resp.url}`);
  }

  console.log('\n7. Testing other pages...');
  
  // Test Config page
  console.log('\n   Testing /config page...');
  await page.goto('http://192.168.1.219:1985/config', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  
  const configHeader = await page.$('h1');
  if (configHeader) {
    const text = await configHeader.innerText();
    console.log(`   Config header: ${text}`);
  }
  const configContent = await page.$('main');
  if (configContent) {
    const text = await configContent.innerText();
    console.log(`   Config content length: ${text.length} characters`);
  }

  // Clear previous API tracking
  apiRequests.length = 0;
  apiResponses.length = 0;

  // Test Templates page
  console.log('\n   Testing /templates page...');
  await page.goto('http://192.168.1.219:1985/templates', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  
  const templatesHeader = await page.$('h2');
  if (templatesHeader) {
    const text = await templatesHeader.innerText();
    console.log(`   Templates header: ${text}`);
  }

  console.log(`   Templates API requests: ${apiRequests.filter(r => r.url.includes('/templates')).length}`);

  // Test Logs page
  console.log('\n   Testing /logs page...');
  await page.goto('http://192.168.1.219:1985/logs', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  
  const logsHeader = await page.$('h2');
  if (logsHeader) {
    const text = await logsHeader.innerText();
    console.log(`   Logs header: ${text}`);
  }

  console.log(`   Logs API requests: ${apiRequests.filter(r => r.url.includes('/logs')).length}`);

  console.log('\n8. Returning to Overview page...');
  await page.goto('http://192.168.1.219:1985/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // Take a screenshot
  await page.screenshot({ path: 'web_interface_debug.png' });
  console.log('\n   Screenshot saved to web_interface_debug.png');

  console.log('\n9. Final Console Messages (last 10):');
  const finalMessages = consoleMessages.slice(-10);
  for (const msg of finalMessages) {
    console.log(`   [${msg.type}] ${msg.text.substring(0, 200)}`);
  }

  console.log('\n10. Checking localStorage:');
  const authEnabled = await page.evaluate(() => localStorage.getItem('auth_enabled'));
  const accessToken = await page.evaluate(() => localStorage.getItem('access_token'));
  console.log(`   auth_enabled: ${authEnabled}`);
  console.log(`   has access_token: ${!!accessToken}`);

  await browser.close();
  
  console.log('\n' + '='.repeat(80));
  console.log('Test Complete');
  console.log('=' + '='.repeat(80));
})();