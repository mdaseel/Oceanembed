import { test, expect } from "@playwright/test";
test("probe follows shared selection, stays on top through depth changes, and hides invalid cells",async({page})=>{
  let requests=0;
  page.on("request",r=>{if(r.url().includes("/api/replay/view"))requests++;});
  await page.goto("/#depth");
  await expect(page.getByTestId("terrain-context")).toBeVisible();
  const view=page.getByTestId("depth-renderer");
  const select=async(lat:string,lon:string)=>{
    await page.getByLabel("Latitude",{exact:true}).fill(lat);
    await page.getByLabel("Longitude",{exact:true}).fill(lon);
    await page.getByRole("button",{name:"Inspect column"}).click();
  };
  await select("15","65");
  await expect(view).toHaveAttribute("data-probe-cell",String(40*241+80));
  const before=await view.getAttribute("data-probe-position");
  await page.getByLabel("Depth",{exact:true}).selectOption("11");
  await expect(view).toHaveAttribute("data-probe-position",before!);
  await select("15.25","87.75");
  await expect(view).toHaveAttribute("data-probe-cell",String(41*241+171));
  expect(await view.getAttribute("data-probe-position")).not.toBe(before);
  await select("0","65");
  await expect(view).toHaveAttribute("data-probe-cell","");
  await expect(view).toHaveAttribute("data-probe-position","");
  expect(requests).toBe(1);
});
