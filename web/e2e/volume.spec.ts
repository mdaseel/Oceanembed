import { test, expect } from "@playwright/test";
import { oceanViewportWidth } from "../src/field/visualConfig";
test("existing depth selection highlights the stack while foreground scale stays pixel-identical",async({page})=>{
  let requests=0; page.on("request",r=>{if(r.url().includes("/api/replay/view"))requests++;});
  await page.goto("/#depth");
  await expect(page.getByTestId("terrain-context")).toBeVisible();
  const view=page.getByTestId("depth-renderer"); await view.scrollIntoViewIfNeeded();
  await expect(page.getByLabel("Depth",{exact:true})).toHaveCount(1);
  const box=(await view.boundingBox())!, width=oceanViewportWidth(box.width);
  const legend=()=>page.screenshot({clip:{x:box.x+width,y:box.y,width:box.width-width,height:box.height}});
  await page.waitForTimeout(500); const before=await legend();
  for(const [index,metres] of [[0,0],[4,30],[7,100],[11,300],[14,1000]]) {
    await page.getByLabel("Depth",{exact:true}).selectOption(String(index));
    await expect(view).toHaveAttribute("data-highlighted-depth",String(metres));
    await page.waitForTimeout(200);
    expect((await legend()).equals(before)).toBe(true);
  }
  await page.mouse.move(box.x+width*.45,box.y+box.height*.5);
  await page.mouse.down(); await page.mouse.move(box.x+width*.53,box.y+box.height*.48,{steps:12}); await page.mouse.up();
  await page.mouse.wheel(0,-80); await page.waitForTimeout(500);
  expect((await legend()).equals(before)).toBe(true);
  await page.getByLabel("Layer separation",{exact:true}).fill("0.7");
  await page.waitForTimeout(300); expect((await legend()).equals(before)).toBe(true);
  expect(requests).toBe(1);
});
