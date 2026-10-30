import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const baseURL = (process.env.ALGOBOT_VISUAL_BASE_URL || 'https://algobot.dpdns.org').replace(/\/$/, '');
const username = process.env.ALGOBOT_VISUAL_USERNAME || '';
const password = process.env.ALGOBOT_VISUAL_PASSWORD || '';
const routes = (process.env.ALGOBOT_VISUAL_PATHS || '/notifications/,/security/,/analysis/')
  .split(',').map(value => value.trim()).filter(Boolean);
const outputDir = process.env.VISUAL_OUTPUT_DIR || 'artifacts/chromium';
const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'tablet', width: 820, height: 1180 },
  { name: 'mobile', width: 390, height: 844 },
];

await fs.mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: viewports[0], deviceScaleFactor: 1 });
const page = await context.newPage();
const failures = [];

try {
  const loginResponse = await page.goto(`${baseURL}/login/`, { waitUntil: 'domcontentloaded', timeout: 45000 });
  if (!loginResponse || loginResponse.status() >= 400) {
    throw new Error(`Login page returned ${loginResponse?.status() ?? 'no response'}`);
  }

  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(`${baseURL}/login/`, { waitUntil: 'networkidle', timeout: 45000 });
    await page.screenshot({ path: path.join(outputDir, `login-${viewport.name}.png`), fullPage: true });
  }

  if (username && password) {
    await page.setViewportSize(viewports[0]);
    await page.goto(`${baseURL}/login/`, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.locator('#identifier').fill(username);
    await page.locator('#password').fill(password);
    await Promise.all([
      page.waitForURL(url => !url.pathname.endsWith('/login/'), { timeout: 30000 }),
      page.locator('form button[type="submit"], form button').first().click(),
    ]);
    if (page.url().includes('/login/')) throw new Error('Visual test credentials did not complete sign-in (MFA may be required).');

    for (const route of routes) {
      const normalizedRoute = route.startsWith('/') ? route : `/${route}`;
      for (const viewport of viewports) {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        const response = await page.goto(`${baseURL}${normalizedRoute}`, { waitUntil: 'networkidle', timeout: 60000 });
        if (!response || response.status() >= 400) {
          failures.push(`${normalizedRoute} at ${viewport.name}: HTTP ${response?.status() ?? 'no response'}`);
          continue;
        }
        if (new URL(page.url()).pathname.endsWith('/login/')) {
          failures.push(`${normalizedRoute} at ${viewport.name}: redirected to login; check account access or route`);
          continue;
        }
        await page.screenshot({
          path: path.join(outputDir, `${normalizedRoute.replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '') || 'page'}-${viewport.name}.png`),
          fullPage: true,
        });
      }
    }
  } else {
    console.log('No visual-test credentials supplied; captured public login page only. Set repository secrets to enable authenticated workspace screenshots.');
  }

  if (failures.length) throw new Error(failures.join('\n'));
  console.log(`Chromium screenshots saved to ${outputDir}`);
} finally {
  await browser.close();
}
