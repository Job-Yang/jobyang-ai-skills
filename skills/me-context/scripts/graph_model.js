/* Deterministic relationship model, shared by the offline viewer and tests.
 * No inference: every displayed edge comes from records, circle is not distance.
 */
(function(root){
  'use strict';
  function build(ids, records){
    var known=new Set(ids), edges=[], seen=new Set(), adj=new Map();
    ids.forEach(function(id){adj.set(id,[]);});
    (records||[]).forEach(function(e){
      if(!known.has(e.from)||!known.has(e.to)||e.from===e.to)return;
      var key=e.from+'\u0000'+e.to+'\u0000'+e.type;
      if(seen.has(key))return;seen.add(key);edges.push(e);
      adj.get(e.from).push({id:e.to,edge:e});adj.get(e.to).push({id:e.from,edge:e});
    });
    adj.forEach(function(xs){xs.sort(function(a,b){return a.id.localeCompare(b.id);});});
    return {ids:ids.slice(),edges:edges,adj:adj};
  }
  function path(g,from,to){
    if(!g.adj.has(from)||!g.adj.has(to))return null;
    var prev=new Map([[from,null]]),q=[from],head=0;
    while(head<q.length){var id=q[head++];if(id===to)break;
      g.adj.get(id).forEach(function(n){if(!prev.has(n.id)){prev.set(n.id,{id:id,edge:n.edge});q.push(n.id);}});
    }
    if(!prev.has(to))return null;
    var nodes=[to],edges=[],cur=to;
    while(cur!==from){var p=prev.get(cur);edges.unshift(p.edge);nodes.unshift(p.id);cur=p.id;}
    return {nodes:nodes,edges:edges};
  }
  function visible(g,focus,expanded,all){
    if(all)return new Set(g.ids);
    var out=new Set([focus]);
    if(g.adj.has(focus))g.adj.get(focus).forEach(function(n){out.add(n.id);});
    // Only expansion of a visible node can reveal its neighbors; cycles terminate.
    var pending=new Set(expanded||[]),changed=true;
    while(changed){changed=false;pending.forEach(function(id){if(out.has(id)&&g.adj.has(id)){
      pending.delete(id);g.adj.get(id).forEach(function(n){if(!out.has(n.id)){out.add(n.id);changed=true;}});
    }});}
    return out;
  }
  function layout(g,shown,focus,rank,viewport,circles){
    if(!g.adj.has('me')||!g.adj.has(focus))return {positions:new Map(),columns:new Map(),rings:[],width:380,height:300};
    circles=circles||{};rank=rank||{};
    var bands={inner:[],close:[],peripheral:[]},positions=new Map(),placed=[],rings=[];
    shown.forEach(function(id){if(id!=='me'&&g.adj.has(id)){var c=circles[id];bands[c==='inner'||c==='close'?c:'peripheral'].push(id);}});
    var prevRadius=0,extent=90;
    ['inner','close','peripheral'].forEach(function(c,ci){
      var ids=bands[c];if(!ids.length)return;
      ids.sort(function(a,b){return (rank[a]||0)-(rank[b]||0)||a.localeCompare(b);});
      // Boxes include full-name/relationship label and expansion button, not just avatars.
      // A ring grows with population; no tiny text or extra distance inferred from graph hops.
      var radius=Math.max(ci===0?138:prevRadius+128,ids.length*182/(2*Math.PI));
      var points;
      for(var attempt=0;attempt<32;attempt++){
        points=ids.map(function(id,i){var start=viewport&&viewport<500?-Math.PI/2:-Math.PI*.8;
          var angle=ids.length===1?(viewport&&viewport<500?Math.PI/2+.32:-Math.PI/4):start+ci*.4+2*Math.PI*i/ids.length;
          if(viewport&&viewport<500&&ids.length>=3&&ids.length<=4){
            var spread=Math.asin(Math.min(.7,80/radius));
            var mobileAngles=ids.length===3?[-Math.PI/2,Math.PI/2-spread,Math.PI/2+spread]:[-Math.PI/2-spread,-Math.PI/2+spread,Math.PI/2-spread,Math.PI/2+spread];
            angle=mobileAngles[i];
          }
          return {id:id,x:radius*Math.cos(angle),y:radius*Math.sin(angle),angle:angle};});
        var collisions=false;
        points.forEach(function(p,i){
          if(Math.abs(p.x)<132&&Math.abs(p.y)<108)collisions=true;
          points.slice(i+1).concat(placed).forEach(function(q){if(Math.abs(p.x-q.x)<148&&Math.abs(p.y-q.y)<120)collisions=true;});
        });
        if(!collisions)break;radius+=24;
      }
      points.forEach(function(p){placed.push(p);positions.set(p.id,{x:p.x,y:p.y,radius:radius,circle:c,depth:null});});
      rings.push({circle:c,radius:radius});prevRadius=radius;extent=Math.max(extent,radius+100);
    });
    var size=Math.ceil(extent*2),center=size/2;
    positions.forEach(function(p){p.x+=center;p.y+=center;});
    positions.set('me',{x:center,y:center,radius:0,circle:'me',depth:0});
    return {positions:positions,columns:new Map(),rings:rings,width:size,height:size,cx:center,cy:center};
  }
  function neighborhood(g,focus,expanded,all,options){
    var result=visible(g,focus,expanded,all);result.add('me');
    var p=path(g,'me',focus);if(p)p.nodes.forEach(function(id){result.add(id);});
    if(options&&!all&&!(expanded&&expanded.size)&&result.size>options.limit){
      var required=new Set(p?p.nodes:['me',focus]);required.add('me');
      var priority={inner:0,close:1,peripheral:2},cs=options.circles||{},rk=options.rank||{};
      Array.from(result).sort(function(a,b){return (priority[cs[a]]==null?2:priority[cs[a]])-(priority[cs[b]]==null?2:priority[cs[b]])||(rk[a]||0)-(rk[b]||0)||a.localeCompare(b);}).forEach(function(id){if(required.size<options.limit)required.add(id);});
      result=required;
    }
    return result;
  }
  function edgeLabel(e,from){
    if(e.type==='parent_of')return e.from===from?'子女':'父母';
    if(e.type==='child_of')return e.from===from?'父母':'子女';
    return {spouse_of:'配偶',partner_of:'伴侣',sibling_of:'兄弟姐妹',lives_with:'同住',knows:'认识',works_with:'同事',related_to:'亲属'}[e.type]||'有关联';
  }
  var api={build:build,path:path,visible:visible,layout:layout,neighborhood:neighborhood,edgeLabel:edgeLabel};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.MCGraph=api;
})(typeof globalThis!=='undefined'?globalThis:this);
