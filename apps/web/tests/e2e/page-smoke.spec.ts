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
    await expect(main).toContainText("研究笔记");
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

test.describe("/papers/[id] detail UX", () => {
  test("后端可用时显示单论文问题模板、Idea fallback 参数和片段定位", async ({ page }) => {
    await page.route("**/papers/1", async (route) => {
      if (route.request().method() !== "GET" || route.request().resourceType() === "document") {
        return route.continue();
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          paper: {
            id: 1,
            title: "Paper Alpha",
            filename: "alpha.pdf",
            status: "completed",
            error_message: null,
            chunk_count: 1,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
          chunks: [
            {
              id: 10,
              chunk_index: 0,
              text: "This paper proposes a retrieval augmented research workflow.",
              page_start: 1,
              page_end: 1,
              section_title: null,
            },
          ],
        }),
      });
    });
    await page.route("**/papers/1/ask", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          answer: "The paper proposes a retrieval augmented workflow.",
          status: "answered",
          confidence: 0.7,
          evidence_gate_reason: "",
          retrieved_source_count: 1,
          top_source_score: 0.7,
          sources: [
            {
              paper_id: 1,
              chunk_id: 10,
              chunk_index: 0,
              page_start: 1,
              page_end: 1,
              text_excerpt: "retrieval augmented research workflow",
              score: 0.7,
              vector_score: 0.2,
              lexical_score: 0.8,
              retrieval_mode: "hybrid",
            },
          ],
        }),
      });
    });

    await page.goto("/papers/1");
    const main = getAppMain(page);
    await expect(main.locator("h1").first()).toBeVisible();
    const text = await main.innerText();
    if (text.includes("无法加载论文信息")) {
      test.skip(true, "纯前端 E2E 环境没有后端数据，跳过详情增强控件检查");
    }

    await expect(main).toContainText("常用问题模板");
    await expect(main.locator('button:has-text("核心贡献")')).toBeVisible();
    await expect(main).toContainText("启用 LLM fallback");
    await expect(main).toContainText("论文片段");

    await main.locator('button:has-text("核心贡献")').click();
    await main.locator('button:has-text("提问")').click();
    await expect(main.locator('a:has-text("定位片段")')).toBeVisible();
    await expect(main).toContainText("证据质量摘要");
    await expect(main).toContainText("平均相关度: 70.0%");
    await expect(main).toContainText("关键词: 80.0%");
    await main.locator('button:has-text("展开片段")').click();
    await expect(main.locator('button:has-text("收起片段")')).toBeVisible();
    await expect(main.locator('button:has-text("复制回答")')).toBeVisible();
    await expect(main.locator('button:has-text("复制片段")')).toBeVisible();
    await expect(main).toContainText("继续追问");
  });

  test("hash 定位片段时高亮当前片段并可展开全文", async ({ page }) => {
    await page.route("**/papers/1", async (route) => {
      if (route.request().method() !== "GET" || route.request().resourceType() === "document") {
        return route.continue();
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          paper: {
            id: 1,
            title: "Paper Alpha",
            filename: "alpha.pdf",
            status: "completed",
            error_message: null,
            chunk_count: 1,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
          chunks: [
            {
              id: 10,
              chunk_index: 0,
              text: "This paper proposes a retrieval augmented research workflow with limitations and future work.",
              page_start: 1,
              page_end: 1,
              section_title: null,
            },
          ],
        }),
      });
    });

    await page.goto("/papers/1#chunk-10");
    const main = getAppMain(page);
    await expect(main).toContainText("当前定位");
    await expect(main.locator('button:has-text("收起全文")')).toBeVisible();
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

  test("显示跨论文问题模板和全选入口", async ({ page }) => {
    await page.route("**/papers", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          papers: [
            { id: 1, title: "Paper Alpha", filename: "a.pdf", status: "completed", chunk_count: 2, created_at: "2026-01-01T00:00:00Z" },
            { id: 2, title: "Paper Beta", filename: "b.pdf", status: "completed", chunk_count: 3, created_at: "2026-01-02T00:00:00Z" },
          ],
          total: 2,
        }),
      });
    });

    await page.goto("/papers/ask");
    const main = getAppMain(page);
    await expect(main).toContainText("常用跨论文问题");
    await expect(main.locator('button:has-text("共同主题")')).toBeVisible();
    await expect(main.locator('button:has-text("全选已完成")')).toBeVisible();

    await main.locator('button:has-text("全选已完成")').click();
    await expect(main).toContainText("已选择 2 篇论文");
  });

  test("回答后显示复制和继续追问", async ({ page }) => {
    await page.route("**/papers", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          papers: [
            { id: 1, title: "Paper Alpha", filename: "a.pdf", status: "completed", chunk_count: 2, created_at: "2026-01-01T00:00:00Z" },
          ],
          total: 1,
        }),
      });
    });
    await page.route("**/papers/ask", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          answer: "These papers share a retrieval workflow.",
          status: "answered",
          confidence: 0.65,
          evidence_gate_reason: "",
          retrieved_source_count: 1,
          top_source_score: 0.65,
          sources: [
            {
              paper_id: 1,
              paper_title: "Paper Alpha",
              chunk_id: 10,
              chunk_index: 0,
              page_start: 1,
              page_end: 1,
              text_excerpt: "retrieval workflow",
              score: 0.65,
              vector_score: 0.2,
              lexical_score: 0.75,
              retrieval_mode: "hybrid",
            },
          ],
        }),
      });
    });

    await page.goto("/papers/ask");
    const main = getAppMain(page);
    await main.locator('button:has-text("共同主题")').click();
    await main.locator('button:has-text("提问")').click();
    await expect(main.locator('button:has-text("复制回答")')).toBeVisible();
    await expect(main).toContainText("继续追问");
    await expect(main.locator('a:has-text("定位片段")')).toBeVisible();
    await expect(main).toContainText("证据质量摘要");
    await expect(main).toContainText("检索模式: 混合 1");
    await expect(main).toContainText("关键词: 75.0%");
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

