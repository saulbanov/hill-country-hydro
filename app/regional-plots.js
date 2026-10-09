'use strict';
// Aligned watershed plots and the full-record history view. Display only: values, ranks and summaries are
// computed offline in hydro (tools/regional_history.py); nothing here reinterprets a provider field.
const HOUR=3600000,DAY=86400000,PALETTE=['#176a74','#b36234','#5b4a8a','#8a6d1a','#2f6f3e','#9c3f5d'];
const ct=(t,o)=>new Date(t).toLocaleString('en-US',Object.assign({timeZone:'America/Chicago'},o));
const shortName=s=>String(s).replace(', TX','').replace(/^Llano Rv /,'Llano ').replace(/^Pedernales Rv /,'Pedernales ').replace('Lake ','');
let historyIndex=null,geology=null,hist={key:null,doc:null,series:0,from:null,to:null,date:null,baseline:'fixed'};

/* ---------- four records, one window ---------- */
function plotWindow(){return mode==='storm'?[Date.parse(data.storm.daily_start+'T00:00:00Z'),Date.parse(data.storm.through)]:[Date.parse(data.seasonal.start+'T00:00:00Z'),Date.parse(data.seasonal.date+'T23:59:59Z')];}
function pointTime(at){return at.length===10?Date.parse(at+'T12:00:00Z'):Date.parse(at);}
function inBasin(x){return basin==='all'||x.basin===basin;}
function lanes(){
  const [lo,hi]=plotWindow(),inside=p=>p.t>=lo&&p.t<=hi,out=[];
  const pts=(arr)=>arr.map(p=>({t:pointTime(p.at),v:p.value,dateOnly:p.at.length===10})).filter(inside);
  // rain: separately labelled statistics, one mark per report, never added together
  const rain=data.items.filter(x=>x.kind==='rain'&&inBasin(x)),stat=mode==='storm'?'increments':'daily';
  const rs=rain.filter(x=>x.aligned?.[stat]?.available).map(x=>({name:x.name,id:x.id,points:x.aligned[stat].points.map(p=>({t:pointTime(p[0]),v:p[1],dateOnly:p[0].length===10})).filter(inside),last:x.aligned[stat].last}));
  out.push({kind:'rain',title:'Rain at individual gauges',unit:mode==='storm'?'inches per report':'inches per reported day',marks:'dots',series:rs,
    note:(basin!=='all'&&data.basins[basin]?.grouping?'Rain gauges here are the City of Austin network, grouped by operator and not by a watershed outline. ':'')+(mode==='storm'?`${rs.length} of ${rain.length} gauges have saved native reports in this window. Each dot is one nonzero reported increment at its report time. Interval endpoints are not certified, so nothing is added up; the space between gauges is unmeasured.`:`${rs.length} of ${rain.length} gauges have provider daily totals in this window. Each dot is one gauge-day; the provider's day boundary is unverified and days are not added.`),
    empty:'No rain gauge with a saved report series in this watershed and window.'});
  const rivers=data.items.filter(x=>x.kind==='river'&&inBasin(x));
  out.push({kind:'river',title:'River flow at gauges',unit:mode==='storm'?'cfs, instantaneous (log scale)':'cfs, daily mean (log scale)',marks:'lines',log:true,series:rivers.map(x=>({name:shortName(x.name),id:x.id,points:pts(x.chart[mode])})),
    note:mode==='storm'?'Each line joins one gauge’s saved readings; gaps over one hour stay open. Lines are gauges, not reaches.':'Daily means through September 30, the day before the river pulse.',empty:'No pilot river gauge lies in these subbasins. The Colorado River between the dams is not gauged in this pilot.'});
  const wells=data.items.filter(x=>x.kind==='well'&&inBasin(x));
  const ws=wells.map(x=>{const p=pts(x.chart[mode]).filter(q=>q.v!=null);return {name:x.name,id:x.id,points:p.map(q=>({t:q.t,v:-(q.v-p[0].v),dateOnly:q.dateOnly}))};}).filter(s=>s.points.length>1);
  out.push({kind:'well',title:'Groundwater level at wells',unit:'ft change since each well’s first reading in the window (up = shallower)',marks:'lines',thin:true,series:ws,
    note:`${ws.length} of ${wells.length} inventoried wells have two or more saved readings here. A well reports the level at that well, not aquifer volume. No spring gauge in the saved records lies in these watersheds.`,empty:'No well with two saved readings in this watershed and window. No local spring record exists either.'});
  const target=basin==='all'||basin==='Highland Lakes'?null:data.basins[basin].receiving_reservoir,none=basin!=='all'&&basin!=='Highland Lakes'&&!target;
  const lakes=none?[]:data.items.filter(x=>x.kind==='reservoir'&&(target?x.id===target:true));
  const ls=lakes.map(x=>{const p=pts(x.chart[mode]).filter(q=>q.v!=null);return {name:shortName(x.name),id:x.id,points:p.map(q=>({t:q.t,v:q.v-p[0].v,dateOnly:true}))};}).filter(s=>s.points.length);
  out.push({kind:'reservoir',title:target?`Storage in ${lakes[0]?.name||'the receiving reservoir'}`:'Storage in the Highland Lakes',unit:'acre-ft change since the first report in the window',marks:'steps',series:ls,
    note:(target?`${data.basins[basin].receiving_basis}. `:'')+'Date-only reports drawn at the middle of their date. Storage also changes with releases, withdrawals and other inflows; this is not gauged inflow.',empty:none?'No receiving reservoir is derived for this group: '+data.basins[basin].receiving_basis+'.':'No reservoir storage report in this window.'});
  return out;
}
function lanePlot(lane,lo,hi,W,l,r){
  const narrow=r<100,H=lane.kind==='rain'?120:150,t=12,b=6,x=v=>l+(v-lo)/(hi-lo)*(W-l-r);
  const all=lane.series.flatMap(s=>s.points.filter(p=>p.v!=null).map(p=>p.v));
  if(!all.length)return `<div class="lane"><h3>${esc(lane.title)}</h3><p class="gap">${esc(lane.empty)}</p></div>`;
  let min=Math.min(...all),max=Math.max(...all);
  if(lane.kind==='rain')min=0;if(lane.log){min=Math.max(.1,Math.min(...all.filter(v=>v>0),1e9));max=Math.max(max,min*10);}
  if(min===max){min-=.5;max+=.5;}
  const f=v=>lane.log?Math.log10(Math.max(v,min)):v,y=v=>H-b-(f(v)-f(min))/(f(max)-f(min))*(H-t-b);
  let marks='',labels='',ends=[];
  lane.series.forEach((s,i)=>{const c=lane.thin?'#72648c':lane.kind==='rain'?'#346fa2':PALETTE[i%PALETTE.length],good=s.points.filter(p=>p.v!=null);if(!good.length)return;
    if(lane.marks==='dots')marks+=good.map(p=>`<circle cx="${x(p.t).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="2.2" fill="${c}" fill-opacity=".45"/>`).join('');
    else{let d='',prev=null;const limit=lane.kind==='river'&&mode==='storm'?HOUR:lane.kind==='well'?2*DAY:1.5*DAY;for(const p of s.points){if(p.v==null){prev=null;continue;}d+=`${prev!=null&&p.t-prev<=limit?(lane.marks==='steps'?'L':'L'):'M'}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)} `;prev=p.t;}
      marks+=`<path d="${d}" fill="none" stroke="${c}" stroke-width="${lane.thin?.9:1.7}" stroke-opacity="${lane.thin?.55:1}"/>`;
      if(lane.marks==='steps')marks+=good.map(p=>`<circle cx="${x(p.t).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="2.4" fill="${c}"/>`).join('');}
    const last=good.at(-1);ends.push({name:s.name,t:last.t,dateOnly:last.dateOnly,c,y:y(last.v),v:last.v});
    if(!lane.thin&&lane.kind!=='rain')marks+=`<path d="M${x(last.t).toFixed(1)},${(y(last.v)-5).toFixed(1)}v10" stroke="${c}" stroke-width="1.5"/>`;});
  if(!lane.thin&&lane.kind!=='rain'&&!narrow){ends.sort((a,b)=>a.y-b.y);let py=-99;for(const e of ends){const ly=Math.max(e.y+3,py+11);py=ly;labels+=`<text x="${(Math.min(x(e.t),W-r)+8).toFixed(1)}" y="${ly.toFixed(1)}" fill="${e.c}" font-weight="600">${esc(e.name)}</text>`;}}
  const ticks=lane.log?[.1,1,10,100,1000,10000,100000].filter(v=>v>=min&&v<=max):[min,max];
  const axis=ticks.map(v=>`<text x="${l-6}" y="${(y(v)+3).toFixed(1)}" text-anchor="end">${num(v)}</text><path d="M${l},${y(v).toFixed(1)}H${W-r}" stroke="#d9dfd3" stroke-width=".6"/>`).join('');
  const lastAll=lane.series.flatMap(s=>s.points.filter(p=>p.v!=null)).reduce((m,p)=>Math.max(m,p.t),0);
  const endNote=lane.thin||lane.kind==='rain'?`Latest saved reading in this panel: ${ct(lastAll,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})} CT.`:'Last saved reading — '+ends.map(e=>`${esc(e.name)}: ${e.dateOnly?ct(e.t,{month:'short',day:'numeric'})+' (date only)':ct(e.t,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})+' CT'}`).join('; ')+'.';
  const legend=narrow&&!lane.thin&&lane.kind!=='rain'?`<p class="lane-legend">${ends.map(e=>`<span><i style="background:${e.c}"></i>${esc(e.name)}</span>`).join('')}</p>`:'';
  return `<div class="lane"><h3>${esc(lane.title)} <small>${esc(lane.unit)}</small></h3><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(lane.title)}; ${esc(lane.unit)}">${axis}${marks}${labels}</svg>${legend}<p class="meta">${esc(lane.note)} ${endNote}</p></div>`;
}
function together(){
  const el=$('#together-plots');if(!el||!data)return;const [lo,hi]=plotWindow(),W=Math.max(300,el.clientWidth-30),l=W<560?46:64,r=W<560?12:150;
  const step=mode==='storm'?DAY:7*DAY,ticks=[];for(let t=Math.ceil(lo/DAY)*DAY+5*HOUR;t<=hi;t+=step)ticks.push(t);
  const axis=`<svg class="time-axis" viewBox="0 0 ${W} 22" aria-hidden="true">${ticks.map(t=>{const px=l+(t-lo)/(hi-lo)*(W-l-r);return `<path d="M${px.toFixed(1)},0v6" stroke="#52686b"/><text x="${px.toFixed(1)}" y="18" text-anchor="middle">${ct(t,{month:'short',day:'numeric'})}</text>`;}).join('')}</svg>`;
  $('#together-title').textContent=(basin==='all'?'Whole pilot':basin)+' · '+(mode==='storm'?'the storm window':'September 2026');
  $('#together-window').textContent=`Shared time axis: ${ct(lo,{month:'short',day:'numeric',hour:'numeric'})} to ${ct(hi,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})} Central. Each panel keeps its own units and statistic. Records end at different times; the end of a line is the end of the saved record, not the end of the water.`;
  el.innerHTML=lanes().map(x=>lanePlot(x,lo,hi,W,l,r)).join('')+axis+'<div class="cursor" hidden></div><p class="cursor-time meta" aria-live="off"></p>';
  const cursor=el.querySelector('.cursor'),label=el.querySelector('.cursor-time');
  el.onmousemove=e=>{const box=el.querySelector('.time-axis').getBoundingClientRect(),host=el.getBoundingClientRect(),fx=(e.clientX-box.left)/box.width*W;if(fx<l||fx>W-r){cursor.hidden=true;label.textContent='';return;}cursor.hidden=false;cursor.style.left=(e.clientX-host.left)+'px';label.textContent='Cursor: '+ct(lo+(fx-l)/(W-l-r)*(hi-lo),{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})+' CT. Similar timing across panels does not establish recharge, connection or cause.';};
  el.onmouseleave=()=>{cursor.hidden=true;label.textContent='';};
}

