// Renders the EngCRM marketing graphics to PNG with headless Chromium.
//
//   node marketing/graphics/build.mjs            # all graphics, all sizes
//   node marketing/graphics/build.mjs hero       # only the named graphic(s)
//
// Each graphic/size is rendered independently: one failure is reported and
// the rest still render. Exit code is 1 if anything failed.
//
// Sizes match the other app banners in ~/ai-workzone/marketing-info-my-apps/<app>/
// (learnwohl, leguilde, notes-world): 750x300, 640x480, Fiverr 750x453, and the
// portrait 430x750 and 300x750.

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = (() => {
  try {
    return require("playwright");
  } catch {
    return require("/opt/node-tools/node_modules/playwright");
  }
})();

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, "out");
const FONT_DIR = path.join(HERE, "../../gcrm/ui/static/fonts");
// Inline the fonts as data URLs: a page loaded with setContent cannot fetch file:// fonts.
const font = (file) =>
  `data:font/woff2;base64,${fs.readFileSync(path.join(FONT_DIR, file)).toString("base64")}`;

// layout: "wide" (short banner), "box" (roughly 4:3), "portrait" (stacked).
const SIZES = [
  { name: "750x300", w: 750, h: 300, layout: "wide" },
  { name: "640x480", w: 640, h: 480, layout: "box" },
  { name: "fiverr-750x453", w: 750, h: 453, layout: "box" },
  { name: "430x750", w: 430, h: 750, layout: "portrait" },
  { name: "300x750", w: 300, h: 750, layout: "portrait" },
];

// ---------------------------------------------------------------- ornaments

const sunburst = (size, rays = 13) => {
  const r = size / 2;
  const lines = Array.from({ length: rays }, (_, i) => {
    const a = Math.PI + (Math.PI * i) / (rays - 1);
    const x = r + Math.cos(a) * r * 0.98;
    const y = r + Math.sin(a) * r * 0.98;
    return `<line x1="${r}" y1="${r}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>`;
  }).join("");
  const arcs = [0.34, 0.58, 0.82]
    .map((k) => `<path d="M ${r - r * k} ${r} A ${r * k} ${r * k} 0 0 1 ${r + r * k} ${r}"/>`)
    .join("");
  return `<svg class="sunburst" viewBox="0 0 ${size} ${r + 2}" width="${size}" height="${r + 2}">
    <g stroke="#c9a24a" stroke-width="1" fill="none" opacity=".55">${lines}${arcs}</g>
    <circle cx="${r}" cy="${r}" r="${r * 0.14}" fill="#c9a24a"/>
  </svg>`;
};

const rule = `<svg class="rule" viewBox="0 0 220 12" width="220" height="12">
  <g stroke="#c9a24a" fill="none"><line x1="0" y1="6" x2="92" y2="6"/><line x1="128" y1="6" x2="220" y2="6"/>
  <path d="M110 0 L116 6 L110 12 L104 6 Z" fill="#c9a24a"/><circle cx="98" cy="6" r="2" fill="#c9a24a"/><circle cx="122" cy="6" r="2" fill="#c9a24a"/></g>
</svg>`;

const wordmark = `<div class="wordmark">EngCRM</div>`;

// ---------------------------------------------------------------- graphics

