import { expect, test } from '@playwright/test'

// Seeds (src/mock/state/seeds.ts):
//  dc-seed-0001 running  manual     harnesses known
//  dc-seed-0002 stopped  manual     NO harness entry -> known:false -> "?"
//  dc-seed-0003 stopped  discovered claude-code not installed
//  dc-seed-0004 error    manual

test('running devcontainer shows Stop / Inject / Delete icon controls', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0001')
  await expect(page.getByTitle('Stop')).toBeVisible()
  await expect(page.getByTitle('Inject runtime')).toBeVisible()
  await expect(page.getByTitle('Delete')).toBeVisible()
})

test('stopped devcontainer shows Start', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0002')
  await expect(page.getByTitle('Start')).toBeVisible()
})

test('unknown harness status renders ? when runtime disconnected', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0002')
  await expect(page.getByText('?', { exact: true }).first()).toBeVisible()
})

test('discovered source is shown', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0003')
  await expect(page.getByText(/discovered/i).first()).toBeVisible()
})

test('deleting a manual devcontainer navigates back to the list', async ({ page }) => {
  page.on('dialog', (d) => d.accept()) // confirm()
  await page.goto('/devcontainers/dc-seed-0002')
  await page.getByTitle('Delete').click()
  await expect(page).toHaveURL(/\/devcontainers\/?$/)
})

// Spinner *persistence* (stays past POST resolve, clears only when the flag flips) is
// verified deterministically in the HarnessList unit test; the mock flips state
// synchronously so the spinner frame isn't observable here. This e2e just confirms the
// install action drives the harness to the Installed state through the SSE refetch path.
test('install action drives harness to Installed via SSE refetch', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0003') // claude-code not installed
  await page.getByTitle('Install claude-code', { exact: true }).click()
  await expect(page.getByTitle('Installed').first()).toBeVisible()
})
