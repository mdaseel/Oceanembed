import { test, expect } from "@playwright/test";
test("real bathymetry masks depth footprints and labels raw below-seafloor profile",async({page})=>{
  let requests=0;page.on("request",r=>{if(r.url().includes("/api/replay/view"))requests++;});
  await page.goto("/#depth");
  await expect(page.getByTestId("bathymetry-context")).toContainText("constrained");
  const view=page.getByTestId("depth-renderer");
  const counts=()=>view.getAttribute("data-depth-cell-counts").then(s=>JSON.parse(s!));
  const c=await counts(); expect(c[1000]).toBeLessThan(c[0]); expect(c[1000]).toBeGreaterThan(0);
  await page.getByLabel("Terrain relief exaggeration").fill("150");
  expect(await counts()).toEqual(c);
  await page.getByLabel("Terrain relief exaggeration").fill("60");
  for(const [index,metres] of [[0,0],[4,30],[7,100],[11,300],[14,1000]]) {
    await page.getByLabel("Depth",{exact:true}).selectOption(String(index));
    await expect(view).toHaveAttribute("data-highlighted-depth",String(metres));
    await view.screenshot({path:`../outputs/phase7b/bathymetry-${metres}m.png`});
  }
  // Real shallow shelf sample identified from the regridded bundle.
  await page.getByLabel("Latitude",{exact:true}).fill("20");
  await page.getByLabel("Longitude",{exact:true}).fill("70");
  await page.getByRole("button",{name:"Inspect column"}).click();
  await expect(page.getByTestId("profile-bathymetry")).toContainText("Local ETOPO water depth");
  await page.getByText("Inspect all profile values",{exact:true}).click();
  await expect(page.locator('[data-depth="1000"] td').last()).toContainText("Below seafloor");
  expect(requests).toBe(1);
});
test("missing bathymetry never silently renders unsupported deep water",async({page})=>{
  await page.route("**/assets/bathymetry/**",r=>r.fulfill({status:404,body:"missing"}));
  await page.goto("/#depth");
  await expect(page.getByTestId("bathymetry-context")).toContainText("layers hidden");
  await expect(page.getByTestId("terrain-context")).toBeVisible();
  const counts=JSON.parse((await page.getByTestId("depth-renderer").getAttribute("data-depth-cell-counts"))!);
  expect(Object.values(counts).every(n=>n===0)).toBe(true);
});
