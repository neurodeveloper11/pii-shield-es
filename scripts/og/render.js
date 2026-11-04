// Genera docs/og-datashield.jpg (1200x627, JPEG) para la vista previa en LinkedIn/redes.
// Uso: node scripts/og/render.js   (requiere Playwright con Chromium)
const path = require("path");
const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 627 }, deviceScaleFactor: 1 });
  await page.goto("file://" + path.join(__dirname, "og-image.html"));
  await page.screenshot({
    path: path.join(__dirname, "..", "..", "docs", "og-datashield.jpg"),
    type: "jpeg",
    quality: 88,
  });
  await browser.close();
})();