/* ---------- this storm against earlier floods ---------- */
let floods=null;
function floodChart(g){
  const W=420,H=170,l=52,r=10,t=12,b=22,rows=g.annual_peaks.filter(p=>p[1]!=null),storm=g.storm_reading?.value;
  const years=rows.map(p=>+p[0].slice(0,4)),y0=Math.min(...years),y1=Math.max(...years,2026),vals=rows.map(p=>p[1]).concat(storm?[storm]:[]);
  const min=Math.max(1,Math.min(...vals.filter(v=>v>0))),max=Math.max(...vals),f=v=>Math.log10(Math.max(v,min)),x=yr=>l+(yr-y0)/(y1-y0||1)*(W-l-r),y=v=>H-b-(f(v)-f(min))/((f(max)-f(min))||1)*(H-t-b);
  const sticks=rows.map(p=>`<path d="M${x(+p[0].slice(0,4)).toFixed(1)},${H-b}V${y(p[1]).toFixed(1)}" stroke="${p[2].length?'#7fa7ab':'#176a74'}" stroke-width="1.6"><title>${p[0]}: ${num(p[1])} cfs${p[2].length?' · code '+p[2].join(','):''}</title></path>`).join('');
  const ticks=[1,10,100,1000,10000,100000,1000000].filter(v=>v>=min&&v<=max).map(v=>`<text x="${l-5}" y="${(y(v)+3).toFixed(1)}" text-anchor="end">${num(v)}</text><path d="M${l},${y(v).toFixed(1)}H${W-r}" stroke="#d9dfd3" stroke-width=".6"/>`).join('');
  const yrs=[[y0,'start'],[Math.round((y0+y1)/20)*10,'middle'],[y1,'end']].map(([v,k])=>`<text x="${x(v).toFixed(1)}" y="${H-6}" text-anchor="${k}">${v}</text>`).join('');
  const line=storm?`<path d="M${l},${y(storm).toFixed(1)}H${W-r}" stroke="#b36234" stroke-width="1.4" stroke-dasharray="5 3"/><text x="${l+4}" y="${(y(storm)-5).toFixed(1)}" fill="#8a4a22" font-weight="600" style="paint-order:stroke;stroke:#fffdf6;stroke-width:3px">this storm: ${num(storm)} cfs</text>`:'';
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Published annual peaks at this gauge with this storm’s largest saved reading">${ticks}${sticks}${line}${yrs}</svg>`;
}
function renderFloods(){
  const el=$('#flood-cards');if(!el)return;$('#floods').hidden=!floods;if(!floods)return;
  const list=Object.entries(floods.gauges).filter(([,g])=>basin==='all'||g.basin===basin);
  if(!list.length){el.innerHTML='<p class="gap">No pilot river gauge lies in these subbasins, so there is no flood record to compare here.</p>';return;}
  el.innerHTML=list.map(([id,g])=>{const p=g.placement,sr=g.storm_reading,codes=[...new Set(g.annual_peaks.flatMap(x=>x[2]))];
    const lead=p.available?`<p class="flood-lead"><b>${num(p.larger)} of ${num(p.published_peaks)}</b> published annual peaks here (${p.first_year}–${p.last_year}) were larger than this storm’s largest saved reading, <b>${num(sr.value)} cfs</b> on ${esc(when(sr.at))}. The largest published peak is ${num(p.largest_published)} cfs.</p>`:`<p class="gap">${esc(p.reason)}</p>`;
    const ev=g.daily_events.available?`<details><summary>Ten largest daily means in this gauge’s record</summary><p class="meta">${esc(g.daily_events.rule)}. Record ${esc(g.daily_events.first)} to ${esc(g.daily_events.last)}. This storm’s daily means are ${esc(g.storm_daily_means)}.</p><div class="table-wrap"><table class="slim"><thead><tr><th>Date</th><th>Daily mean</th><th>Three days before</th><th>Days at or above half the peak, after</th></tr></thead><tbody>${g.daily_events.events.map(e=>`<tr><td>${esc(e.date)}</td><td>${num(e.daily_mean_cfs)} cfs</td><td>${e.three_days_before_cfs==null?'no value':num(e.three_days_before_cfs)+' cfs'}</td><td>${e.days_at_or_above_half_peak_after==null?'gap in record':e.days_at_or_above_half_peak_after}</td></tr>`).join('')}</tbody></table></div></details>`:'';
    return `<article class="flood"><h3>${esc(g.name.replace(', TX',''))}</h3>${lead}${floodChart(g)}<p class="meta">One stick per water year: the instantaneous annual peak USGS published.${codes.length?' Lighter sticks carry a USGS code: '+codes.map(c=>`${esc(c)} = ${esc(g.code_meanings.peak_cd[c]||'see source')}`).join('; ')+'.':''} The storm’s true peak can exceed its largest saved reading, and USGS has not yet published this water year’s peak. <a href="${esc(g.annual_source.url)}" target="_blank" rel="noopener">USGS peak file ↗</a></p>${ev}</article>`;}).join('')+
    `<p class="meta flood-foot">${Object.entries(floods.pair_lags).map(([k,v])=>{const [a,b]=k.split('>'),m=v.filter(x=>x.lag_days!=null);return `${esc(shortName(floods.gauges[b].name))}: ${m.length} of its ${v.length} largest daily-mean events have one matching event at ${esc(shortName(floods.gauges[a].name))} within three days; the downstream peak date minus the upstream one was ${[...new Set(m.map(x=>x.lag_days))].sort((p,q)=>p-q).join(', ')} days.`;}).join(' ')} Dates only: daily values cannot resolve hours. ${floods.limits.map(esc).join(' ')}</p>`;
}

