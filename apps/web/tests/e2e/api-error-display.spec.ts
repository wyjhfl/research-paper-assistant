import { test, expect, type Page, type Locator } from "@playwright/test";

function getAppMain(page: Page): Locator {
  return page.getByTestId("app-main");
}

test.describe("422 错误展示 — 跨论文问答", () => {
  test("FastAPI 422 detail 数组显示格式化错误，而非 [object Object]", async ({ page }) => {
    await page.route("**/papers", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ papers: [], total: 0 }),
      })
    );

    await page.route("**/papers/ask", (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({
            detail: [
              {
                loc: ["body", "question"],
                msg: "Field required",
                type: "value_error.missing",
              },
            ],
          }),
        });
      }
      return route.continue();
    });

    await page.goto("/papers/ask");
    const main = getAppMain(page);
    await expect(main.locator("h1").first()).toContainText("跨论文问答");

    const input = main.locator('input[type="text"]');
    await expect(input).toBeVisible({ timeout: 10000 });
    await input.fill("test question");

    const btn = main.locator('button:has-text("提问")');
    await btn.click();

    await expect(main.locator("text=请求参数不合法")).toBeVisible({ timeout: 5000 });
    await expect(main.locator("text=question")).toBeVisible();
    await expect(main.locator("text=Field required")).toBeVisible();
    const errorArea = main.locator(".bg-red-50");
    const errorText = await errorArea.innerText();
    expect(errorText).not.toContain("[object Object]");
  });

  test("FastAPI 422 多字段错误用分号拼接", async ({ page }) => {
    await page.route("**/papers", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ papers: [], total: 0 }),
      })
    );

    await page.route("**/papers/ask", (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({
            detail: [
              {
                loc: ["body", "question"],
                msg: "Field required",
                type: "value_error.missing",
              },
              {
                loc: ["body", "top_k"],
                msg: "ensure this value is greater than 0",
                type: "value_error.number.not_gt",
              },
            ],
          }),
        });
      }
      return route.continue();
    });

    await page.goto("/papers/ask");
    const main = getAppMain(page);
    await expect(main.locator("h1").first()).toContainText("跨论文问答");

    const input = main.locator('input[type="text"]');
    await expect(input).toBeVisible({ timeout: 10000 });
    await input.fill("test");

    const btn = main.locator('button:has-text("提问")');
    await btn.click();

    await expect(main.locator("text=请求参数不合法")).toBeVisible({ timeout: 5000 });
    const errorArea = main.locator(".bg-red-50");
    const errorText = await errorArea.innerText();
    expect(errorText).toContain("question");
    expect(errorText).toContain("top_k");
    expect(errorText).toContain("；");
  });

  test("{ detail: string } 格式显示可读文本", async ({ page }) => {
    await page.route("**/papers", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ papers: [], total: 0 }),
      })
    );

    await page.route("**/papers/ask", (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Paper not found" }),
        });
      }
      return route.continue();
    });

    await page.goto("/papers/ask");
    const main = getAppMain(page);
    await expect(main.locator("h1").first()).toContainText("跨论文问答");

    const input = main.locator('input[type="text"]');
    await expect(input).toBeVisible({ timeout: 10000 });
    await input.fill("test question");

    const btn = main.locator('button:has-text("提问")');
    await btn.click();

    await expect(main.locator("text=Paper not found")).toBeVisible({ timeout: 5000 });
    const allText = await main.innerText();
    expect(allText).not.toContain("[object Object]");
  });
});

test.describe("422 错误展示 — Agent Runner", () => {
  test("FastAPI 422 detail 数组显示格式化错误", async ({ page }) => {
    await page.route("**/papers", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          papers: [
            { id: 1, title: "Test Paper", filename: "test.pdf", status: "completed", chunk_count: 5, created_at: "2025-01-01" },
          ],
          total: 1,
        }),
      })
    );

    await page.route("**/agent/run", (route) =>
      route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          detail: [
            {
              loc: ["body", "task_type"],
              msg: "field required",
              type: "value_error.missing",
            },
          ],
        }),
      })
    );

    await page.goto("/agent");
    const main = getAppMain(page);
    await expect(main.locator("h1").first()).toContainText("Agent 工作流");

    await expect(main.locator("text=加载论文列表...")).not.toBeVisible({ timeout: 10000 });

    const taskSelect = main.locator("select").first();
    await expect(taskSelect).toBeVisible({ timeout: 10000 });
    await taskSelect.selectOption({ value: "summarize_paper" });

    const paperSelect = main.locator("select").nth(1);
    await expect(paperSelect).toBeVisible({ timeout: 5000 });
    await paperSelect.selectOption({ value: "1" });

    const runBtn = main.locator('button:has-text("运行 Agent")');
    await expect(runBtn).toBeEnabled({ timeout: 5000 });
    await runBtn.click();

    await expect(main.locator("text=请求参数不合法")).toBeVisible({ timeout: 5000 });
    await expect(main.locator("text=task_type")).toBeVisible();
    await expect(main.locator("text=field required")).toBeVisible();
    const errorArea = main.locator(".bg-red-50");
    const errorText = await errorArea.innerText();
    expect(errorText).not.toContain("[object Object]");
  });
});

test.describe("非 JSON 错误展示", () => {
  test("500 text/plain 响应显示可读 fallback", async ({ page }) => {
    await page.route("**/papers", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ papers: [], total: 0 }),
      })
    );

    await page.route("**/papers/ask", (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 500,
          contentType: "text/plain",
          body: "Internal Server Error",
        });
      }
      return route.continue();
    });

    await page.goto("/papers/ask");
    const main = getAppMain(page);
    await expect(main.locator("h1").first()).toContainText("跨论文问答");

    const input = main.locator('input[type="text"]');
    await expect(input).toBeVisible({ timeout: 10000 });
    await input.fill("test question");

    const btn = main.locator('button:has-text("提问")');
    await btn.click();

    await expect(main.locator("text=请求失败 (500)")).toBeVisible({ timeout: 5000 });
  });
});
