import { test, expect, type Page, type Locator } from "@playwright/test";

function getAppMain(page: Page): Locator {
  return page.getByTestId("app-main");
}

test.describe("/usage 页面", () => {
  test("h1 包含'模型调用与质量看板'", async ({ page }) => {
    await page.goto("/usage");
    const h1 = getAppMain(page).locator("h1").first();
    await expect(h1).toContainText("模型调用与质量看板");
  });

  test("mock 空列表时显示 empty 状态", async ({ page }) => {
    await page.route("**/usage/model-calls**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          events: [],
          total: 0,
        }),
      })
    );
    await page.route("**/usage/model-calls/summary**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total_calls: 0,
          success_calls: 0,
          failed_calls: 0,
          avg_duration_ms: 0,
          calls_by_operation: {},
          calls_by_provider: {},
        }),
      })
    );
    await page.route("**/usage/eval-report/latest**", (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "No eval report found" }),
      })
    );

    await page.goto("/usage");
    const main = getAppMain(page);
    await expect(main.locator("h1").first()).toContainText("模型调用与质量看板");
    await expect(main.locator("[data-testid='usage-empty']")).toBeVisible({ timeout: 10000 });
  });

  test("mock summary 返回统计时显示 total_calls / failed_calls / avg_duration_ms", async ({ page }) => {
    await page.route("**/usage/model-calls**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          events: [],
          total: 0,
        }),
      })
    );
    await page.route("**/usage/model-calls/summary**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total_calls: 42,
          success_calls: 40,
          failed_calls: 2,
          avg_duration_ms: 123.5,
          calls_by_operation: { embedding_query: 20, llm_answer: 22 },
          calls_by_provider: { local: 30, openai_compatible: 12 },
        }),
      })
    );
    await page.route("**/usage/eval-report/latest**", (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "No eval report found" }),
      })
    );

    await page.goto("/usage");
    const main = getAppMain(page);
    await expect(main.locator("[data-testid='total-calls']")).toContainText("42", { timeout: 10000 });
    await expect(main.locator("[data-testid='failed-calls']")).toContainText("2");
    await expect(main.locator("[data-testid='avg-duration']")).toContainText("123.5");
  });

  test("mock eval-report 返回 passed 报告时显示 can_proceed 和 case 状态", async ({ page }) => {
    await page.route("**/usage/model-calls**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ events: [], total: 0 }),
      })
    );
    await page.route("**/usage/model-calls/summary**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total_calls: 0,
          success_calls: 0,
          failed_calls: 0,
          avg_duration_ms: 0,
          calls_by_operation: {},
          calls_by_provider: {},
        }),
      })
    );
    await page.route("**/usage/eval-report/latest**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          timestamp: "2025-05-24T10:00:00+00:00",
          can_proceed: true,
          metadata: {
            llm_model: "gpt-4",
            embedding_model: "text-embedding-3-small",
            embedding_dimension: 1536,
            case_file: "",
          },
          totals: { total: 3, passed: 3, warning: 0, failed: 0, blocker_failed: 0 },
          trend: { previous_report_count: 0, previous_latest_timestamp: null, passed_delta: 0, warning_delta: 0, failed_delta: 0 },
          cases: [
            { case_id: "single_rag_basic", type: "single_rag", severity: "blocker", status: "passed", duration_ms: 1200, warnings: [] },
            { case_id: "multi_rag_filter", type: "multi_rag", severity: "blocker", status: "passed", duration_ms: 800, warnings: [] },
          ],
        }),
      })
    );

    await page.goto("/usage");
    const main = getAppMain(page);
    await expect(main.locator("[data-testid='eval-can-proceed']")).toContainText("通过", { timeout: 10000 });
    await expect(main.locator("[data-testid='eval-totals']")).toContainText("3 / 3");
    await expect(main.locator("[data-testid='eval-cases-table']")).toBeVisible();
  });

  test("mock usage API 失败时显示可读错误，不显示 [object Object]", async ({ page }) => {
    await page.route("**/usage/model-calls**", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      })
    );
    await page.route("**/usage/model-calls/summary**", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      })
    );

    await page.goto("/usage");
    const main = getAppMain(page);
    await expect(main.locator("[data-testid='usage-error']")).toBeVisible({ timeout: 10000 });
    const errorText = await main.locator("[data-testid='usage-error']").innerText();
    expect(errorText).not.toContain("[object Object]");
    expect(errorText.length).toBeGreaterThan(0);
  });

  test("请求带 X-User-Id header", async ({ page }) => {
    let capturedHeaders: Record<string, string> | null = null;

    await page.route("**/usage/model-calls/summary", (route) => {
      capturedHeaders = route.request().headers();
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total_calls: 0,
          success_calls: 0,
          failed_calls: 0,
          avg_duration_ms: 0,
          calls_by_operation: {},
          calls_by_provider: {},
        }),
      });
    });
    await page.route("**/usage/model-calls*", (route) => {
      if (!route.request().url().includes("/summary")) {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ events: [], total: 0 }),
        });
      }
    });
    await page.route("**/usage/eval-report/latest", (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "No eval report found" }),
      })
    );

    await page.goto("/usage");
    await expect(getAppMain(page).locator("h1").first()).toContainText("模型调用与质量看板");

    await expect.poll(() => capturedHeaders, { timeout: 10000 }).not.toBeNull();
    const userId = capturedHeaders!["x-user-id"];
    expect(userId).toBeTruthy();
  });

  test("导航栏有 /usage 入口", async ({ page }) => {
    await page.goto("/");
    const nav = page.locator("nav");
    await expect(nav.locator('a:has-text("用量/质量")')).toBeVisible();
  });

  test("移动端无横向溢出", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 720 });

    await page.route("**/usage/model-calls**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ events: [], total: 0 }),
      })
    );
    await page.route("**/usage/model-calls/summary**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total_calls: 0,
          success_calls: 0,
          failed_calls: 0,
          avg_duration_ms: 0,
          calls_by_operation: {},
          calls_by_provider: {},
        }),
      })
    );
    await page.route("**/usage/eval-report/latest**", (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "No eval report found" }),
      })
    );

    await page.goto("/usage");
    await expect(getAppMain(page).locator("h1").first()).toContainText("模型调用与质量看板");
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
  });
});
