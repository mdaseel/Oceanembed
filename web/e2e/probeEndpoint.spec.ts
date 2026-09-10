import {test,expect} from "@playwright/test";
test("probe guide follows selected depth and withholds below-seafloor extent",async({page})=>{
  let requests=0;page.on("request",r=>{if(r.url().includes("/api/replay/view"))requests++;});
  await page.goto("/#depth"); await expect(page.getByTestId("terrain-context")).toBeVisible();
  const view=page.getByTestId("depth-renderer");
  const select=async(lat:string,lon:string)=>{
    await page.getByLabel("Latitude",{exact:true}).fill(lat);await page.getByLabel("Longitude",{exact:true}).fill(lon);
    await page.getByRole("button",{name:"Inspect column"}).click();
  };
  await select("15","65");
  const position=(await view.getAttribute("data-probe-position"))!;
  let previous=Infinity;
  for(const [k,m] of [[0,0],[4,30],[7,100],[11,300],[14,1000]]) {
    await page.getByLabel("Depth",{exact:true}).selectOption(String(k));
    await expect(view).toHaveAttribute("data-highlighted-depth",String(m));
    await expect(view).toHaveAttribute("data-probe-position",position);
    await expect(view).toHaveAttribute("data-probe-depth-valid","true");
    const end=Number(await view.getAttribute("data-probe-endpoint"));
    if(k===0) expect(end).toBe(Number(position.split(",")[1]));
    else expect(end).toBeLessThan(previous);
    previous=end;
    await view.screenshot({path:`../outputs/phase7b/terrain-edges-probe-${m}m.png`});
  }
  await page.getByLabel("Layer separation",{exact:true}).fill("0.5");
  await expect.poll(async()=>Number(await view.getAttribute("data-probe-endpoint"))).toBeGreaterThan(previous);
  await select("20","70");
  await expect(view).toHaveAttribute("data-probe-depth-valid","false");
  const shallow=(await view.getAttribute("data-probe-position"))!;
  expect(Number(await view.getAttribute("data-probe-endpoint"))).toBe(Number(shallow.split(",")[1]));
  expect(requests).toBe(1);
});
