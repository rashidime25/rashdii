/* TiTaN — bridge to make the uploaded design functional while keeping its exact visuals */
(() => {
  'use strict';
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));

  // --- helpers ---
  function fmtBytes(b){
    b = Number(b)||0;
    if(b===0) return '0 B';
    const u=['B','KB','MB','GB','TB']; let i=0;
    while(b>=1024 && i<u.length-1){b/=1024;i++;}
    return (i===0? b : b.toFixed(b>=10?1:2).replace(/\.0+$/,''))+' '+u[i];
  }
  function esc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c])); }
  function flagFor(cc){
    cc=(cc||'').toUpperCase().trim();
    if(/^[A-Z]{2}$/.test(cc)) return String.fromCodePoint(...[...cc].map(c=>0x1F1E6 + c.charCodeAt(0)-65));
    return '🏳️';
  }
  async function apiJson(url, opts={}){
    opts.credentials='same-origin';
    opts.headers = Object.assign({'Content-Type':'application/json'}, opts.headers||{});
    if(opts.body && typeof opts.body!=='string') opts.body=JSON.stringify(opts.body);
    const r=await fetch(url, opts);
    let d={};
    try{ d=await r.json(); }catch(e){ if(!r.ok) throw new Error(r.statusText); }
    if(!r.ok) throw new Error(d.detail||d.message||r.statusText);
    return d;
  }

  // --- toast (reuse existing or create) ---
  let toastEl = $('#titanToast');
  if(!toastEl){
    toastEl=document.createElement('div');
    toastEl.id='titanToast';
    toastEl.style.cssText='position:fixed;left:50%;bottom:22px;transform:translate(-50%,14px);opacity:0;pointer-events:none;padding:10px 16px;border-radius:12px;color:#eeeaff;background:rgba(6,8,35,.94);border:1px solid rgba(104,77,255,.45);box-shadow:0 0 24px rgba(75,40,255,.18);backdrop-filter:blur(12px);transition:.24s;z-index:9999;font-size:12px;';
    document.body.appendChild(toastEl);
  }
  function toast(msg){
    toastEl.textContent=msg;
    toastEl.style.opacity='1'; toastEl.style.transform='translate(-50%,0)';
    clearTimeout(toastEl._t);
    toastEl._t=setTimeout(()=>{toastEl.style.opacity='0';toastEl.style.transform='translate(-50%,14px)';}, 2200);
  }

  // --- populate header ---
  async function loadMe(){
    try{
      const me = await apiJson('/api/me');
      if(me.username){
        const pn = $('.profile-name'); if(pn) pn.textContent=me.username;
        const pr = $('.profile-role'); if(pr) pr.innerHTML='<span class="dot"></span> '+(me.username==='TiTaN'?'ادمین کل':'مدیر');
      }
      if(me.avatar && me.avatar.url){
        const av = $('.profile .avatar img'); if(av) av.src=me.avatar.url;
      }
      // header profile name also in welcome
      const w = $('.welcome h1'); if(w && me.username) w.textContent='خوش آمدید، '+me.username;
    }catch(e){}
  }

  // --- load overview stats ---
  async function loadOverview(){
    try{
      const [stats, usersRes, nodesRes] = await Promise.all([
        apiJson('/api/stats'),
        apiJson('/api/users'),
        apiJson('/api/nodes')
      ]);
      const users = usersRes.users||[];
      const nodes = nodesRes.nodes||[];
      const online = nodes.filter(n=>n.enabled && n.status && n.status.online).length;
      // version
      const vv = $('.version-v'); if(vv && stats.app_version) vv.textContent='v'+stats.app_version;
      const vt = $('.version-title'); if(vt) vt.textContent='TiTaN';
      // stats cards - mapping: users, traffic, servers, configs (left to right in design is Active users, Used traffic, Servers, Active configs)
      // In new design, order is: card.users (active users), card.traffic, card.servers, card.configs
      const totalTraffic = (stats.total_up||0)+(stats.total_down||0);
      const activeUsers = users.filter(u=>u.enabled && !(u.status && u.status.expired) && (u.status && u.status.live_enabled)).length;
      // card.users
      const cu = document.querySelector('.card.users .card-number');
      if(cu) cu.textContent = String(activeUsers);
      const cum = document.querySelector('.card.users .card-meta');
      if(cum) cum.textContent = 'از '+users.length+' کاربر';
      // card.traffic
      const ct = document.querySelector('.card.traffic .card-number');
      if(ct) ct.textContent = fmtBytes(totalTraffic);
      const ctm = document.querySelector('.card.traffic .card-meta');
      if(ctm) ctm.innerHTML = `MB ↓ ${fmtBytes(stats.total_down||0)} &nbsp; ↑ ${fmtBytes(stats.total_up||0)}`;
      // card.servers
      const cs = document.querySelector('.card.servers .card-number');
      if(cs) cs.textContent = String(nodes.length);
      const csm = document.querySelector('.card.servers .card-meta');
      if(csm) csm.innerHTML = `<span class="green">● ${online} آنلاین</span>`;
      // card.configs (active configs = enabled users)
      const cc = document.querySelector('.card.configs .card-number');
      if(cc) cc.textContent = String(stats.enabled_count||0);
      const ccm = document.querySelector('.card.configs .card-meta');
      if(ccm) ccm.textContent = 'از '+users.length+' کانفیگ';

      // server status panel
      const srvContent = $('.server-content');
      if(srvContent){
        if(nodes.length){
          srvContent.innerHTML = nodes.slice(0,4).map(n=>{
            const st=n.status||{};
            const lat = st.latency_ms!=null? st.latency_ms+'ms' : '—';
            const city = (n.city && n.city!=='—')? n.city : n.name;
            const cc = (n.country_code||'').toUpperCase();
            const flag = n.flag || flagFor(cc) || '🌐';
            const on = n.enabled && st.online;
            return `<div class="server-row">
              <div class="latency">${esc(lat)}<small>تاخیر</small></div>
              <div class="status" style="color:${on?'#39e1b9':'#ff6b8a'}">${on?'آنلاین':'آفلاین'}</div>
              <div class="location"><span class="flag">${esc(flag)}</span><span>${esc(city)}${cc? ' · '+esc(cc):''}</span></div>
            </div>`;
          }).join('');
        } else {
          srvContent.innerHTML = '<div style="color:#8586a8;font-size:11px;padding:12px">سروری ثبت نشده است.</div>';
        }
      }

      // recent users (users-table)
      const ruHead = document.querySelector('.recent-panel.users-table .recent-table');
      if(ruHead){
        // keep head, replace rows
        const rows = ruHead.querySelectorAll('.recent-table-row');
        rows.forEach(r=>r.remove());
        const recent = [...users].sort((a,b)=>(b.created_at||0)-(a.created_at||0)).slice(0,3);
        if(recent.length===0){
          ruHead.insertAdjacentHTML('beforeend','<div style="padding:14px;color:#8586a8;font-size:11px">کاربری وجود ندارد.</div>');
        } else {
          recent.forEach(u=>{
            const av = (u.avatar_url||'/static/img/titan-avatar.svg');
            const st = u.status||{};
            const used = fmtBytes(st.used||0);
            const label = st.expired? 'منقضی' : (!u.enabled? 'غیرفعال' : 'فعال');
            const row = document.createElement('div');
            row.className='recent-table-row';
            row.innerHTML=`
              <div class="recent-user"><span class="recent-avatar user-avatar"><img src="${esc(av)}" alt=""></span><span class="recent-name">${esc(u.name)}</span></div>
              <div class="recent-traffic">${esc(used)}</div>
              <div class="recent-status">${esc(label)}</div>`;
            ruHead.appendChild(row);
          });
        }
      }
      // recent configs
      const rcHead = document.querySelector('.recent-panel.configs-table .recent-table');
      if(rcHead){
        rcHead.querySelectorAll('.recent-table-row').forEach(r=>r.remove());
        const nodeMap={}; nodes.forEach(n=>nodeMap[n.id]=n);
        const recent = [...users].sort((a,b)=>(b.created_at||0)-(a.created_at||0)).slice(0,3);
        if(recent.length===0){
          rcHead.insertAdjacentHTML('beforeend','<div style="padding:14px;color:#8586a8;font-size:11px">کانفیگی وجود ندارد.</div>');
        } else {
          recent.forEach(u=>{
            const av = (u.avatar_url||'/static/img/titan-avatar.svg');
            const n = nodeMap[u.node_id||1];
            const flag = n? (n.flag||flagFor(n.country_code)||'🌐') : '🌐';
            const loc = n? ((n.city && n.city!=='—')? n.city : n.name) : '—';
            const st = u.status||{};
            const label = st.expired? 'منقضی' : (!u.enabled? 'غیرفعال' : 'فعال');
            const row=document.createElement('div');
            row.className='recent-table-row';
            row.innerHTML=`
              <div class="recent-config"><span class="recent-avatar user-avatar"><img src="${esc(av)}" alt=""></span><span class="recent-name">${esc(u.name)}</span></div>
              <div>${esc((u.protocol||'').toUpperCase())}</div>
              <div class="recent-server"><span class="flag">${esc(flag)}</span><span>${esc(loc)}</span></div>
              <div class="recent-status">${esc(label)}</div>`;
            rcHead.appendChild(row);
          });
        }
      }

      // chart - keep static for now, but we could make dynamic later
    }catch(e){ console.error('loadOverview',e); }
  }

  // --- detailed views ---
  function wireDetails(){
    // users section table
    const usersSection = document.querySelector('.section-view[data-section="users"]');
    if(usersSection){
      const tbody = usersSection.querySelector('.data-table tbody');
      const search = usersSection.querySelector('[data-filter="users"]');
      async function refreshUsers(){
        try{
          const d = await apiJson('/api/users');
          const users = d.users||[];
          // update metrics
          const cards = usersSection.querySelectorAll('.detail-card');
          // first card: total/active
          // we can update counts
          const totalEl = usersSection.querySelector('.section-grid .detail-card:first-child .metric-row strong');
          // simpler: just render table
          if(tbody){
            tbody.innerHTML = users.length? users.map(u=>{
              const st=u.status||{};
              const used=fmtBytes(st.used||0);
              const days = u.expire_at? Math.max(0,Math.ceil((u.expire_at - Date.now()/1000)/86400))+' روز' : 'هرگز';
              const label = st.expired? 'منقضی' : (!u.enabled? 'غیرفعال':'فعال');
              const cls = st.expired? 'warn' : (!u.enabled? 'off':'');
              return `<tr><td><span class="user-cell"><span class="avatar user-avatar"><img src="${esc(u.avatar_url||'/static/img/titan-avatar.svg')}" alt=""></span>${esc(u.name)}</span></td><td class="muted">#${esc(u.uid.slice(0,6))}</td><td>${esc(used)}</td><td>${esc(days)}</td><td><span class="pill ${cls}">${esc(label)}</span></td><td><button class="mini-btn" data-uid="${esc(u.uid)}" data-act="detail">جزئیات</button> <button class="mini-btn" data-uid="${esc(u.uid)}" data-act="del" style="color:#ff8297">حذف</button></td></tr>`;
            }).join('') : '<tr><td colspan="6" style="text-align:center;color:#8586a8">کاربری وجود ندارد</td></tr>';
            // wire delete/detail
            tbody.querySelectorAll('[data-act="del"]').forEach(b=>{
              b.addEventListener('click', async ()=>{
                const uid=b.dataset.uid;
                if(!confirm('حذف کاربر؟')) return;
                try{ await apiJson('/api/users/'+uid,{method:'DELETE'}); toast('حذف شد'); refreshUsers(); loadOverview(); }catch(e){toast(e.message);}
              });
            });
            tbody.querySelectorAll('[data-act="detail"]').forEach(b=>{
              b.addEventListener('click', async ()=>{
                const uid=b.dataset.uid;
                try{
                  const u = await apiJson('/api/users/'+uid);
                  const links = await apiJson('/api/users/'+uid+'/links');
                  alert('لینک: '+(links.main_link||links.links?.[0]||'—')+'\n\nاشتراک: '+links.sub_url);
                }catch(e){toast(e.message);}
              });
            });
          }
          // update header count
          const cnt = usersSection.querySelector('.data-card .muted');
          if(cnt) cnt.textContent = users.length+' مورد';
        }catch(e){ console.error(e); }
      }
      refreshUsers();
      // search filter already handled by existing script, but also wire our tbody
      if(search){
        search.addEventListener('input', ()=>{
          const q=search.value.trim().toLowerCase();
          if(!tbody) return;
          tbody.querySelectorAll('tr').forEach(tr=>{
            tr.style.display = tr.textContent.toLowerCase().includes(q)?'':'none';
          });
        });
      }
      // add user button
      const addBtn = usersSection.querySelector('.section-btn.primary');
      if(addBtn){
        addBtn.addEventListener('click', ()=> openUserModal());
      }
    }

    // configs section
    const configsSection = document.querySelector('.section-view[data-section="configs"]');
    if(configsSection){
      const tbody = configsSection.querySelector('.data-table tbody');
      async function refreshConfigs(){
        try{
          const [uRes, nRes]=await Promise.all([apiJson('/api/users'), apiJson('/api/nodes')]);
          const users=uRes.users||[];
          const nodes=nRes.nodes||[];
          const nodeMap={}; nodes.forEach(n=>nodeMap[n.id]=n);
          if(tbody){
            tbody.innerHTML = users.length? users.map(u=>{
              const n=nodeMap[u.node_id||1];
              const loc = n? ((n.city && n.city!=='—')?n.city:n.name) : '—';
              const flag=n? (n.flag||flagFor(n.country_code)||'🌐'):'🌐';
              const st=u.status||{};
              const label = st.expired?'منقضی':(!u.enabled?'غیرفعال':'فعال');
              const cls = st.expired?'warn':(!u.enabled?'off':'');
              return `<tr><td><span class="user-cell"><span class="avatar user-avatar"><img src="${esc(u.avatar_url||'/static/img/titan-avatar.svg')}" alt=""></span>${esc(u.name)}</span></td><td>${esc((u.protocol||'').toUpperCase())}</td><td>${esc(flag)} ${esc(loc)}</td><td>443</td><td><span class="pill ${cls}">${esc(label)}</span></td><td><button class="mini-btn" data-uid="${esc(u.uid)}" data-act="links">لینک</button> <button class="mini-btn" data-uid="${esc(u.uid)}" data-act="del" style="color:#ff8297">حذف</button></td></tr>`;
            }).join('') : '<tr><td colspan="6" style="text-align:center;color:#8586a8">کانفیگی وجود ندارد</td></tr>';
            tbody.querySelectorAll('[data-act="del"]').forEach(b=>{
              b.addEventListener('click', async ()=>{
                const uid=b.dataset.uid;
                if(!confirm('حذف کانفیگ؟')) return;
                try{ await apiJson('/api/users/'+uid,{method:'DELETE'}); toast('حذف شد'); refreshConfigs(); loadOverview(); }catch(e){toast(e.message);}
              });
            });
            tbody.querySelectorAll('[data-act="links"]').forEach(b=>{
              b.addEventListener('click', async ()=>{
                const uid=b.dataset.uid;
                try{
                  const d=await apiJson('/api/users/'+uid+'/links');
                  const txt = (d.links||[]).join('\\n')+'\\n\\nاشتراک: '+d.sub_url;
                  // simple copy
                  await navigator.clipboard.writeText(d.main_link||d.links[0]||txt);
                  toast('لینک کپی شد');
                }catch(e){toast(e.message);}
              });
            });
          }
        }catch(e){console.error(e);}
      }
      refreshConfigs();
      const addBtn = configsSection.querySelector('.section-btn.primary');
      if(addBtn) addBtn.addEventListener('click', ()=> openUserModal());
    }

    // servers section
    const serversSection = document.querySelector('.section-view[data-section="servers"]');
    if(serversSection){
      async function refreshServers(){
        try{
          const d=await apiJson('/api/nodes');
          const nodes=d.nodes||[];
          const grid = serversSection.querySelector('.section-grid');
          if(grid){
            // keep first 3 detail cards but update counts
            // we will also ensure a table/list exists; if not, create
            let list = serversSection.querySelector('.server-list');
            if(!list){
              list=document.createElement('div');
              list.className='detail-card data-card server-list';
              list.style.marginTop='14px';
              list.innerHTML='<div class="card-title"><h3 style="margin:0">فهرست سرورها</h3></div><div class="table-scroll"><table class="data-table"><thead><tr><th>نام</th><th>آدرس</th><th>وضعیت</th><th>پینگ</th><th>عملیات</th></tr></thead><tbody></tbody></table></div>';
              serversSection.appendChild(list);
            }
            const tbody=list.querySelector('tbody');
            tbody.innerHTML = nodes.length? nodes.map(n=>{
              const st=n.status||{};
              const on=n.enabled && st.online;
              const flag=n.flag||flagFor(n.country_code)||'🌐';
              return `<tr><td>${esc(flag)} ${esc(n.name)}</td><td style="direction:ltr">${esc(n.address||'—')}</td><td><span class="pill ${on?'':'off'}">${on?'آنلاین':'آفلاین'}</span></td><td>${st.latency_ms!=null? st.latency_ms+'ms':'—'}</td><td><button class="mini-btn" data-id="${n.id}" data-act="ping">بررسی</button> ${!n.is_local?'<button class="mini-btn" data-id="'+n.id+'" data-act="del" style="color:#ff8297">حذف</button>':''}</td></tr>`;
            }).join('') : '<tr><td colspan="5" style="text-align:center;color:#8586a8">سروری وجود ندارد</td></tr>';
            tbody.querySelectorAll('[data-act="ping"]').forEach(b=>{
              b.addEventListener('click', async ()=>{
                const id=b.dataset.id;
                b.disabled=true; b.textContent='...';
                try{
                  await apiJson('/api/nodes/'+id+'/ping',{method:'POST'});
                  toast('بررسی شد');
                  refreshServers(); loadOverview();
                }catch(e){toast(e.message);} finally{ b.disabled=false; b.textContent='بررسی';}
              });
            });
            tbody.querySelectorAll('[data-act="del"]').forEach(b=>{
              b.addEventListener('click', async ()=>{
                const id=b.dataset.id;
                if(!confirm('حذف سرور؟')) return;
                try{ await apiJson('/api/nodes/'+id,{method:'DELETE'}); toast('حذف شد'); refreshServers(); loadOverview(); }catch(e){toast(e.message);}
              });
            });
          }
        }catch(e){console.error(e);}
      }
      refreshServers();
      const addBtn = serversSection.querySelector('.section-btn.primary');
      if(addBtn) addBtn.addEventListener('click', ()=> openNodeModal());
      const pingBtn = serversSection.querySelector('.section-btn:not(.primary)');
      if(pingBtn) pingBtn.addEventListener('click', refreshServers);
    }

    // subscriptions
    const subsSection = document.querySelector('.section-view[data-section="subscriptions"]');
    if(subsSection){
      async function refreshSubs(){
        try{
          const d=await apiJson('/api/users');
          const users=d.users||[];
          const tbody=subsSection.querySelector('.data-table tbody');
          if(tbody){
            tbody.innerHTML = users.length? users.map(u=>{
              const st=u.status||{};
              const label = st.expired?'منقضی':(!u.enabled?'غیرفعال':'فعال');
              const cls = st.expired?'warn':(!u.enabled?'off':'');
              const exp = u.expire_at? new Date(u.expire_at*1000).toLocaleDateString('fa-IR') : 'هرگز';
              return `<tr><td><span class="user-cell"><span class="avatar user-avatar"><img src="${esc(u.avatar_url||'/static/img/titan-avatar.svg')}" alt=""></span>${esc(u.name)}</span></td><td><span class="pill ${cls}">${esc(label)}</span></td><td>${esc(exp)}</td><td>1</td><td>${esc(fmtBytes(st.used||0))}</td><td><button class="mini-btn" data-uid="${u.uid}" data-act="copy"><span class="subscription-icon">⎘</span></button><button class="mini-btn" data-uid="${u.uid}" data-act="qr">QR</button><button class="mini-btn" data-uid="${u.uid}" data-act="view">👁</button></td></tr>`;
            }).join('') : '<tr><td colspan="6" style="text-align:center;color:#8586a8">اشتراکی وجود ندارد</td></tr>';
            tbody.querySelectorAll('[data-act="copy"]').forEach(b=>{
              b.addEventListener('click', async ()=>{
                const uid=b.dataset.uid;
                try{
                  const d=await apiJson('/api/users/'+uid+'/links');
                  await navigator.clipboard.writeText(d.sub_url);
                  toast('اشتراک کپی شد');
                }catch(e){toast(e.message);}
              });
            });
            tbody.querySelectorAll('[data-act="qr"]').forEach(b=>{
              b.addEventListener('click', ()=>{
                const uid=b.dataset.uid;
                window.open('/api/users/'+uid+'/qr','_blank');
              });
            });
            tbody.querySelectorAll('[data-act="view"]').forEach(b=>{
              b.addEventListener('click', async ()=>{
                const uid=b.dataset.uid;
                try{
                  const d=await apiJson('/api/users/'+uid+'/links');
                  const txt=(d.links||[]).join('\\n');
                  await navigator.clipboard.writeText(d.main_link||txt);
                  toast('لینک کپی شد');
                }catch(e){toast(e.message);}
              });
            });
          }
        }catch(e){console.error(e);}
      }
      refreshSubs();
    }

    // reports
    const reportsSection = document.querySelector('.section-view[data-section="reports"]');
    if(reportsSection){
      async function refreshReports(){
        try{
          const r=await apiJson('/api/reports?days=7');
          const t=r.totals||{};
          const cards=reportsSection.querySelectorAll('.section-grid .detail-card');
          // update metrics if needed
        }catch(e){}
      }
      refreshReports();
    }

    // settings
    const settingsSection = document.querySelector('.section-view[data-section="settings"]');
    if(settingsSection){
      const publicDomain = settingsSection.querySelector('input[placeholder="example.com"]');
      const publicPort = settingsSection.querySelector('input[value="443"]');
      const saveBtn = settingsSection.querySelector('.section-btn.primary');
      const oldPass = settingsSection.querySelector('input[placeholder="••••••••"]');
      const newPass = settingsSection.querySelector('input[placeholder="رمز عبور جدید"]');
      const changeBtn = settingsSection.querySelector('button[data-demo="تغییر رمز عبور"]');
      let settingsData=null;
      async function loadSettings(){
        try{
          const s=await apiJson('/api/settings');
          settingsData=s;
          if(publicDomain) publicDomain.value=s.public_domain||'';
          if(publicPort) publicPort.value=s.public_port||'443';
          // fill other fields if present
          const transportSel = settingsSection.querySelector('select');
          // ... more mappings can be added
        }catch(e){}
      }
      loadSettings();
      if(saveBtn){
        saveBtn.addEventListener('click', async ()=>{
          const body={};
          if(publicDomain) body.public_domain=publicDomain.value.trim();
          if(publicPort) body.public_port=publicPort.value.trim();
          try{
            await apiJson('/api/settings',{method:'POST',body});
            toast('تنظیمات ذخیره شد');
          }catch(e){toast(e.message);}
        });
      }
      if(changeBtn){
        changeBtn.addEventListener('click', async ()=>{
          const oldV=oldPass?oldPass.value:'';
          const newV=newPass?newPass.value:'';
          if(!newV || newV.length<6){ toast('رمز جدید باید حداقل ۶ کاراکتر باشد'); return;}
          try{
            await apiJson('/api/change-password',{method:'POST',body:{old_password:oldV,new_password:newV}});
            toast('رمز عبور تغییر کرد');
            if(oldPass) oldPass.value=''; if(newPass) newPass.value='';
          }catch(e){toast(e.message==='wrong-old-password'?'رمز فعلی اشتباه است':e.message);}
        });
      }
      // backup buttons
      const dlBtn = settingsSection.querySelector('button[data-demo="دانلود پشتیبان"]');
      if(dlBtn) dlBtn.addEventListener('click', ()=>{ location.href='/api/backup'; });
      const restoreBtn = settingsSection.querySelector('button[data-demo="بازیابی از پشتیبان"]') || settingsSection.querySelector('button[data-demo="بازیابی پشتیبان"]');
      if(restoreBtn){
        restoreBtn.addEventListener('click', ()=>{
          const inp=document.createElement('input'); inp.type='file'; inp.accept='.b64,.gz';
          inp.onchange=async ()=>{
            const file=inp.files[0]; if(!file) return;
            if(!confirm('بازیابی از پشتیبان؟')) return;
            const fd=new FormData(); fd.append('file',file);
            try{
              const r=await fetch('/api/backup/restore',{method:'POST',body:fd,credentials:'same-origin'});
              const d=await r.json().catch(()=>({}));
              if(r.ok) toast('بازیابی شد'); else toast(d.detail||'خطا');
            }catch(e){toast(e.message);}
          };
          inp.click();
        });
      }
      const restartBtn = settingsSection.querySelector('.danger-btn');
      if(restartBtn) restartBtn.addEventListener('click', async ()=>{
        if(!confirm('راه‌اندازی مجدد پنل؟')) return;
        try{ await apiJson('/api/restart',{method:'POST'}); toast('در حال راه‌اندازی...'); }catch(e){toast(e.message);}
      });
    }

    // admins
    const adminsSection = document.querySelector('.section-view[data-section="admins"]');
    if(adminsSection){
      async function refreshAdmins(){
        try{
          const info=await apiJson('/api/admin-info');
          const nameEl=adminsSection.querySelector('.data-table tbody td');
          // update avatar
          const av = adminsSection.querySelector('.avatar img');
          if(av && info.avatar && info.avatar.url) av.src=info.avatar.url;
        }catch(e){}
      }
      refreshAdmins();
    }

    // tools
    const toolsSection = document.querySelector('.section-view[data-section="tools"]');
    if(toolsSection){
      const testBtn = toolsSection.querySelector('button[data-demo="تست اتصال"]') || toolsSection.querySelector('button[data-demo="اجرای تست اتصال"]');
      if(testBtn){
        testBtn.addEventListener('click', async ()=>{
          testBtn.disabled=true; const old=testBtn.textContent; testBtn.textContent='در حال تست...';
          try{
            const r=await apiJson('/api/connection-test');
            alert('Xray: '+(r.xray_running?'فعال':'غیرفعال')+'\\nپنل: '+r.public?.ws_path_routed);
          }catch(e){toast(e.message);} finally{ testBtn.disabled=false; testBtn.textContent=old; }
        });
      }
    }
  }

  // --- modals (simple) ---
  function createModal(title, bodyHtml, onSave){
    // remove existing
    const ex=$('#titanModal'); if(ex) ex.remove();
    const overlay=document.createElement('div');
    overlay.id='titanModal';
    overlay.style.cssText='position:fixed;inset:0;z-index:9998;background:rgba(2,4,18,.62);backdrop-filter:blur(8px);display:grid;place-items:center;padding:18px;';
    overlay.innerHTML=`<div style="width:min(560px,96vw);max-height:90vh;overflow:auto;background:linear-gradient(145deg,rgba(24,12,56,.96),rgba(8,6,26,.98));border:1px solid rgba(151,116,255,.42);border-radius:18px;box-shadow:0 0 30px rgba(94,48,205,.22);">
      <div style="padding:18px 20px;border-bottom:1px solid rgba(151,116,255,.18);display:flex;align-items:center;justify-content:space-between"><div style="font-weight:700;color:#f2edff">${esc(title)}</div><button id="titanModalClose" style="width:32px;height:32px;border-radius:9px;border:1px solid rgba(151,116,255,.24);background:rgba(91,49,176,.16);color:#d8c7ff;cursor:pointer">×</button></div>
      <div style="padding:18px 20px">${bodyHtml}</div>
      <div style="padding:14px 20px;border-top:1px solid rgba(151,116,255,.18);display:flex;gap:10px;justify-content:flex-end"><button id="titanModalCancel" style="padding:10px 14px;border-radius:10px;border:1px solid rgba(151,116,255,.24);background:rgba(91,49,176,.12);color:#eee9ff;cursor:pointer">انصراف</button><button id="titanModalSave" style="padding:10px 16px;border-radius:10px;border:1px solid rgba(188,157,255,.5);background:linear-gradient(135deg,#7436f5,#4b1bb4);color:#fff;cursor:pointer">ذخیره</button></div>
    </div>`;
    document.body.appendChild(overlay);
    const close=()=>overlay.remove();
    $('#titanModalClose').addEventListener('click',close);
    $('#titanModalCancel').addEventListener('click',close);
    overlay.addEventListener('click',e=>{ if(e.target===overlay) close(); });
    $('#titanModalSave').addEventListener('click', async ()=>{
      const btn=$('#titanModalSave');
      btn.disabled=true; const old=btn.textContent; btn.textContent='...';
      try{ await onSave(); close(); toast('انجام شد'); loadOverview(); }
      catch(e){ toast(e.message); }
      finally{ btn.disabled=false; btn.textContent=old; }
    });
  }

  function openUserModal(){
    apiJson('/api/nodes').then(nRes=>{
      const nodes=nRes.nodes||[];
      const opts = '<option value="0">🌐 خودکار (نزدیک‌ترین)</option>' + nodes.map(n=>`<option value="${n.id}">${esc(n.flag||'🌐')} ${esc(n.name)}</option>`).join('');
      createModal('افزودن کاربر / کانفیگ', `
        <div style="display:grid;gap:12px">
          <label style="display:flex;flex-direction:column;gap:6px;font-size:12px;color:#a8a6bf">نام<input id="mu_name" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px;font-size:12px" placeholder="مثلا Test"></label>
          <label style="display:flex;flex-direction:column;gap:6px;font-size:12px;color:#a8a6bf">پروتکل<select id="mu_protocol" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"><option value="vless">VLESS</option><option value="vmess">VMess</option><option value="trojan">Trojan</option><option value="shadowsocks">Shadowsocks</option><option value="hysteria2">Hysteria2</option><option value="wireguard">WireGuard</option></select></label>
          <label style="display:flex;flex-direction:column;gap:6px;font-size:12px;color:#a8a6bf">سرور<select id="mu_node" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px">${opts}</select></label>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <label style="display:flex;flex-direction:column;gap:6px;font-size:12px;color:#a8a6bf">حجم (GB)<input id="mu_quota" type="number" value="0" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
            <label style="display:flex;flex-direction:column;gap:6px;font-size:12px;color:#a8a6bf">انقضا (روز)<input id="mu_expire" type="number" value="0" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px"></label>
          </div>
        </div>
      `, async ()=>{
        const name=$('#mu_name').value.trim()||'User';
        const protocol=$('#mu_protocol').value;
        const node_id=parseInt($('#mu_node').value)||0;
        const quota_gb=parseFloat($('#mu_quota').value)||0;
        const expire_days=parseInt($('#mu_expire').value)||0;
        const body={name,protocol,node_id,quota_gb,expire_days,client_nonce: Math.random().toString(36).slice(2)+Date.now().toString(36)};
        await apiJson('/api/users',{method:'POST',body});
        // refresh tables
        const ev=new Event('refresh'); document.dispatchEvent(ev);
        // reload overview after save via caller
      });
    }).catch(e=>toast(e.message));
  }

  function openNodeModal(){
    createModal('افزودن سرور', `
      <div style="display:grid;gap:12px">
        <label style="display:flex;flex-direction:column;gap:6px;font-size:12px;color:#a8a6bf">نام سرور<input id="mn_name" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px" placeholder="مثلا IR-1"></label>
        <label style="display:flex;flex-direction:column;gap:6px;font-size:12px;color:#a8a6bf">آدرس (دامنه یا IP)<input id="mn_addr" style="background:rgba(10,20,39,.8);border:1px solid rgba(108,125,165,.18);border-radius:10px;color:#e9e6f6;padding:11px;direction:ltr" placeholder="your-node.up.railway.app"></label>
      </div>
    `, async ()=>{
      const name=$('#mn_name').value.trim();
      const address=$('#mn_addr').value.trim();
      if(!name) throw new Error('نام الزامی است');
      await apiJson('/api/nodes',{method:'POST',body:{name,address}});
    });
  }

  // --- init ---
  document.addEventListener('DOMContentLoaded', ()=>{
    loadMe();
    loadOverview();
    // delay details to ensure DOM ready
    setTimeout(wireDetails, 300);
    // global search (header)
    const gSearch = document.querySelector('.search input[type="search"]');
    if(gSearch){
      gSearch.addEventListener('input', ()=>{
        const q=gSearch.value.trim().toLowerCase();
        // filter recent tables
        document.querySelectorAll('.recent-table-row').forEach(r=>{
          r.style.display = r.textContent.toLowerCase().includes(q)?'':'none';
        });
      });
      // shortcut Ctrl+K
      document.addEventListener('keydown', e=>{
        if((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='k'){ e.preventDefault(); gSearch.focus(); }
      });
    }
    // header actions: refresh
    const refreshBtn = document.querySelectorAll('.action')[1];
    if(refreshBtn){
      refreshBtn.addEventListener('click', ()=>{ loadOverview(); toast('به‌روزرسانی شد'); });
    }
    // profile click -> logout menu
    const prof = document.querySelector('.profile');
    if(prof){
      prof.style.cursor='pointer';
      prof.title='کلیک برای خروج';
      prof.addEventListener('click', async ()=>{
        if(confirm('خروج از حساب؟')){
          try{ await apiJson('/api/logout',{method:'POST'}); location.href='/login'; }catch(e){ location.href='/login'; }
        }
      });
    }
    // version click -> copy
    const ver=document.querySelector('.version');
    if(ver) ver.addEventListener('click', ()=> toast('TiTaN Panel'));

    // handle hash navigation compatibility: if hash is #/users etc, switch nav
    function handleHash(){
      const h=location.hash||'';
      const map={ '#/dashboard':0,'#/users':1,'#/configs':2,'#/nodes':3,'#/subscriptions':4,'#/reports':5,'#/settings':6,'#/admins':7,'#/tools':8 };
      const idx=map[h];
      if(idx!=null){
        const nav=document.querySelectorAll('.nav-item');
        if(nav[idx]) nav[idx].click();
      }
    }
    window.addEventListener('hashchange', handleHash);
    handleHash();
  });

  // expose for refresh
  window._titanRefresh = ()=>{ loadOverview(); };
})();
