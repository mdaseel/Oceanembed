from pathlib import Path
from html import escape
P=Path('outputs/sih-presentation')
s=[]
s.append('''<svg xmlns="http://www.w3.org/2000/svg" width="3840" height="2160" viewBox="0 0 1920 1080"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8" fill="#167d9a"/></marker></defs><rect width="1920" height="1080" fill="#f5f8fb"/><style>text{font-family:Segoe UI,Arial,sans-serif;fill:#142c42}.small{font-size:18px}.body{font-size:21px}.title{font-size:24px;font-weight:700}.tag{font-size:16px;font-weight:700;letter-spacing:1.5px}</style>''')
def text(x,y,t,size=21,color='#142c42',weight=400):
 s.append(f'<text x="{x}" y="{y}" style="font-size:{size}px;fill:{color};font-weight:{weight}">{escape(t)}</text>')
def rect(x,y,w,h,fill='#fff',stroke='#c6d6e2',r=14):
 s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
def line(points,dashed=False):
 s.append(f'<path d="{points}" fill="none" stroke="#167d9a" stroke-width="2.6" marker-end="url(#arrow)" '+('stroke-dasharray="7 5"' if dashed else '')+'/>')
def stage(x,w,n,title,sub,h=390):
 rect(x,180,w,h);rect(x,180,w,66,'#e8f2f8','#c6d6e2');text(x+17,209,n,16,'#167d9a',700);text(x+17,236,title,20,weight=700);text(x+17,269,sub,17,'#587185')
def item(x,y,title,sub,w=234):
 rect(x,y,w,57,'#f7fafc','#dde6ed',8);text(x+13,y+23,title,17,weight=650);text(x+13,y+45,sub,16,'#587185')
# Own ocean identity, not the reference's logos.
for j in range(3):
 s.append(f'<path d="M40 {42+j*10} Q55 {28+j*10} 70 {42+j*10} T100 {42+j*10}" fill="none" stroke="#167d9a" stroke-width="4"/>')
