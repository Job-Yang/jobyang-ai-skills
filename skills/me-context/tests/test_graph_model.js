const assert=require('node:assert/strict'),M=require('../scripts/graph_model.js');
let checks=0;function check(b,msg){assert.ok(b,msg);checks++;}
const e=(a,b,t='knows')=>({from:a,to:b,type:t,label:t});
let g=M.build(['me','spouse','parent','friend','other','island'],[e('me','spouse','spouse_of'),e('me','parent','child_of'),e('me','friend'),e('spouse','friend'),e('friend','other'),e('other','spouse'),e('spouse','friend','works_with'),e('ghost','me'),e('me','me')]);
const c={spouse:'inner',parent:'inner',friend:'close',other:'peripheral',island:'peripheral'};
const initial=M.neighborhood(g,'me',new Set(),false),all=M.neighborhood(g,'me',new Set(),true);
check(initial.size===4,'direct neighborhood');
check(M.neighborhood(g,'friend',new Set(),false).has('me'),'ego remains present in a focused neighborhood');
check(g.edges.length===7,'cross edges and multiple types preserved; phantom/self removed');
check(M.path(g,'me','other').edges.length===2,'shortest recorded relationship chain');
check(M.path(g,'me','island')===null,'disconnected never receives fabricated path');
check(M.visible(g,'me',new Set(['spouse','friend']),false).size===5,'cycles reveal each person once');
const l=M.layout(g,all,'friend',{},700,c);
check(l.positions.get('me').x===l.cx&&l.positions.get('me').y===l.cy,'me fixed at exact center while inspecting friend');
check(l.positions.get('spouse').radius===l.positions.get('parent').radius,'same closeness belongs to same ring');
check(l.positions.get('friend').radius>l.positions.get('parent').radius,'friend physically farther than parent when declared close');
check(l.positions.get('other').radius>l.positions.get('friend').radius,'peripheral outside close');
check(l.positions.size===6,'every person retained in all view');
const capped=M.neighborhood(g,'friend',new Set(),false,{limit:3,circles:c,rank:{}});
check(capped.has('me')&&capped.has('friend'),'initial limit never drops ego or focused person');
check(capped.size===3,'initial number bounded without removing data');
check(M.neighborhood(g,'me',new Set(['me']),false,{limit:2,circles:c}).size===4,'explicit expansion bypasses initial budget');
check(M.neighborhood(g,'me',new Set(),true,{limit:2,circles:c}).size===6,'all view preserves all people regardless of initial budget');
for(const t of ['parent_of','child_of']){check(M.edgeLabel(e('a','b',t),'a')===(t==='parent_of'?'子女':'父母'),'forward kinship');check(M.edgeLabel(e('a','b',t),'b')===(t==='parent_of'?'父母':'子女'),'reverse kinship');}
const invalid=M.layout(g,all,'bad',{},330,c);check(invalid.positions.size===0,'invalid focus guarded');
// Capacity: 180 people across three declared closeness levels, 6-hop chains and cycles.
const ids=['me',...Array.from({length:180},(_,i)=>'p'+i)],edges=[],circles={};
for(let i=0;i<180;i++){if(i<178)edges.push(e(i<30?'me':'p'+(i-30),'p'+i));circles['p'+i]=i<60?'inner':i<120?'close':'peripheral';}
g=M.build(ids,edges);const shown=new Set(ids);
check(M.path(g,'me','p177').edges.length===6,'six hops independent from three circles');
for(const vw of [330,700]){
 const lay=M.layout(g,shown,'me',{},vw,circles),v=[...lay.positions.values()];let overlaps=0;
 for(let i=0;i<v.length;i++)for(let j=i+1;j<v.length;j++)if(Math.abs(v[i].x-v[j].x)<148&&Math.abs(v[i].y-v[j].y)<120)overlaps++;
 check(overlaps===0,'no readable label overlap even with 180 people');
 check(lay.positions.size===181,'capacity retains all records');
 check(lay.rings[0].radius<lay.rings[1].radius&&lay.rings[1].radius<lay.rings[2].radius,'ordered closeness rings');
}
console.log('graph model: '+checks+' assertions PASS');