/* ---------- the long record ---------- */
const dayIndex=(start,iso)=>Math.round((Date.parse(iso+'T00:00:00Z')-Date.parse(start+'T00:00:00Z'))/DAY);
const isoAt=(start,i)=>new Date(Date.parse(start+'T00:00:00Z')+i*DAY).toISOString().slice(0,10);
function seriesPoints(s){if(s.encoding==='dense')return s.values.map((v,i)=>v==null?null:[Date.parse(s.start+'T00:00:00Z')+i*DAY,v]).filter(Boolean);return (s.points||[]).map(p=>[p[0].length===10?Date.parse(p[0]+'T00:00:00Z'):Date.parse(p[0]),p[1]]);}
// zero_default is a lossless packing: measured zeros are implied, missing days are listed as runs
function expandSeries(s){if(s.encoding!=='zero_default')return;const v=new Array(s.length).fill(0);for(const [i,x] of s.nonzero)v[i]=x;for(const [a,b] of s.missing_runs)for(let i=a;i<=b;i++)v[i]=null;s.values=v;s.encoding='dense';}
function bandColor(p){return p==null?'#e4e6dc':p<10?'#9a5a2c':p<25?'#d2a36f':p<=75?'#b9d3cd':p<=90?'#5b93b8':'#234f86';}
function historyChart(){
  const s=hist.doc.series[hist.series],W=Math.max(300,$('#h-chart').clientWidth-26),H=250,l=W<560?46:64,r=16,t=14,b=26,lo=Date.UTC(hist.from,0,1),hi=Date.UTC(hist.to+1,0,1)-DAY;
  const pts=seriesPoints(s).filter(p=>p[0]>=lo&&p[0]<=hi+DAY);
  if(!pts.length)return `<p class="gap">No preserved value for this series between ${hist.from} and ${hist.to}. An empty range is shown as empty.</p>`;
  const log=s.quantity==='discharge',inverted=s.quantity==='groundwater_depth',vals=pts.map(p=>p[1]);
  let min=Math.min(...vals),max=Math.max(...vals);if(s.quantity==='rain'||s.quantity==='storage'||s.quantity==='percent_full')min=Math.min(0,min);
  if(log){min=Math.max(.01,Math.min(...vals.filter(v=>v>0),1e9));max=Math.max(max,min*10);}if(min===max){min-=.5;max+=.5;}
  const f=v=>log?Math.log10(Math.max(v,min)):v,x=tm=>l+(tm-lo)/(hi+DAY-lo)*(W-l-r),y=v=>{const k=(f(v)-f(min))/(f(max)-f(min));return inverted?t+k*(H-t-b):H-b-k*(H-t-b);};
  // per-pixel-column envelope: the drawing is thinned to the screen, the values are not changed
  const cols=new Map();for(const [tm,v] of pts){const c=Math.round(x(tm));const e=cols.get(c);if(!e)cols.set(c,[v,v,tm,tm]);else{e[0]=Math.min(e[0],v);e[1]=Math.max(e[1],v);e[3]=tm;}}
  const dense=s.encoding==='dense',gapLimit=Math.max(2*DAY,(hi-lo)/(W-l-r)*2.5);let d='',marks='',prev=null;
  for(const [c,e] of [...cols].sort((a,b)=>a[0]-b[0])){if(dense){d+=`${prev!=null&&e[2]-prev<=gapLimit?'L':'M'}${c},${y(e[0]).toFixed(1)} L${c},${y(e[1]).toFixed(1)} `;prev=e[3];}else marks+=`<path d="M${c},${y(e[0]).toFixed(1)}V${(y(e[1])+.01).toFixed(1)}" stroke="#176a74" stroke-width="2.4" stroke-linecap="round"/>`;}
  if(s.quantity==='rain'){d='';marks=[...cols].map(([c,e])=>`<path d="M${c},${y(0).toFixed(1)}V${y(e[1]).toFixed(1)}" stroke="#346fa2" stroke-width="1"/>`).join('');}
  const ticks=log?[.01,.1,1,10,100,1000,10000,100000,1000000].filter(v=>v>=min&&v<=max):[min,(min+max)/2,max];
  let g=ticks.map(v=>`<text x="${l-6}" y="${(y(v)+3).toFixed(1)}" text-anchor="end">${num(v)}</text><path d="M${l},${y(v).toFixed(1)}H${W-r}" stroke="#d9dfd3" stroke-width=".6"/>`).join('');
  const span=hist.to-hist.from+1,tight=W<560?2:1,every=span>80/tight?20:span>40/tight?10:span>16/tight?5:span>6/tight?2:1;for(let yr=hist.from;yr<=hist.to+1;yr++){if(yr%every)continue;const px=x(Date.UTC(yr,0,1));if(px>W-r)continue;g+=`<path d="M${px.toFixed(1)},${H-b}v5" stroke="#52686b"/><text x="${px.toFixed(1)}" y="${H-8}" text-anchor="middle">${yr}</text>`;}
  let strip='';const ranked=hist.baseline==='fixed'&&s.percentile;
  if(ranked){const best=new Map();const i0=Math.max(0,dayIndex(s.start,new Date(lo).toISOString().slice(0,10))),i1=Math.min(s.values.length-1,dayIndex(s.start,new Date(hi).toISOString().slice(0,10)));for(let i=i0;i<=i1;i++){if(s.values[i]==null)continue;if(s.percentile[i]==null)continue;const c=Math.round(x(Date.parse(s.start+'T00:00:00Z')+i*DAY));if(!best.has(c))best.set(c,[]);best.get(c).push(s.percentile[i]);}
    strip=[...best].map(([c,e])=>{e.sort((a,b)=>a-b);return `<rect x="${c-.5}" y="${H+3}" width="1.2" height="9" fill="${bandColor(e[Math.floor(e.length/2)])}"/>`;}).join('');
    const [ra,rb]=hist.doc.baseline.reference_years,xa=Math.max(l,x(Date.UTC(ra,0,1))),xb=Math.min(W-r,x(Date.UTC(rb+1,0,1)));if(xb>xa)g+=`<path d="M${xa.toFixed(1)},${t-4}H${xb.toFixed(1)}" stroke="#b36234" stroke-width="2"/><text x="${((xa+xb)/2).toFixed(1)}" y="${t-7}" text-anchor="middle" fill="#8a4a22">baseline era ${ra}–${rb}</text>`;}
  let pick='';if(hist.date){const px=x(Date.parse(hist.date+'T00:00:00Z'));if(px>=l&&px<=W-r)pick=`<path d="M${px.toFixed(1)},${t}V${H-b}" stroke="#b36234" stroke-dasharray="3 3"/>`;}
  let eras='';for(const e of (s.continuity.capacity_eras||[]).slice(1)){const px=x(Date.parse(e.from+'T00:00:00Z'));if(px>=l&&px<=W-r)eras+=`<path d="M${px.toFixed(1)},${t}V${H-b}" stroke="#8a6d1a" stroke-width=".8"/><text x="${(px+3).toFixed(1)}" y="${t+9}" fill="#8a6d1a">capacity value changes</text>`;}
  return `<svg class="h-svg" viewBox="0 0 ${W} ${H+(ranked?16:0)}" role="img" aria-label="${esc(s.label)}, ${hist.from} to ${hist.to}">${g}${eras}<path d="${d}" fill="none" stroke="#176a74" stroke-width="1"/>${marks}${strip}${pick}</svg><p class="meta">${esc(s.label)} · ${esc(s.unit)}${log?' · log scale; zero flow is drawn at the axis floor':''}${inverted?' · axis inverted: higher on the chart is a shallower water level':''}. Drawn as the lowest-to-highest value in each screen column; gaps longer than the drawing resolution stay open. ${s.subsample?esc(s.subsample):''}${ranked?' Colored strip under the years: the middle fixed-baseline percentile among the days in each screen column (brown below the 10th and 25th, pale 25th–75th, blue above the 75th and 90th). Show fewer years for a day-by-day strip.':''}</p>`;
}
function historyCoverage(){
  const s=hist.doc.series[hist.series],by=s.continuity.by_year||{},leap=y=>y%4===0&&(y%100!==0||y%400===0),cells=[];
  for(let y=hist.from;y<=hist.to;y++){const n=by[y]||0,frac=n/(leap(y)?366:365);cells.push(`<span class="yr${n?'':' none'}" style="${n?`background:rgba(23,106,116,${(.15+.85*Math.min(1,frac)).toFixed(2)})`:''}" title="${y}: ${n} days with values"></span>`);}
  const missing=(s.continuity.missing_years||[]).filter(y=>y>=hist.from&&y<=hist.to),net=historyIndex.stations_reporting_by_year[hist.doc.kind]||{};
  const counts=[hist.from,Math.round((hist.from+hist.to)/2),hist.to].map(y=>`${y}: ${net[y]||0}`).join(' · ');
  return `<div class="coverage" aria-label="Days with values in each year">${cells.join('')}</div><p class="meta">One cell per year, ${hist.from}–${hist.to}; darker means more days with a preserved value, hollow means none. ${missing.length?`Years with no value in this range: ${missing.join(', ')}.`:'No year in this range is empty.'} Mapped ${esc(hist.doc.kind)} stations with any value — ${counts}. ${esc(historyIndex.network_note)}</p>`;
}
function historyRead(){
  const s=hist.doc.series[hist.series],d=hist.date;if(!d)return '';let v=null,p=null,at=d;
  if(s.encoding==='dense'){const i=dayIndex(s.start,d);if(i>=0&&i<s.values.length){v=s.values[i];p=s.percentile?s.percentile[i]:null;}}
  else{const hit=(s.points||[]).filter(q=>q[0].slice(0,10)===d);if(hit.length){v=hit.at(-1)[1];at=hit.at(-1)[0];}}
  const [ra,rb]=hist.doc.baseline.reference_years,yr=+d.slice(0,4),prov=(s.not_approved_runs||[]).some(r=>d>=r[0]&&d<=r[1]);
  const era=yr<ra?'This date is before the baseline era. The percentile says where this day would fall among 2006–2025 days at the same gauge and season; measurement and management continuity between the eras is not certified.':yr>rb?'Ranked against the fixed prior reference.':`This date is inside the baseline era, so all of ${yr} is left out of its reference; it is ranked against the other reference years.`;
  let rank='';if(s.percentile){rank=hist.baseline==='none'?'<p class="meta">Comparison baseline is off. Values only.</p>':v==null?'':p==null?'<p class="note">No percentile: the fixed baseline lacks enough Approved daily means around this calendar date (five qualifying years and 80% coverage are required).</p>':`<div class="metrics"><span><b>${num(p)}th</b>Percentile in the fixed baseline</span><span><b>${ra}–${rb}</b>Same gauge, ±${hist.doc.baseline.half_window_days} calendar days</span></div><p class="note">${era}</p>`;}
  else rank='<p class="meta">No daily percentile exists for this kind of record. The baseline applies to daily mean discharge only.</p>';
  return `<p class="eyebrow">READING FOR ${esc(d)}</p>${v==null?'<p class="detail-value unavailable-big">No preserved value</p><p class="note">Nothing is recorded for this series on this date. The nearest or latest reading is not substituted.</p>':`<p class="detail-value">${num(v)} <small>${esc(s.unit)} · ${esc(s.statistic.replaceAll('_',' '))}${at.length>10?' · '+esc(when(at)):''}${prov?' · not yet Approved':''}</small></p>${rank}`}`;
}
function historyContinuity(){
  const s=hist.doc.series[hist.series],c=s.continuity,src=s.source_ids.map(id=>hist.doc.sources[id]).filter(Boolean);
  const yrs=s.years?`<p>Yearly summaries use ${esc(s.years.input_statistic.replaceAll('_',' '))} values and require ${Math.round(s.years.coverage_threshold*100)}% of a year’s days. ${s.years.periods.filter(p=>p.complete).length} of ${s.years.periods.length} years qualify. ${esc(s.years.rain_note||'')}</p>`:'<p>No yearly summary: point readings are not turned into daily or yearly statistics.</p>';
  return `<summary>Span, gaps, continuity and sources for this series</summary><p><b>${esc(c.first)} to ${esc(c.last)}</b> · ${num(c.days_with_values)} days with values${c.day_coverage!=null?` (${Math.round(c.day_coverage*100)}% of the span)`:''} · ${num(c.unavailable)} unavailable records · approval: ${esc(JSON.stringify(s.approval))}.</p>${c.gaps?.length?`<p>Longest gaps: ${c.gaps.slice(0,5).map(g=>`${esc(g.after)} → ${esc(g.before)} (${num(g.missing_days)} days)`).join('; ')}. ${esc(c.gap_meaning)}.</p>`:''}${c.capacity_eras?`<p>Stated conservation capacity: ${c.capacity_eras.map(e=>`${num(e.conservation_capacity_af)} acre-ft from ${esc(e.from)}`).join('; ')}.</p>`:''}<p><b>Known:</b> ${esc((c.continuity?.known||[]).join('; ')||'nothing certified')}.<br><b>Unknown:</b> ${esc((c.continuity?.unknown||[]).join('; '))}.</p>${yrs}${s.stamp_clock_utc?`<p>The provider stamps each daily value at ${esc(Object.keys(s.stamp_clock_utc).join(' or '))} UTC, which is midnight Central. Which 24 hours each total covers is not certified; values are placed on the stamp’s UTC date.</p>`:''}<p>Series ${esc(s.id)}. ${src.map(x=>`Capture ${esc(x.sha256.slice(0,12))}… retrieved ${esc(when(x.retrieved_at))}${x.url?` · <a target="_blank" rel="noopener" href="${esc(x.url)}">official request ↗</a>`:''}`).join('<br>')}</p><p>${esc(hist.doc.trace)}</p>`;
}
function renderHistory(){
  if(!hist.doc)return;const s=hist.doc.series[hist.series];
  $('#h-series').innerHTML=hist.doc.series.map((x,i)=>`<option value="${i}"${i===hist.series?' selected':''}>${esc(x.label)}</option>`).join('');
  $('#h-from').value=hist.from;$('#h-to').value=hist.to;$('#h-date').value=hist.date||'';$('#h-date').min=s.continuity.first;$('#h-date').max=hist.doc.cutoff.slice(0,10);
  $('#h-baseline').disabled=!s.percentile;$('#h-baseline-note').textContent=s.percentile?`Usual is fixed. A day is compared with this gauge’s Approved daily means within ${hist.doc.baseline.half_window_days} calendar days of the same date in ${hist.doc.baseline.reference_years.join('–')}. A day inside those years is compared with the other nineteen. A day before them is compared with the same years and labelled. Changing the years shown never changes this.`:'The seasonal baseline applies to daily mean discharge only. This record is shown as values.';
  $('#h-swim').innerHTML=swimLink(hist.key);$('#h-chart').innerHTML=historyChart();$('#h-coverage').innerHTML=historyCoverage();$('#h-read').innerHTML=historyRead();$('#h-continuity').innerHTML=historyContinuity();
}
async function openHistory(key,scroll){
  const entry=historyIndex?.stations[key];if(!entry)return;$('#h-station').value=key;hist.want=key; // the last station asked for wins; a slower earlier fetch is dropped
  if(!entry.file){hist.doc=null;$('#h-chart').innerHTML=`<p class="gap">${esc(entry.name)}: ${esc(entry.reason)}</p>`;$('#h-coverage').innerHTML=$('#h-read').innerHTML=$('#h-continuity').innerHTML='';return;}
  $('#h-chart').innerHTML='<p class="gap">Loading this station’s record…</p>';
  let doc;try{const r=await fetch(entry.file,{cache:'no-cache'});if(!r.ok)throw Error('missing file');doc=await r.json();}catch(e){if(hist.want===key)$('#h-chart').innerHTML='<p class="gap">This station’s history file could not load.</p>';return;}
  if(hist.want!==key)return;hist.doc=doc;hist.doc.series.forEach(expandSeries);
  hist.key=key;hist.series=0;const c=hist.doc.series[0].continuity;hist.from=+c.first.slice(0,4);hist.to=+c.last.slice(0,4);hist.date=hist.doc.series[0].encoding==='dense'?c.last:null;renderHistory();
  if(scroll)$('#history').scrollIntoView({behavior:'smooth',block:'start'});
}
function initHistory(){
  if(!historyIndex){$('#history').hidden=true;return;}
  const groups={river:'Rivers',reservoir:'Reservoirs',well:'Wells',rain:'Rain gauges',spring:'Springs outside the pilot watersheds'};
  $('#h-station').innerHTML=Object.entries(groups).map(([k,label])=>`<optgroup label="${label}">${Object.entries(historyIndex.stations).filter(([,v])=>v.kind===k).sort((a,b)=>a[1].name.localeCompare(b[1].name)).map(([id,v])=>`<option value="${esc(id)}">${esc(v.name)}${v.file?` · ${v.series[0].first.slice(0,4)}–${v.series[0].last.slice(0,4)}`:' · no usable history'}</option>`).join('')}</optgroup>`).join('');
  $('#h-station').onchange=e=>selectStation(e.target.value);$('#h-series').onchange=e=>{hist.series=+e.target.value;const c=hist.doc.series[hist.series].continuity;hist.from=+c.first.slice(0,4);hist.to=+c.last.slice(0,4);renderHistory();};
  const clamp=()=>{const c=hist.doc.series[hist.series].continuity,a=+c.first.slice(0,4),b=+c.last.slice(0,4);hist.from=Math.min(Math.max(+$('#h-from').value||a,a),b);hist.to=Math.max(Math.min(+$('#h-to').value||b,b),hist.from);renderHistory();};
  $('#h-from').onchange=clamp;$('#h-to').onchange=clamp;$('#h-date').onchange=e=>{hist.date=e.target.value||null;renderHistory();};$('#h-baseline').onchange=e=>{hist.baseline=e.target.value;renderHistory();};
  document.querySelectorAll('[data-range]').forEach(b=>b.onclick=()=>{if(!hist.doc)return;const c=hist.doc.series[hist.series].continuity,a=+c.first.slice(0,4),z=+c.last.slice(0,4);hist.to=z;hist.from=b.dataset.range==='all'?a:b.dataset.range==='2006'?Math.max(a,2006):Math.max(a,z-4);renderHistory();});
  station='USGS:08151500';openHistory(station);
}
/* ---------- underground context: mapped interpretation, never measurement ---------- */
const AQ={'Edwards-Trinity (Plateau)':'#a98bcb','Trinity':'#7d6fb5','Edwards (Balcones Fault Zone)':'#4f63a8','Hickory':'#c47a3d','Ellenburger-San Saba':'#cfa63a','Marble Falls':'#9c4f76'};
const PERIOD={Precambrian:'#c98a8a',Cambrian:'#c9a36b',Ordovician:'#d9c46a',Mississippian:'#9db4a0',Pennsylvanian:'#8aa9b8',Permian:'#b99ab5',Cretaceous:'#a9c58f',Tertiary:'#e0cf9c',Quaternary:'#efe6b5',water:'#bcd6e0'};
const GEO={aquifers:{file:'regional-aquifers.geojson',layer:null,style:f=>{const c=AQ[f.properties.aquifer]||'#888',out=f.properties.extent==='outcrop';return {stroke:false,fillColor:c,fillOpacity:out?.5:.16};},tip:f=>`${f.properties.aquifer} aquifer · ${f.properties.extent==='outcrop'?'outcrop':'subsurface extent'} · TWDB mapped interpretation`},
  faults:{file:'regional-faults.geojson',layer:null,style:f=>({color:'#7a2e2e',weight:1,opacity:.8,dashArray:/Inferred|Concealed|Unspecified/.test(f.properties.fault_type)?'3 3':null}),tip:f=>`Mapped fault · ${f.properties.fault_type} · Geologic Atlas of Texas`},
  surface:{file:'regional-surface-geology.geojson',layer:null,style:f=>({color:'#8b8b7a',weight:.3,fillColor:PERIOD[f.properties.period]||'#ccc',fillOpacity:.5}),tip:f=>`${f.properties.unit} · ${f.properties.period} · surface rock, Geologic Atlas of Texas ${f.properties.sheet} sheet`}};
