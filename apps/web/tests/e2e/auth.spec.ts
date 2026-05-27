import { test, expect, type Page, type Locator } from "@playwright/test";

function getAppMain(page: Page): Locator {
  return page.getByTestId("app-main");
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

test.describe("/login page text", () => {
  test("login page shows: login, email, password, register link", async ({ page }) => {
    await page.goto("/login");
    const main = getAppMain(page);
    await expect(main.locator("h1")).toContainText("\u767B\u5F55");
    await expect(main.getByText("\u90AE\u7BB1", { exact: true })).toBeVisible();
    await expect(main.getByText("\u5BC6\u7801", { exact: true })).toBeVisible();
    await expect(main.locator('input[placeholder="\u81F3\u5C11 8 \u4F4D"]')).toBeVisible();
    await expect(main.locator('button:has-text("\u767B\u5F55")')).toBeVisible();
    await expect(main.locator('a:has-text("\u6CE8\u518C")')).toBeVisible();
    await expect(main.locator("text=\u6CA1\u6709\u8D26\u53F7\uFF1F")).toBeVisible();
  });

  test("login page no mojibake", async ({ page }) => {
    await page.goto("/login");
    const main = getAppMain(page);
    const text = await main.innerText();
    expect(text).not.toMatch(MOJIBAKE_RE);
  });

  test("login 401 shows: wrong email or password, no [object Object] no mojibake", async ({ page }) => {
    await page.route("**/auth/login", (route) =>
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Invalid credentials" }),
      })
    );

    await page.goto("/login");
    const main = getAppMain(page);

    await main.locator('input[type="email"]').fill("test@example.com");
    await main.locator('input[type="password"]').fill("wrongpass1");
    await main.locator('button:has-text("\u767B\u5F55")').click();

    await expect(main.locator(".text-red-600")).toBeVisible({ timeout: 5000 });
    const errorText = await main.locator(".text-red-600").innerText();
    expect(errorText).toContain("\u90AE\u7BB1\u6216\u5BC6\u7801\u9519\u8BEF");
    expect(errorText).not.toContain("[object Object]");
    expect(errorText).not.toMatch(MOJIBAKE_RE);
  });
});

test.describe("/register page text", () => {
  test("register page shows: register, email, password, login link", async ({ page }) => {
    await page.goto("/register");
    const main = getAppMain(page);
    await expect(main.locator("h1")).toContainText("\u6CE8\u518C");
    await expect(main.getByText("\u90AE\u7BB1", { exact: true })).toBeVisible();
    await expect(main.getByText("\u5BC6\u7801", { exact: true })).toBeVisible();
    await expect(main.locator('input[placeholder="\u81F3\u5C11 8 \u4F4D"]')).toBeVisible();
    await expect(main.locator("text=\u663E\u793A\u540D\u79F0\uFF08\u53EF\u9009\uFF09")).toBeVisible();
    await expect(main.locator('button:has-text("\u6CE8\u518C")')).toBeVisible();
    await expect(main.locator('a:has-text("\u767B\u5F55")')).toBeVisible();
    await expect(main.locator("text=\u5DF2\u6709\u8D26\u53F7\uFF1F")).toBeVisible();
  });

  test("register page no mojibake", async ({ page }) => {
    await page.goto("/register");
    const main = getAppMain(page);
    const text = await main.innerText();
    expect(text).not.toMatch(MOJIBAKE_RE);
  });

  test("register 409 shows: email already registered, no [object Object] no mojibake", async ({ page }) => {
    await page.route("**/auth/register", (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Email already registered" }),
      })
    );

    await page.goto("/register");
    const main = getAppMain(page);

    await main.locator('input[type="email"]').fill("existing@example.com");
    await main.locator('input[type="password"]').fill("password1");
    await main.locator('button:has-text("\u6CE8\u518C")').click();

    await expect(main.locator(".text-red-600")).toBeVisible({ timeout: 5000 });
    const errorText = await main.locator(".text-red-600").innerText();
    expect(errorText).toContain("\u8BE5\u90AE\u7BB1\u5DF2\u6CE8\u518C");
    expect(errorText).not.toContain("[object Object]");
    expect(errorText).not.toMatch(MOJIBAKE_RE);
  });
});

