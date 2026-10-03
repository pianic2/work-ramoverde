import { expect, test } from '@playwright/test';

test('home page renders the RamoVerde shell and reserved-area navigation', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'RamoVerde' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Area riservata' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'it');
});