function interval(w){return w.screen_or_open_intervals.length?w.screen_or_open_intervals.map(i=>`${esc(i.type.toLowerCase())} ${num(i.top_ft)}–${num(i.bottom_ft)} ft`).join('; '):esc(w.interval_status);}
function wellEvidence(item){const w=geology?.wells?.[item.id];if(!w)return '';const u=w.surface_unit;return `<p class="note geo-note"><b>TWDB Groundwater Database.</b> Aquifer: ${esc(w.gwdb_aquifer_code||w.gwdb_aquifer||'not recorded')} (${esc(w.aquifer_assignment.agreement)} as the measurement feed; pick method ${esc(w.aquifer_assignment.pick_method)}). Well depth: ${w.well_depth_ft==null?'not recorded':num(w.well_depth_ft)+' ft'}. Screen or open interval: ${interval(w)}. ${u?.available?`Rock mapped at the surface here: ${esc(u.unit)} (${esc(u.period)}). That is the surface rock, not the unit this well draws from.`:''}</p>`;}
async function toggleGeo(name,on){const g=GEO[name],map=window.regionalPilot.map;if(!g.layer&&on){const r=await fetch(g.file,{cache:'no-cache'});if(!r.ok)return;const d=await r.json();g.layer=L.geoJSON(d,{pane:'geology',renderer:GEO.renderer,style:g.style,interactive:true,onEachFeature:(f,l)=>l.bindTooltip(esc(g.tip(f)),{sticky:true})});}if(g.layer){on?g.layer.addTo(map):g.layer.remove();}geoLegend();}
function geoLegend(){const on=n=>GEO[n].layer&&window.regionalPilot.map.hasLayer(GEO[n].layer),parts=[];
  if(on('aquifers'))parts.push('<b>Aquifer extents (TWDB):</b> '+Object.entries(AQ).map(([n,c])=>`<span class="sw" style="background:${c}"></span>${esc(n)}`).join(' ')+' · strong color = outcrop, pale = subsurface extent; TWDB draws each aquifer in many pieces, shown here without their seams; clipped to the pilot rectangle');
  if(on('faults'))parts.push('<b>Faults:</b> <span class="fault-key"></span> mapped trace; dashed = inferred, concealed or unspecified');
  if(on('surface'))parts.push('<b>Surface rock by period:</b> '+Object.entries(PERIOD).filter(([n])=>n!=='water').map(([n,c])=>`<span class="sw" style="background:${c}"></span>${n}`).join(' '));
  $('#geo-legend').innerHTML=parts.length?parts.join('<br>')+'<br><small>Mapped geological interpretation at 1:250,000. It is not a measurement, and it does not show where water moves underground.</small>':'';}