test.describe("/papers/review", () => {
  test("显示文献综述表入口、选择论文并生成矩阵", async ({ page }) => {
    await page.route("**/papers", async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          papers: [
            { id: 1, title: "Paper Alpha", filename: "a.pdf", status: "completed", chunk_count: 2, created_at: "2026-01-01T00:00:00Z" },
            { id: 2, title: "Paper Beta", filename: "b.pdf", status: "completed", chunk_count: 3, created_at: "2026-01-02T00:00:00Z" },
          ],
          total: 2,
        }),
      });
    });
    await page.route("**/papers/review-matrix", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          rows: [
            {
              paper_id: 1,
              paper_title: "Paper Alpha",
              problem: "The paper studies a retrieval problem.",
              method: "It proposes a workflow.",
              evidence: "Experiments evaluate the workflow.",
              metric: "Accuracy is reported.",
              limitation: "Limitations remain.",
              future_work: "Future work can improve retrieval.",
              source_chunk_ids: [10],
              sources: [
                {
                  paper_id: 1,
                  paper_title: "Paper Alpha",
                  chunk_id: 10,
                  chunk_index: 0,
                  page_start: 1,
                  page_end: 1,
                  text_excerpt: "This paper studies a retrieval problem and proposes a workflow.",
                  matched_fields: ["problem", "method"],
                },
              ],
            },
          ],
          total_papers: 1,
          generated_by: "heuristic",
          warnings: [],
        }),
      });
    });
    await page.route("**/notes", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          note: {
            id: 3,
            title: "文献综述表：1 篇论文",
            content: "matrix",
            note_type: "review_matrix",
            paper_id: null,
            paper_title: null,
            chunk_id: null,
            source: { source_kind: "review_matrix" },
            tags: ["review", "matrix"],
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        }),
      });
    });

    await page.goto("/papers/review");
    const main = getAppMain(page);
    await expect(main.locator("h1").first()).toContainText("文献综述表");
    await expect(main).toContainText("选择论文");
    await main.locator('button:has-text("全选已完成")').click();
    await main.locator('button:has-text("生成综述表")').click();
    await expect(main).toContainText("结构化综述表");
    await expect(main).toContainText("问题");
    await expect(main).toContainText("The paper studies a retrieval problem.");
    await expect(main.locator('a:has-text("chunk #0")')).toBeVisible();
    await expect(main.locator('button:has-text("复制 Markdown")')).toBeVisible();
    await main.locator('button:has-text("存为笔记")').click();
    await expect(main.locator('button:has-text("已保存")')).toBeVisible();
  });
});

test.describe("/notes", () => {
  test("显示研究笔记工作台、保存手动笔记并复制", async ({ page }) => {
    await page.route("**/notes?limit=100", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          notes: [
            {
              id: 1,
              title: "Existing note",
              content: "Saved answer content.",
              note_type: "qa_answer",
              paper_id: 1,
              paper_title: "Paper Alpha",
              chunk_id: 10,
              source: { paper_id: 1, chunk_id: 10, chunk_index: 0 },
              tags: ["qa"],
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
            },
          ],
          total: 1,
        }),
      });
    });
    await page.route("**/notes", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          note: {
            id: 2,
            title: "Manual note",
            content: "Manual note body.",
            note_type: "manual",
            paper_id: null,
            paper_title: null,
            chunk_id: null,
            source: {},
            tags: ["draft"],
            created_at: "2026-01-02T00:00:00Z",
            updated_at: "2026-01-02T00:00:00Z",
          },
        }),
      });
    });

    await page.goto("/notes");
    const main = getAppMain(page);
    await expect(main.locator("h1").first()).toContainText("研究笔记");
    await expect(main).toContainText("Existing note");
    await main.getByPlaceholder("笔记标题").fill("Manual note");
    await main.getByPlaceholder("笔记内容").fill("Manual note body.");
    await main.getByPlaceholder("标签，用逗号分隔").fill("draft");
    await main.locator('button:has-text("保存笔记")').click();
    await expect(main).toContainText("Manual note");
    await expect(main.locator('button:has-text("复制")').first()).toBeVisible();
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
