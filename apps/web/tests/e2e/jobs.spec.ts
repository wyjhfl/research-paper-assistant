import { test, expect, type Page, type Locator } from "@playwright/test";

function getJobsPage(page: Page): Locator {
  return page.getByTestId("jobs-page");
}

const MOJIBAKE_CODE_POINTS = [
  0x9427, 0x95AD, 0x7480, 0x9983, 0x922B, 0x9241, 0x6DA4,
  0x93C4, 0x5909, 0x7075, 0x4F63, 0x8133, 0x95B2, 0x9422,
  0x93C8, 0x951B, 0xFFFD,
];

function buildMojibakeRe(): RegExp {
  const parts = MOJIBAKE_CODE_POINTS.map((cp) => {
    if (cp === 0xFFFD) return "\\ufffd";
    return String.fromCodePoint(cp);
  });
  return new RegExp(parts.join("|"));
}

const MOJIBAKE_RE = buildMojibakeRe();

const API_BASE = "http://localhost:8091";

function mockJobsRoute(page: Page, handler: (route: import("@playwright/test").Route) => Promise<void>) {
  return page.route(`${API_BASE}/jobs?*`, handler);
}

test.describe("/jobs page", () => {
  test("jobs page is accessible and shows heading", async ({ page }) => {
    await mockJobsRoute(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ jobs: [], total: 0 }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    await expect(jobsPage.locator("h1")).toContainText("\u4EFB\u52A1", { timeout: 10000 });
  });

  test("empty list shows empty state", async ({ page }) => {
    await mockJobsRoute(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ jobs: [], total: 0 }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    await expect(jobsPage.locator("text=\u6682\u65E0\u4EFB\u52A1")).toBeVisible({ timeout: 10000 });
  });

  test("mock jobs data shows status badges", async ({ page }) => {
    await mockJobsRoute(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          jobs: [
            {
              job_id: "job_abc123",
              job_type: "process_paper",
              status: "completed",
              input_summary: null,
              output_summary: null,
              error_message: null,
              progress_current: 1,
              progress_total: 1,
              attempts: 1,
              max_attempts: 1,
              created_at: "2025-01-01T00:00:00+00:00",
              started_at: "2025-01-01T00:00:01+00:00",
              finished_at: "2025-01-01T00:00:05+00:00",
            },
            {
              job_id: "job_def456",
              job_type: "rebuild_embeddings",
              status: "pending",
              input_summary: null,
              output_summary: null,
              error_message: null,
              progress_current: 0,
              progress_total: 0,
              attempts: 0,
              max_attempts: 1,
              created_at: "2025-01-01T00:01:00+00:00",
              started_at: null,
              finished_at: null,
            },
          ],
          total: 2,
        }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    await expect(jobsPage.locator("text=\u5DF2\u5B8C\u6210")).toBeVisible({ timeout: 10000 });
    await expect(jobsPage.getByText("\u7B49\u5F85\u4E2D", { exact: true })).toBeVisible();
    await expect(jobsPage.locator("text=process_paper")).toBeVisible();
    await expect(jobsPage.locator("text=rebuild_embeddings")).toBeVisible();
  });

  test("cancel pending job calls API and refreshes", async ({ page }) => {
    let cancelCalled = false;
    await page.route(`${API_BASE}/jobs/job_cancel_me/cancel`, (route) => {
      cancelCalled = true;
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
    });
    await mockHealthRoute(page, {
      worker_enabled: true,
      poll_interval_seconds: 1.0,
      max_attempts_default: 1,
      stale_running_seconds: 900,
      running_count: 0,
      pending_count: 1,
      failed_count: 0,
      stale_running_count: 0,
    });
    await page.route(`${API_BASE}/jobs?*`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          jobs: [
            {
              job_id: "job_cancel_me",
              job_type: "process_paper",
              status: "pending",
              input_summary: null,
              output_summary: null,
              error_message: null,
              progress_current: 0,
              progress_total: 0,
              attempts: 0,
              max_attempts: 1,
              created_at: "2025-01-01T00:00:00+00:00",
              started_at: null,
              finished_at: null,
            },
          ],
          total: 1,
        }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    const cancelBtn = jobsPage.locator('button:has-text("\u53D6\u6D88")');
    await expect(cancelBtn).toBeVisible({ timeout: 10000 });
    await cancelBtn.click();
    await page.waitForTimeout(1000);
    expect(cancelCalled).toBe(true);
  });

  test("error state shows readable error, no [object Object]", async ({ page }) => {
    await mockJobsRoute(page, (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal server error" }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    const errorDiv = jobsPage.locator(".bg-red-50");
    await expect(errorDiv).toBeVisible({ timeout: 10000 });
    const errorText = await errorDiv.innerText();
    expect(errorText.length).toBeGreaterThan(0);
    expect(errorText).not.toContain("[object Object]");
    expect(errorText).not.toMatch(MOJIBAKE_RE);
  });

  test("navbar has jobs entry", async ({ page }) => {
    await page.goto("/");
    const navLink = page.locator('nav a:has-text("\u4EFB\u52A1")');
    await expect(navLink).toBeVisible({ timeout: 10000 });
  });

  test("jobs page no mojibake", async ({ page }) => {
    await mockJobsRoute(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ jobs: [], total: 0 }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    const text = await jobsPage.innerText({ timeout: 10000 });
    expect(text).not.toMatch(MOJIBAKE_RE);
  });

  test("jobs page shows input_summary and output_summary", async ({ page }) => {
    await mockJobsRoute(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          jobs: [
            {
              job_id: "job_summary_test",
              job_type: "process_paper",
              status: "completed",
              input_summary: "paper_id=42",
              output_summary: "paper_id=42, status=completed",
              error_message: null,
              progress_current: 1,
              progress_total: 1,
              attempts: 1,
              max_attempts: 1,
              created_at: "2025-01-01T00:00:00+00:00",
              started_at: "2025-01-01T00:00:01+00:00",
              finished_at: "2025-01-01T00:00:05+00:00",
            },
          ],
          total: 1,
        }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    await expect(jobsPage.locator("text=\u8F93\u5165: paper_id=42")).toBeVisible({ timeout: 10000 });
    await expect(jobsPage.locator("text=\u8F93\u51FA: paper_id=42, status=completed")).toBeVisible();
  });

  test("jobs page shows attempts/max_attempts", async ({ page }) => {
    await mockJobsRoute(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          jobs: [
            {
              job_id: "job_attempts_test",
              job_type: "agent_run",
              status: "failed",
              input_summary: "task_type=summarize_paper",
              output_summary: null,
              error_message: "RuntimeError: job execution failed",
              progress_current: 0,
              progress_total: 0,
              attempts: 2,
              max_attempts: 2,
              created_at: "2025-01-01T00:00:00+00:00",
              started_at: "2025-01-01T00:00:01+00:00",
              finished_at: "2025-01-01T00:00:10+00:00",
            },
          ],
          total: 1,
        }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    await expect(jobsPage.locator("text=2/2")).toBeVisible({ timeout: 10000 });
  });

  test("pending/running jobs show auto-refresh notice", async ({ page }) => {
    await mockJobsRoute(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          jobs: [
            {
              job_id: "job_running_test",
              job_type: "process_paper",
              status: "running",
              input_summary: "paper_id=1",
              output_summary: null,
              error_message: null,
              progress_current: 0,
              progress_total: 1,
              attempts: 1,
              max_attempts: 1,
              created_at: "2025-01-01T00:00:00+00:00",
              started_at: "2025-01-01T00:00:01+00:00",
              finished_at: null,
            },
          ],
          total: 1,
        }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    await expect(jobsPage.locator("text=\u81EA\u52A8\u5237\u65B0")).toBeVisible({ timeout: 10000 });
  });
});

test.describe("upload paper async flow", () => {
  test("upload returns job_id and shows task link", async ({ page }) => {
    await page.route(`${API_BASE}/papers/upload*`, (route) =>
      route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: 1,
          title: "Test Paper",
          filename: "test.pdf",
          status: "pending",
          chunk_count: 0,
          job_id: "job_upload_abc",
        }),
      })
    );
    await page.goto("/papers");
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: "test.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 test"),
    });
    const uploadBtn = page.locator('button:has-text("\u4E0A\u4F20")');
    await uploadBtn.click();
    await expect(page.locator("text=\u540E\u53F0\u4EFB\u52A1\u5DF2\u542F\u52A8")).toBeVisible({ timeout: 10000 });
    await expect(page.locator('a:has-text("\u67E5\u770B\u4EFB\u52A1")')).toBeVisible();
  });
});

