import { test, expect } from "@playwright/test";

test.describe("UserSwitcher 组件", () => {
  test("默认显示 default 用户", async ({ page }) => {
    await page.goto("/");
    const userLabel = page.locator("text=用户 default");
    await expect(userLabel).toBeVisible();
  });

  test("点击用户标签进入编辑模式", async ({ page }) => {
    await page.goto("/");
    const userLabel = page.locator("text=用户 default");
    await userLabel.click();
    const input = page.locator('input[placeholder="user_id"]');
    await expect(input).toBeVisible();
  });

  test("输入新 user_id 并保存到 localStorage 和 cookie", async ({ page }) => {
    await page.goto("/");
    const userLabel = page.locator("text=用户 default");
    await userLabel.click();

    const input = page.locator('input[placeholder="user_id"]');
    await input.fill("testuser1");
    const okBtn = page.locator('button:has-text("OK")');
    await okBtn.click();

    await page.waitForLoadState("load");

    const stored = await page.evaluate(() =>
      localStorage.getItem("research_user_id")
    );
    expect(stored).toBe("testuser1");

    const cookieVal = await page.evaluate(() => {
      const match = document.cookie.match(/(?:^|;\s*)research_user_id=([^;]*)/);
      return match ? match[1] : null;
    });
    expect(cookieVal).toBe("testuser1");
  });

  test("reset 后 localStorage 清空且 cookie 删除", async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() =>
      localStorage.setItem("research_user_id", "bob")
    );
    await page.evaluate(() => {
      document.cookie = "research_user_id=bob; path=/; SameSite=Lax; max-age=31536000";
    });
    await page.reload();

    const resetBtn = page.locator('button[title="重置为 default"]');
    await resetBtn.click();

    await page.waitForLoadState("load");

    const stored = await page.evaluate(() =>
      localStorage.getItem("research_user_id")
    );
    expect(stored).toBeNull();

    const cookieVal = await page.evaluate(() => {
      const match = document.cookie.match(/(?:^|;\s*)research_user_id=([^;]*)/);
      return match ? match[1] : null;
    });
    expect(cookieVal).toBeNull();
  });

  test("切换后显示新 user_id", async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() =>
      localStorage.setItem("research_user_id", "alice")
    );
    await page.reload();
    const userLabel = page.locator("text=用户 alice");
    await expect(userLabel).toBeVisible();
  });

  test("重置按钮恢复 default", async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() =>
      localStorage.setItem("research_user_id", "bob")
    );
    await page.reload();
    const resetBtn = page.locator('button[title="重置为 default"]');
    await resetBtn.click();

    await page.waitForLoadState("load");
    const stored = await page.evaluate(() =>
      localStorage.getItem("research_user_id")
    );
    expect(stored).toBeNull();
  });
});

test.describe("X-User-Id header 注入", () => {
  test("客户端 API 请求带 X-User-Id header", async ({ page }) => {
    await page.goto("/papers/ask");
    await page.evaluate(() =>
      localStorage.setItem("research_user_id", "header_test")
    );

    let capturedHeader: string | null = null;
    await page.route("http://localhost:8091/papers**", async (route) => {
      capturedHeader = route.request().headers()["x-user-id"] || null;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ papers: [], total: 0 }),
      });
    });

    await page.reload();
    await expect.poll(() => capturedHeader, { timeout: 10000 }).toBe("header_test");
  });

  test("default 用户请求也带 X-User-Id header", async ({ page }) => {
    let capturedHeader: string | undefined;
    await page.route("http://localhost:8091/papers**", async (route) => {
      capturedHeader = route.request().headers()["x-user-id"];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ papers: [], total: 0 }),
      });
    });

    await page.goto("/papers/ask");
    await expect.poll(() => capturedHeader, { timeout: 10000 }).toBe("default");
  });
});

test.describe("SSR cookie 用户隔离", () => {
  test("cookie 设置 research_user_id 后 SSR 页面可访问", async ({ page }) => {
    await page.context().addCookies([
      {
        name: "research_user_id",
        value: "ssr_alice",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.goto("/papers");
    const h1 = page.locator("h1").first();
    await expect(h1).toContainText("论文库");

    const cookies = await page.context().cookies();
    const userIdCookie = cookies.find((c) => c.name === "research_user_id");
    expect(userIdCookie).toBeDefined();
    expect(userIdCookie!.value).toBe("ssr_alice");
  });

  test("cookie 中的 user_id 在 UserSwitcher 中显示", async ({ page }) => {
    await page.context().addCookies([
      {
        name: "research_user_id",
        value: "cookie_user",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.goto("/");
    const userLabel = page.locator("text=用户 cookie_user");
    await expect(userLabel).toBeVisible();
  });
});

test.describe("cookie-only 场景一致性", () => {
  test("cookie-only 且 localStorage 为空时，客户端 API 请求带 cookie 中的 X-User-Id", async ({ page }) => {
    await page.goto("/papers/ask");
    await page.evaluate(() => {
      localStorage.removeItem("research_user_id");
      document.cookie = "research_user_id=cookie_only_user; path=/; SameSite=Lax; max-age=31536000";
    });

    let capturedHeader: string | null = null;
    await page.route("http://localhost:8091/papers**", async (route) => {
      capturedHeader = route.request().headers()["x-user-id"] || null;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ papers: [], total: 0 }),
      });
    });

    await page.reload();
    await expect.poll(() => capturedHeader, { timeout: 10000 }).toBe("cookie_only_user");
  });

  test("非法 cookie 值不会被用于 X-User-Id，回退 default", async ({ page }) => {
    await page.goto("/papers/ask");
    await page.evaluate(() => {
      localStorage.removeItem("research_user_id");
      document.cookie = "research_user_id=bad!id; path=/; SameSite=Lax; max-age=31536000";
    });

    let capturedHeader: string | null = null;
    await page.route("http://localhost:8091/papers**", async (route) => {
      capturedHeader = route.request().headers()["x-user-id"] || null;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ papers: [], total: 0 }),
      });
    });

    await page.reload();
    await expect.poll(() => capturedHeader, { timeout: 10000 }).toBe("default");
  });

  test("UserSwitcher 从 cookie 读取用户后同步到 localStorage", async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => {
      localStorage.removeItem("research_user_id");
      document.cookie = "research_user_id=sync_test; path=/; SameSite=Lax; max-age=31536000";
    });
    await page.reload();

    const userLabel = page.locator("text=用户 sync_test");
    await expect(userLabel).toBeVisible();

    const stored = await page.evaluate(() =>
      localStorage.getItem("research_user_id")
    );
    expect(stored).toBe("sync_test");
  });
});
