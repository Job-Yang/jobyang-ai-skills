// Assembly adapter only. The pinned compiler and viewer stay upstream-identical.
// applyTemplate remains the sole viewer assembler; its export cleanup is reused.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { isDeepStrictEqual } from 'node:util';
import { applyTemplate, renderCards, esc } from '../vendor/archify/renderers/shared/utils.mjs';
const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [inputPath, outputDir] = process.argv.slice(2);
const safe = value => JSON.stringify(value).replaceAll('<', '\\u003c').replaceAll('&', '\\u0026').replaceAll('>', '\\u003e');
const scriptData = (name, value) => `<script id="diagram-kit-${name}" type="application/json">${safe(value)}</script>`;
function playwrightModule() {
  if (process.env.PLAYWRIGHT_MODULE) return require(process.env.PLAYWRIGHT_MODULE);
  try { const p=require('playwright'); if(fs.existsSync(p.chromium.executablePath())) return p; } catch {}
  const cache = path.join(process.env.HOME, '.npm', '_npx');
  if (fs.existsSync(cache)) {
    for (const dir of fs.readdirSync(cache).sort()) {
      const module = path.join(cache, dir, 'node_modules', 'playwright');
      if (fs.existsSync(path.join(module, 'package.json'))) {
        const p=require(module);
        if(fs.existsSync(p.chromium.executablePath())) return p;
      }
    }
  }
  throw new Error('缺少Playwright＋匹配Chromium；不自动安装浏览器。可设置PLAYWRIGHT_MODULE。');
}
if(inputPath==='--preflight') {
  const p=playwrightModule(); const executable=p.chromium.executablePath();
  if(!fs.existsSync(executable)) throw new Error('Playwright的匹配Chromium缺失；不安装或升级。');
  console.log(JSON.stringify({ok:true,executable,node:process.version}));process.exit(0);
}
const input = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
const { source, scene, tokens, theme, formats } = input;
function cssTokens() {
  let css = Object.entries(tokens.modes).map(([mode, vars]) => `html[data-theme="${mode}"], [data-theme="${mode}"] {${Object.entries(vars).map(([k,v]) => `${k}:${v};`).join('')}}`).join('\n');
  css += `\nhtml body, .diagram-container > svg {font-family:${tokens.fonts.sans};}
    html .diagram-container svg text[data-dk-font="sans"] {font-family:${tokens.fonts.sans};}
    html .diagram-container svg text[data-dk-font="mono"], code {font-family:${tokens.fonts.mono};}\n`;
  // Template presets must not override the shared document-role theme.
  css += '.diagram-container > svg{background:var(--bg);filter:none;} #btn-preset{display:none!important;}';
  // Keep mature viewer controls, but host them in ordinary flow so a long figure
  // never has a toolbar covering its authored nodes at document reading width.
  css += '.diagram-nav{position:static!important;transform:none!important;inset:auto!important;max-width:100%;width:max-content;margin:8px 0 8px auto;}';
  for (const object of scene.objects) {
    if (!object.paint) continue;
    const id = object.id.replaceAll('\\','\\\\').replaceAll('"','\\"');
    const p = object.paint;
    const variable = hex => `var(--dk-${hex.slice(1).toLowerCase()})`;
    // Primitive-specific bindings were made before assembly. No blanket sibling
    // rect/polygon selector: terminal rings, masks and badges retain their job.
    css += `svg [data-node-id="${id}"] {--dk-node-ink:${variable(p.text)};}\n`;
    // 显式角色把树根改为浅色面时，文字也必须同步，不能沿用默认深底的白字。
    if (scene.type === 'tree') {
      const rootNode = `svg[data-tree-ui] [data-node-id="${id}"][data-tree-depth="0"]`;
      css += `${rootNode} .tree-label {fill:${variable(p.text)};}\n`;
      css += `${rootNode} .tree-sublabel {fill:${variable(p.text)};opacity:1;}\n`;
    }
  }
  for (const attr of ['fill','stroke']) {
    const values = new Set([...input.svg.matchAll(new RegExp(`data-dk-${attr}="([^"]*)"`, 'g'))].map(m=>m[1]));
    for (const value of values) {
      const key = value.startsWith('#') ? '--dk-'+value.slice(1).toLowerCase() : null;
      const paint = key && tokens.modes.light[key] ? `var(${key})` : value;
      css += `html[data-preset][data-theme] .diagram-container > svg [data-dk-paint][data-dk-${attr}="${value}"] {${attr}:${paint};}\n`;
    }
  }
  const outlines = tokens.layout?.surface_outline;
  if (outlines) {
    css += 'html .diagram-container > svg rect[data-surface-outline="none"] {stroke:none!important;}';
    css += `html .diagram-container > svg rect[data-surface-outline="thin"] {stroke-opacity:${outlines.filled_opacity}!important;stroke-dasharray:none!important;}`;
    css += 'html .diagram-container > svg rect[data-boundary-treatment="filled-outer"] {fill:var(--security-fill)!important;}';
    const widths = new Set([...input.svg.matchAll(/data-surface-outline-width="([^"]*)"/g)].map(match => match[1]));
    for (const width of widths) {
      css += `html .diagram-container > svg rect[data-surface-outline-width="${width}"] {stroke-width:${width}px!important;}`;
    }
  }
  // Role header and code text use text ink, not a hue pretending to be prose.
  css += 'svg [data-dk-paint="header"] + text, svg .er-title, svg .cl-title {fill:var(--text);}'
  for(const [color, plain] of Object.entries(input.explicitColors || {})) {
    for(const attr of ['fill','stroke']) css += `svg[data-theme="plain"] [data-explicit-${attr}="${color}"], html[data-theme="plain"] svg [data-explicit-${attr}="${color}"] {${attr}:${plain}!important;}\n`;
  }
  if (!scene.edges.some(e => e.directed ?? e.arrow ?? true)) css += '#btn-route-probe,#route-probe,#focus-reach{display:none!important;}';
  return css;
}
let template = fs.readFileSync(path.join(root,'vendor/archify/assets/template.html'),'utf8');
// Expose the existing canonical serializer for the assembly export adapter.
// This is a generated-page adaptation, not a patch to the pinned vendor source.
if (!template.includes('run: runExport,')) throw new Error('Pinned viewer export hook differs');
template = template.replace('run: runExport,', 'run: runExport,\n        serialize: serializeSvg,');
// The pinned collision owner only manages in-stage floating navigation. Our
// flow-hosted toolbar is outside that stage, so it must not accumulate reserve.
if (!template.includes('container && svg && nav &&')) throw new Error('Pinned chrome owner hook differs');
template = template.replace('container && svg && nav &&', 'container && svg && nav && nav.parentElement === container &&');
const reachStart=template.indexOf('function reachabilityRelationships()');
const reachEnd=template.indexOf('function computeReachability(',reachStart);
if(reachStart<0 || reachEnd<0) throw new Error('Pinned reachability hook differs');
let reachBlock=template.slice(reachStart,reachEnd);
reachBlock=reachBlock.replace('edges().forEach(function (edge) {', "edges().forEach(function (edge) {\n          if (edge.getAttribute('data-edge-directed') === 'false') return;");
template=template.slice(0,reachStart)+reachBlock+template.slice(reachEnd);
const routeStart=template.indexOf('Archify.routeProbe = (function () {');
const routeEnd=template.indexOf('Archify.semanticLens =',routeStart);
if(routeStart<0 || routeEnd<0) throw new Error('Pinned route probe hook differs');
let routeBlock=template.slice(routeStart,routeEnd);
const edgeQuery="return Array.prototype.slice.call(svg.querySelectorAll('[data-edge-from][data-edge-to]'));";
if(!routeBlock.includes(edgeQuery)) throw new Error('Pinned directed edge query differs');
routeBlock=routeBlock.replace(edgeQuery,"return Array.prototype.slice.call(svg.querySelectorAll('[data-edge-from][data-edge-to]')).filter(function(edge){return edge.getAttribute('data-edge-directed') !== 'false';});");
template=template.slice(0,routeStart)+routeBlock+template.slice(routeEnd);
template = template.replace("format === 'svg' ? 'auto' :", "format === 'svg' ? (document.documentElement.getAttribute('data-theme') || 'light') :");
template = template.replace("requestedTheme !== 'light' && requestedTheme !== 'dark'", "requestedTheme !== 'light' && requestedTheme !== 'dark' && requestedTheme !== 'plain'");
const flattenHook = String.raw`
        // Local delivery adaptation: resolve styles on the cleaned export clone,
        // not the focused live SVG. This preserves upstream state cleanup.
        var mount = document.createElement('div');
        mount.className = 'diagram-container';
        mount.style.cssText = 'position:fixed;left:-100000px;top:0;pointer-events:none;';
        clone.setAttribute('data-theme', requestedTheme === 'auto' ? 'light' : (requestedTheme || document.documentElement.getAttribute('data-theme') || 'light'));
        mount.appendChild(clone); document.body.appendChild(mount);
        try {
          var elements = [clone].concat(Array.from(clone.querySelectorAll('*')));
          var computedPaint = elements.map(function(el){var cs=getComputedStyle(el);var values={};
            ['fill','stroke','stroke-width','stroke-dasharray','stroke-linecap','stroke-linejoin','marker-end','marker-start','marker-mid','opacity','fill-opacity','stroke-opacity','font-family','font-size','font-weight','font-style','text-anchor','dominant-baseline','visibility','display'].forEach(function(prop){
              // A definition with no own paint inherits from each <use> instance.
              // getComputedStyle(defs/path) returns defaults, not that instance's
              // colour. Freezing those defaults turns every chart marker black.
              if (el.closest('defs') && ['fill','stroke','fill-opacity','stroke-opacity'].indexOf(prop)!==-1 &&
                  !el.hasAttribute(prop) && !el.style.getPropertyValue(prop) && !el.hasAttribute('class')) return;
              values[prop]=cs.getPropertyValue(prop).replace(/url\(["']?[^#)]*#([^"')]+)["']?\)/g,'url(#$1)');
            });return values;});
          elements.forEach(function(el,index){Object.entries(computedPaint[index]).forEach(function(pair){if(pair[1])el.setAttribute(pair[0],pair[1])});el.removeAttribute('style');});
          clone.querySelectorAll('style').forEach(function(el){el.remove()});
        } finally {mount.remove();}
`;
const returnHook = "        // The XML declaration pins UTF-8: without it, consumers that guess an";
if (!template.includes(returnHook)) throw new Error('Pinned serializer hook differs');
template = template.replace(returnHook, flattenHook + '\n' + returnHook);
template = template.replace("theme = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';", `theme = '${theme}';`);
template = template.replace("if (theme !== 'light' && theme !== 'dark')", "if (theme !== 'light' && theme !== 'dark' && theme !== 'plain')");
const adapterRuntime = `
(function(){
  var source=JSON.parse(document.getElementById('diagram-kit-source').textContent);
  var scene=JSON.parse(document.getElementById('diagram-kit-scene').textContent);
  document.documentElement.setAttribute('data-theme',${JSON.stringify(theme)});
  var details=document.createElement('details'); details.id='diagram-kit-inspector';
  var summary=document.createElement('summary');summary.textContent='图义与可编辑源';details.appendChild(summary);
  var info=document.createElement('pre');info.style.whiteSpace='pre-wrap';info.style.fontFamily='inherit';details.appendChild(info);
  var button=document.createElement('button');button.textContent='下载作者源 JSON';
  button.onclick=function(){var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(source,null,2)],{type:'application/json'}));a.download='diagram.source.json';a.click();setTimeout(function(){URL.revokeObjectURL(a.href)},1000)};details.appendChild(button);
  var container=document.querySelector('.diagram-container');
  var nav=document.querySelector('.diagram-nav');if(nav)container.before(nav);
  container.after(details);
  if(scene.supplemental){
    var supplemental=document.createElement('details');supplemental.id='diagram-kit-supplemental';
    var heading=document.createElement('summary');heading.textContent=scene.supplemental.title||'补充记录与说明';supplemental.appendChild(heading);
    scene.supplemental.sections.forEach(function(section){
      var title=document.createElement('h3');title.textContent=section.title||section.id;supplemental.appendChild(title);
      var table=document.createElement('table');table.style.cssText='width:100%;border-collapse:collapse;';
      section.rows.forEach(function(row){var tr=document.createElement('tr');var label=document.createElement('th');var value=document.createElement('td');label.textContent=String(row.label);value.textContent=typeof row.value==='string'?row.value:JSON.stringify(row.value,null,2);[label,value].forEach(function(cell){cell.style.cssText='padding:8px;text-align:left;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere;border-bottom:1px solid var(--panel-border)';tr.appendChild(cell)});table.appendChild(tr)});
      supplemental.appendChild(table);
    });
    var linkData=JSON.parse(document.getElementById('diagram-kit-supplemental-link').textContent);
    if(linkData.href){var link=document.createElement('a');link.textContent='单独查看完整补充记录';link.href=linkData.href;supplemental.appendChild(link)}
    container.after(supplemental);
  }
  function show(id){var o=scene.objects.find(function(n){return n.id===id});if(!o)return;var edges=scene.edges.filter(function(e){return e.from===id||e.to===id});info.textContent=JSON.stringify({id:id,kind:o.kind,content:o.content,membership:o.membership,relationships:edges.length?edges:'无显式关系'},null,2)}
  document.querySelector('.diagram-container svg').addEventListener('click',function(e){var node=e.target.closest('[data-node-id]');if(node)show(node.getAttribute('data-node-id'))});
  document.querySelector('.diagram-container svg').addEventListener('focusin',function(e){var node=e.target.closest('[data-node-id]');if(node)show(node.getAttribute('data-node-id'))});
  var plain=document.createElement('button');plain.id='btn-diagram-plain';plain.textContent='灰阶';plain.type='button';plain.onclick=function(){document.documentElement.setAttribute('data-theme','plain')};document.getElementById('btn-theme').after(plain);
  window.DiagramKit={source:source,scene:scene,exportSVG:function(mode){
    var previous=document.documentElement.getAttribute('data-theme');
    var selected=mode===undefined?previous:mode;
    if(['light','dark','plain'].indexOf(selected)===-1)throw new RangeError('Unsupported SVG theme: '+String(selected));
    document.documentElement.setAttribute('data-theme',selected);
    try {return Archify.exportMenu.serialize(1,{theme:selected});
    } finally {document.documentElement.setAttribute('data-theme',previous)}
  }};
})();`;
function assemble() {
  let html = applyTemplate(template, { title: source.meta.title, subtitle: source.meta.subtitle,
    svg: input.svg, cards: renderCards(source.payload.cards || []), locale: source.meta.locale || 'zh-CN', visualPreset:'classic', sourceEvidence:input.sourceEvidence || null });
  html = html.replace('</head>', `<style id="diagram-kit-theme">${cssTokens()}</style></head>`);
  if (source.meta.note) html = html.replace('</h1>', () => `</h1><p class="subtitle diagram-kit-note">${esc(source.meta.note)}</p>`);
  html = html.replaceAll('SVG · 自动', 'SVG · 当前主题').replaceAll('匹配宿主主题', '固定当前主题，离线可用');
  html = html.replace('</body>', `${scriptData('source',source)}${scriptData('scene',scene)}${scriptData('components',input.components)}${scriptData('supplemental-link',{href:input.supplementalHref||null})}<script>${adapterRuntime}</script></body>`);
  return html;
}
const { chromium } = playwrightModule();
const browser = await chromium.launch({headless:true,executablePath:chromium.executablePath()});
const page = await browser.newPage({viewport:{width:1100,height:900},locale:'zh-CN',colorScheme:'light'});
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route('http**/*',route=>route.abort());
async function verifyEmbeddedData() {
  const actual=await page.evaluate(()=>({
    sourceScripts:[...document.querySelectorAll('script#diagram-kit-source')].map(e=>e.textContent),
    sceneScripts:[...document.querySelectorAll('script#diagram-kit-scene')].map(e=>e.textContent),
    runtimeSource:window.DiagramKit && window.DiagramKit.source,
    runtimeScene:window.DiagramKit && window.DiagramKit.scene
  }));
  for(const [name, expected] of [['source',source],['scene',scene]]) {
    const scripts=actual[name+'Scripts'];
    if(scripts.length!==1 || !isDeepStrictEqual(JSON.parse(scripts[0]),expected) ||
       !isDeepStrictEqual(actual[name==='source'?'runtimeSource':'runtimeScene'],expected)) {
      throw new Error('Embedded '+name+' differs from frozen assembly input');
    }
  }
}
try {
  await page.setContent(assemble(),{waitUntil:'load'});
  await page.evaluate(()=>document.fonts.ready);
  await verifyEmbeddedData();
  const observations = await page.evaluate(()=>{
    const svg=document.querySelector('.diagram-container svg');
    const boxes={};
    for(const el of svg.querySelectorAll('[data-node-id]')){const b=el.getBBox(); boxes[el.getAttribute('data-node-id')]=[b.x,b.y,b.width,b.height];}
    return {boxes,canvas:[svg.viewBox.baseVal.width,svg.viewBox.baseVal.height],language:document.documentElement.lang,
      semanticObjects:svg.querySelectorAll('[data-node-id]').length,semanticEdges:svg.querySelectorAll('[data-edge-key]').length};
  });
  for(const object of scene.objects) {
    if(object.interactive===false) continue;
    if(!observations.boxes[object.id]) throw new Error(`Viewer did not recognize ${object.id}`);
    object.rendered_geometry=observations.boxes[object.id];
    if(object.geometry===null) object.geometry=observations.boxes[object.id];
  }
  if (scene.type !== 'free') scene.canvas = observations.canvas;
  // Serialize the source and complete scene only after the final geometry exists.
  fs.writeFileSync(path.join(outputDir,'diagram.scene.json'),JSON.stringify(scene,null,2)+'\n');
  fs.writeFileSync(path.join(outputDir,'diagram.html'),assemble());
  await page.goto('about:blank');
  await page.setContent(assemble(),{waitUntil:'load'});
  await page.evaluate(()=>document.fonts.ready);
  await verifyEmbeddedData();
  const exported = await page.evaluate(()=>{
    const result=Archify.exportMenu.serialize(1,{theme:document.documentElement.getAttribute('data-theme') || 'light'});
    return {text:result.svgString,canonicalStateClean:result.canonicalStateClean,width:result.width,height:result.height};
  });
  if(!exported.canonicalStateClean) throw new Error('Upstream export cleaner rejected state');
  if(/var\(--/.test(exported.text)) throw new Error('Platform SVG contains unresolved CSS variables');
  // Export selected theme, not the native auto SVG that defaults to dark in rsvg.
  if(formats.includes('svg')) fs.writeFileSync(path.join(outputDir,'diagram.svg'),exported.text+'\n');
  if(formats.includes('png')) {
    const raster=await browser.newPage({viewport:{width:Math.ceil(exported.width),height:Math.ceil(exported.height)},deviceScaleFactor:2});
    await raster.setContent(`<html><body style="margin:0">${exported.text}</body></html>`);
    await raster.evaluate(()=>document.fonts.ready);
    await raster.locator('svg').screenshot({path:path.join(outputDir,'diagram.png')});
    await raster.close();
  }
  if(errors.length) throw new Error('Viewer errors: '+errors.join('; '));
  console.log(JSON.stringify({ok:true,observations,export:{canonicalStateClean:exported.canonicalStateClean,theme,width:exported.width,height:exported.height},browser:'playwright/chromium',independent_visual_review:false}));
} finally {await browser.close();}