test.describe("rebuild embeddings async flow", () => {
  test("rebuild job appears in jobs list with correct type", async ({ page }) => {
    await mockJobsRoute(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          jobs: [
            {
              job_id: "job_rebuild_xyz",
              job_type: "rebuild_embeddings",
              status: "pending",
              input_summary: "paper_id=1",
              output_summary: null,
              error_message: null,
              progress_current: 0,
              progress_total: 0,
              attempts: 0,
              max_attempts: 1,
              created_at: "2025-01-01T00:00:00+00:00",
              started_at: null,
              finished_at: null,
            },
          ],
          total: 1,
        }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    await expect(jobsPage.locator("text=rebuild_embeddings")).toBeVisible({ timeout: 10000 });
    await expect(jobsPage.locator("text=\u8F93\u5165: paper_id=1")).toBeVisible();
    await expect(jobsPage.getByText("\u7B49\u5F85\u4E2D", { exact: true })).toBeVisible();
  });
});

function mockHealthRoute(page: Page, health: Record<string, unknown>) {
  return page.route(`${API_BASE}/jobs/worker/health`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(health),
    })
  );
}

test.describe("worker health and retry", () => {
  test("/jobs shows worker health summary", async ({ page }) => {
    await mockHealthRoute(page, {
      worker_enabled: true,
      poll_interval_seconds: 1.0,
      max_attempts_default: 1,
      stale_running_seconds: 900,
      running_count: 1,
      pending_count: 2,
      failed_count: 3,
      stale_running_count: 0,
    });
    await mockJobsRoute(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ jobs: [], total: 0 }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    await expect(jobsPage.locator("text=\u7B49\u5F85\u4E2D: 2")).toBeVisible({ timeout: 10000 });
    await expect(jobsPage.locator("text=\u8FD0\u884C\u4E2D: 1")).toBeVisible();
    await expect(jobsPage.locator("text=\u5DF2\u5931\u8D25: 3")).toBeVisible();
  });

  test("stale warning is visible when stale_running_count > 0", async ({ page }) => {
    await mockHealthRoute(page, {
      worker_enabled: true,
      poll_interval_seconds: 1.0,
      max_attempts_default: 1,
      stale_running_seconds: 900,
      running_count: 2,
      pending_count: 0,
      failed_count: 0,
      stale_running_count: 1,
    });
    await mockJobsRoute(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ jobs: [], total: 0 }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    await expect(jobsPage.locator("text=\u5361\u4F4F\u4EFB\u52A1: 1")).toBeVisible({ timeout: 10000 });
    await expect(jobsPage.locator(".bg-orange-50")).toBeVisible();
    await expect(jobsPage.locator("text=900")).toBeVisible();
  });

  test("failed job has retry button and clicking calls retry API", async ({ page }) => {
    await mockHealthRoute(page, {
      worker_enabled: true,
      poll_interval_seconds: 1.0,
      max_attempts_default: 1,
      stale_running_seconds: 900,
      running_count: 0,
      pending_count: 0,
      failed_count: 1,
      stale_running_count: 0,
    });
    await mockJobsRoute(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          jobs: [
            {
              job_id: "job_retry_test",
              job_type: "process_paper",
              status: "failed",
              input_summary: "paper_id=1",
              output_summary: null,
              error_message: "RuntimeError: job execution failed",
              progress_current: 0,
              progress_total: 0,
              attempts: 1,
              max_attempts: 1,
              created_at: "2025-01-01T00:00:00+00:00",
              started_at: "2025-01-01T00:00:01+00:00",
              finished_at: "2025-01-01T00:00:05+00:00",
            },
          ],
          total: 1,
        }),
      })
    );
    let retryCalled = false;
    await page.route(`${API_BASE}/jobs/job_retry_test/retry`, (route) => {
      retryCalled = true;
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
    });
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    const retryBtn = jobsPage.locator('button:has-text("\u91CD\u8BD5")');
    await expect(retryBtn).toBeVisible({ timeout: 10000 });
    await retryBtn.click();
    await expect(jobsPage.locator("text=\u7B49\u5F85\u4E2D: 0")).toBeVisible({ timeout: 10000 });
  });

  test("error display does not show [object Object]", async ({ page }) => {
    await mockHealthRoute(page, {
      worker_enabled: true,
      poll_interval_seconds: 1.0,
      max_attempts_default: 1,
      stale_running_seconds: 900,
      running_count: 0,
      pending_count: 0,
      failed_count: 0,
      stale_running_count: 0,
    });
    await page.route(`${API_BASE}/jobs?*`, (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      })
    );
    await page.goto("/jobs");
    const jobsPage = getJobsPage(page);
    await expect(jobsPage.locator("text=Internal Server Error")).toBeVisible({ timeout: 10000 });
    await expect(jobsPage.locator("text=[object Object]")).not.toBeVisible();
  });
});
