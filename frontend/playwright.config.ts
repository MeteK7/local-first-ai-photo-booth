import { defineConfig } from '@playwright/test';

const edgePath = process.env['PHOTOBOOTH_EDGE_PATH'];

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: process.env['PHOTOBOOTH_TEST_URL'] ?? 'http://127.0.0.1:8000',
    channel: 'msedge',
    launchOptions: edgePath ? { executablePath: edgePath } : {},
  },
});