test.describe("register then login flow", () => {
  test("register success redirects to login, login success redirects to home", async ({ page }) => {
    await page.route("**/auth/register", (route) =>
      route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "testuser_abc",
          email: "newuser@example.com",
          display_name: null,
          created_at: "2025-01-01T00:00:00+00:00",
        }),
      })
    );

    await page.route("**/auth/login", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "testuser_abc",
          email: "newuser@example.com",
          display_name: null,
          created_at: "2025-01-01T00:00:00+00:00",
        }),
        headers: {
          "Set-Cookie": "research_session=fake-session-token; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800",
        },
      })
    );

    await page.route("**/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "testuser_abc",
          email: "newuser@example.com",
          display_name: null,
          auth_mode: "session",
        }),
      })
    );

    await page.goto("/register");
    const main = getAppMain(page);
    await main.locator('input[type="email"]').fill("newuser@example.com");
    await main.locator('input[type="password"]').fill("password1");
    await main.locator('button:has-text("\u6CE8\u518C")').click();

    await expect(page).toHaveURL(/\/login/, { timeout: 5000 });

    const loginMain = getAppMain(page);
    await loginMain.locator('input[type="email"]').fill("newuser@example.com");
    await loginMain.locator('input[type="password"]').fill("password1");
    await loginMain.locator('button:has-text("\u767B\u5F55")').click();

    await expect(page).toHaveURL(/\//, { timeout: 5000 });
  });
});

test.describe("navbar after login", () => {
  test("session mode navbar shows display_name and logout button, no mojibake", async ({ page }) => {
    await page.route("**/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "testuser_abc",
          email: "test@example.com",
          display_name: "\u6D4B\u8BD5\u7528\u6237",
          auth_mode: "session",
        }),
      })
    );

    await page.goto("/");
    const nav = page.locator("nav");
    await expect(nav).toContainText("\u6D4B\u8BD5\u7528\u6237", { timeout: 5000 });
    await expect(nav.locator('button:has-text("\u767B\u51FA")')).toBeVisible();
    const navText = await nav.innerText();
    expect(navText).not.toMatch(MOJIBAKE_RE);
  });

  test("session mode without display_name shows email", async ({ page }) => {
    await page.route("**/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "testuser_abc",
          email: "nodisplay@example.com",
          display_name: null,
          auth_mode: "session",
        }),
      })
    );

    await page.goto("/");
    await expect(page.locator("nav")).toContainText("nodisplay@example.com", { timeout: 5000 });
  });
});

test.describe("logout flow", () => {
  test("click logout redirects to login page", async ({ page }) => {
    let logoutCalled = false;
    await page.route("**/auth/me", (route) => {
      if (!logoutCalled) {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            user_id: "testuser_abc",
            email: "test@example.com",
            display_name: "\u6D4B\u8BD5\u7528\u6237",
            auth_mode: "session",
          }),
        });
      } else {
        route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Not authenticated" }),
        });
      }
    });

    await page.route("**/auth/logout", (route) => {
      logoutCalled = true;
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
    });

    await page.goto("/");
    await expect(page.locator("nav")).toContainText("\u6D4B\u8BD5\u7528\u6237", { timeout: 5000 });

    await page.locator('button:has-text("\u767B\u51FA")').click();
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 });
  });
});

test.describe("unauthenticated /papers shows login prompt", () => {
  test("no session shows login entry or redirect", async ({ page }) => {
    await page.route("**/auth/me", (route) =>
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Not authenticated" }),
      })
    );

    await page.route("**/papers", (route) =>
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Not authenticated" }),
      })
    );

    await page.goto("/papers");

    await expect.poll(async () => {
      const text = await page.locator("body").innerText();
      return (
        text.includes("\u767B\u5F55") ||
        text.includes("\u8BF7\u5148\u767B\u5F55") ||
        text.includes("Not authenticated") ||
        page.url().includes("/login")
      );
    }, { timeout: 10000 }).toBeTruthy();
  });
});

