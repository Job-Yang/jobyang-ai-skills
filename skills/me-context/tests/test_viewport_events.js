/* Event-boundary regression. Executes production handlers against a DOM mock.
 * Node is a test dependency only; the generated viewer remains zero-dependency.
 */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync(require('node:path').join(__dirname,'../scripts/viz.py'),'utf8');
let checks=0;function check(b,msg){assert.ok(b,msg);checks++;}
class Target{
 constructor(){this.listeners={};this.attrs={};}
 addEventListener(t,f){(this.listeners[t]||(this.listeners[t]=[])).push(f);}
 dispatch(t,id,x=0,y=0){const e={pointerId:id,clientX:x,clientY:y,button:0,target:this,preventDefault(){}};(this.listeners[t]||[]).forEach(f=>f(e));}
 setPointerCapture(){} setAttribute(k,v){this.attrs[k]=v;}
}
let width=1440,frames=[],renders=0;
const app=new Target();app.style={setProperty(k,v){this[k]=v;}};app.classList={contains(){return false;}};app.getBoundingClientRect=()=>({left:0,width});
const classes=new Set(['view-all']);const body={classList:{add(x){classes.add(x);},remove(x){classes.delete(x);},contains(x){return classes.has(x);}}};
const bar=new Target(),net=new Target();net.scrollLeft=300;net.scrollTop=200;net.closest=()=>null;
const win=new Target(),ctx={innerWidth:1440,document:{querySelector:()=>app,body},$:s=>s==='#column-divider'?bar:null,
 getComputedStyle:()=>({paddingLeft:'24',paddingRight:'24'}),requestAnimationFrame:f=>{frames.push(f);return 1;},
 G:{camera:false},renderNet(){renders++;},route(){},window:win,refitColumns:()=>false};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('  function initColumnDivider(){'),src.indexOf('  function initGraphControls(){'))+'\ninitColumnDivider();',ctx);
function flush(){const f=frames;frames=[];f.forEach(x=>x());}
bar.dispatch('pointerdown',1,550);bar.dispatch('pointermove',1,870);flush();
check(+parseFloat(app.style['--left-weight'])>60,'first pointer changes split');
const start=app.style['--left-weight'];
bar.dispatch('pointerdown',2,600);bar.dispatch('pointermove',2,800);flush();
check(start===app.style['--left-weight'],'second pointer does not replace active pointer');
bar.dispatch('pointerup',2);bar.dispatch('pointermove',1,600);flush();
check(parseFloat(app.style['--left-weight'])<60,'other pointer up cannot stop active split');
bar.dispatch('lostpointercapture',1);const ended=app.style['--left-weight'];bar.dispatch('pointermove',1,870);flush();
check(ended===app.style['--left-weight'],'lost capture stops split');
bar.dispatch('pointerdown',3,550);bar.dispatch('pointermove',3,870);flush();win.dispatch('blur');
check(!classes.has('resizing-columns'),'window blur clears split visual state');
width=901;ctx.innerWidth=901;check(ctx.refitColumns(),'narrow desktop refit scheduled');flush();
check((width-72)*(1-parseFloat(app.style['--left-weight'])/100)>=379.99,'resize enforces right pane minimum width');
ctx.innerWidth=390;check(!ctx.refitColumns(),'mobile does not clamp stacked layout');
check(!classes.has('resizing-columns'),'mobile transition stops active drag');
// Production graph drag handlers, isolated from controls unrelated to this event boundary.
ctx.$=s=>s==='#net'?net:null;ctx.updateOverview=()=>{};
const begin=src.indexOf("    var net=$('#net');if(net){\n      net.addEventListener('scroll',updateOverview);var drag=null;");
assert.ok(begin>=0,'production pan block missing');
const end=src.indexOf("    var all=$('#graph-all');",begin);
vm.runInContext(src.slice(begin,end),ctx);
net.dispatch('pointerdown',10,100,100);net.dispatch('pointermove',10,120,110);
check(net.scrollLeft===280&&net.scrollTop===190,'first finger pans from its own baseline');
net.dispatch('pointerdown',11,300,300);net.dispatch('pointermove',11,320,320);
check(net.scrollLeft===280&&net.scrollTop===190,'second finger cannot jump graph');
net.dispatch('pointerup',11);net.dispatch('pointermove',10,140,120);
check(net.scrollLeft===260&&net.scrollTop===180,'other finger release preserves active pan');
net.dispatch('lostpointercapture',10);net.dispatch('pointermove',10,160,130);
check(net.scrollLeft===260&&net.scrollTop===180,'lost capture stops pan');
net.dispatch('pointerdown',12,100,100);win.dispatch('resize');net.dispatch('pointermove',12,200,200);
check(net.scrollLeft===260,'resize ends active pan');
net.dispatch('pointerdown',13,100,100);win.dispatch('blur');net.dispatch('pointermove',13,200,200);
check(net.scrollLeft===260,'blur ends active pan');
console.log('viewport event boundaries: '+checks+' assertions PASS');
