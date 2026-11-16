// Real standalone-SVG raster regression: <use> colours must survive serialization.
const fs=require('node:fs');
const assert=require('node:assert/strict');
// 复用配置的浏览器包，不绑定开发者本机缓存路径，也不自动安装。
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:chromium.executablePath()});
 try {
  for(const filename of process.argv.slice(2)){
   const page=await browser.newPage();
   await page.setContent('<html><body style="margin:0">'+fs.readFileSync(filename,'utf8')+'</body></html>');
   await page.evaluate(()=>document.fonts.ready);
   const result=await page.evaluate(async()=>{
    const svg=document.querySelector('svg');
    const w=svg.viewBox.baseVal.width,h=svg.viewBox.baseVal.height;
    svg.setAttribute('width',w);svg.setAttribute('height',h);
    const markers=[...svg.querySelectorAll('g[id^="PathCollection"] use')].map(el=>{
     const b=el.getBBox(),p=svg.createSVGPoint();p.x=b.x+b.width/2;p.y=b.y+b.height/2;
     const point=p.matrixTransform(el.getCTM());
     return {href:el.getAttribute('href')||el.getAttributeNS('http://www.w3.org/1999/xlink','href'),x:point.x,y:point.y,fill:getComputedStyle(el).fill};
    });
    const image=new Image();image.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(new XMLSerializer().serializeToString(svg));
    await image.decode();
    const canvas=document.createElement('canvas');canvas.width=Math.ceil(w);canvas.height=Math.ceil(h);
    const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0,w,h);
    return markers.map(m=>({...m,pixel:[...ctx.getImageData(Math.round(m.x),Math.round(m.y),1,1).data]}));
   });
   const sourcefile=filename.replace(/\.svg$/,'.source.json');
   const source=fs.existsSync(sourcefile) ? JSON.parse(fs.readFileSync(sourcefile,'utf8')) : null;
   const authoredCount=source?.payload?.points?.length ?? 4;
   assert.equal(result.length,authoredCount,'all authored points survive, including explicit panels');
   const expected=result.map(m=>{
    assert.match(m.fill,/^rgba?\(/,'marker instance must resolve to a real colour');
    const colour=m.fill.match(/[0-9.]+/g).slice(0,3).map(v=>Math.round(Number(v)));
    assert.notDeepEqual(colour,[0,0,0],'marker instance must not fall back to default black');
    return colour;
   });
   result.forEach((m,i)=>assert.deepEqual(m.pixel.slice(0,3),expected[i],`marker ${i}: standalone SVG raster must preserve the instance fill, not default black`));
   const pngfile=filename.replace(/\.svg$/,'.png');
   if(fs.existsSync(pngfile)) {
    const pixels=await page.evaluate(async ({data,markers})=>{
     const image=new Image();image.src='data:image/png;base64,'+data;await image.decode();
     const svg=document.querySelector('svg'),w=svg.viewBox.baseVal.width,h=svg.viewBox.baseVal.height;
     const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
     const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);
     return markers.map(m=>[...ctx.getImageData(Math.round(m.x*image.naturalWidth/w),Math.round(m.y*image.naturalHeight/h),1,1).data]);
    },{data:fs.readFileSync(pngfile).toString('base64'),markers:result});
    pixels.forEach((pixel,i)=>assert.deepEqual(pixel.slice(0,3),expected[i],`PNG marker ${i}: actual delivery PNG must have same series colour`));
    result.forEach((m,i)=>m.pngPixel=pixels[i]);
   }
   console.log(JSON.stringify({file:filename,markers:result,passed:true}));
   await page.close();
  }
 } finally {await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