/* ---------- one selected station drives the record and the geology panel ---------- */
const KIND={river:['#176a74','Rivers and creeks'],reservoir:['#38767b','Reservoirs'],well:['#72648c','Wells'],rain:['#346fa2','Rain gauges'],spring:['#8a6d1a','Springs']};
let hMap=null,hDots={},station=null,swim={stations:{}};
function swimLink(key){const s=swim.stations?.[key];return s?`<a class="swim-link" href="${esc(swim.swim_map_url+'#'+s.anchor)}" target="_blank" rel="noopener">Swimming places on this gauge: Austin Swim Map ↗</a>`:'';}
function openFromAddress(){const m=/^#([A-Za-z-]+)\.([0-9A-Za-z-]+)$/.exec(location.hash||'');if(!m)return;const key=m[1]+':'+m[2];if(!historyIndex?.stations[key])return;const item=data.items.find(x=>x.id===key);if(item)details(item);selectStation(key,true);}
function stationPoint(key){const c=historyIndex?.stations[key]?.coordinates||data.items.find(x=>x.id===key)?.coordinates;return c&&c[0]!=null&&c[1]!=null?[c[1],c[0]]:null;}
function markStation(){for(const [k,m] of Object.entries(hDots))m.setStyle({weight:k===station?4:1,color:k===station?'#b36234':'#fffdf6'});if(hDots[station])hDots[station].bringToFront();}
function selectStation(key,scroll){station=key;if(historyIndex?.stations[key])openHistory(key,scroll);markStation();renderGeoStation();}
function initStationMap(){
  if(!historyIndex||!window.L)return;const layers=window.regionalPilot.layers;hMap=L.map('h-map',{scrollWheelZoom:false,preferCanvas:true,zoomSnap:.25,zoomDelta:.5}).setView([30.5,-98.9],8); // a view must exist before canvas layers are added
  L.tileLayer('https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}',{maxZoom:16,attribution:'USGS The National Map'}).addTo(hMap);
  L.geoJSON(layers.basins,{style:{color:'#98aa8b',weight:.8,fillColor:'#dbe3c9',fillOpacity:.2},interactive:false}).addTo(hMap);L.geoJSON(layers.channels,{style:{color:'#6f9698',weight:1.4},interactive:false}).addTo(hMap);L.geoJSON(layers.creeks,{style:{color:'#6f9698',weight:1},interactive:false}).addTo(hMap);
  const off=[];for(const k of ['rain','well','reservoir','spring','river'])for(const [key,v] of Object.entries(historyIndex.stations)){if(v.kind!==k||!v.file)continue;const p=stationPoint(key);if(!p){off.push(v.name);continue;}const r=k==='rain'?4:6;const m=L.circleMarker(p,{radius:r,color:'#fffdf6',weight:1,fillColor:KIND[k][0],fillOpacity:.9}).addTo(hMap);m.kindRadius=r;m.bindTooltip(`<b>${esc(v.name)}</b><br>${esc(KIND[k][1])} · ${v.series[0].first.slice(0,4)}–${v.series[0].last.slice(0,4)}`);m.on('click',()=>selectStation(key));hDots[key]=m;}
  hMap.fitBounds(Object.values(hDots).map(m=>m.getLatLng()),{padding:[20,20]});
  $('#h-map-key').innerHTML=Object.values(KIND).map(([c,n])=>`<span class="band"><i style="background:${c};height:10px;width:10px;border-radius:50%"></i>${n}</span>`).join('')+(off.length?` Not on the map, no verified coordinates: ${off.map(esc).join(', ')}. They are in the list.`:'');
}
function wellDiagram(w,level){
  const rows=w.casing_rows.filter(c=>c.top_ft!=null&&c.bottom_ft!=null),lith=w.lithology||[],deep=Math.max(w.well_depth_ft||0,...rows.map(c=>c.bottom_ft),...lith.map(l=>l.bottom_ft||0),level?level.v:0);
  if(!deep)return '<p class="gap">No depth is recorded for this well, so no diagram is drawn.</p>';
  const W=440,H=300,t=18,b=10,cx=250,y=d=>t+d/deep*(H-t-b);let g=`<path d="M40,${t}H${W-10}" stroke="#52686b"/><text x="40" y="${t-5}">land surface</text>`;
  for(const d of [0,.25,.5,.75,1].map(f=>Math.round(deep*f)))g+=`<text x="34" y="${y(d)+3}" text-anchor="end">${num(d)} ft</text><path d="M36,${y(d)}h6" stroke="#52686b"/>`;
  lith.slice(0,14).forEach((l,i)=>{if(l.top_ft==null||l.bottom_ft==null)return;g+=`<rect x="46" y="${y(l.top_ft)}" width="150" height="${Math.max(1,y(l.bottom_ft)-y(l.top_ft))}" fill="${i%2?'#e9e4d2':'#f3efe2'}" stroke="#cfc8b0" stroke-width=".5"><title>${esc(l.description)} (${num(l.top_ft)}–${num(l.bottom_ft)} ft)</title></rect>`;if(y(l.bottom_ft)-y(l.top_ft)>11)g+=`<text x="50" y="${(y(l.top_ft)+y(l.bottom_ft))/2+3}">${esc(l.description.slice(0,30))}</text>`;});
  for(const c of rows){const open=c.type&&c.type.toLowerCase()!=='blank';g+=`<rect x="${cx-14}" y="${y(c.top_ft)}" width="28" height="${Math.max(1,y(c.bottom_ft)-y(c.top_ft))}" fill="${open?'#bfd9e6':'none'}" stroke="${open?'#346fa2':'#444'}" stroke-width="${open?1:2}" ${open?'stroke-dasharray="3 2"':''}><title>${esc(c.type||'casing')} ${num(c.top_ft)}–${num(c.bottom_ft)} ft</title></rect>`;}
  if(w.well_depth_ft)g+=`<path d="M${cx-20},${y(w.well_depth_ft)}h40" stroke="#193d42" stroke-width="2"/><text x="${cx+26}" y="${y(w.well_depth_ft)+3}">well depth ${num(w.well_depth_ft)} ft</text>`;
  for(const c of rows.filter(c=>c.type&&c.type.toLowerCase()!=='blank'))g+=`<text x="${cx+26}" y="${(y(c.top_ft)+y(c.bottom_ft))/2+3}" fill="#346fa2">${esc(c.type.toLowerCase())} ${num(c.top_ft)}–${num(c.bottom_ft)} ft</text>`;
  if(level)g+=`<path d="M${cx-30},${y(level.v)}h60" stroke="#b36234" stroke-width="2"/><text x="${cx+36}" y="${y(level.v)+3}" fill="#8a4a22" font-weight="600">water ${num(level.v)} ft down</text>`;
  return `<svg class="well-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Recorded depths for this well">${g}</svg><p class="meta">Every depth here is a recorded value: the driller’s log bands on the left${lith.length?'':' (none recorded)'}, casing as solid outline, ${rows.some(c=>c.type&&c.type.toLowerCase()!=='blank')?'screen or open hole as a dashed blue box':'no screen or open interval recorded'}, total depth, and the latest saved water level${level?' ('+esc(level.at.slice(0,10))+')':' (none saved)'}. No rock unit is drawn that the log does not name.</p>`;
}
function renderGeoStation(){
  const el=$('#geo-station');if(!el||!geology)return;const key=station||selected,g=geology.stations?.[key],item=data.items.find(x=>x.id===key),name=item?.name||historyIndex?.stations[key]?.name||key;
  if(!key||!g){el.innerHTML=`<div class="geo-here"><p class="eyebrow">AT THE SELECTED STATION</p><p class="gap">${key?esc(name)+(historyIndex?.stations[key]?.coordinates?' is outside the area the geology layers cover, so nothing is looked up for it.':' has no verified coordinates inside the mapped area, so nothing is looked up for it.'):'Select a station on either map to see what is mapped and recorded there.'}</p></div>`;return;}
  const u=g.surface_unit,aq=g.aquifer_extents,w=geology.wells?.[key],basinName=item?.basin||historyIndex?.stations[key]?.basin;
  const levelPoint=item?.kind==='well'?[...(item.chart.seasonal||[])].reverse().find(p=>p.value!=null):null;
  const sec=geology.sections.find(s=>s.applies_to_basins.includes(basinName));
  el.innerHTML=`<div class="geo-here"><p class="eyebrow">AT THE SELECTED STATION</p><h3>${esc(name)}</h3><div class="geo-here-grid"><div><p><b>Rock mapped at the surface:</b> ${u?.available?`${esc(u.unit)} (${esc(u.period)}), ${esc(u.sheet)} sheet of the Geologic Atlas of Texas.`:'not resolved to one mapped unit.'}</p><p><b>Aquifer extents mapped at this point:</b> ${aq.length?aq.map(a=>`${esc(a.aquifer)} (${a.extent==='outcrop'?'outcrop':'subsurface extent'})`).join('; ')+'.':'none of the mapped extents covers this point.'}</p>${w?`<p><b>This well:</b> TWDB assigns it to the ${esc(w.feed_aquifer)} aquifer (${esc(w.gwdb_aquifer_code||'no code')}). Screen or open interval: ${interval(w)}.</p>`:''}<p><b>Published section:</b> ${sec?`${esc(sec.figure)} below crosses the Pedernales River, and this station is in the Pedernales watershed. The section line is not captured as geometry, so its distance from this station is not known.`:'no reproduced section crosses this station’s watershed. Figure 79 below is a region-wide diagram.'}</p><p class="meta">${esc(geology.station_basis)}</p></div><div>${w?wellDiagram(w,levelPoint?{v:levelPoint.value,at:levelPoint.at}:null):''}</div></div></div>`;
}
window.initGeology=async()=>{try{const r=await fetch('regional-geology.json',{cache:'no-cache'});if(!r.ok)throw 0;geology=await r.json();}catch(e){$('#geology').hidden=true;document.querySelector('.geo-toggles').hidden=true;return;}
  const map=window.regionalPilot.map;map.createPane('geology');map.getPane('geology').style.zIndex=350;GEO.renderer=L.canvas({pane:'geology'});
  document.querySelectorAll('[data-geo]').forEach(b=>b.onchange=()=>toggleGeo(b.dataset.geo,b.checked));
  $('#geo-sections').innerHTML=geology.sections.map(s=>`<figure><img src="${esc(s.file)}" alt="${esc(s.figure+': '+s.caption)}" loading="lazy"><figcaption><b>${esc(s.figure)} · ${esc(s.kind)}.</b> ${esc(s.caption)}<br>${esc(s.relevance)}<br><span class="limit">${esc(s.limits)}</span><br><small>${esc(s.credit)} <a href="${esc(s.url)}" target="_blank" rel="noopener">USGS original ↗</a></small></figcaption></figure>`).join('');
  $('#geo-relations').innerHTML='<h3>What the published sources say about the order of the units</h3>'+geology.relationships.map(q=>`<blockquote><b class="subject">${esc(q.subject)}</b>“${esc(q.quote)}”<cite><a href="${esc(q.url)}" target="_blank" rel="noopener">USGS HA 730-E ↗</a></cite></blockquote>`).join('')+'<h3>Sections linked, not reproduced</h3><ul>'+geology.linked_not_reproduced.map(x=>`<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)} ↗</a></li>`).join('')+'</ul>';
  const ws=Object.entries(geology.wells),sum=geology.well_summary;
  $('#geo-wells').innerHTML=`<h3>Which aquifer each pilot well is assigned to, and on what evidence</h3><p class="meta">${ws.length} wells. Screen or open interval documented for ${sum.documented||0}; casing recorded without such an interval for ${sum['casing recorded without a screen or open interval']||0}; no completion rows for ${sum['not documented in the Groundwater Database']||0}. The aquifer is TWDB’s assignment. The last column is the rock mapped at the surface, which is often a different unit.</p><div class="table-wrap"><table><thead><tr><th>Well</th><th>Watershed</th><th>TWDB aquifer</th><th>Depth</th><th>Screen or open interval</th><th>Surface rock at the well</th></tr></thead><tbody>${ws.map(([k,w])=>`<tr><td>${esc(k.split(':')[1])}</td><td>${esc(w.basin||'')}</td><td>${esc(w.feed_aquifer)}</td><td>${w.well_depth_ft==null?'—':num(w.well_depth_ft)+' ft'}</td><td class="${w.screen_or_open_intervals.length?'':'unknown'}">${interval(w)}</td><td>${w.surface_unit?.available?esc(w.surface_unit.unit)+' · '+esc(w.surface_unit.period):'not resolved'}</td></tr>`).join('')}</tbody></table></div>`;
  const cm=geology.aquifer_extents.code_meaning;
  renderGeoStation();
  $('#geo-gaps').innerHTML='<h3>What is not established</h3><ul>'+geology.evidence_gaps.map(g=>`<li>${esc(g)}</li>`).join('')+`<li>Outcrop check: ${esc(cm.summary)}.</li>`+geology.limits.map(g=>`<li>${esc(g)}</li>`).join('')+'</ul>';
};
let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{together();if(hist.doc)renderHistory();},200);});
window.regionalHooks={afterRender:()=>{together();renderFloods();},detailExtra:item=>wellEvidence(item)+(swimLink(item.id)?`<p>${swimLink(item.id)}</p>`:'')+(historyIndex?.stations[item.id]?.file?`<p><button class="open-history" data-history="${esc(item.id)}">Open this station’s full record ↓</button></p>`:''),onSelect:key=>selectStation(key,false),bindDetail:()=>document.querySelectorAll('[data-history]').forEach(b=>b.onclick=()=>selectStation(b.dataset.history,true)),
  afterBoot:async()=>{try{const r=await fetch('history/index.json',{cache:'no-cache'});if(r.ok)historyIndex=await r.json();}catch(e){}try{const r=await fetch('regional-events.json',{cache:'no-cache'});if(r.ok)floods=await r.json();}catch(e){}try{const r=await fetch('swim-map-links.json',{cache:'no-cache'});if(r.ok)swim=await r.json();}catch(e){}initHistory();if(window.initGeology)await window.initGeology();render();initStationMap();markStation();openFromAddress();window.addEventListener('hashchange',openFromAddress);}};
