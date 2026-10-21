const {defineConfig} = require('@playwright/test');
const chromiumLaunch = process.env.RADAR_TEST_CHROMIUM ? {executablePath:process.env.RADAR_TEST_CHROMIUM} : {};
module.exports = defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.spec.cjs',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30000,
  expect: {timeout: 5000},
  forbidOnly: !!process.env.CI,
  reporter: [['line'], ['html', {open:'never'}]],
  use: {trace:'retain-on-failure', screenshot:'only-on-failure'},
  projects: [
    {name:'chromium-desktop', use:{browserName:'chromium', viewport:{width:1280,height:900}, launchOptions:chromiumLaunch}},
    {name:'chromium-celular', use:{browserName:'chromium', viewport:{width:390,height:844}, isMobile:true, hasTouch:true, launchOptions:chromiumLaunch}},
    // Gecko com tela estreita e toque. Playwright nao automatiza Firefox Android.
    {name:'firefox-desktop', use:{browserName:'firefox', viewport:{width:1280,height:900}}},
    {name:'firefox-tela-estreita', use:{browserName:'firefox', viewport:{width:390,height:844}, hasTouch:true}},
  ],
});
