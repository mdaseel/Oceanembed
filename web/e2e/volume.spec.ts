import { test, expect } from "@playwright/test";

test("existing depth selection highlights the stack without changing model inference",async({page})=>{
  let requests=0; page.on("request",r=>{if(r.url().includes("/api/replay/view"))requests++;});
  await page.goto("/#depth");
  await expect(page.getByTestId("terrain-context")).toBeVisible();
  const view=page.getByTestId("depth-renderer"); await view.scrollIntoViewIfNeeded();
  await expect(page.getByLabel("Depth",{exact:true})).toHaveCount(1);
  for(const [index,metres] of [[0,0],[4,30],[7,100],[11,300],[14,1000]]) {
    await page.getByLabel("Depth",{exact:true}).selectOption(String(index));
    await expect(view).toHaveAttribute("data-highlighted-depth",String(metres));
    await page.waitForTimeout(200);

  }
  expect(requests).toBe(1);
});