const GRAPHICS = {
  hero: () => `
    <div class="split">
      <div class="copy">
        <div class="eyebrow">AI outreach CRM</div>
        <h1 class="brand">EngCRM</h1>
        ${rule}
        <p class="lead">Finds the businesses, researches them <br/>and drafts the emails. <br/>You approve every one.</p>
      </div>
      <div class="art">${sunburst(300, 15)}</div>
    </div>`,

  pipeline: () => {
    const steps = [
      ["Research", "finds businesses on the map"],
      ["Enrich", "fills in website & email"],
      ["Scout", "scores each one for fit"],
      ["Outreach", "drafts a personal email"],
      ["Follow-up", "reads replies, nudges later"],
    ];
    const nodes = steps
      .map(
        ([t, d], i) => `
        <div class="step">
          <div class="num">${["I", "II", "III", "IV", "V"][i]}</div>
          <div class="step-text"><div class="step-title">${t}</div><div class="step-desc">${d}</div></div>
        </div>${i < steps.length - 1 ? '<div class="chev">&#x203A;</div>' : ""}`
      )
      .join("");
    return `
      ${wordmark}
      <div class="stack">
        <h2>Five agents. One pipeline.</h2>
        ${rule}
        <div class="steps">${nodes}</div>
      </div>`;
  },

  approval: () => `
    ${wordmark}
    <div class="split">
      <div class="copy">
        <h2>Nothing sends <br/>without your yes.</h2>
        ${rule}
        <p class="lead">Every AI-drafted email waits in your approval queue. Read it, edit it, send it, or reject it.</p>
      </div>
      <div class="art">
        <div class="mail">
          <div class="mail-head"><span class="dot"></span>Approval queue</div>
          <div class="mail-line w90"></div>
          <div class="mail-line w70"></div>
          <div class="mail-line w80"></div>
          <div class="mail-line w50"></div>
          <div class="mail-actions"><span class="btn ok">Approve</span><span class="btn no">Reject</span></div>
        </div>
      </div>
    </div>`,

  claude: () => `
    ${wordmark}
    <div class="split">
      <div class="copy">
        <h2 class="sm">Talk to Claude. <br/>It runs the pipeline.</h2>
        ${rule}
        <p class="lead">Built-in MCP server: start research, check status and clear the approval queue in plain conversation.</p>
      </div>
      <div class="art">
        <div class="chat">
          <div class="bubble you">Research cafés in Augsburg.</div>
          <div class="bubble ai">Research started. New leads will be scouted and scored.</div>
          <div class="bubble you">What's waiting for my approval?</div>
        </div>
      </div>
    </div>`,

  mobile: () => `
    ${wordmark}
    <div class="split">
      <div class="copy">
        <h2>Your CRM <br/>in your pocket.</h2>
        ${rule}
        <p class="lead">Log a meeting, dictate the note, set the follow-up and move the stage in one save.</p>
      </div>
      <div class="art">
        <div class="phone">
          <div class="notch"></div>
          <div class="ph-title">Log a meeting</div>
          <div class="ph-field"></div>
          <div class="ph-field tall"></div>
          <div class="ph-row"><span class="chip">Follow-up</span><span class="chip on">Meeting held</span></div>
          <div class="ph-save">Save</div>
        </div>
      </div>
    </div>`,

  vertical: () => {
    const chips = ["Art galleries", "Cafés", "Law firms", "Distributors", "Your market"]
      .map((c, i, a) => `<span class="vchip${i === a.length - 1 ? " on" : ""}">${c}</span>`)
      .join("");
    return `
      ${wordmark}
      <div class="stack">
        <h2>One config file.<br class="tall-only"/> Any market.</h2>
        ${rule}
        <p class="lead center">Swap the vertical and the whole system retargets: what to look for, how to score fit, how to write.</p>
        <div class="vchips">${chips}</div>
      </div>`;
  },
};

// ---------------------------------------------------------------- page

