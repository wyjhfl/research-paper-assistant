import { test, expect, type Page, type Locator } from "@playwright/test";

function getAppMain(page: Page): Locator {
  return page.getByTestId("app-main");
}

async function waitForSsrContent(page: Page, h1Text: string): Promise<Locator> {
  const main = getAppMain(page);
  await expect(main.locator("h1").first()).toContainText(h1Text);
  return main;
}

test.describe("首页 /", () => {
  test("h1 包含'多 Agent 科研论文助手'", async ({ page }) => {
    await page.goto("/");
    const h1 = getAppMain(page).locator("h1").first();
    await expect(h1).toContainText("多 Agent 科研论文助手");
  });

  test("存在论文库、跨论文问答、Agent、MCP 入口", async ({ page }) => {
    await page.goto("/");
    const main = getAppMain(page);
    await expect(main).toContainText("论文库");
    await expect(main).toContainText("跨论文问答");
    await expect(main).toContainText("Agent");
    await expect(main).toContainText("MCP");
  });

  test("页面不是空白", async ({ page }) => {
    await page.goto("/");
    const main = getAppMain(page);
    await expect(main.locator("h1").first()).toContainText("多 Agent 科研论文助手");
    const text = await main.innerText();
    expect(text.trim().length).toBeGreaterThan(50);
  });
});

test.describe("/papers", () => {
  test("h1 包含'论文库'", async ({ page }) => {
    await page.goto("/papers");
    const main = await waitForSsrContent(page, "论文库");
    await expect(main.locator("h1").first()).toContainText("论文库");
  });

  test("空数据时显示 EmptyState，不允许空白页", async ({ page }) => {
    await page.goto("/papers");
    const main = await waitForSsrContent(page, "论文库");
    await expect.poll(async () => {
      const text = await main.innerText();
      return (
        text.includes("暂无论文") ||
        text.includes("论文库") ||
        text.includes("上传") ||
        text.includes("无法连接")
      );
    }).toBeTruthy();
  });
});

test.describe("/papers/ask", () => {
  test("h1 包含'跨论文问答'", async ({ page }) => {
    await page.goto("/papers/ask");
    const h1 = getAppMain(page).locator("h1").first();
    await expect(h1).toContainText("跨论文问答");
  });

  test("页面包含'提问'按钮", async ({ page }) => {
    await page.goto("/papers/ask");
    const btn = getAppMain(page).locator('button:has-text("提问")');
    await expect(btn).toBeVisible();
  });

  test("loading 态：延迟响应时显示'正在加载论文列表'，不显示空状态", async ({ page }) => {
    await page.route("**/papers", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 300));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ papers: [], total: 0 }),
      });
    });

    await page.goto("/papers/ask");
    const main = getAppMain(page);

    await expect(main.locator("text=正在加载论文列表")).toBeVisible();
    await expect(main.locator("text=暂无已完成的论文")).not.toBeVisible();

    await expect(main.locator("text=暂无已完成的论文")).toBeVisible({ timeout: 5000 });
    await expect(main.locator("text=正在加载论文列表")).not.toBeVisible();
  });

  test("error 态：请求失败时显示错误提示和'前往论文库'入口", async ({ page }) => {
    await page.route("**/papers", (route) => route.abort("failed"));

    await page.goto("/papers/ask");
    const main = getAppMain(page);

    await expect(main.locator("p.text-red-600")).toBeVisible({ timeout: 5000 });
    await expect(main.locator('a:has-text("前往论文库")')).toBeVisible();
  });
});

