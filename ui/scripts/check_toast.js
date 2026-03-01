const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const apiResponses = [];
  page.on("response", (res) => {
    const url = res.url();
    if (url.includes("/api/")) {
      apiResponses.push({ status: res.status(), url: url.replace("http://213.163.193.6:3001", "") });
    }
  });

  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });

  await page.goto("http://213.163.193.6:3001/prompt", {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  await page.waitForTimeout(5000);

  const toasts = await page.evaluate(() => {
    const texts = [];
    const nodes = Array.from(
      document.querySelectorAll("[data-sonner-toast], [role='status'], [role='alert']"),
    );
    for (const node of nodes) {
      const txt = (node.textContent || "").trim();
      if (txt) texts.push(txt);
    }
    return texts;
  });

  console.log("API_RESPONSES", JSON.stringify(apiResponses, null, 2));
  console.log("CONSOLE_ERRORS", JSON.stringify(consoleErrors, null, 2));
  console.log("TOAST_TEXTS", JSON.stringify(toasts, null, 2));

  await browser.close();
})();