const css = (size) => {
  const { w, h } = size;
  const t = size.layout !== "wide";
  return `
@font-face { font-family: "Poiret One"; src: url("${font("poiret-one-latin-400-normal.woff2")}"); }
@font-face { font-family: "Josefin Sans"; src: url("${font("josefin-sans-latin-400-normal.woff2")}"); font-weight: 400; }
@font-face { font-family: "Josefin Sans"; src: url("${font("josefin-sans-latin-600-normal.woff2")}"); font-weight: 600 700; }
* { box-sizing: border-box; margin: 0; padding: 0; }
:root { --gold:#c9a24a; --gold-hi:#e6c877; --text:#ebe3cf; --muted:#a09578; --bg:#0c0b09; --surface:#15130e; --jade:#5fb3a8; --danger:#e0645a; }
html, body { width:${w}px; height:${h}px; overflow:hidden; }
body { font-family:"Josefin Sans",sans-serif; color:var(--text);
  background: radial-gradient(ellipse 70% 55% at 78% 0%, #c9a24a2a, transparent 70%),
              radial-gradient(ellipse 50% 60% at 0% 100%, #5fb3a812, transparent 70%), var(--bg); }
.frame { position:absolute; inset:0; padding:${t ? 46 : 30}px 48px; display:flex; flex-direction:column; justify-content:center; }
.frame::before { content:""; position:absolute; inset:12px; border:1px solid #c9a24a66; pointer-events:none; }
.frame::after  { content:""; position:absolute; inset:17px; border:1px solid #c9a24a26; pointer-events:none; }
.corner { position:absolute; width:22px; height:22px; border-color:var(--gold); border-style:solid; }
.c-tl { top:8px; left:8px; border-width:2px 0 0 2px; } .c-tr { top:8px; right:8px; border-width:2px 2px 0 0; }
.c-bl { bottom:8px; left:8px; border-width:0 0 2px 2px; } .c-br { bottom:8px; right:8px; border-width:0 2px 2px 0; }
.wordmark { position:absolute; top:${t ? 30 : 22}px; right:34px; font-family:"Poiret One"; font-size:${t ? 22 : 16}px; color:var(--gold); letter-spacing:.06em; }
.split { display:flex; align-items:center; gap:28px; height:100%; }
.copy { flex:1 1 56%; }
.art { flex:0 0 40%; display:flex; justify-content:center; align-items:center; }
.stack { display:flex; flex-direction:column; align-items:center; text-align:center; }
.eyebrow { text-transform:uppercase; letter-spacing:.32em; font-size:12px; color:var(--muted); margin-bottom:${t ? 10 : 4}px; }
.brand { font-family:"Poiret One"; font-weight:400; color:var(--gold-hi); font-size:${t ? 96 : 72}px; line-height:1; letter-spacing:.02em; }
h2.sm { font-size:${t ? 38 : 34}px; }
h2 { font-family:"Poiret One"; font-weight:400; color:var(--gold-hi); font-size:${t ? 42 : 36}px; line-height:1.08; letter-spacing:.01em; }
.rule { display:block; margin:${t ? 18 : 12}px 0; }
.stack .rule { margin-left:auto; margin-right:auto; }
.lead { font-size:${t ? 18 : 16}px; line-height:1.45; color:var(--text); max-width:400px; }
.lead.center { max-width:560px; margin:0 auto; color:var(--muted); }
.tall-only { display:${t ? "inline" : "none"}; }
.sunburst { width:${t ? 300 : 250}px; height:auto; }

/* pipeline */
.steps { display:flex; align-items:stretch; gap:4px; width:100%; margin-top:${t ? 18 : 2}px; }
.step { flex:1 1 0; min-width:0; padding:${t ? "18px 8px" : "10px 6px"}; border:1px solid #c9a24a55; background:#15130ecc; display:flex; flex-direction:column; align-items:center; gap:${t ? 8 : 4}px; }
.num { font-family:"Poiret One"; color:var(--gold); font-size:${t ? 22 : 16}px; }
.step-text { display:flex; flex-direction:column; align-items:center; gap:inherit; }
.step-title { font-weight:600; font-size:${t ? 16 : 14}px; letter-spacing:.04em; }
.step-desc { font-size:${t ? 13 : 11.5}px; color:var(--muted); line-height:1.3; }
.chev { align-self:center; color:var(--gold); font-size:26px; width:14px; text-align:center; }

/* approval mock */
.mail { width:${t ? 250 : 220}px; border:1px solid #c9a24a77; background:var(--surface); padding:16px; box-shadow:0 0 0 5px #0c0b09, 0 0 0 6px #c9a24a33; }
.mail-head { font-size:12px; letter-spacing:.2em; text-transform:uppercase; color:var(--gold); margin-bottom:14px; display:flex; align-items:center; gap:8px; }
.dot { width:7px; height:7px; border-radius:50%; background:var(--gold); display:inline-block; }
.mail-line { height:7px; background:#ebe3cf2e; margin:9px 0; }
.w90{width:90%} .w70{width:70%} .w80{width:80%} .w50{width:50%}
.mail-actions { display:flex; gap:10px; margin-top:16px; }
.btn { font-size:13px; font-weight:600; padding:7px 12px; letter-spacing:.06em; }
.btn.ok { background:var(--gold); color:#14110a; } .btn.no { border:1px solid var(--danger); color:var(--danger); }

/* chat mock */
.chat { width:${t ? 280 : 270}px; display:flex; flex-direction:column; gap:${t ? 12 : 8}px; }
.bubble { font-size:${t ? 15 : 13.5}px; line-height:1.35; padding:9px 13px; max-width:88%; }
.bubble.you { align-self:flex-end; background:var(--gold); color:#14110a; }
.bubble.ai { align-self:flex-start; border:1px solid #c9a24a77; background:var(--surface); }

/* phone mock */
.phone { width:${t ? 170 : 132}px; height:${t ? 330 : 214}px; border:2px solid var(--gold); border-radius:22px; background:var(--surface); padding:${t ? "30px 14px" : "20px 11px"}; display:flex; flex-direction:column; gap:${t ? 12 : 8}px; position:relative; }
.notch { position:absolute; top:9px; left:50%; transform:translateX(-50%); width:40px; height:5px; border-radius:3px; background:#c9a24a66; }
.ph-title { font-family:"Poiret One"; color:var(--gold-hi); font-size:${t ? 18 : 14}px; }
.ph-field { height:${t ? 26 : 18}px; border:1px solid #c9a24a44; }
.ph-field.tall { height:${t ? 70 : 34}px; }
.ph-row { display:flex; gap:5px; flex-wrap:wrap; }
.chip { font-size:${t ? 11 : 9}px; padding:3px 6px; border:1px solid #c9a24a66; color:var(--muted); }
.chip.on { background:#5fb3a833; border-color:var(--jade); color:var(--text); }
.ph-save { margin-top:auto; text-align:center; background:var(--gold); color:#14110a; font-weight:600; font-size:${t ? 14 : 11}px; padding:${t ? 8 : 5}px; }

/* vertical */
.vchips { display:flex; gap:10px; justify-content:center; flex-wrap:wrap; margin-top:${t ? 30 : 14}px; }
.vchip { font-size:${t ? 15 : 13}px; padding:${t ? "8px 14px" : "5px 11px"}; border:1px solid #c9a24a66; color:var(--muted); letter-spacing:.04em; }
.vchip.on { background:var(--gold); color:#14110a; border-color:var(--gold); font-weight:600; }
${w < 700 && size.layout === "box" ? narrowBox : ""}
${size.layout === "portrait" ? portrait(w) : ""}
`;
};