text(115,53,'OCEANEMBED',27,weight=750)
text(1880,43,'SIH 2026  •  SIH26066',18,'#167d9a',650)
s[-1]=s[-1].replace('x="1880"','text-anchor="end" x="1880"')
text(40,115,'TECHNICAL APPROACH',48,weight=800)
text(40,148,'Surface observations → spatial embeddings → subsurface ocean intelligence',24,'#587185')
text(1880,110,'NORTH INDIAN OCEAN',18,'#167d9a',700);s[-1]=s[-1].replace('x="1880"','text-anchor="end" x="1880"')
text(1880,139,'5–30°N  |  45–105°E  |  0.25° grid',18,'#587185');s[-1]=s[-1].replace('x="1880"','text-anchor="end" x="1880"')
stage(40,270,'01 / OBSERVE','SURFACE INPUTS','Historical inputs • 7 channels',390)
for y,a,b in [(285,'SST','OSTIA'),(348,'SSS + SLA','CMEMS MULTIOBS + DUACS'),(411,'Currents u / v','OSCAR Final v2.0'),(474,'Winds u / v','CCMP v3.1')]:item(58,y,a,b)
stage(335,270,'02 / HARMONISE','SCIENTIFIC PROCESSING','Daily, aligned, model-ready',390)
for y,a,b in [(285,'QC + valid-ocean mask','Missing data stays explicit'),(348,'Spatial / temporal alignment','xarray → 101 × 241 grid'),(411,'Train-only standardisation','Frozen feature + target scalers'),(474,'7 inputs + validity channel','Zarr model-ready stores')]:item(353,y,a,b)
# Dominant AI engine
rect(630,180,480,450,'#102e45','#167d9a');text(653,211,'03 / CORE INNOVATION',17,'#5bd1df',700)
text(653,248,'SPATIAL SATELLITE',30,'#fff',750);text(653,283,'EMBEDDING ENGINE',30,'#fff',750)
rect(653,305,434,67,'#1b4059','#416278',9);text(673,333,'33 × 33 context • dilated CNN',25,'#fff',650);text(673,357,'Dilations 1 / 2 / 4 / 8 / 1',18,'#b8d6e5')
line('M870 375 V393');rect(715,398,310,47,'#167d9a','#48bfd1',9);text(736,429,'32-D SATELLITE EMBEDDING',20,'#fff',750)
line('M870 449 V466');text(653,493,'+ latitude / longitude / seasonal context',19,'#b8d6e5')
rect(653,507,434,56,'#1b4059','#416278',9);text(673,542,'MLP decoder → 15 temperatures',24,'#fff',650)
text(653,593,'0–1000 m   •   136,335 parameters',22,'#5bd1df',650)
text(653,617,'One shared field pass; no per-click model run',17,'#d4e6ee')
stage(1135,285,'04 / QUALIFY','PHYSICAL DIAGNOSTICS','Derived from the same field',450)
for y,a,b in [(285,'ETOPO depth support','Hide below-seafloor values'),(348,'Temperature anomaly','Reconstruction − frozen L0'),(411,'D26 + TCHP','26°C depth + ocean heat'),(474,'Thermal-support indicators','Explainable historical categories')]:item(1153,y,a,b,249)
text(1153,584,'Validity + provenance',21,'#167d9a',650);text(1153,609,'Not a cyclone forecast',18,'#587185')
stage(1445,435,'05 / DELIVER','INTERACTIVE OCEAN INTELLIGENCE','FastAPI serves one authoritative field',450)
for y,a,b in [(285,'2D map + bathymetry-aware 3D','Linked location, depth and 15-level profile'),(348,'Historical event replay','IBTrACS tracks + along-track analysis'),(411,'Model-science workspace','Attribution • occlusion • physical QA'),(474,'Evidence + scientific exports','CSV / NetCDF / PNG + provenance')]:item(1463,y,a,b,399)
text(1463,584,'React dashboard • local runtime',21,'#167d9a',650);text(1463,609,'Provenance-keyed field cache',18,'#587185')
for x1,x2 in [(310,335),(605,630),(1110,1135),(1420,1445)]:line(f'M{x1} 389 H{x2-3}')
# Training side flow
rect(40,590,565,67,'#edf6f6','#b1d8d9',10)
text(57,616,'TRAINING BRANCH  •  GLORYS12V1 TARGETS',18,'#167d9a',700)
text(57,643,'Supervised training → validation selection → frozen L2',19)
line('M605 624 H617 V549 H647',True)
text(630,666,'Frozen checkpoint + hash-verified scalers',18,'#587185')
# Verification evidence lane
rect(40,705,1380,151,'#fff','#9fc4d4')
text(59,735,'06 / VERIFY  —  TWO COMPLEMENTARY EVIDENCE TRACKS',22,'#167d9a',750)
text(59,774,'HELD-OUT REANALYSIS',20,weight=750);text(59,803,'GLORYS • L0 / L1 baselines',20);text(59,832,'Depth-wise RMSE / MAE / bias',19,'#587185')
text(444,774,'INDEPENDENT ARGO AUDIT',20,weight=750);text(444,803,'5,176 profiles • 92 floats',22,'#167d9a',700);text(444,832,'Profile QC + float-clustered bootstrap',19,'#587185')
text(908,774,'SCIENTIFIC DISCIPLINE',20,weight=750);text(908,803,'Train 2015–20 • validation 2021',19);text(908,832,'Test 2022–24 • 2024 Argo held out',19,'#587185')
line('M1010 632 V695');text(1030,686,'prediction audit',16,'#167d9a')
# Operational qualification, no invented live status
rect(1445,658,435,198,'#edf6f6','#b1d8d9')
text(1463,690,'QUALIFIED RECENT STATES',22,'#167d9a',750)
text(1463,723,'Availability → source checks → same L2',19)
text(1463,751,'Actual valid date + operating-mode flags',18)
text(1463,783,'Temperature: qualified with limitations',18)
text(1463,811,'TCHP qualified • D26 withheld',19,weight=650)
text(1463,839,'Provider latency is disclosed',17,'#587185')
# Bottom technology panel
rect(40,882,1840,143,'#e8f0f6','#bdcedb')
text(60,913,'IMPLEMENTED TECH STACK',23,weight=750)
cols=[(60,'AI / SCIENCE','Python • PyTorch','NumPy • SciPy • gsw'),(425,'DATA ENGINEERING','xarray • pandas • Dask','NetCDF • Zarr'),(790,'SERVING / STORAGE','FastAPI • Uvicorn','Local files + field cache'),(1155,'FRONTEND','React • TypeScript • Vite','Tailwind CSS'),(1520,'VISUALS / TESTS','Three.js • Plotly','pytest • Vitest • Playwright')]
for x,a,b,c in cols:text(x,944,a,16,'#167d9a',750);text(x,976,b,21,weight=600);text(x,1006,c,18,'#587185')
text(40,1055,'SPATIAL CONTEXT  +  INDEPENDENT EVIDENCE  +  PHYSICAL SUPPORT  +  TRACEABLE REPLAY',19,'#167d9a',700)
text(1880,1055,'Implemented system • repository-verified',16,'#587185');s[-1]=s[-1].replace('x="1880"','text-anchor="end" x="1880"')
# Restrained, consistent technical line icons in the header corners.
icons=[(274,194,'sat'),(569,194,'grid'),(1384,194,'shield'),(1844,194,'screen'),(1074,194,'network')]
for x,y,kind in icons:
 s.append(f'<g transform="translate({x},{y})" fill="none" stroke="#168aa6" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">')
 if kind=='sat': s.append('<rect x="7" y="6" width="10" height="12" rx="2"/><path d="M1 4H6V18H1ZM18 4H23V18H18ZM12 1V5M12 19V23"/>')
 elif kind=='grid': s.append('<path d="M2 5H22M2 12H22M2 19H22"/><circle cx="7" cy="5" r="3" fill="#e8f2f8"/><circle cx="17" cy="12" r="3" fill="#e8f2f8"/><circle cx="9" cy="19" r="3" fill="#e8f2f8"/>')
 elif kind=='shield': s.append('<path d="M12 1L22 5V13Q21 20 12 24Q3 20 2 13V5ZM6 12L10 16L18 8"/>')
 elif kind=='screen': s.append('<rect x="1" y="2" width="22" height="16" rx="2"/><path d="M12 18V23M6 23H18M5 13L10 8L14 11L19 5"/>')
 else:s.append('<path d="M3 5L12 12L21 5M3 20L12 12L21 20"/><circle cx="3" cy="5" r="3"/><circle cx="3" cy="20" r="3"/><circle cx="12" cy="12" r="3"/><circle cx="21" cy="5" r="3"/><circle cx="21" cy="20" r="3"/>')
 s.append('</g>')
s.append('</svg>')
(P/'TECHNICAL_APPROACH.svg').write_text('\n'.join(s),encoding='utf-8')
