import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHmac } from 'node:crypto';

const baseURL = (process.env.ALGOBOT_VISUAL_BASE_URL || 'https://algobot.dpdns.org').replace(/\/$/, '');
const username = process.env.ALGOBOT_VISUAL_USERNAME || '';
const password = process.env.ALGOBOT_VISUAL_PASSWORD || '';
const totpSecret = process.env.ALGOBOT_VISUAL_TOTP_SECRET || '';
const routes = (process.env.ALGOBOT_VISUAL_PATHS || '/notifications/,/security/,/analysis/')
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
    await page.locator('form button[type="submit"], form button').first().click();
    await page.waitForURL(url => !url.pathname.endsWith('/login/'), { timeout: 15000 }).catch(() => null);

    if (new URL(page.url()).pathname.endsWith('/login/')) {
      const otp = page.locator('input[autocomplete="one-time-code"], input[name="two_factor_code"], input[name="otp"], input[name="totp"], input[id*="otp"], input[id*="totp"]').first();
      if (await otp.count()) {
        if (!totpSecret) {
          await page.screenshot({ path: path.join(outputDir, 'login-mfa-required.png'), fullPage: true });
          throw new Error('The visual test account requires MFA. Add the ALGOBOT_VISUAL_TOTP_SECRET GitHub Actions secret to enable authenticated screenshots.');
        }
        await otp.fill(generateTotp(totpSecret));
        await page.locator('form button[type="submit"], form button').first().click();
        await page.waitForURL(url => !url.pathname.endsWith('/login/'), { timeout: 30000 });
      } else {
        const messages = await page.locator('[role="alert"], .alert-danger, .errorlist, .login-error').allTextContents().catch(() => []);
        await page.screenshot({ path: path.join(outputDir, 'login-auth-failed.png'), fullPage: true });
        throw new Error('Visual test sign-in did not complete. Check ALGOBOT_VISUAL_USERNAME/PASSWORD and account access. ' + messages.join(' ').trim());
      }
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