// 640 wide: same composition as 750, scaled down a notch.
const narrowBox = `
.frame { padding-left:40px; padding-right:40px; }
h2 { font-size:36px; } h2.sm { font-size:33px; }
.brand { font-size:70px; }
.lead { font-size:16px; }
.art { zoom:.82; }
.step-desc { font-size:11.5px; }
`;

// Portrait: everything stacks and centres; the pipeline runs top to bottom.
const portrait = (w) => {
  const n = w < 400; // 300 wide
  return `
.frame { padding:${n ? "56px 26px 64px" : "64px 36px 72px"}; }
.wordmark { top:auto; bottom:${n ? 28 : 32}px; left:0; right:0; text-align:center; font-size:${n ? 18 : 22}px; }
.split { flex-direction:column; justify-content:center; gap:${n ? 30 : 38}px; text-align:center; }
.copy, .art { flex:none; width:100%; }
.copy .rule { margin-left:auto; margin-right:auto; }
h2, .lead { text-wrap:balance; }
.lead br { display:none; }
h2 { font-size:${n ? 31 : 40}px; } h2.sm { font-size:${n ? 27 : 38}px; }
.brand { font-size:${n ? 60 : 84}px; }
.eyebrow { font-size:${n ? 11 : 12}px; letter-spacing:.26em; }
.lead { font-size:${n ? 15.5 : 18}px; max-width:none; margin:0 auto; }
.sunburst { width:${n ? 230 : 320}px; }
.chat { width:100%; max-width:300px; }
.bubble { font-size:${n ? 13.5 : 15}px; }
.mail { width:${n ? 230 : 280}px; }
.phone { width:${n ? 150 : 170}px; height:${n ? 290 : 320}px; }
.steps { flex-direction:column; align-items:stretch; width:100%; gap:2px; margin-top:${n ? 8 : 14}px; }
.step { width:auto; flex:none; flex-direction:row; text-align:left; gap:${n ? 10 : 14}px; padding:${n ? "10px 12px" : "13px 16px"}; }
.step .num { width:${n ? 30 : 36}px; text-align:center; flex:none; }
.step-text { display:flex; flex-direction:column; align-items:flex-start; gap:3px; }
.step-desc { font-size:${n ? 12 : 13.5}px; }
.chev { transform:rotate(90deg); align-self:center; height:16px; line-height:16px; font-size:22px; }
.vchips { flex-direction:column; align-items:center; gap:${n ? 8 : 10}px; margin-top:${n ? 26 : 34}px; }
`;
};

const page = (body, size) => `<!doctype html><html><head><meta charset="utf-8"><style>${css(size)}</style></head>
<body><div class="frame"><i class="corner c-tl"></i><i class="corner c-tr"></i><i class="corner c-bl"></i><i class="corner c-br"></i>${body}</div></body></html>`;

// ---------------------------------------------------------------- render

async function main() {
  const wanted = process.argv.slice(2);
  const names = wanted.length ? wanted : Object.keys(GRAPHICS);
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch({
    executablePath: fs.existsSync("/opt/pw-browsers/chromium") ? "/opt/pw-browsers/chromium" : undefined,
  });
  const failures = [];
  try {
    for (const name of names) {
      for (const s of SIZES) {
        const file = path.join(OUT, `engcrm-${name}-${s.name}.png`);
        try {
          if (!GRAPHICS[name]) throw new Error(`unknown graphic "${name}"`);
          const tab = await browser.newPage({ viewport: { width: s.w, height: s.h } });
          try {
            await tab.setContent(page(GRAPHICS[name](), s), { waitUntil: "load" });
            await tab.evaluate(() => document.fonts.ready);
            await tab.screenshot({ path: file });
          } finally {
            await tab.close();
          }
          console.log(`ok    ${path.relative(process.cwd(), file)}`);
        } catch (err) {
          failures.push(`${name} ${s.name}`);
          console.error(`FAIL  ${name} ${s.name}: ${err.message}`);
        }
      }
    }
  } finally {
    await browser.close();
  }
  if (failures.length) {
    console.error(`\n${failures.length} failed: ${failures.join(", ")}`);
    process.exit(1);
  }
}

main();
