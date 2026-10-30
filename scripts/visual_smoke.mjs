import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHmac } from 'node:crypto';

const baseURL = (process.env.ALGOBOT_VISUAL_BASE_URL || 'https://algobot.dpdns.org').replace(/\/$/, '');
const username = process.env.ALGOBOT_VISUAL_USERNAME || '';
const password = process.env.ALGOBOT_VISUAL_PASSWORD || '';
const totpSecret = process.env.ALGOBOT_VISUAL_TOTP_SECRET || '';
const routes = (process.env.ALGOBOT_VISUAL_PATHS || '/notifications/,/operations/security/,/analysis/,/profile/,/settings/,/account/identity/')
  .split(',').map(value => value.trim()).filter(Boolean);
const outputDir = process.env.VISUAL_OUTPUT_DIR || 'artifacts/chromium';
const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'tablet', width: 820, height: 1180 },
  { name: 'mobile', width: 390, height: 844 },
];

function generateTotp(secret, timestamp = Date.now()) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const normalized = String(secret || '').toUpperCase().replace(/[^A-Z2-7]/g, '');
  if (!normalized) throw new Error('ALGOBOT_VISUAL_TOTP_SECRET is empty.');
  let bits = '';
  for (const character of normalized) {
    const value = alphabet.indexOf(character);
    if (value < 0) throw new Error('ALGOBOT_VISUAL_TOTP_SECRET is not valid Base32.');
    bits += value.toString(2).padStart(5, '0');
  }
  const bytes = [];
  for (let index = 0; index + 8 <= bits.length; index += 8) {
    bytes.push(parseInt(bits.slice(index, index + 8), 2));
  }
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(timestamp / 30000)));
  const digest = createHmac('sha1', Buffer.from(bytes)).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const code = (digest.readUInt32BE(offset) & 0x7fffffff) % 1000000;
  return String(code).padStart(6, '0');
}

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
    await page.locator('form button[type="submit"]').first().click();
    const otp = page.locator('input[autocomplete="one-time-code"]:visible, input[name="two_factor_code"]:visible, input[name="otp"]:visible, input[name="totp"]:visible, input[id*="otp"]:visible, input[id*="totp"]:visible').first();
    await Promise.race([
      page.waitForURL(url => !url.pathname.endsWith('/login/'), { timeout: 15000 }).catch(() => null),
      otp.waitFor({ state: 'visible', timeout: 15000 }).catch(() => null),
    ]);

    if (await otp.count()) {
      if (!totpSecret) {
        await page.locator('#identifier').fill('').catch(() => {});
        await page.locator('#password').fill('').catch(() => {});
        await page.screenshot({ path: path.join(outputDir, 'login-mfa-required.png'), fullPage: true });
        throw new Error('The visual test account requires MFA. Add the ALGOBOT_VISUAL_TOTP_SECRET GitHub Actions secret to enable authenticated screenshots.');
      }
      await otp.fill(generateTotp(totpSecret));
      await page.locator('form button[type="submit"]').first().click();
      await page.waitForURL(url => !url.pathname.endsWith('/login/') && !/mfa|two.factor|verify/i.test(url.pathname), { timeout: 30000 });
    } else if (new URL(page.url()).pathname.endsWith('/login/') || /mfa|two.factor|verify/i.test(new URL(page.url()).pathname)) {
      const messages = await page.locator('[role="alert"], .alert-danger, .errorlist, .login-error').allTextContents().catch(() => []);
      await page.locator('#identifier').fill('').catch(() => {});
      await page.locator('#password').fill('').catch(() => {});
      await page.screenshot({ path: path.join(outputDir, 'login-auth-failed.png'), fullPage: true });
      throw new Error('Visual test sign-in did not complete. Check credentials and MFA configuration. ' + messages.join(' ').trim());
    }

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
        if (normalizedRoute === '/settings/') {
          await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
          const timezone = page.locator('#settings-timezone');
          if (await timezone.count()) {
            await timezone.evaluate(element => element.__abSelectRoot?.querySelector('.ab-select-trigger')?.scrollIntoView({ block: 'center' }));
            await timezone.evaluate(element => element.__abSelectRoot?.querySelector('.ab-select-trigger')?.click());
            const menu = page.locator('.ab-select-menu:not([hidden])').last();
            await menu.waitFor({ state: 'visible', timeout: 5000 });
            const bounds = await menu.boundingBox();
            const size = page.viewportSize();
            if (!bounds || bounds.x < 0 || bounds.y < 0 || bounds.x + bounds.width > size.width + 1 || bounds.y + bounds.height > size.height + 1) {
              failures.push(`${normalizedRoute} at ${viewport.name}: timezone menu is clipped or outside the viewport`);
            }
            const colors = await menu.evaluate(element => {
              const style = getComputedStyle(element);
              return { background: style.backgroundColor, text: style.color };
            });
            if (colors.background === colors.text) failures.push(`${normalizedRoute} at ${viewport.name}: timezone menu text is not distinguishable from its background`);
            const search = menu.locator('.ab-select-search');
            if (await search.isVisible()) {
              await search.fill('Africa/Nairobi');
              const matches = await menu.locator('.ab-select-option:not([hidden])').count();
              if (matches !== 1) failures.push(`${normalizedRoute} at ${viewport.name}: searchable timezone menu returned ${matches} matches for Africa/Nairobi`);
            } else {
              failures.push(`${normalizedRoute} at ${viewport.name}: timezone menu has no accessible search control`);
            }
            await page.keyboard.press('Escape');
          } else {
            failures.push(`${normalizedRoute} at ${viewport.name}: timezone preference control is missing`);
          }
        }
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
