import { expect, test } from '@playwright/test';

test('home page provides API shell and account navigation', async ({ page }) => {
  await page.route('**/api/v1/health/live', (route) => route.fulfill({ json: { status: 'ok' } }));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /build the product/i })).toBeVisible();
  await expect(page.getByRole('status')).toContainText('API connected');
});
