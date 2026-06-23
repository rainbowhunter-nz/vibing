import { expect, test } from '@playwright/test'

// Seeds (src/mock/state/seeds.ts):
//  dc-seed-0001 running  manual     harnesses known  runtime connected
//  dc-seed-0002 stopped  manual     NO harness entry -> known:false -> "container not running" message  runtime error (seeded)
//  dc-seed-0003 stopped  discovered claude-code not installed
//  dc-seed-0004 error    manual

test('running devcontainer shows Stop / Stop-runtime / Remove container icon controls', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0001')
  await expect(page.getByTitle('Stop', { exact: true })).toBeVisible()
  await expect(page.getByTitle('Stop runtime')).toBeVisible()
  await expect(page.getByTitle('Remove container')).toBeVisible()
})

test('stopped devcontainer shows Start', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0002')
  await expect(page.getByTitle('Start', { exact: true })).toBeVisible()
})

test('stopped devcontainer shows runtime state with Inject disabled', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0002')
  // dc-seed-0002 is seeded with runtime state 'error' (see SEED_RUNTIME)
  await expect(page.getByRole('main').getByText('Error', { exact: true })).toBeVisible()
  await expect(page.getByTitle('Start the container to inject runtime')).toBeDisabled()
})

test('stopping a running devcontainer reverts runtime and harness panel to unknown', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0001') // running, runtime connected, harnesses known
  await expect(page.getByRole('main').getByText('Connected', { exact: true })).toBeVisible()
  await page.getByTitle('Stop', { exact: true }).click()
  await expect(page.getByRole('main').getByText('Disconnected', { exact: true })).toBeVisible()
  // Container is now stopped → harness status is container-scoped, not runtime-scoped
  await expect(page.getByText(/container not running/i).first()).toBeVisible()
})

test('runtime section: connected shows Stop and live logs dialog', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0001')
  await expect(page.getByRole('main').getByText('Connected', { exact: true })).toBeVisible()
  await expect(page.getByTitle('Stop runtime')).toBeVisible()
  await page.getByTitle('View runtime logs').click()
  await expect(page.getByRole('dialog').getByText('Runtime logs')).toBeVisible()
  await expect(page.getByRole('dialog').getByText(/runtime started/)).toBeVisible()
})

test('stopped container shows a descriptive harness message', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0002')
  // dc-seed-0002 is stopped → no harness entry → known:false → container-scoped message
  await expect(page.getByText(/container not running/i).first()).toBeVisible()
})

test('discovered source is shown', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0003')
  await expect(page.getByText(/discovered/i).first()).toBeVisible()
})

test('removing a container keeps the devcontainer and stays on the detail page', async ({ page }) => {
  page.on('dialog', (d) => d.accept()) // confirm()
  await page.goto('/devcontainers/dc-seed-0001') // running
  await page.getByTitle('Remove container').click()
  await expect(page).toHaveURL(/\/devcontainers\/dc-seed-0001$/)
  await expect(page.getByTitle('Start', { exact: true })).toBeVisible() // back to stopped
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
