/* TiTaN — bridge v2: exact visuals + fully real data (no fakes) */
(() => {
  'use strict';
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));
  function fmtBytes(b){ b=Number(b)||0; if(b===0) return '0 B'; const u=['B','KB','MB','GB','TB']; let i=0; while(b>=1024&&i<u.length-1){b/=1024;i++;} return (i===0?b:b.toFixed(b>=10?1:2).replace(/\.0+$/,''))+' '+u[i]; }
  function esc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c])); }
  function flagFor(cc){ cc=(cc||'').toUpperCase().trim(); if(/^[A-Z]{2}$/.test(cc)) return String.fromCodePoint(...[...cc].map(c=>0x1F1E6+c.charCodeAt(0)-65)); return '🏳️'; }
  function fmtDate(ts){ try{ return new Date(ts*1000).toLocaleDateString('fa-IR'); }catch(e){ return '—'; } }
  async function apiJson(url, opts={}){ opts.credentials='same-origin'; opts.headers=Object.assign({'Content-Type':'application/json'},opts.headers||{}); if(opts.body&&typeof opts.body!=='string') opts.body=JSON.stringify(opts.body); const r=await fetch(url,opts); let d={}; try{d=await r.json();}catch(e){ if(!r.ok) throw new Error(r.statusText); } if(!r.ok) throw new Error(d.detail||d.message||r.statusText); return d; }

  let toastEl=$('#titanToast');
  if(!toastEl){ toastEl=document.createElement('div'); toastEl.id='titanToast'; toastEl.style.cssText='position:fixed;left:50%;bottom:22px;transform:translate(-50%,14px);opacity:0;pointer-events:none;padding:10px 16px;border-radius:12px;color:#eeeaff;background:rgba(6,8,35,.94);border:1px solid rgba(104,77,255,.45);box-shadow:0 0 24px rgba(75,40,255,.18);backdrop-filter:blur(12px);transition:.24s;z-index:9999;font-size:12px;'; document.body.appendChild(toastEl); }
  function toast(m){ toastEl.textContent=m; toastEl.style.opacity='1'; toastEl.style.transform='translate(-50%,0)'; clearTimeout(toastEl._t); toastEl._t=setTimeout(()=>{toastEl.style.opacity='0';toastEl.style.transform='translate(-50%,14px)';},2200); }

  // --- gallery picker (real, as in old panel) ---
  function avatarUrl(key){
    key=key||''; if(key.startsWith('gallery:')) return '/static/img/gallery/'+key.slice(8)+'.svg'; if(key.startsWith('upload:')) return '/api/gallery-image/'+key.slice(7); return '/static/img/titan-avatar.svg';
  }
  async function openGalleryPicker(current=''){
    return new Promise(resolve=>{
      let items=[]; let sel=current||'';
      const overlay=document.createElement('div');
      overlay.style.cssText='position:fixed;inset:0;z-index:10000;background:rgba(2,4,18,.62);backdrop-filter:blur(8px);display:grid;place-items:center;padding:16px;';
      overlay.innerHTML=`<div style="width:min(520px,96vw);background:linear-gradient(145deg,rgba(24,12,56,.96),rgba(8,6,26,.98));border:1px solid rgba(151,116,255,.42);border-radius:18px;overflow:hidden;max-height:90vh;display:flex;flex-direction:column">
        <div style="padding:16px 18px;border-bottom:1px solid rgba(151,116,255,.18);display:flex;justify-content:space-between;align-items:center"><div style="font-weight:700;color:#f2edff">انتخاب تصویر</div><button id="gpClose" style="width:32px;height:32px;border-radius:9px;border:1px solid rgba(151,116,255,.24);background:rgba(91,49,176,.16);color:#d8c7ff;cursor:pointer">×</button></div>
        <div style="padding:16px;overflow:auto;flex:1">
          <button id="gpLogo" style="padding:8px 12px;border-radius:9px;border:1px solid rgba(151,116,255,.24);background:rgba(91,49,176,.12);color:#eee9ff;cursor:pointer;margin-bottom:12px">لوگوی TiTaN</button>
          <div id="gpGrid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px"></div>
          <div style="margin-top:14px;display:flex;gap:8px"><button id="gpUploadBtn" style="padding:8px 12px;border-radius:9px;border:1px solid rgba(151,116,255,.24);background:rgba(91,49,176,.12);color:#eee9ff;cursor:pointer">آپلود عکس</button><input type="file" id="gpFile" accept="image/png,image/jpeg,image/webp" style="display:none"></div>
        </div>
        <div style="padding:14px 18px;border-top:1px solid rgba(151,116,255,.18);display:flex;justify-content:flex-end;gap:10px"><button id="gpCancel" style="padding:10px 14px;border-radius:10px;border:1px solid rgba(151,116,255,.24);background:rgba(91,49,176,.12);color:#eee9ff;cursor:pointer">انصراف</button><button id="gpSave" style="padding:10px 16px;border-radius:10px;border:1px solid rgba(188,157,255,.5);background:linear-gradient(135deg,#7436f5,#4b1bb4);color:#fff;cursor:pointer">ذخیره</button></div>
      </div>`;
      document.body.appendChild(overlay);
      const close=(v)=>{ overlay.remove(); resolve(v); };
      overlay.addEventListener('click',e=>{ if(e.target===overlay) close(null); });
      $('#gpClose',overlay).onclick=()=>close(null);
      $('#gpCancel',overlay).onclick=()=>close(null);
      $('#gpSave',overlay).onclick=()=>close(sel);
      const render=()=>{
        const grid=$('#gpGrid',overlay);
        const logoBtn=$('#gpLogo',overlay);
        logoBtn.style.background = sel==='' ? 'linear-gradient(135deg,#7436f5,#4b1bb4)' : 'rgba(91,49,176,.12)';
        logoBtn.style.color = sel==='' ? '#fff' : '#eee9ff';
        grid.innerHTML = items.length ? items.map(it=>`
          <button data-key="${esc(it.id)}" style="position:relative;height:84px;border-radius:12px;overflow:hidden;border:1px solid ${sel===it.id?'rgba(188,157,255,.7)':'rgba(151,116,255,.18)'};background:rgba(10,20,39,.5);cursor:pointer;display:grid;place-items:center">
            <img src="${esc(it.url)}" style="width:100%;height:100%;object-fit:cover;display:block">
            ${sel===it.id?'<span style="position:absolute;inset:0;border:2px solid #a07bff;border-radius:12px;pointer-events:none"></span>':''}
            ${!it.builtin?'<span data-del="'+esc(it.id)+'" style="position:absolute;top:4px;left:4px;width:20px;height:20px;border-radius:50%;background:rgba(0,0,0,.6);color:#fff;display:grid;place-items:center;font-size:12px">×</span>':''}
          </button>
        `).join('') : '<div style="color:#8586a8;font-size:11px">موردی وجود ندارد</div>';
      };
      overlay.querySelector('#gpGrid').addEventListener('click', async e=>{
        const del=e.target.closest('[data-del]');
        if(del){
          const key=del.dataset.del;
          if(key && key.startsWith('upload:')){
            try{ await apiJson('/api/gallery/'+key.slice(7),{method:'DELETE'}); items=items.filter(i=>i.id!==key); if(sel===key) sel=''; render(); }catch(err){ toast(err.message); }
          }
          return;
        }
        const btn=e.target.closest('[data-key]');
        if(btn){ sel=btn.dataset.key; render(); }
      });
      $('#gpLogo',overlay).onclick=()=>{ sel=''; render(); };
      $('#gpUploadBtn',overlay).onclick=()=> $('#gpFile',overlay).click();
      $('#gpFile',overlay).addEventListener('change', async e=>{
        const f=e.target.files[0]; if(!f) return;
        const fd=new FormData(); fd.append('file',f);
        try{
          const r=await fetch('/api/gallery',{method:'POST',body:fd,credentials:'same-origin'});
          const d=await r.json().catch(()=>({}));
          if(r.ok){ items.push(d.item); sel=d.item.id; render(); } else toast(d.detail||'خطا');
        }catch(err){ toast(err.message); }
        e.target.value='';
      });
      (async()=>{ try{ const d=await apiJson('/api/gallery'); items=d.items||[]; render(); }catch(e){} })();
      render();
    });
  }

  async function loadMe(){
    try{
      const me=await apiJson('/api/me');
      if(me.username){
        const pn=$('.profile-name'); if(pn) pn.textContent=me.username;
        const pr=$('.profile-role'); if(pr) pr.innerHTML='<span class="dot"></span> '+(me.username==='TiTaN'?'ادمین کل':'مدیر');
        const w=$('.welcome h1'); if(w) w.textContent='خوش آمدید، '+me.username;
      }
      if(me.avatar && me.avatar.url){
        const av=$('.profile .avatar img'); if(av) av.src=me.avatar.url;
        const vvAv=$('.version-logo img'); if(vvAv) vvAv.src=me.avatar.url;
      }
    }catch(e){}
  }

  function drawChart(container, daily){
    const el = typeof container==='string' ? $(container) : container;
    if(!el) return;
    const yAxis = el.querySelector('.y-axis');
    const svgEl = el.querySelector('.chart-svg');
    const xAxis = el.querySelector('.chart-x');
    const grid = el.querySelector('.grid-lines');
    if(!daily || !daily.length || daily.every(d=>!d.up && !d.down)){
      if(svgEl) svgEl.style.display='none';
      if(xAxis) xAxis.innerHTML='<span style="color:#8586a8;font-size:10px">داده‌ای وجود ندارد</span>';
      if(yAxis) yAxis.innerHTML='<span>0</span><span>0</span><span>0</span><span>0</span><span>0</span>';
      return;
    }
    const max = Math.max(1, ...daily.map(d=> (d.up||0)+(d.down||0)));
    const W=760, H=170, padB=24;
    const points = daily.map((d,i)=>{
      const x = (i/(daily.length-1))*(W-20)+10;
      const y = H - padB - ((d.up+d.down)/max)*(H - padB - 20);
      return {x,y,v:d};
    });
    const path = points.map((p,i)=> (i===0?`M${p.x} ${p.y}`:`L${p.x} ${p.y}`)).join(' ');
    const area = path + ` L${points[points.length-1].x} ${H - padB} L${points[0].x} ${H - padB} Z`;
    const xLabels = daily.map(d=> new Date(d.t*1000).toLocaleDateString('fa-IR',{month:'short',day:'numeric'}));
    if(svgEl){
      svgEl.style.display='';
      svgEl.setAttribute('viewBox', `0 0 ${W} ${H}`);
      svgEl.innerHTML=`
        <defs>
          <linearGradient id="area2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a14fff" stop-opacity=".35"/><stop offset="1" stop-color="#a14fff" stop-opacity="0"/></linearGradient>
          <filter id="glow2"><feGaussianBlur stdDeviation="4.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        </defs>
        <path d="${area}" fill="url(#area2)"/>
        <path d="${path}" fill="none" stroke="#9b49ff" stroke-width="2.2" filter="url(#glow2)"/>
        <path d="${path}" fill="none" stroke="#b45cff" stroke-width="1.1"/>
        ${points.map(p=>`<circle cx="${p.x}" cy="${p.y}" r="4" fill="#b65cff" stroke="#170d37" stroke-width="2"/>`).join('')}
      `;
    }
    if(xAxis) xAxis.innerHTML = xLabels.map(l=>`<span>${esc(l)}</span>`).join('');
    if(yAxis){
      const steps=[max, max*0.75, max*0.5, max*0.25, 0];
      yAxis.innerHTML=steps.map(v=>`<span>${esc(fmtBytes(v))}</span>`).join('');
    }
  }

  async function loadOverview(){
    try{
      const [stats, usersRes, nodesRes, reports] = await Promise.all([
        apiJson('/api/stats'),
        apiJson('/api/users'),
        apiJson('/api/nodes'),
        apiJson('/api/reports?days=7').catch(()=>({daily:[]}))
      ]);
      const users=usersRes.users||[]; const nodes=nodesRes.nodes||[];
      const online=nodes.filter(n=>n.enabled && n.status && n.status.online).length;
      const vv=$('.version-v'); if(vv && stats.app_version) vv.textContent='v'+stats.app_version;
      const totalTraffic=(stats.total_up||0)+(stats.total_down||0);
      const activeUsers=users.filter(u=>u.enabled && !(u.status && u.status.expired) && (u.status && u.status.live_enabled)).length;
      const cu=$('.card.users .card-number'); if(cu) cu.textContent=String(activeUsers);
      const cum=$('.card.users .card-meta'); if(cum) cum.textContent='از '+users.length+' کاربر';
      const ct=$('.card.traffic .card-number'); if(ct) ct.textContent=fmtBytes(totalTraffic);
      const ctm=$('.card.traffic .card-meta'); if(ctm) ctm.innerHTML=`MB ↓ ${fmtBytes(stats.total_down||0)} &nbsp; ↑ ${fmtBytes(stats.total_up||0)}`;
      const cs=$('.card.servers .card-number'); if(cs) cs.textContent=String(nodes.length);
      const csm=$('.card.servers .card-meta'); if(csm) csm.innerHTML=`<span class="green">● ${online} آنلاین</span>`;
      const cc=$('.card.configs .card-number'); if(cc) cc.textContent=String(stats.enabled_count||0);
      const ccm=$('.card.configs .card-meta'); if(ccm) ccm.textContent='از '+users.length+' کانفیگ';

      const srvContent=$('.server-content');
      if(srvContent){
        if(nodes.length){
          srvContent.innerHTML=nodes.slice(0,4).map(n=>{
            const st=n.status||{}; const lat=st.latency_ms!=null?st.latency_ms+'ms':'—';
            const city=(n.city && n.city!=='—')?n.city:n.name; const cc=(n.country_code||'').toUpperCase();
            const flag=n.flag||flagFor(cc)||'🌐'; const on=n.enabled && st.online;
            return `<div class="server-row"><div class="latency">${esc(lat)}<small>تاخیر</small></div><div class="status" style="color:${on?'#39e1b9':'#ff6b8a'}">${on?'آنلاین':'آفلاین'}</div><div class="location"><span class="flag">${esc(flag)}</span><span>${esc(city)}${cc?' · '+cc:''}</span></div></div>`;
          }).join('');
        } else srvContent.innerHTML='<div style="color:#8586a8;font-size:11px;padding:12px">سروری ثبت نشده است.</div>';
      }

      const ruHead=document.querySelector('.recent-panel.users-table .recent-table');
      if(ruHead){
        ruHead.querySelectorAll('.recent-table-row').forEach(r=>r.remove());
        const recent=[...users].sort((a,b)=>(b.created_at||0)-(a.created_at||0)).slice(0,3);
        if(recent.length===0) ruHead.insertAdjacentHTML('beforeend','<div style="padding:14px;color:#8586a8;font-size:11px">کاربری وجود ندارد.</div>');
        else recent.forEach(u=>{
          const av=(u.avatar_url||'/static/img/titan-avatar.svg'); const st=u.status||{}; const used=fmtBytes(st.used||0);
          const label=st.expired?'منقضی':(!u.enabled?'غیرفعال':'فعال');
          const row=document.createElement('div'); row.className='recent-table-row';
          row.innerHTML=`<div class="recent-user"><span class="recent-avatar user-avatar"><img src="${esc(av)}" alt=""></span><span class="recent-name">${esc(u.name)}</span></div><div class="recent-traffic">${esc(used)}</div><div class="recent-status">${esc(label)}</div>`;
          ruHead.appendChild(row);
        });
      }
      const rcHead=document.querySelector('.recent-panel.configs-table .recent-table');
      if(rcHead){
        rcHead.querySelectorAll('.recent-table-row').forEach(r=>r.remove());
        const nodeMap={}; nodes.forEach(n=>nodeMap[n.id]=n);
        const recent=[...users].sort((a,b)=>(b.created_at||0)-(a.created_at||0)).slice(0,3);
        if(recent.length===0) rcHead.insertAdjacentHTML('beforeend','<div style="padding:14px;color:#8586a8;font-size:11px">کانفیگی وجود ندارد.</div>');
        else recent.forEach(u=>{
          const av=(u.avatar_url||'/static/img/titan-avatar.svg'); const n=nodeMap[u.node_id||1];
          const flag=n?(n.flag||flagFor(n.country_code)||'🌐'):'🌐'; const loc=n?((n.city && n.city!=='—')?n.city:n.name):'—';
          const st=u.status||{}; const label=st.expired?'منقضی':(!u.enabled?'غیرفعال':'فعال');
          const row=document.createElement('div'); row.className='recent-table-row';
          row.innerHTML=`<div class="recent-config"><span class="recent-avatar user-avatar"><img src="${esc(av)}" alt=""></span><span class="recent-name">${esc(u.name)}</span></div><div>${esc((u.protocol||'').toUpperCase())}</div><div class="recent-server"><span class="flag">${esc(flag)}</span><span>${esc(loc)}</span></div><div class="recent-status">${esc(label)}</div>`;
          rcHead.appendChild(row);
        });
      }

      // real traffic chart
      const chartArea=$('.chart-area');
      if(chartArea && reports.daily){
        drawChart(chartArea, reports.daily);
      }
    }catch(e){ console.error('loadOverview',e); }
  }

  // --- modals ---
  function createModal(title, bodyHtml, onSave){
    const ex=$('#titanModal'); if(ex) ex.remove();
    const overlay=document.createElement('div'); overlay.id='titanModal';
    overlay.style.cssText='position:fixed;inset:0;z-index:9998;background:rgba(2,4,18,.62);backdrop-filter:blur(8px);display:grid;place-items:center;padding:18px;';
    overlay.innerHTML=`<div style="width:min(640px,96vw);max-height:92vh;overflow:auto;background:linear-gradient(145deg,rgba(24,12,56,.96),rgba(8,6,26,.98));border:1px solid rgba(151,116,255,.42);border-radius:18px;box-shadow:0 0 30px rgba(94,48,205,.22);">
      <div style="position:sticky;top:0;z-index:1;background:linear-gradient(145deg,rgba(24,12,56,1),rgba(12,8,32,1));padding:18px 20px;border-bottom:1px solid rgba(151,116,255,.18);display:flex;align-items:center;justify-content:space-between"><div style="font-weight:700;color:#f2edff">${esc(title)}</div><button id="titanModalClose" style="width:32px;height:32px;border-radius:9px;border:1px solid rgba(151,116,255,.24);background:rgba(91,49,176,.16);color:#d8c7ff;cursor:pointer">×</button></div>
      <div style="padding:18px 20px">${bodyHtml}</div>
      <div style="position:sticky;bottom:0;background:linear-gradient(145deg,rgba(24,12,56,1),rgba(8,6,26,1));padding:14px 20px;border-top:1px solid rgba(151,116,255,.18);display:flex;gap:10px;justify-content:flex-end"><button id="titanModalCancel" style="padding:10px 14px;border-radius:10px;border:1px solid rgba(151,116,255,.24);background:rgba(91,49,176,.12);color:#eee9ff;cursor:pointer">انصراف</button><button id="titanModalSave" style="padding:10px 16px;border-radius:10px;border:1px solid rgba(188,157,255,.5);background:linear-gradient(135deg,#7436f5,#4b1bb4);color:#fff;cursor:pointer">ذخیره</button></div>
    </div>`;
    document.body.appendChild(overlay);
    const close=()=>overlay.remove();
    $('#titanModalClose',overlay).onclick=close;
    $('#titanModalCancel',overlay).onclick=close;
    overlay.addEventListener('click',e=>{ if(e.target===overlay) close(); });
    $('#titanModalSave',overlay).onclick=async()=>{
      const btn=$('#titanModalSave',overlay); btn.disabled=true; const old=btn.textContent; btn.textContent='...';
      try{ await onSave(overlay); close(); toast('انجام شد'); loadOverview(); }
      catch(e){ toast(e.message); }
      finally{ btn.disabled=false; btn.textContent=old; }
    };
  }

  // --- full user/config modal (all previous settings) ---
  async function openUserModal(existing=null){
    const settings = await apiJson('/api/settings').catch(()=>({}));
    const nodesRes = await apiJson('/api/nodes').catch(()=>({nodes:[]}));
    const nodes = nodesRes.nodes||[];
    const isEdit = !!existing;
    const u = existing || {};
    const nodeOpts = '<option value="0">🌐 خودکار (نزدیک‌ترین)</option>' + nodes.map(n=>`<option value="${n.id}" ${String(u.node_id||0)===String(n.id)?'selected':''}>${esc(n.flag||flagFor(n.country_code)||'🌐')} ${esc(n.name)}</option>`).join('');
    const protocols=['vless','vmess','trojan','shadowsocks','hysteria2','wireguard'];
    const transports=['ws','xhttp','grpc','tcp','httpupgrade'];
    const fingerprints=['chrome','firefox','safari','ios','android','edge','random','randomized'];
    const alpns=['http/1.1','h2,http/1.1','h3,h2,http/1.1',''];
    const ssMethods=['2022-blake3-aes-128-gcm','2022-blake3-aes-256-gcm','2022-blake3-chacha20-poly1305','aes-128-gcm','aes-256-gcm','chacha20-ietf-poly1305'];
    const expireDays = u.expire_at ? Math.max(0, Math.ceil((u.expire_at - Date.now()/1000)/86400)) : 0;

    createModal(isEdit?'ویرایش کاربر / کانفیگ':'افزودن کاربر / کانفیگ', `
      <div style="display:grid;gap:16px">
        <div style="display:flex;gap:12px;align-items:center">
          <div id="avPreview" style="width:54px;height:54px;border-radius:14px;overflow:hidden;border:1px solid rgba(151,116,255,.3);background:rgba(10,20,39,.6);display:grid;place-items:center"><img src="${esc(avatarUrl(u.avatar||''))}" style="width:100%;height:100%;object-fit:cover"></div>
          <input type="hidden" id="mu_avatar" value="${esc(u.avatar||'')}">
          <button type="button" id="avPickBtn" style="padding:8px 12px;border-radius:10px;border:1px solid rgba(151,116,255,.24);background:rgba(91,49,176,.12);color:#eee9ff;cursor:pointer">انتخاب تصویر</button>
          <span style="font-size:10px;color:#8586a8">پروفایل کاربر — مثل قبل</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">نام*<input id="mu_name" value="${esc(u.name||'')}" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">یادداشت<input id="mu_note" value="${esc(u.note||'')}" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
        </div>
        <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">سرور<select id="mu_node" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px">${nodeOpts}</select></label>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">پروتکل<select id="mu_protocol" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px">${protocols.map(p=>`<option value="${p}" ${ (u.protocol||'vless')===p?'selected':''}>${p.toUpperCase()}</option>`).join('')}</select></label>
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">انتقال<select id="mu_transport" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px">${transports.map(t=>`<option value="${t}" ${(u.transport||settings.default_transport||'ws')===t?'selected':''}>${t.toUpperCase()}</option>`).join('')}</select></label>
        </div>
        <div id="ssRow" style="display:${(u.protocol||'vless')==='shadowsocks'?'flex':'none'};flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">متد Shadowsocks<select id="mu_ss" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px">${ssMethods.map(m=>`<option value="${m}" ${(u.ss_method||settings.ss_method||'2022-blake3-aes-128-gcm')===m?'selected':''}>${m}</option>`).join('')}</select></div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">امنیت<select id="mu_security" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"><option value="tls" ${(u.security||'tls')==='tls'?'selected':''}>TLS</option><option value="none" ${u.security==='none'?'selected':''}>None</option><option value="reality" ${u.security==='reality'?'selected':''}>Reality</option></select></label>
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">فینگرپرینت<select id="mu_fp" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px">${fingerprints.map(f=>`<option value="${f}" ${(u.fingerprint||settings.default_fingerprint||'chrome')===f?'selected':''}>${f}</option>`).join('')}</select></label>
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">ALPN<select id="mu_alpn" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px">${alpns.map(a=>`<option value="${a}" ${(u.alpn??settings.default_alpn??'http/1.1')===a?'selected':''}>${a||'—'}</option>`).join('')}</select></label>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">حجم (GB)<input id="mu_quota" type="number" step="0.1" value="${u.quota_gb||0}" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">انقضا (روز)<input id="mu_expire" type="number" value="${expireDays}" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">حد دستگاه<input id="mu_devices" type="number" value="${u.max_devices||0}" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">حد درخواست<input id="mu_requests" type="number" value="${u.max_requests||0}" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
        </div>
        <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">IPهای مجاز (با کاما جدا کن، CIDR هم قبول است)<input id="mu_ips" value="${esc((u.allowed_ips||[]).join(','))}" dir="ltr" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
        <div style="border-top:1px solid rgba(151,116,255,.16);padding-top:14px;display:grid;gap:12px">
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">پروفایل آماده (Recipe)<select id="mu_recipe" data-cur="${esc(u.recipe||'')}" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"><option value="">بدون پروفایل</option></select></label>
          <div id="mu_recipe_hint" style="font-size:10px;color:#7d829d;line-height:1.7">انتخاب پروفایل، فیلدهای خالی زیر را پر می‌کند؛ هر چیزی که خودت تنظیم کرده باشی دست‌نخورده می‌ماند.</div>
          <details id="mu_adv" style="border:1px solid rgba(151,116,255,.18);border-radius:12px;padding:10px 12px;background:rgba(10,20,39,.35)">
            <summary style="cursor:pointer;font-size:11px;color:#cbb8ff">تنظیمات پیشرفته کانفیگ</summary>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px">
              <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">Flow (VLESS)<select id="mu_flow" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"><option value="" ${(u.flow||'')===''?'selected':''}>پیش‌فرض سرور</option><option value="none" ${u.flow==='none'?'selected':''}>بدون Flow (VLESS ساده)</option><option value="xtls-rprx-vision" ${u.flow==='xtls-rprx-vision'?'selected':''}>xtls-rprx-vision</option><option value="xtls-rprx-vision-udp443" ${u.flow==='xtls-rprx-vision-udp443'?'selected':''}>vision + udp443</option></select></label>
              <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">پلن سرعت (Policy)<select id="mu_plan" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"><option value="0" ${(u.policy_level||0)===0?'selected':''}>متعادل (پیش‌فرض)</option><option value="1" ${u.policy_level===1?'selected':''}>گیمینگ — تأخیر کم</option><option value="2" ${u.policy_level===2?'selected':''}>استریم/دانلود — توان بالا</option></select></label>
              <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">SNI اختصاصی Reality<input id="mu_rsni" value="${esc(u.reality_sni||'')}" dir="ltr" placeholder="www.samsung.com" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
              <label style="display:flex;flex-direction:row;align-items:center;gap:8px;font-size:11px;color:#a8a6bf;margin-top:18px"><input id="mu_mux" type="checkbox" ${u.mux_enabled?'checked':''}><span>Mux چند-کاناله (برای کلاینت JSON)</span></label>
            </div>
            <div style="font-size:10px;color:#7d829d;margin-top:10px;line-height:1.7">SNI اختصاصی روی Reality معنی دارد؛ پلن سرعت سرور را برای همین کاربر تنظیم می‌کند.</div>
          </details>
        </div>
      </div>
    `, async (overlay)=>{
      const body={
        name: $('#mu_name',overlay).value.trim()||'User',
        note: $('#mu_note',overlay).value,
        node_id: parseInt($('#mu_node',overlay).value)||0,
        protocol: $('#mu_protocol',overlay).value,
        transport: $('#mu_transport',overlay).value,
        security: $('#mu_security',overlay).value,
        fingerprint: $('#mu_fp',overlay).value,
        alpn: $('#mu_alpn',overlay).value,
        ss_method: $('#mu_ss',overlay) ? $('#mu_ss',overlay).value : undefined,
        quota_gb: parseFloat($('#mu_quota',overlay).value)||0,
        expire_days: parseInt($('#mu_expire',overlay).value)||0,
        max_devices: parseInt($('#mu_devices',overlay).value)||0,
        max_requests: parseInt($('#mu_requests',overlay).value)||0,
        allowed_ips: ($('#mu_ips',overlay).value||'').split(',').map(s=>s.trim()).filter(Boolean),
        avatar: $('#mu_avatar',overlay).value,
        recipe: $('#mu_recipe',overlay) ? $('#mu_recipe',overlay).value : '',
        flow: $('#mu_flow',overlay) ? $('#mu_flow',overlay).value : '',
        reality_sni: $('#mu_rsni',overlay) ? $('#mu_rsni',overlay).value.trim() : '',
        policy_level: $('#mu_plan',overlay) ? (parseInt($('#mu_plan',overlay).value)||0) : 0,
        mux_enabled: $('#mu_mux',overlay) ? $('#mu_mux',overlay).checked : false,
        client_nonce: Math.random().toString(36).slice(2)+Date.now().toString(36)
      };
      if(isEdit){
        await apiJson('/api/users/'+u.uid,{method:'PATCH',body});
      } else {
        await apiJson('/api/users',{method:'POST',body});
      }
      setTimeout(()=>{ const ev=new Event('titan:refresh'); document.dispatchEvent(ev); }, 100);
    });
    // wire ui immediately after modal creation (not only on save)
    setTimeout(()=>{
      const overlay=$('#titanModal'); if(!overlay) return;
      const avBtn=$('#avPickBtn',overlay), avIn=$('#mu_avatar',overlay), avImg=$('#avPreview img',overlay);
      if(avBtn) avBtn.onclick=async()=>{
        const k=await openGalleryPicker(avIn.value);
        if(k!=null){ avIn.value=k; if(avImg) avImg.src=avatarUrl(k); }
      };
      const protoSel=$('#mu_protocol',overlay), ssRow=$('#ssRow',overlay), transSel=$('#mu_transport',overlay), secSel=$('#mu_security',overlay);
      const updateDeps=()=>{
        if(!protoSel) return;
        const p=protoSel.value; const noNet=(p==='hysteria2'||p==='wireguard');
        if(transSel) transSel.disabled=noNet;
        if(secSel) secSel.disabled=noNet;
        if(ssRow) ssRow.style.display = p==='shadowsocks' ? 'flex' : 'none';
      };
      if(protoSel) protoSel.addEventListener('change',updateDeps);
      updateDeps();
    }, 20);
  }

  async function openNodeModal(existing=null){
    const isEdit=!!existing; const n=existing||{};
    createModal(isEdit?'ویرایش سرور':'افزودن سرور', `
      <div style="display:grid;gap:12px">
        <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">نام*<input id="mn_name" value="${esc(n.name||'')}" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
        <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">آدرس (دامنه/IP)<input id="mn_addr" value="${esc(n.address||'')}" dir="ltr" placeholder="your-node.up.railway.app" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">شهر<input id="mn_city" value="${esc(n.city||'')}" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">کشور<input id="mn_country" value="${esc(n.country||'')}" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">کد کشور (2 حرف)<input id="mn_cc" value="${esc(n.country_code||'')}" maxlength="2" style="text-transform:uppercase;background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
          <label style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#a8a6bf">پرچم<input id="mn_flag" value="${esc(n.flag||'')}" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
        </div>
        <div style="font-size:10px;color:#7d829d">اگر پرچم/شهر خالی باشد، با «بررسی» خودکار پر می‌شود (معماری قبلی).</div>
      </div>
    `, async (overlay)=>{
      const body={
        name: $('#mn_name',overlay).value.trim(),
        address: $('#mn_addr',overlay).value.trim(),
        city: $('#mn_city',overlay).value.trim(),
        country: $('#mn_country',overlay).value.trim(),
        country_code: $('#mn_cc',overlay).value.trim(),
        flag: $('#mn_flag',overlay).value.trim()
      };
      if(!body.name) throw new Error('نام الزامی است');
      if(isEdit) await apiJson('/api/nodes/'+n.id,{method:'PATCH',body});
      else {
        const res=await apiJson('/api/nodes',{method:'POST',body});
        if(res.token) toast('توکن نود: '+res.token);
      }
      setTimeout(()=> document.dispatchEvent(new Event('titan:refresh')), 100);
    });
    setTimeout(()=>{
      const overlay=$('#titanModal'); if(!overlay) return;
      const ccIn=$('#mn_cc',overlay), flagIn=$('#mn_flag',overlay);
      if(ccIn && flagIn) ccIn.addEventListener('input',()=>{ flagIn.value = flagFor(ccIn.value); });
    }, 20);
  }

  function wireDetails(){
    // hide export button in users section (keep only Add User)
    $$('.section-view[data-section="users"] .section-actions button').forEach(b=>{
      const t=(b.textContent||'').trim();
      if(t.includes('خروجی')) b.style.display='none';
    });

    const usersSection=document.querySelector('.section-view[data-section="users"]');
    if(usersSection){
      const tbody=usersSection.querySelector('.data-table tbody');
      const search=usersSection.querySelector('[data-filter="users"]');
      async function refreshUsers(){
        try{
          const d=await apiJson('/api/users'); const users=d.users||[];
          // update the 3 top cards with real data
          const cards=usersSection.querySelectorAll('.section-grid .detail-card');
          if(cards[0]){
            const total=users.length;
            const active=users.filter(u=> u.enabled && !(u.status&&u.status.expired) && u.status&&u.status.live_enabled).length;
            const connecting=users.filter(u=> (u.status&&u.status.active_connections>0)).length;
            const disabled=users.filter(u=> !u.enabled && !(u.status&&u.status.expired)).length;
            cards[0].innerHTML=`<h3>کاربران فعال</h3><div class="metric-row"><span>تعداد کل</span><strong>${total}</strong></div><div class="metric-row"><span>در حال اتصال</span><strong>${connecting}</strong></div><div class="metric-row"><span>غیرفعال</span><strong>${disabled}</strong></div>`;
            if(cards[1]){
              const totalUsed=users.reduce((a,u)=>a+((u.status&&u.status.used)||0),0);
              const todayUsed = totalUsed; // approximate, real daily is in reports
              cards[1].innerHTML=`<h3>مصرف ترافیک</h3><div class="metric-row"><span>مصرف کل</span><strong>${esc(fmtBytes(totalUsed))}</strong></div><div class="metric-row"><span>تعداد کاربران</span><strong>${total}</strong></div><div class="progress"><span style="width:${Math.min(100, Math.round((totalUsed/(10*1024*1024*1024))*100))}%"></span></div>`;
            }
            if(cards[2]){
              const activeSub=active; const nearExpire=users.filter(u=> u.expire_at && (u.expire_at - Date.now()/1000) < 3*86400 && !(u.status&&u.status.expired)).length;
              const expired=users.filter(u=> u.status&&u.status.expired).length;
              cards[2].innerHTML=`<h3>وضعیت اشتراک</h3><div class="metric-row"><span>فعال</span><span class="pill">● ${activeSub} حساب</span></div><div class="metric-row"><span>نزدیک به انقضا</span><span class="pill warn">${nearExpire} حساب</span></div><div class="metric-row"><span>منقضی</span><span class="pill off">${expired} حساب</span></div>`;
            }
          }
          if(tbody){
            tbody.innerHTML=users.length? users.map(u=>{
              const st=u.status||{}; const used=fmtBytes(st.used||0);
              const days=u.expire_at? Math.max(0,Math.ceil((u.expire_at - Date.now()/1000)/86400))+' روز':'هرگز';
              const label=st.expired?'منقضی':(!u.enabled?'غیرفعال':'فعال'); const cls=st.expired?'warn':(!u.enabled?'off':'');
              return `<tr><td><span class="user-cell"><span class="avatar user-avatar"><img src="${esc(u.avatar_url||'/static/img/titan-avatar.svg')}" alt=""></span>${esc(u.name)}</span></td><td class="muted">#${esc(u.uid.slice(0,6))}</td><td>${esc(used)}</td><td>${esc(days)}</td><td><span class="pill ${cls}">${esc(label)}</span></td><td><button class="mini-btn" data-uid="${esc(u.uid)}" data-act="edit">ویرایش</button> <button class="mini-btn" data-uid="${esc(u.uid)}" data-act="detail">لینک</button> <button class="mini-btn" data-uid="${esc(u.uid)}" data-act="del" style="color:#ff8297">حذف</button></td></tr>`;
            }).join('') : '<tr><td colspan="6" style="text-align:center;color:#8586a8">کاربری وجود ندارد</td></tr>';
            tbody.querySelectorAll('[data-act="del"]').forEach(b=> b.addEventListener('click', async()=>{ const uid=b.dataset.uid; if(!confirm('حذف کاربر؟')) return; try{ await apiJson('/api/users/'+uid,{method:'DELETE'}); toast('حذف شد'); refreshUsers(); loadOverview(); }catch(e){toast(e.message);} }));
            tbody.querySelectorAll('[data-act="detail"]').forEach(b=> b.addEventListener('click', async()=>{ const uid=b.dataset.uid; try{ const d=await apiJson('/api/users/'+uid+'/links'); await navigator.clipboard.writeText(d.main_link||d.links[0]); toast('لینک کپی شد'); }catch(e){toast(e.message);} }));
            tbody.querySelectorAll('[data-act="edit"]').forEach(b=> b.addEventListener('click', async()=>{ const uid=b.dataset.uid; try{ const u=await apiJson('/api/users/'+uid); await openUserModal(u); }catch(e){toast(e.message);} }));
          }
          const cnt=usersSection.querySelector('.data-card .muted'); if(cnt) cnt.textContent=users.length+' مورد';
        }catch(e){ console.error(e); }
      }
      refreshUsers();
      document.addEventListener('titan:refresh', refreshUsers);
      if(search) search.addEventListener('input', ()=>{ const q=search.value.trim().toLowerCase(); if(!tbody) return; tbody.querySelectorAll('tr').forEach(tr=> tr.style.display=tr.textContent.toLowerCase().includes(q)?'':'none'); });
      const addBtn=usersSection.querySelector('.section-btn.primary'); if(addBtn) addBtn.onclick=()=> openUserModal();
      // remove old demo handlers that showed "✓ انجام شد"
      $$('button',usersSection).forEach(b=>{ if(b.dataset.demo) b.removeAttribute('data-demo'); });
    }

    const configsSection=document.querySelector('.section-view[data-section="configs"]');
    if(configsSection){
      const tbody=configsSection.querySelector('.data-table tbody');
      async function refreshConfigs(){
        try{
          const [uRes,nRes]=await Promise.all([apiJson('/api/users'), apiJson('/api/nodes')]);
          const users=uRes.users||[]; const nodes=nRes.nodes||[]; const nodeMap={}; nodes.forEach(n=>nodeMap[n.id]=n);
          // update top 3 cards
          const cards=configsSection.querySelectorAll('.section-grid .detail-card');
          if(cards[0]){
            const total=users.length; const active=users.filter(u=>u.enabled && !(u.status&&u.status.expired)).length;
            cards[0].innerHTML=`<h3>کانفیگ‌های فعال</h3><div class="metric-row"><span>کل کانفیگ‌ها</span><strong>${total}</strong></div><div class="metric-row"><span>فعال</span><strong>${active}</strong></div><div class="metric-row"><span>منقضی</span><strong>${total-active}</strong></div>`;
          }
          if(cards[1]){
            const prots={}; users.forEach(u=> prots[u.protocol]=(prots[u.protocol]||0)+1);
            cards[1].innerHTML=`<h3>پروتکل‌های استفاده‌شده</h3>`+Object.entries(prots).map(([k,v])=>`<div class="metric-row"><span>${esc(k.toUpperCase())}</span><span class="pill">${v} مورد</span></div>`).join('') + (Object.keys(prots).length===0?'<div class="metric-row"><span class="muted">موردی وجود ندارد</span></div>':'');
          }
          if(tbody){
            tbody.innerHTML=users.length? users.map(u=>{
              const n=nodeMap[u.node_id||1]; const loc=n?((n.city&&n.city!=='—')?n.city:n.name):'—'; const flag=n?(n.flag||flagFor(n.country_code)||'🌐'):'🌐';
              const st=u.status||{}; const label=st.expired?'منقضی':(!u.enabled?'غیرفعال':'فعال'); const cls=st.expired?'warn':(!u.enabled?'off':'');
              return `<tr><td><span class="user-cell"><span class="avatar user-avatar"><img src="${esc(u.avatar_url||'/static/img/titan-avatar.svg')}" alt=""></span>${esc(u.name)}</span></td><td>${esc((u.protocol||'').toUpperCase())}</td><td>${esc(flag)} ${esc(loc)}</td><td>${u.expire_at? fmtDate(u.expire_at):'هرگز'}</td><td><span class="pill ${cls}">${esc(label)}</span></td><td><button class="mini-btn" data-uid="${esc(u.uid)}" data-act="edit">ویرایش</button> <button class="mini-btn" data-uid="${esc(u.uid)}" data-act="links">لینک</button> <button class="mini-btn" data-uid="${esc(u.uid)}" data-act="del" style="color:#ff8297">حذف</button></td></tr>`;
            }).join('') : '<tr><td colspan="6" style="text-align:center;color:#8586a8">کانفیگی وجود ندارد</td></tr>';
            tbody.querySelectorAll('[data-act="del"]').forEach(b=> b.addEventListener('click', async()=>{ const uid=b.dataset.uid; if(!confirm('حذف کانفیگ؟')) return; try{ await apiJson('/api/users/'+uid,{method:'DELETE'}); toast('حذف شد'); refreshConfigs(); loadOverview(); }catch(e){toast(e.message);} }));
            tbody.querySelectorAll('[data-act="links"]').forEach(b=> b.addEventListener('click', async()=>{ const uid=b.dataset.uid; try{ const d=await apiJson('/api/users/'+uid+'/links'); await navigator.clipboard.writeText(d.main_link||d.links[0]); toast('لینک کپی شد'); }catch(e){toast(e.message);} }));
            tbody.querySelectorAll('[data-act="edit"]').forEach(b=> b.addEventListener('click', async()=>{ const uid=b.dataset.uid; try{ const u=await apiJson('/api/users/'+uid); await openUserModal(u); }catch(e){toast(e.message);} }));
          }
        }catch(e){ console.error(e); }
      }
      refreshConfigs();
      document.addEventListener('titan:refresh', refreshConfigs);
      const addBtn=configsSection.querySelector('.section-btn.primary'); if(addBtn) addBtn.onclick=()=> openUserModal();
      $$('button',configsSection).forEach(b=>{ if(b.dataset.demo) b.removeAttribute('data-demo'); });
    }

    const serversSection=document.querySelector('.section-view[data-section="servers"]');
    if(serversSection){
      async function refreshServers(){
        try{
          const d=await apiJson('/api/nodes'); const nodes=d.nodes||[];
          const grid=serversSection.querySelector('.section-grid');
          if(grid && grid.children.length>=3){
            // update 3 top cards with real data
            const total=nodes.length; const online=nodes.filter(n=>n.enabled && n.status&&n.status.online).length;
            grid.children[0].innerHTML=`<h3>وضعیت نودها</h3><div class="metric-row"><span>کل سرورها</span><strong>${total}</strong></div><div class="metric-row"><span>آنلاین</span><span class="pill">● ${online}</span></div><div class="metric-row"><span>آفلاین</span><span class="pill off">${total-online}</span></div>`;
            const avgLat = (()=>{ const v=nodes.map(n=>n.status&&n.status.latency_ms).filter(x=>x!=null); return v.length? Math.round(v.reduce((a,b)=>a+b,0)/v.length)+' ms' : '—'; })();
            grid.children[1].innerHTML=`<h3>سلامت اتصال</h3><div class="metric-row"><span>میانگین پینگ</span><strong>${avgLat}</strong></div><div class="metric-row"><span>پایداری</span><strong>${online===total&&total>0?'99.9%':'—'}</strong></div><div class="progress"><span style="width:${total?Math.round((online/total)*100):0}%"></span></div>`;
          }
          let list=serversSection.querySelector('.server-list');
          if(!list){
            list=document.createElement('div'); list.className='detail-card data-card server-list'; list.style.marginTop='14px';
            list.innerHTML='<div class="card-title"><h3 style="margin:0">فهرست سرورها</h3></div><div class="table-scroll"><table class="data-table"><thead><tr><th>نام</th><th>آدرس</th><th>وضعیت</th><th>پینگ</th><th>عملیات</th></tr></thead><tbody></tbody></table></div>';
            serversSection.appendChild(list);
          }
          const tbody=list.querySelector('tbody');
          tbody.innerHTML=nodes.length? nodes.map(n=>{
            const st=n.status||{}; const on=n.enabled && st.online; const flag=n.flag||flagFor(n.country_code)||'🌐';
            return `<tr><td>${esc(flag)} ${esc(n.name)}</td><td style="direction:ltr">${esc(n.address||'—')}</td><td><span class="pill ${on?'':'off'}">${on?'آنلاین':'آفلاین'}</span></td><td>${st.latency_ms!=null?st.latency_ms+'ms':'—'}</td><td><button class="mini-btn" data-id="${n.id}" data-act="ping">بررسی</button> <button class="mini-btn" data-id="${n.id}" data-act="edit">ویرایش</button> ${!n.is_local?'<button class="mini-btn" data-id="'+n.id+'" data-act="del" style="color:#ff8297">حذف</button>':''}</td></tr>`;
          }).join('') : '<tr><td colspan="5" style="text-align:center;color:#8586a8">سروری وجود ندارد</td></tr>';
          tbody.querySelectorAll('[data-act="ping"]').forEach(b=> b.addEventListener('click', async()=>{ const id=b.dataset.id; b.disabled=true; const old=b.textContent; b.textContent='...'; try{ await apiJson('/api/nodes/'+id+'/ping',{method:'POST'}); toast('بررسی شد'); refreshServers(); loadOverview(); }catch(e){toast(e.message);} finally{ b.disabled=false; b.textContent=old; } }));
          tbody.querySelectorAll('[data-act="edit"]').forEach(b=> b.addEventListener('click', async()=>{ const id=b.dataset.id; try{ const n=(await apiJson('/api/nodes')).nodes.find(x=>String(x.id)===String(id)); if(n) await openNodeModal(n); }catch(e){toast(e.message);} }));
          tbody.querySelectorAll('[data-act="del"]').forEach(b=> b.addEventListener('click', async()=>{ const id=b.dataset.id; if(!confirm('حذف سرور؟')) return; try{ await apiJson('/api/nodes/'+id,{method:'DELETE'}); toast('حذف شد'); refreshServers(); loadOverview(); }catch(e){toast(e.message);} }));
        }catch(e){ console.error(e); }
      }
      refreshServers();
      document.addEventListener('titan:refresh', refreshServers);
      const addBtn=serversSection.querySelector('.section-btn.primary'); if(addBtn) addBtn.onclick=()=> openNodeModal();
      $$('button',serversSection).forEach(b=>{ if(b.dataset.demo) b.removeAttribute('data-demo'); });
    }

    const subsSection=document.querySelector('.section-view[data-section="subscriptions"]');
    if(subsSection){
      async function refreshSubs(){
        try{
          const d=await apiJson('/api/users'); const users=d.users||[]; const tbody=subsSection.querySelector('.data-table tbody');
          if(tbody){
            tbody.innerHTML=users.length? users.map(u=>{
              const st=u.status||{}; const label=st.expired?'منقضی':(!u.enabled?'غیرفعال':'فعال'); const cls=st.expired?'warn':(!u.enabled?'off':'');
              const exp=u.expire_at? new Date(u.expire_at*1000).toLocaleDateString('fa-IR') : 'هرگز';
              return `<tr><td><span class="user-cell"><span class="avatar user-avatar"><img src="${esc(u.avatar_url||'/static/img/titan-avatar.svg')}" alt=""></span>${esc(u.name)}</span></td><td><span class="pill ${cls}">${esc(label)}</span></td><td>${esc(exp)}</td><td>1</td><td>${esc(fmtBytes(st.used||0))}</td><td><button class="mini-btn" data-uid="${u.uid}" data-act="copy">کپی</button><button class="mini-btn" data-uid="${u.uid}" data-act="qr">QR</button><button class="mini-btn" data-uid="${u.uid}" data-act="view">نمایش</button></td></tr>`;
            }).join('') : '<tr><td colspan="6" style="text-align:center;color:#8586a8">اشتراکی وجود ندارد</td></tr>';
            tbody.querySelectorAll('[data-act="copy"]').forEach(b=> b.addEventListener('click', async()=>{ const uid=b.dataset.uid; try{ const d=await apiJson('/api/users/'+uid+'/links'); await navigator.clipboard.writeText(d.sub_url); toast('اشتراک کپی شد'); }catch(e){toast(e.message);} }));
            tbody.querySelectorAll('[data-act="qr"]').forEach(b=> b.addEventListener('click', ()=>{ const uid=b.dataset.uid; window.open('/api/users/'+uid+'/qr','_blank'); }));
            tbody.querySelectorAll('[data-act="view"]').forEach(b=> b.addEventListener('click', async()=>{ const uid=b.dataset.uid; try{ const d=await apiJson('/api/users/'+uid+'/links'); await navigator.clipboard.writeText(d.main_link||d.links[0]); toast('لینک کپی شد'); }catch(e){toast(e.message);} }));
          }
        }catch(e){ console.error(e); }
      }
      refreshSubs(); document.addEventListener('titan:refresh', refreshSubs);
    }

    const reportsSection=document.querySelector('.section-view[data-section="reports"]');
    if(reportsSection){
      async function refreshReports(){
        try{
          const r=await apiJson('/api/reports?days=7');
          const t=r.totals||{}; const prots=r.protocols||[]; const daily=r.daily||[];
          const grid=reportsSection.querySelector('.section-grid');
          if(grid && grid.children.length>=3){
            grid.children[0].innerHTML=`<h3>مصرف ترافیک</h3><div class="metric-row"><span>دانلود</span><strong>${esc(fmtBytes(t.total_down||0))}</strong></div><div class="metric-row"><span>آپلود</span><strong>${esc(fmtBytes(t.total_up||0))}</strong></div><div class="progress"><span style="width:${Math.min(100, Math.round(((t.total_up+t.total_down)/(1024*1024*1024))*10))}%"></span></div>`;
            grid.children[1].innerHTML=`<h3>رشد کاربران</h3><div class="metric-row"><span>کل</span><strong>${t.users||0}</strong></div><div class="metric-row"><span>فعال</span><strong>${t.active||0}</strong></div><div class="metric-row"><span>منقضی</span><strong>${t.expired||0}</strong></div>`;
            const evCount = (r.daily||[]).reduce((a,d)=>a+ (d.up||0)+(d.down||0),0);
            grid.children[2].innerHTML=`<h3>رویدادهای سیستم</h3><div class="metric-row"><span>کاربران فعال</span><strong>${t.active||0}</strong></div><div class="metric-row"><span>غیرفعال</span><strong>${t.disabled||0}</strong></div><div class="metric-row"><span>پروتکل‌ها</span><strong>${prots.length}</strong></div>`;
          }
          // chart-mini
          const chartMini=reportsSection.querySelector('.chart-mini');
          if(chartMini && daily.length){
            const max=Math.max(1, ...daily.map(d=> (d.up||0)+(d.down||0)));
            chartMini.innerHTML=daily.map(d=>{
              const h=Math.max(8, Math.round(((d.up+d.down)/max)*100));
              return `<span style="height:${h}%" title="${esc(fmtBytes(d.up+d.down))}"></span>`;
            }).join('');
            const totEl=reportsSection.querySelector('.chart-mini + .metric-row strong');
            if(totEl) totEl.textContent='مجموع '+fmtBytes(daily.reduce((a,d)=>a+d.up+d.down,0));
          }
          // keep "آخرین رویدادها" table as static events; top_users is shown in chart tooltip, not overwriting events
          // (if needed, could render top users elsewhere without destroying real event log)
        }catch(e){ console.error(e); }
      }
      refreshReports(); document.addEventListener('titan:refresh', refreshReports);
      // remove demo handlers
      $$('button',reportsSection).forEach(b=>{ if(b.dataset.demo) b.removeAttribute('data-demo'); });
    }

    const settingsSection=document.querySelector('.section-view[data-section="settings"]');
    if(settingsSection){
      // map inputs by placeholder/label
      const findInput=(ph)=> settingsSection.querySelector(`input[placeholder="${ph}"]`) || [...settingsSection.querySelectorAll('input')].find(i=> i.placeholder&&i.placeholder.includes(ph));
      const publicDomain = findInput('example.com');
      const publicPort = [...settingsSection.querySelectorAll('input')].find(i=> i.value==='443' && i.type!=='password') || settingsSection.querySelector('input[value="443"]');
      const saveBtn = settingsSection.querySelector('.section-btn.primary');
      const oldPass = settingsSection.querySelector('input[placeholder="••••••••"]');
      const newPass = settingsSection.querySelector('input[placeholder="رمز عبور جدید"]');
      const changeBtn = [...settingsSection.querySelectorAll('button')].find(b=> (b.textContent||'').includes('تغییر رمز'));
      const transportSel = [...settingsSection.querySelectorAll('select')].find(s=> [...s.options].some(o=> o.value==='WS' || o.textContent==='WS'));
      const fpSel = [...settingsSection.querySelectorAll('select')].find(s=> [...s.options].some(o=> o.value==='chrome'));
      const alpnIn = [...settingsSection.querySelectorAll('input')].find(i=> i.value==='http/1.1');
      const sniIn = findInput('') && [...settingsSection.querySelectorAll('.field')].find(f=> f.textContent.includes('SNI'))?.querySelector('input');

      async function loadSettings(){
        try{
          const s=await apiJson('/api/settings');
          if(publicDomain) publicDomain.value=s.public_domain||'';
          if(publicPort) publicPort.value=s.public_port||'443';
          if(transportSel && s.default_transport) transportSel.value=s.default_transport.toUpperCase();
          if(fpSel && s.default_fingerprint) fpSel.value=s.default_fingerprint;
          if(alpnIn) alpnIn.value=s.default_alpn||'http/1.1';
          if(sniIn) sniIn.value=s.sni_override||'';
          // toggles
          const mapToggle={'مسدودسازی IPهای خصوصی':'restrict_ips','مسدودسازی تبلیغات':'block_ads','مسدودسازی سایت‌های ایرانی':'block_iran_sites','اعلان اتصال جدید':'notify_new_conn','فعال‌سازی Fragment':'fragment_enabled','پشتیبان‌گیری خودکار':'backup_enabled'};
          $$('.toggle-row',settingsSection).forEach(row=>{
            const label=(row.textContent||'').trim();
            for(const [k,ck] of Object.entries(mapToggle)){
              if(label.includes(k)){
                const sw=row.querySelector('.switch');
                if(sw){
                  const on=!!s[ck];
                  sw.classList.toggle('on', on);
                  sw.onclick=()=> sw.classList.toggle('on');
                }
              }
            }
          });
          const fragLen=[...settingsSection.querySelectorAll('input')].find(i=> i.value==='10-30');
          const fragInt=[...settingsSection.querySelectorAll('input')].find(i=> i.value==='10-20');
          if(fragLen) fragLen.value=s.fragment_length||'10-30';
          if(fragInt) fragInt.value=s.fragment_interval||'10-20';
          const backupInt=[...settingsSection.querySelectorAll('input')].find(i=> i.type==='number' && i.value==='24');
          // actually backup interval is number input
          const allNum=[...settingsSection.querySelectorAll('input[type="number"]')];
          // find backup interval by label
          const backupField=[...settingsSection.querySelectorAll('.field')].find(f=> f.textContent.includes('بازه پشتیبان'));
          if(backupField){
            const inp=backupField.querySelector('input');
            if(inp) inp.value=s.backup_interval_hours||24;
          }
          // update notice about password
          const notice=settingsSection.querySelector('.notice');
          if(notice){
            const me=await apiJson('/api/me').catch(()=>null);
            if(me && !me.default_auth) notice.style.display='none';
            else notice.style.display='block';
          }
        }catch(e){ console.error(e); }
      }
      loadSettings();
      if(saveBtn) saveBtn.onclick=async()=>{
        const body={};
        if(publicDomain) body.public_domain=publicDomain.value.trim();
        if(publicPort) body.public_port=publicPort.value.trim();
        if(transportSel) body.default_transport=(transportSel.value||'ws').toLowerCase();
        if(fpSel) body.default_fingerprint=fpSel.value;
        if(alpnIn) body.default_alpn=alpnIn.value;
        if(sniIn) body.sni_override=sniIn.value.trim();
        // toggles
        const mapToggle={'مسدودسازی IPهای خصوصی':'restrict_ips','مسدودسازی تبلیغات':'block_ads','مسدودسازی سایت‌های ایرانی':'block_iran_sites','اعلان اتصال جدید':'notify_new_conn','فعال‌سازی Fragment':'fragment_enabled','پشتیبان‌گیری خودکار':'backup_enabled'};
        $$('.toggle-row',settingsSection).forEach(row=>{
          const label=(row.textContent||'').trim();
          for(const [k,ck] of Object.entries(mapToggle)){
            if(label.includes(k)){
              const sw=row.querySelector('.switch');
              if(sw) body[ck]=sw.classList.contains('on');
            }
          }
        });
        const fragLen=[...settingsSection.querySelectorAll('input')].find(i=> i.placeholder==='' && i.value.includes('-') && i.value!=='10-20');
        // more robust: find by label
        const fragLenField=[...settingsSection.querySelectorAll('.field')].find(f=> f.textContent.includes('طول Fragment'));
        if(fragLenField) body.fragment_length=fragLenField.querySelector('input').value;
        const fragIntField=[...settingsSection.querySelectorAll('.field')].find(f=> f.textContent.includes('بازه Fragment'));
        if(fragIntField) body.fragment_interval=fragIntField.querySelector('input').value;
        const backupField=[...settingsSection.querySelectorAll('.field')].find(f=> f.textContent.includes('بازه پشتیبان'));
        if(backupField) body.backup_interval_hours=parseInt(backupField.querySelector('input').value)||24;

        try{ await apiJson('/api/settings',{method:'POST',body}); toast('تنظیمات ذخیره شد'); }
        catch(e){ toast(e.message); }
      };
      if(changeBtn) changeBtn.onclick=async()=>{
        const oldV=oldPass?oldPass.value:''; const newV=newPass?newPass.value:'';
        if(!newV || newV.length<6){ toast('رمز جدید باید حداقل ۶ کاراکتر باشد'); return; }
        try{ await apiJson('/api/change-password',{method:'POST',body:{old_password:oldV,new_password:newV}}); toast('رمز عبور تغییر کرد'); if(oldPass) oldPass.value=''; if(newPass) newPass.value=''; }
        catch(e){ toast(e.message==='wrong-old-password'?'رمز فعلی اشتباه است':e.message); }
      };
      const dlBtn=[...settingsSection.querySelectorAll('button')].find(b=> (b.textContent||'').includes('دانلود پشتیبان'));
      if(dlBtn) dlBtn.onclick=()=>{ location.href='/api/backup'; };
      const restoreBtn=[...settingsSection.querySelectorAll('button')].find(b=> (b.textContent||'').includes('بازیابی'));
      if(restoreBtn) restoreBtn.onclick=()=>{
        const inp=document.createElement('input'); inp.type='file'; inp.accept='.b64,.gz';
        inp.onchange=async()=>{
          const file=inp.files[0]; if(!file) return; if(!confirm('بازیابی از پشتیبان؟')) return;
          const fd=new FormData(); fd.append('file',file);
          try{ const r=await fetch('/api/backup/restore',{method:'POST',body:fd,credentials:'same-origin'}); const d=await r.json().catch(()=>({})); if(r.ok) toast('بازیابی شد'); else toast(d.detail||'خطا'); }catch(e){ toast(e.message); }
        };
        inp.click();
      };
      const restartBtn=settingsSection.querySelector('.danger-btn');
      if(restartBtn) restartBtn.onclick=async()=>{ if(!confirm('راه‌اندازی مجدد پنل؟')) return; try{ await apiJson('/api/restart',{method:'POST'}); toast('در حال راه‌اندازی...'); }catch(e){ toast(e.message); } };
      // avatar in settings
      const avatarBtn=[...settingsSection.querySelectorAll('button')].find(b=> (b.textContent||'').includes('گالری'));
      if(avatarBtn) avatarBtn.onclick=async()=>{
        const me=await apiJson('/api/me').catch(()=>null);
        const cur=me&&me.avatar?me.avatar.key:'';
        const k=await openGalleryPicker(cur);
        if(k==null) return;
        try{ await apiJson('/api/admin-avatar',{method:'POST',body:{avatar:k}}); toast('تصویر ذخیره شد'); loadMe(); }
        catch(e){ toast(e.message); }
      };
      $$('button',settingsSection).forEach(b=>{ if(b.dataset.demo) b.removeAttribute('data-demo'); });
    }

    const adminsSection=document.querySelector('.section-view[data-section="admins"]');
    if(adminsSection){
      async function refreshAdmins(){
        try{
          const info=await apiJson('/api/admin-info');
          // update avatar in the table
          const imgs=adminsSection.querySelectorAll('.avatar img');
          imgs.forEach(img=>{ if(info.avatar&&info.avatar.url) img.src=info.avatar.url; });
          const nameCell=adminsSection.querySelector('.data-table tbody td');
          if(nameCell && info.username) nameCell.textContent=info.username;
        }catch(e){}
      }
      refreshAdmins(); document.addEventListener('titan:refresh', refreshAdmins);
    }

    const toolsSection=document.querySelector('.section-view[data-section="tools"]');
    if(toolsSection){
      const testBtn=[...toolsSection.querySelectorAll('button')].find(b=> (b.textContent||'').includes('تست اتصال'));
      if(testBtn) testBtn.onclick=async()=>{
        testBtn.disabled=true; const old=testBtn.textContent; testBtn.textContent='در حال تست...';
        try{ const r=await apiJson('/api/connection-test'); toast('Xray: '+(r.xray_running?'فعال':'غیرفعال')+' - WS: '+(r.internal_ports_open&&r.internal_ports_open['vless-ws']?'ok':'fail')); }catch(e){ toast(e.message); } finally{ testBtn.disabled=false; testBtn.textContent=old; }
      };
      $$('button',toolsSection).forEach(b=>{ if(b.dataset.demo) b.removeAttribute('data-demo'); });
    }
  }

  // --- header & sidebar wiring ---
  document.addEventListener('DOMContentLoaded', ()=>{
    loadMe(); loadOverview(); setTimeout(wireDetails, 400);

    const gSearch=document.querySelector('.search input[type="search"]');
    if(gSearch){
      gSearch.addEventListener('input', ()=>{
        const q=gSearch.value.trim().toLowerCase();
        $$('.recent-table-row').forEach(r=> r.style.display=r.textContent.toLowerCase().includes(q)?'':'none');
      });
      document.addEventListener('keydown', e=>{ if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){ e.preventDefault(); gSearch.focus(); } });
    }
    const refreshBtn=document.querySelectorAll('.action')[1];
    if(refreshBtn) refreshBtn.onclick=()=>{ loadOverview(); toast('به‌روزرسانی شد'); };

    // profile: click avatar -> change picture (not just logout)
    const prof=document.querySelector('.header .profile');
    const profAv=document.querySelector('.header .profile .avatar');
    if(profAv){
      profAv.style.cursor='pointer';
      profAv.title='تغییر تصویر پروفایل';
      profAv.onclick=async (e)=>{
        e.stopPropagation();
        try{
          const me=await apiJson('/api/me');
          const cur=me.avatar?me.avatar.key:'';
          const k=await openGalleryPicker(cur);
          if(k==null) return;
          await apiJson('/api/admin-avatar',{method:'POST',body:{avatar:k}});
          toast('تصویر پروفایل ذخیره شد');
          loadMe();
        }catch(err){ toast(err.message); }
      };
    }
    // profile container click -> show menu with avatar change + logout
    if(prof){
      // add a small logout icon next to profile if not exists
      if(!$('#headerLogout')){
        const lo=document.createElement('button');
        lo.id='headerLogout';
        lo.title='خروج';
        lo.style.cssText='width:32px;height:32px;border-radius:9px;border:1px solid rgba(151,116,255,.18);background:rgba(91,49,176,.1);color:#c5c5df;display:grid;place-items:center;cursor:pointer;margin-right:6px';
        lo.innerHTML='<svg viewBox="0 0 24 24" style="width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.7"><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/><path d="M13 21H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7"/></svg>';
        lo.onclick=async()=>{
          if(confirm('خروج از حساب؟')){ try{ await apiJson('/api/logout',{method:'POST'}); location.href='/login'; }catch(e){ location.href='/login'; } }
        };
        const actions=document.querySelector('.actions');
        if(actions) actions.appendChild(lo);
      }
    }
    const ver=document.querySelector('.version');
    if(ver) ver.onclick=()=> toast('TiTaN Panel');

    // sidebar version avatar also clickable to change
    const verLogo=document.querySelector('.version-logo');
    if(verLogo){
      verLogo.style.cursor='pointer';
      verLogo.onclick=async()=>{
        try{
          const me=await apiJson('/api/me');
          const cur=me.avatar?me.avatar.key:'';
          const k=await openGalleryPicker(cur);
          if(k!=null){ await apiJson('/api/admin-avatar',{method:'POST',body:{avatar:k}}); toast('تصویر ذخیره شد'); loadMe(); }
        }catch(e){ toast(e.message); }
      };
    }

    function handleHash(){
      const h=location.hash||'';
      const map={'#/dashboard':0,'#/users':1,'#/configs':2,'#/nodes':3,'#/subscriptions':4,'#/reports':5,'#/settings':6,'#/admins':7,'#/tools':8};
      const idx=map[h];
      if(idx!=null){ const nav=document.querySelectorAll('.nav-item'); if(nav[idx]) nav[idx].click(); }
    }
    window.addEventListener('hashchange', handleHash); handleHash();
  });

  window._titanRefresh=()=>{ loadOverview(); document.dispatchEvent(new Event('titan:refresh')); };
})();
