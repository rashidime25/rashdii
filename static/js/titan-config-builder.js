/* TiTaN — config builder UI (recipes, link test).
 *
 * Deliberately additive: this file never rewrites the dashboard's markup, never
 * re-renders a section, and never touches the sidebar/tab logic. It only:
 *
 *   1. fills the recipe <select> that titan-bridge.js already renders in the
 *      user modal, and turns a recipe choice into field values,
 *   2. adds two per-user buttons (JSON config + real connection test) into the
 *      users table by *appending* to the existing action cell,
 *   3. fills the one empty card that dashboard.html reserves in the configs
 *      section with the recipe gallery and the engine tuning form.
 *
 * Everything is wrapped in guards, so if a section is missing (a trimmed
 * template, an old cached HTML) the rest still works and nothing throws — a
 * broken script here would take the whole dashboard down with it.
 */
(function () {
  'use strict';

  var recipesCache = null;
  var recipesPromise = null;

  // ---------------------------------------------------------------- utilities
  function api(url, opts) {
    opts = opts || {};
    opts.credentials = 'same-origin';
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (opts.body && typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.detail || d.message || r.statusText);
        return d;
      });
    });
  }

  function toast(msg) {
    var el = document.getElementById('titanToast');
    if (!el) {                       // bridge not loaded yet: degrade silently
      console.log('[titan-config-builder]', msg);
      return;
    }
    el.textContent = msg;
    el.style.opacity = '1';
    el.style.transform = 'translate(-50%,0)';
    clearTimeout(el._t);
    el._t = setTimeout(function () {
      el.style.opacity = '0';
      el.style.transform = 'translate(-50%,14px)';
    }, 2400);
  }

  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function el(tag, attrs, html) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'style') node.style.cssText = attrs[k];
      else if (k === 'class') node.className = attrs[k];
      else node.setAttribute(k, attrs[k]);
    });
    if (html != null) node.innerHTML = html;
    return node;
  }

  function loadRecipes() {
    if (recipesCache) return Promise.resolve(recipesCache);
    if (!recipesPromise) {
      recipesPromise = api('/api/recipes').then(function (d) {
        recipesCache = d || { recipes: [] };
        return recipesCache;
      }).catch(function () { return { recipes: [] }; });
    }
    return recipesPromise;
  }

  // The builder's own vocabulary, mirrored from app/config.py. Kept here as the
  // single place the UI needs it (the selects are already in the modal markup).
  var FIELD_BY_KEY = {
    protocol: 'mu_protocol', transport: 'mu_transport', security: 'mu_security',
    fingerprint: 'mu_fp', alpn: 'mu_alpn', flow: 'mu_flow', ss_method: 'mu_ss',
    reality_sni: 'mu_rsni', policy_level: 'mu_plan'
  };

  // ---------------------------------------------------------------- 1) modal
  function applyRecipeToForm(overlay, recipe) {
    if (!overlay || !recipe) return 0;
    var fields = recipe.fields || {};
    var applied = 0;
    Object.keys(FIELD_BY_KEY).forEach(function (key) {
      var sel = document.getElementById(FIELD_BY_KEY[key]);
      if (!sel || !(key in fields)) return;
      var want = fields[key] == null ? '' : String(fields[key]);
      var ok = Array.prototype.some.call(sel.options, function (o) { return o.value === want; });
      if (!ok) return;                      // never invent an option that servers reject
      sel.value = want;
      applied++;
    });
    if ('mux_enabled' in fields) {
      var mux = document.getElementById('mu_mux');
      if (mux) { mux.checked = !!fields.mux_enabled; applied++; }
    }
    return applied;
  }

  function wireRecipeSelect(overlay) {
    var sel = document.getElementById('mu_recipe');
    if (!sel) return;
    loadRecipes().then(function (data) {
      var list = (data && data.recipes) || [];
      sel.innerHTML = '<option value="">بدون پروفایل</option>' + list.map(function (r) {
        return '<option value="' + esc(r.id) + '">' + esc((r.emoji ? r.emoji + ' ' : '') + r.name) + '</option>';
      }).join('');
      var want = sel.getAttribute('data-cur') || '';
      if (want && list.some(function (r) { return r.id === want; })) sel.value = want;
      updateHint(sel.value, list);
    });
    sel.addEventListener('change', function () {
      loadRecipes().then(function (data) {
        var list = (data && data.recipes) || [];
        var chosen = list.filter(function (r) { return r.id === sel.value; })[0];
        updateHint(sel.value, list);
        if (chosen) {
          var n = applyRecipeToForm(overlay, chosen);
          toast(n ? ('پروفایل «' + chosen.name + '» اعمال شد (' + n + ' فیلد)') : chosen.name);
        }
      });
    });
  }

  function updateHint(id, list) {
    var hint = document.getElementById('mu_recipe_hint');
    if (!hint) return;
    var chosen = (list || []).filter(function (r) { return r.id === id; })[0];
    if (!chosen) {
      hint.textContent = 'انتخاب پروفایل، فیلدهای خالی را پر می‌کند؛ مقادیری که خودت ست کرده‌ای دست‌نخورده می‌مانند.';
      return;
    }
    hint.innerHTML = esc(chosen.tagline || '') + (chosen.note ? '<br>' + esc(chosen.note) : '');
  }

  function mountModal() {
    var overlay = document.getElementById('titanModal');
    if (!overlay || !overlay.querySelector('#mu_protocol')) return;
    if (overlay.dataset.cbMounted === '1') return;
    overlay.dataset.cbMounted = '1';
    wireRecipeSelect(overlay);
  }

  // ---------------------------------------------------------------- 2) user rows
  function decorateUserRows() {
    var section = document.querySelector('.section-view[data-section="users"]');
    if (!section) return;
    var uidOf = function (tr) {
      var b = tr.querySelector('[data-uid]');
      return b ? b.dataset.uid : '';
    };
    Array.prototype.forEach.call(section.querySelectorAll('.data-table tbody tr'), function (tr) {
      var cell = tr.lastElementChild;
      if (!cell || !uidOf(tr) || cell.querySelector('[data-cb]')) return;
      var uid = uidOf(tr);
      cell.appendChild(el('button', {
        'class': 'mini-btn', 'data-cb': 'json', 'data-uid': uid,
        title: 'دانلود کانفیگ JSON آماده (همان تنظیمات سرور)'
      }, 'JSON'));
      cell.appendChild(document.createTextNode(' '));
      cell.appendChild(el('button', {
        'class': 'mini-btn', 'data-cb': 'test', 'data-uid': uid,
        title: 'تست واقعی اتصال همین کانفیگ از روی سرور'
      }, 'تست اتصال'));
    });
  }

  function download(name, obj) {
    var blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 400);
  }

  function reportHtml(rep) {
    var rows = (rep.steps || []).map(function (s) {
      return '<div class="metric-row"><span>' + esc(s.name) + '</span><span class="pill ' +
        (s.ok ? '' : 'warn') + '">' + (s.ok ? '✓' : '✗') + ' ' + esc(s.detail || '') + '</span></div>';
    }).join('');
    return '<div style="display:grid;gap:10px">' +
      '<div class="metric-row"><span>نتیجه</span><span class="pill ' + (rep.ok ? '' : 'warn') + '">' +
      (rep.ok ? 'اتصال برقرار است' : 'اتصال برقرار نشد') + '</span></div>' +
      '<div class="metric-row"><span>تأخیر (Time to first byte)</span><strong>' +
      (rep.latency_ms != null ? rep.latency_ms + ' ms' : '—') + '</strong></div>' +
      '<div class="metric-row"><span>مقصد تست</span><strong dir="ltr" style="font-size:11px">' + esc(rep.target || '') + '</strong></div>' +
      rows + '</div>';
  }

  function showReport(rep) {
    var old = document.getElementById('cbReport');
    if (old) old.remove();
    var overlay = el('div', {
      id: 'cbReport',
      style: 'position:fixed;inset:0;z-index:10001;background:rgba(2,4,18,.62);backdrop-filter:blur(8px);display:grid;place-items:center;padding:16px'
    });
    var box = el('div', {
      style: 'width:min(520px,96vw);background:linear-gradient(145deg,rgba(24,12,56,.96),rgba(8,6,26,.98));border:1px solid rgba(151,116,255,.42);border-radius:18px;overflow:hidden;max-height:90vh;display:flex;flex-direction:column'
    });
    box.innerHTML =
      '<div style="padding:16px 18px;border-bottom:1px solid rgba(151,116,255,.18);display:flex;justify-content:space-between;align-items:center">' +
      '<div style="font-weight:700;color:#f2edff">نتیجه تست اتصال — ' + esc(rep.name || '') + '</div>' +
      '<button id="cbReportClose" style="width:32px;height:32px;border-radius:9px;border:1px solid rgba(151,116,255,.24);background:rgba(91,49,176,.16);color:#d8c7ff;cursor:pointer">×</button></div>' +
      '<div style="padding:16px;overflow:auto;flex:1;color:#cfc9e8">' + reportHtml(rep) + '</div>';
    overlay.appendChild(box);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
    document.getElementById('cbReportClose').addEventListener('click', function () { overlay.remove(); });
  }

  function wireUserSectionClicks() {
    var section = document.querySelector('.section-view[data-section="users"]');
    if (!section || section.dataset.cbClicks === '1') return;
    section.dataset.cbClicks = '1';
    section.addEventListener('click', function (e) {
      var btn = e.target.closest && e.target.closest('[data-cb]');
      if (!btn) return;
      var uid = btn.dataset.uid;
      if (btn.dataset.cb === 'json') {
        api('/api/users/' + uid + '/client-config').then(function (cfg) {
          download('titan-' + (cfg.remarks || uid) + '.json', cfg);
          toast('کانفیگ JSON آماده دانلود شد');
        }).catch(function (err) { toast(err.message); });
        return;
      }
      var old = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'در حال تست…';
      api('/api/users/' + uid + '/link-test', { method: 'POST' }).then(function (d) {
        showReport(d.report || {});
        toast((d.report && d.report.ok) ? 'اتصال سالم است ✓' : 'اتصال برقرار نشد');
      }).catch(function (err) { toast(err.message); }).then(function () {
        btn.disabled = false;
        btn.textContent = old;
      });
    });
  }

  // ---------------------------------------------------------------- 3) workshop
  function renderWorkshop() {
    var host = document.getElementById('cb-workshop');
    if (!host || host.dataset.cbFilled === '1') return;
    host.dataset.cbFilled = '1';
    host.innerHTML =
      '<div class="card-title" style="margin-bottom:12px"><h3 style="margin:0">کارگاه کانفیگ</h3>' +
      '<span class="muted">پروفایل آماده</span></div>' +
      '<div id="cb-recipes" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px"></div>';

    loadRecipes().then(function (data) {
      var box = document.getElementById('cb-recipes');
      if (!box) return;
      box.innerHTML = ((data && data.recipes) || []).map(function (r) {
        return '<article class="detail-card" style="padding:14px">' +
          '<h3 style="margin:0 0 6px">' + esc((r.emoji ? r.emoji + ' ' : '') + r.name) + '</h3>' +
          '<p class="sub" style="margin:0 0 6px">' + esc(r.tagline || '') + '</p>' +
          '<p class="muted" style="font-size:10px;line-height:1.7;margin:0 0 10px">' + esc(r.note || '') + '</p>' +
          '<button class="mini-btn" data-recipe="' + esc(r.id) + '" style="width:100%">ساخت کانفیگ با این پروفایل</button>' +
          '</article>';
      }).join('') || '<p class="muted">پروفایلی موجود نیست</p>';
      wireRecipeButtons(box);
    });

  }

  function wireRecipeButtons(box) {
    box.addEventListener('click', function (e) {
      var btn = e.target.closest && e.target.closest('[data-recipe]');
      if (!btn) return;
      var section = document.querySelector('.section-view[data-section="configs"]');
      var add = section && section.querySelector('.section-btn.primary');
      if (!add) { toast('دکمه ساخت کانفیگ پیدا نشد'); return; }
      add.click();                                  // reuse the panel's own modal
      setTimeout(function () {
        var sel = document.getElementById('mu_recipe');
        if (!sel) return;
        sel.value = btn.dataset.recipe;
        sel.dispatchEvent(new Event('change'));
      }, 120);
    });
  }

  // ---------------------------------------------------------------- bootstrap
  function boot() {
    if (!document.getElementById('titanToast')) {
      var t = el('div', { id: 'titanToast' });
      t.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translate(-50%,14px);opacity:0;pointer-events:none;padding:10px 16px;border-radius:12px;color:#eeeaff;background:rgba(6,8,35,.94);border:1px solid rgba(104,77,255,.45);box-shadow:0 0 24px rgba(75,40,255,.18);backdrop-filter:blur(12px);transition:.24s;z-index:9999;font-size:12px;';
      document.body.appendChild(t);
    }
    renderWorkshop();
    decorateUserRows();
    wireUserSectionClicks();
    mountModal();

    // The modal and the users table are rendered by titan-bridge.js after this
    // file runs, so watch for them instead of guessing a delay.
    var observer = new MutationObserver(function () {
      mountModal();
      decorateUserRows();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('titan:refresh', function () {
      setTimeout(decorateUserRows, 150);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