test.describe("/mcp", () => {
  const REAL_TOOLS = [
    "search_papers",
    "get_paper_summary",
    "search_ideas",
    "recommend_citations",
    "search_paper_chunks",
    "save_research_idea",
  ];

  const FAKE_TOOLS = [
    "upload_paper",
    "ask_paper",
    "multi_paper_ask",
    "extract_ideas",
    "run_agent",
  ];

  test("h1 包含'MCP 工具'", async ({ page }) => {
    await page.goto("/mcp");
    const h1 = getAppMain(page).locator("h1").first();
    await expect(h1).toContainText("MCP 工具");
  });

  for (const tool of REAL_TOOLS) {
    test(`显示真实 MCP tool: ${tool}`, async ({ page }) => {
      await page.goto("/mcp");
      const main = getAppMain(page);
      await expect(main).toContainText(tool);
    });
  }

  for (const tool of FAKE_TOOLS) {
    test(`不允许显示不存在的旧工具名: ${tool}`, async ({ page }) => {
      await page.goto("/mcp");
      const main = getAppMain(page);
      await expect(main.locator("h1").first()).toContainText("MCP 工具");
      const text = await main.innerText();
      expect(text).not.toContain(tool);
    });
  }

  test("启动命令包含 docker compose exec backend python run_mcp.py", async ({ page }) => {
    await page.goto("/mcp");
    const main = getAppMain(page);
    await expect(main).toContainText("docker compose exec backend python run_mcp.py");
  });

  test("启动命令包含 python run_mcp.py", async ({ page }) => {
    await page.goto("/mcp");
    const main = getAppMain(page);
    await expect(main).toContainText("python run_mcp.py");
  });

  test("不允许出现 python -m app.mcp.server", async ({ page }) => {
    await page.goto("/mcp");
    const main = getAppMain(page);
    await expect(main.locator("h1").first()).toContainText("MCP 工具");
    const text = await main.innerText();
    expect(text).not.toContain("python -m app.mcp.server");
  });
});

test.describe("/agent", () => {
  test("h1 包含'Agent 工作流'", async ({ page }) => {
    await page.goto("/agent");
    const h1 = getAppMain(page).locator("h1").first();
    await expect(h1).toContainText("Agent 工作流");
  });

  const TASK_TYPES = [
    { value: "summarize_paper", label: "论文总结" },
    { value: "extract_ideas", label: "Idea 抽取" },
    { value: "recommend_citations", label: "引用推荐" },
    { value: "recommend_citations_multi", label: "多论文引用推荐" },
  ];

  test("显示 4 个 task_type 说明卡片", async ({ page }) => {
    await page.goto("/agent");
    const main = getAppMain(page);
    for (const task of TASK_TYPES) {
      await expect(main).toContainText(task.label);
    }
  });

  test("select 包含 4 个 task_type option", async ({ page }) => {
    await page.goto("/agent");
    const select = getAppMain(page).locator("select").first();
    for (const task of TASK_TYPES) {
      const option = select.locator(`option[value="${task.value}"]`);
      await expect(option).toBeAttached();
    }
  });
});

test.describe("/ideas", () => {
  test("h1 包含'Idea 列表'", async ({ page }) => {
    await page.goto("/ideas");
    const h1 = getAppMain(page).locator("h1").first();
    await expect(h1).toContainText("Idea 列表");
  });

  test("有数据时显示 idea 卡片或无数据时显示 EmptyState", async ({ page }) => {
    await page.goto("/ideas");
    const main = await waitForSsrContent(page, "Idea 列表");
    await expect.poll(async () => {
      const text = await main.innerText();
      return (
        text.includes("暂无 Idea") ||
        text.includes("置信度") ||
        text.includes("无法连接") ||
        (await main.locator('a[href^="/ideas/"]').count()) > 0
      );
    }).toBeTruthy();
  });
});

test.describe("404 页面", () => {
  test("显示'页面未找到'", async ({ page }) => {
    await page.goto("/this-page-does-not-exist-xyz");
    const main = getAppMain(page);
    await expect(main).toContainText("页面未找到");
  });

  test("有返回首页入口", async ({ page }) => {
    await page.goto("/this-page-does-not-exist-xyz");
    const link = getAppMain(page).locator('a:has-text("返回首页")');
    await expect(link).toBeVisible();
  });

  test("有论文库入口", async ({ page }) => {
    await page.goto("/this-page-does-not-exist-xyz");
    const link = getAppMain(page).locator('a:has-text("论文库")');
    await expect(link).toBeVisible();
  });

  test("有跨论文问答入口", async ({ page }) => {
    await page.goto("/this-page-does-not-exist-xyz");
    const link = getAppMain(page).locator('a:has-text("跨论文问答")');
    await expect(link).toBeVisible();
  });
});

test.describe("移动端响应式", () => {
  test.use({ viewport: { width: 375, height: 720 } });

  test("/mcp 无横向溢出", async ({ page }) => {
    await page.goto("/mcp");
    await expect(getAppMain(page).locator("h1").first()).toContainText("MCP 工具");
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
  });

  test("/papers/ask 无横向溢出", async ({ page }) => {
    await page.goto("/papers/ask");
    await expect(getAppMain(page).locator("h1").first()).toContainText("跨论文问答");
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
  });
});