test.describe("401 error readable text", () => {
  test("API 401 shows readable error, no [object Object] no mojibake", async ({ page }) => {
    await page.route("**/auth/me", (route) =>
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Not authenticated" }),
      })
    );

    await page.route("**/papers", (route) =>
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Not authenticated" }),
      })
    );

    await page.goto("/papers");

    const bodyText = await page.locator("body").innerText({ timeout: 10000 });
    expect(bodyText).not.toContain("[object Object]");
    expect(bodyText).not.toMatch(MOJIBAKE_RE);
  });

  test("login API 401 shows readable error", async ({ page }) => {
    await page.route("**/auth/login", (route) =>
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Invalid credentials" }),
      })
    );

    await page.goto("/login");
    const main = getAppMain(page);
    await main.locator('input[type="email"]').fill("bad@example.com");
    await main.locator('input[type="password"]').fill("badpass123");
    await main.locator('button:has-text("\u767B\u5F55")').click();

    await expect(main.locator(".text-red-600")).toBeVisible({ timeout: 5000 });
    const errorText = await main.locator(".text-red-600").innerText();
    expect(errorText).toContain("\u90AE\u7BB1\u6216\u5BC6\u7801\u9519\u8BEF");
    expect(errorText).not.toContain("[object Object]");
    expect(errorText).not.toContain("Invalid credentials");
    expect(errorText).not.toMatch(MOJIBAKE_RE);
  });
});

test.describe("dev mode UserSwitcher text", () => {
  test("dev mode shows default user, click title readable", async ({ page }) => {
    await page.route("**/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "default",
          email: "dev@localhost",
          display_name: "default",
          auth_mode: "dev",
        }),
      })
    );

    await page.goto("/");
    const userLabel = page.locator("text=\u7528\u6237 default");
    await expect(userLabel).toBeVisible({ timeout: 5000 });

    const title = await userLabel.getAttribute("title");
    expect(title).toBe("\u70B9\u51FB\u5207\u6362\u7528\u6237");
  });

  test("dev mode reset button text readable", async ({ page }) => {
    await page.route("**/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "default",
          email: "dev@localhost",
          display_name: "default",
          auth_mode: "dev",
        }),
      })
    );

    await page.goto("/");
    await page.evaluate(() =>
      localStorage.setItem("research_user_id", "reset_test")
    );
    await page.reload();

    const resetBtn = page.locator('button[title="\u91CD\u7F6E\u4E3A default"]');
    await expect(resetBtn).toBeVisible({ timeout: 5000 });
    const resetText = await resetBtn.innerText();
    expect(resetText).toContain("\u91CD\u7F6E");
    expect(resetText).not.toMatch(MOJIBAKE_RE);
  });

  test("dev mode can switch user_id", async ({ page }) => {
    await page.route("**/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "default",
          email: "dev@localhost",
          display_name: "default",
          auth_mode: "dev",
        }),
      })
    );

    await page.goto("/");
    const userLabel = page.locator("text=\u7528\u6237 default");
    await expect(userLabel).toBeVisible({ timeout: 5000 });
    await userLabel.click();

    const input = page.locator('input[placeholder="user_id"]');
    await expect(input).toBeVisible();
    await input.fill("devuser1");
    await page.locator('button:has-text("OK")').click();

    await page.waitForLoadState("load");
    const stored = await page.evaluate(() =>
      localStorage.getItem("research_user_id")
    );
    expect(stored).toBe("devuser1");
  });

  test("dev mode navbar no mojibake", async ({ page }) => {
    await page.route("**/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "default",
          email: "dev@localhost",
          display_name: "default",
          auth_mode: "dev",
        }),
      })
    );

    await page.goto("/");
    const navText = await page.locator("nav").innerText({ timeout: 5000 });
    expect(navText).not.toMatch(MOJIBAKE_RE);
  });
});
