var Mon = {interval:null, sysLoaded:false};

Admin.on('navigate', function(page) {
    if (page === 'monitoring') { Mon.init(); Mon.load(); Mon.interval = setInterval(Mon.load, 5000); }
    else { if (Mon.interval) { clearInterval(Mon.interval); Mon.interval = null; } }
});

Mon.init = function() {
    var p = document.getElementById('page-monitoring');
    if (!p || p.dataset.inited) return;
    p.dataset.inited = '1';
    p.innerHTML =
        '<style>'+
        /* Alerts */
        '.mon-alerts{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px 0}'+
        '.mon-alert{padding:6px 12px;border-radius:6px;font-size:12px;font-weight:700;color:#fff;display:flex;align-items:center;gap:6px}'+
        '.mon-alert.ok{background:rgba(35,134,54,.25);border:1px solid #238636;color:#3fb950}'+
        '.mon-alert.warn{background:rgba(217,162,24,.2);border:1px solid #d29922;color:#d29922}'+
        '.mon-alert.crit{background:rgba(218,54,51,.25);border:1px solid #da3633;color:#f85149}'+
        /* Info header */
        '.mon-header{font-size:11px;color:#8b949e;margin:0 0 14px 0;line-height:1.7}'+
        '.mon-header b{color:#c9d1d9;font-weight:600}'+
        '.mon-header i{color:#6e7681}'+
        /* Quick cards */
        '.mon-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px;margin:0 0 16px 0}'+
        '.mon-card{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:10px 12px;position:relative;overflow:hidden;min-width:0}'+
        '.mon-card.warn{border-color:#d29922}.mon-card.crit{border-color:#da3633}'+
        '.mon-card .mon-clb{font-size:9px;color:#6e7681;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}'+
        '.mon-card .mon-cval{font-size:20px;font-weight:800;color:#c9d1d9;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}'+
        '.mon-card.warn .mon-cval{color:#d29922}.mon-card.crit .mon-cval{color:#f85149}'+
        '.mon-card .mon-csub{font-size:10px;color:#6e7681;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}'+
        '.mon-card .mon-spark-wrap{float:right;width:50px;height:22px;opacity:.5;margin-left:4px;margin-top:-2px}'+
        '.mon-card .mon-spark{width:100%;height:100%;display:block}'+
        /* Details grid */
        '.mon-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:10px;margin:0 0 16px 0}'+
        '.mon-grid > *{min-width:0}'+
        '.mon-panel{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:12px 14px;font-size:12px;color:#8b949e;line-height:1.6;min-width:0}'+
        '.mon-panel h4{font-size:11px;font-weight:700;color:#58a6ff;margin:0 0 8px 0;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #21262d;padding-bottom:6px;display:flex;align-items:center;gap:6px}'+
        '.mon-panel b{color:#c9d1d9;font-weight:600}'+
        '.mon-panel table{width:100%;border-collapse:collapse;font-size:11px;margin-top:4px;table-layout:fixed}'+
        '.mon-panel td{padding:3px 0;border-bottom:1px solid #21262d;vertical-align:top}'+
        '.mon-panel tr:last-child td{border-bottom:none}'+
        '.mon-panel td:first-child{color:#6e7681;width:50%;overflow-wrap:break-word;word-break:break-word}'+
        '.mon-panel td:last-child{text-align:right;color:#c9d1d9;width:50%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}'+
        /* Charts */
        '.mon-charts{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:10px;margin-top:10px}'+
        '.mon-ch{background:transparent;border:none;border-radius:0;padding:0}'+
        /* Pipeline/GPU lock status */
        '.mon-status{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:10px 14px;margin-bottom:14px;font-size:12px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}'+
        '.mon-status .st-dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}'+
        '.mon-status .st-green{background:#3fb950;box-shadow:0 0 6px #3fb950}'+
        '.mon-status .st-red{background:#f85149}'+
        '.mon-status .st-yellow{background:#d29922;box-shadow:0 0 6px #d29922}'+
        '.mon-status .st-grey{background:#484f58}'+
        /* Light theme */
        '.light-theme .mon-alert.ok{background:rgba(31,136,61,.1);border-color:#1f883d;color:#1a7f37}'+
        '.light-theme .mon-alert.warn{background:rgba(154,103,0,.1);border-color:#bf8700;color:#9a6700}'+
        '.light-theme .mon-alert.crit{background:rgba(207,34,46,.1);border-color:#cf222e;color:#cf222e}'+
        '.light-theme .mon-header{color:#57606a}.light-theme .mon-header b{color:#24292f}'+
        '.light-theme .mon-card{background:#fff;border-color:#d0d7de}.light-theme .mon-card .mon-cval{color:#24292f}'+
        '.light-theme .mon-card.warn .mon-cval{color:#9a6700}.light-theme .mon-card.crit .mon-cval{color:#cf222e}'+
        '.light-theme .mon-card .mon-clb{color:#8c949e}.light-theme .mon-card .mon-csub{color:#57606a}'+
        '.light-theme .mon-panel{background:#fff;border-color:#d0d7de;color:#57606a}'+
        '.light-theme .mon-panel h4{color:#0969da;border-color:#d0d7de}'+
        '.light-theme .mon-panel b{color:#24292f}.light-theme .mon-panel td:first-child{color:#57606a}'+
        '.light-theme .mon-panel td:last-child{color:#24292f}.light-theme .mon-panel td{border-color:#eaeef2}'+
        '.light-theme .mon-ch{background:transparent}'+
        '.light-theme .mon-status{background:#fff;border-color:#d0d7de}'+
        /* Modal */
        '.mon-modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);z-index:200;display:none;align-items:center;justify-content:center;padding:20px}'+
        '.mon-modal-overlay.open{display:flex}'+
        '.mon-modal-box{background:#0d1117;border:1px solid #30363d;border-radius:10px;width:90vw;height:85vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.5)}'+
        '.mon-modal-head{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-bottom:1px solid #21262d;background:#161b22}'+
        '.mon-modal-head h3{margin:0;font-size:14px;color:#c9d1d9}'+
        '.mon-modal-close{background:none;border:none;color:#8b949e;font-size:20px;cursor:pointer;padding:0 4px}'+
        '.mon-modal-close:hover{color:#f85149}'+
        '.mon-modal-body{flex:1;padding:10px;overflow:hidden;position:relative}'+
        '.light-theme .mon-modal-box{background:#fff;border-color:#d0d7de}'+
        '.light-theme .mon-modal-head{background:#f6f8fa;border-color:#d0d7de}'+
        '.light-theme .mon-modal-head h3{color:#24292f}'+
        '.light-theme .mon-modal-close{color:#57606a}'+
        '</style>'+
        '<h2 style="margin:0 0 12px 0;font-size:18px;font-weight:700;color:#e3b341">📈 System Monitor</h2>'+
        '<div class="mon-status" id="monStatus"></div>'+
        '<div class="mon-alerts" id="monAlerts"></div>'+
        '<div class="mon-header" id="mInfo"></div>'+
        '<div class="mon-cards" id="mGrid"></div>'+
        '<div class="mon-grid" id="mReport"></div>'+
        '<div class="mon-charts" id="mCharts"></div>'+
        '<div class="mon-modal-overlay" id="monModal">'+
        '<div class="mon-modal-box">'+
        '<div class="mon-modal-head"><h3 id="monModalTitle">Chart</h3><button class="mon-modal-close" id="monModalClose">×</button></div>'+
        '<div class="mon-modal-body" id="monModalBody"></div>'+
        '</div></div>';
    Mon.initModalHandlers();
};

Mon._modalPlot = null;

Mon.initModalHandlers = function() {
    var overlay = document.getElementById('monModal');
    var closeBtn = document.getElementById('monModalClose');
    if (!overlay || !closeBtn) return;
    closeBtn.addEventListener('click', Mon.closeModal);
    overlay.addEventListener('click', function(e){
        if (e.target === overlay) Mon.closeModal();
    });
    document.addEventListener('keydown', function(e){
        if (e.key === 'Escape' && overlay.classList.contains('open')) Mon.closeModal();
    });
};

Mon.openModal = function(idx, title, data, series, unit) {
    var overlay = document.getElementById('monModal');
    var body = document.getElementById('monModalBody');
    var titleEl = document.getElementById('monModalTitle');
    if (!overlay || !body) return;
    titleEl.textContent = title;
    body.innerHTML = '';
    overlay.classList.add('open');

    if (Mon._modalPlot) { Mon._modalPlot.destroy(); Mon._modalPlot = null; }

    var isDark = !document.body.classList.contains('light-theme');
    var axisColor = isDark ? '#8b949e' : '#57606a';
    var gridColor = isDark ? '#21262d' : '#d0d7de';
    var tickColor = isDark ? '#30363d' : '#d0d7de';

    var opts = {
        width: 0, height: 0,
        title: '',
        scales: { x: { time: true }, y: { auto: true } },
        axes: [
            { stroke: axisColor, grid: { stroke: gridColor }, ticks: { stroke: tickColor } },
            { stroke: axisColor, grid: { stroke: gridColor }, ticks: { stroke: tickColor }, label: unit || '', labelSize: 12, size: 56, gap: 6 }
        ],
        series: [{ label: 'Time' }].concat(series.map(function(s){
            return { label: s.label, stroke: s.stroke, fill: s.fill || 'transparent', width: 2, points: { show: false } };
        })),
        legend: { live: true, font: '12px monospace' }
    };

    Mon._modalPlot = new uPlot(opts, data, body);

    requestAnimationFrame(function(){
        var w = body.clientWidth - 4;
        var h = body.clientHeight - 4;
        if (w > 0 && h > 0) Mon._modalPlot.setSize({width: w, height: h});
    });
};

Mon.closeModal = function() {
    var overlay = document.getElementById('monModal');
    if (overlay) overlay.classList.remove('open');
    if (Mon._modalPlot) { Mon._modalPlot.destroy(); Mon._modalPlot = null; }
};

Mon.load = function() {
    Admin.ajax('/../api/monitoring', function(d) {
        Mon._hist = d.history;
        Mon.renderCards(d.live);
        Mon.renderCharts(d.history);
        Mon.renderInfo(d.live);
        Mon.renderAlerts(d.live);
    });
    Admin.ajax('/../api/system-report', function(r) {
        Mon.renderReport(r);
    });
    Admin.ajax('/../api/mqtt/workers', function(w) {
        Mon.renderStatus(w);
    });
    if (!Mon.sysLoaded) { Mon.sysLoaded = true; Mon.loadPhotos(); }
};

Mon.loadPhotos = function() {
    Admin.ajax('/../api/status', function(s) {
        Mon._photos = s.catalog_total ? s.catalog_total+' photos, '+s.personas_total+' personas' : '';
        if (Mon._lastLive) Mon.renderInfo(Mon._lastLive);
    });
};

Mon.renderStatus = function(w) {
    var el = document.getElementById('monStatus');
    if (!el) return;
    var workers = w.workers || {};
    var step = w.current_step || '';
    var gpuHolder = null;
    for (var name in workers) {
        if (workers[name].gpu_held) gpuHolder = name;
    }
    var h = '';
    if (step) {
        h += '<span><span class="st-dot st-green"></span><b>Пайплайн:</b> '+Admin.esc(step)+'</span>';
    } else {
        h += '<span><span class="st-dot st-grey"></span>Пайплайн: idle</span>';
    }
    if (gpuHolder) {
        h += '<span><span class="st-dot st-yellow"></span><b>GPU locked by:</b> '+Admin.esc(gpuHolder)+'</span>';
    } else {
        h += '<span><span class="st-dot st-green"></span>GPU: свободен</span>';
    }
    el.innerHTML = h;
};

Mon.renderAlerts = function(L) {
    var el = document.getElementById('monAlerts');
    if (!el) return;
    var alerts = [];
    var si = L.system_info || {};
    if (L.cpu_percent > 80) alerts.push({t:'CPU '+Math.round(L.cpu_percent)+'%', cls:'crit'});
    else if (L.cpu_percent > 60) alerts.push({t:'CPU '+Math.round(L.cpu_percent)+'%', cls:'warn'});
    if (L.mem_percent > 90) alerts.push({t:'RAM '+Math.round(L.mem_percent)+'%', cls:'crit'});
    else if (L.mem_percent > 75) alerts.push({t:'RAM '+Math.round(L.mem_percent)+'%', cls:'warn'});
    if (L.gpu_load > 80) alerts.push({t:'GPU '+Math.round(L.gpu_load)+'%', cls:'crit'});
    else if (L.gpu_load > 50) alerts.push({t:'GPU '+Math.round(L.gpu_load)+'%', cls:'warn'});
    if (L.gpu_temp > 80) alerts.push({t:'GPU '+Math.round(L.gpu_temp)+'°C', cls:'crit'});
    else if (L.gpu_temp > 70) alerts.push({t:'GPU '+Math.round(L.gpu_temp)+'°C', cls:'warn'});
    if (L.disk_root > 90) alerts.push({t:'Disk / '+Math.round(L.disk_root)+'%', cls:'crit'});
    else if (L.disk_root > 80) alerts.push({t:'Disk / '+Math.round(L.disk_root)+'%', cls:'warn'});
    if (L.disk_share > 90) alerts.push({t:'Disk /mnt '+Math.round(L.disk_share)+'%', cls:'crit'});
    else if (L.disk_share > 80) alerts.push({t:'Disk /mnt '+Math.round(L.disk_share)+'%', cls:'warn'});
    if (alerts.length === 0) alerts.push({t:'Система в норме', cls:'ok'});
    el.innerHTML = alerts.map(function(a){
        return '<div class="mon-alert '+a.cls+'">'+Admin.esc(a.t)+'</div>';
    }).join('');
};

Mon.renderInfo = function(L) {
    Mon._lastLive = L;
    var el = document.getElementById('mInfo');
    if (!el) return;
    var si = L.system_info || {};
    var u = L.uptime_seconds || 0;
    var ud = Math.floor(u/86400), uh = Math.floor((u%86400)/3600), um = Math.floor((u%3600)/60);
    var up = ud+'d '+uh+'h '+um+'m';
    el.innerHTML =
        '<b>'+Admin.esc(si.hostname||'?')+'</b> [LXC] &bull; kernel <b>'+Admin.esc(si.kernel||'?')+'</b> &bull; up <b>'+up+'</b> &bull; '+
        'GPU <b>'+Admin.esc(si.gpu_name||'?')+'</b> (drv '+Admin.esc(si.driver_ver||'?')+', PCIe '+si.pcie_gen+'x'+si.pcie_width+') &bull; '+
        'CPU <b>'+Admin.esc(si.cpu_model||'?')+'</b>, '+si.cpu_count+' cores &bull; '+
        'RAM <b>'+si.ram_total_gb+' GiB</b> (used '+(si.ram_total_gb - L.mem_avail_gb).toFixed(1)+' GiB) &bull; '+
        'Disks <b>'+(si.disk_root_gb||'?')+' GiB</b> + <b>'+(si.disk_share_gb||'?')+' GiB</b>'+
        (Mon._photos ? ' &bull; '+Mon._photos : '')+
        '<br><i>'+(L.timestamp||'').substring(0,19).replace('T',' ')+'</i>';
};

Mon.renderCards = function(L) {
    var el = document.getElementById('mGrid');
    if (!el) return;
    var H = Mon._hist;
    var si = L.system_info || {};
    var ramTotal = si.ram_total_gb || 16;
    var rootGb = si.disk_root_gb || 126;
    var shareGb = si.disk_share_gb || 1800;
    var vr = (L.gpu_vram_mb/1024).toFixed(1), vt = ((L.gpu_vram_total||8192)/1024).toFixed(0);
    var rf = L.mem_avail_gb.toFixed(1);
    var netRx = (L.net_rx_mbps||0).toFixed(1), netTx = (L.net_tx_mbps||0).toFixed(1);
    var dRead = (L.disk_read_mbps||0).toFixed(1), dWrite = (L.disk_write_mbps||0).toFixed(1);

    var items = [
        {k:'gpu_load',      lb:'GPU Load',  vl:L.gpu_load+'%',        dt:'VRAM '+vr+'/'+vt+' GiB', cl:'#3fb950', w:L.gpu_load>80, c:L.gpu_load>80},
        {k:'gpu_vram_mb',   lb:'VRAM',      vl:vr+' GiB',             dt:'of '+vt+' GiB ('+(L.gpu_vram_total?Math.round(L.gpu_vram_mb/L.gpu_vram_total*100):0)+'%)', cl:'#58a6ff', w:L.gpu_vram_mb/L.gpu_vram_total>0.85, c:L.gpu_vram_mb/L.gpu_vram_total>0.85},
        {k:'gpu_temp',      lb:'GPU °C',    vl:L.gpu_temp+'°C',       dt:'Fan '+L.gpu_fan+'%', cl:'#d29922', w:L.gpu_temp>75, c:L.gpu_temp>75},
        {k:'gpu_power_w',   lb:'GPU Power', vl:Math.round(L.gpu_power_w)+'W', dt:'Limit 180W', cl:'#f0883e', w:L.gpu_power_w>160, c:L.gpu_power_w>160},
        {k:'cpu_percent',   lb:'CPU Load',  vl:Math.round(L.cpu_percent)+'%', dt:'Load '+L.load1.toFixed(1), cl:'#58a6ff', w:L.cpu_percent>80, c:L.cpu_percent>80},
        {k:'cpu_temp_max',  lb:'CPU °C',    vl:L.cpu_temp_max+'°C',   dt:'max temp', cl:'#f0883e', w:L.cpu_temp_max>85, c:L.cpu_temp_max>85},
        {k:'mem_percent',   lb:'RAM Used',  vl:Math.round(L.mem_percent)+'%', dt:'Free '+rf+' GiB', cl:'#bc8cff', w:L.mem_percent>85, c:L.mem_percent>85},
        {k:'disk_root',     lb:'Disk /',    vl:Math.round(L.disk_root)+'%', dt:rootGb+' GiB SSD', cl:'#a5d6ff', w:L.disk_root>85, c:L.disk_root>85},
        {k:'disk_share',    lb:'Disk /mnt', vl:Math.round(L.disk_share)+'%', dt:(shareGb>=1000?(shareGb/1000).toFixed(1)+' TiB':shareGb+' GiB'), cl:'#d29922', w:L.disk_share>85, c:L.disk_share>85},
        {k:'net_rx_mbps',   lb:'Net RX',    vl:netRx+' Mbps',        dt:'TX '+netTx+' Mbps', cl:'#3fb950', w:false, c:false},
        {k:'disk_read_mbps',lb:'Disk Read', vl:dRead+' MB/s',        dt:'Write '+dWrite+' MB/s', cl:'#58a6ff', w:false, c:false},
    ];

    el.innerHTML = items.map(function(x){
        var sp = '';
        var vals;
        if (H && H.length >= 2) {
            vals = H.map(function(r){return (r[x.k]||0);});
        }
        if (vals && vals.length >= 2) {
            var lo = Math.min.apply(null,vals), hi = Math.max.apply(null,vals);
            if (hi-lo < 0.5) { hi = lo + 1; lo = lo - 1; }
            var rng = hi - lo, n = vals.length-1, sw = 60, sh = 28;
            var pts = vals.map(function(v,i){
                return Math.round(i/n*sw)+','+Math.round(sh-4-((v-lo)/rng)*(sh-8));
            }).join(' ');
            sp = '<div class="mon-spark-wrap" data-mkey="'+Admin.esc(x.k)+'" data-mlb="'+Admin.esc(x.lb)+'" data-mcl="'+Admin.esc(x.cl)+'" data-munit="" style="cursor:pointer" title="Клик для подробного просмотра"><svg class="mon-spark" viewBox="0 0 '+sw+' '+sh+'" preserveAspectRatio="none"><polyline points="'+pts+'" fill="none" stroke="'+x.cl+'" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg></div>';
        }
        var cls = '';
        if (x.c) cls = ' crit';
        else if (x.w) cls = ' warn';
        return '<div class="mon-card'+cls+'"><div class="mon-clb">'+Admin.esc(x.lb)+'</div><div class="mon-cval" style="color:'+x.cl+'">'+Admin.esc(x.vl)+'</div><div class="mon-csub">'+Admin.esc(x.dt)+'</div>'+sp+'</div>';
    }).join('');

    // Click handler for sparklines to open modal
    el.addEventListener('click', function(e){
        var wrap = e.target.closest('.mon-spark-wrap');
        if (!wrap) return;
        var key = wrap.dataset.mkey;
        var lb = wrap.dataset.mlb;
        var cl = wrap.dataset.mcl;
        var H2 = Mon._hist;
        if (!H2 || H2.length < 3) return;
        var xs = H2.map(function(r){ return r.timestamp ? new Date(r.timestamp).getTime()/1000 : 0; });
        var vals = H2.map(function(r){ return r[key] || 0; });
        // apply transforms for display consistency
        if (key === 'gpu_vram_mb') vals = vals.map(function(v){ return (v||0)/1024; });
        if (key === 'disk_share') vals = vals.map(function(v){ return v; });
        var data = [xs, vals];
        var series = [{label: lb, stroke: cl, fill: cl + '18'}];
        Mon.openModal(99, lb, data, series, '');
    });
};

Mon.renderCharts = function(H) {
    var el = document.getElementById('mCharts');
    if (!el || !H || H.length < 3) return;

    // Store previous chart instances to reuse
    if (!Mon._uplots) Mon._uplots = [];
    if (!Mon._chartContainers) Mon._chartContainers = [];

    var xs = H.map(function(r){
        return r.timestamp ? new Date(r.timestamp).getTime() / 1000 : 0;
    });

    var panels = [
        {title:'CPU + GPU load', unit:'%', series:[
            {label:'CPU', key:'cpu_percent', stroke:'#58a6ff', fill:'rgba(88,166,255,0.08)'},
            {label:'GPU', key:'gpu_load', stroke:'#3fb950', fill:'rgba(63,185,80,0.08)'}
        ]},
        {title:'Temperatures', unit:'°C', series:[
            {label:'CPU °C', key:'cpu_temp_max', stroke:'#f0883e', fill:'rgba(240,136,62,0.08)'},
            {label:'GPU °C', key:'gpu_temp', stroke:'#db6d28', fill:'rgba(219,109,40,0.08)'}
        ]},
        {title:'Memory + VRAM', unit:'%', series:[
            {label:'RAM %', key:'mem_percent', stroke:'#58a6ff', fill:'rgba(88,166,255,0.08)'},
            {label:'VRAM GiB', key:'gpu_vram_mb', stroke:'#3fb950', fill:'rgba(63,185,80,0.08)', transform:function(v){return (v||0)/1024;}}
        ]},
        {title:'Load Average', unit:'', series:[
            {label:'1m', key:'load1', stroke:'#58a6ff'},
            {label:'5m', key:'load5', stroke:'#f0883e'},
            {label:'15m', key:'load15', stroke:'#8b949e'}
        ]},
        {title:'GPU Power + Fan', unit:'W / %', series:[
            {label:'Power W', key:'gpu_power_w', stroke:'#f0883e', fill:'rgba(240,136,62,0.08)'},
            {label:'Fan %', key:'gpu_fan', stroke:'#8b949e', fill:'rgba(139,148,158,0.08)'}
        ]},
        {title:'Disks', unit:'%', series:[
            {label:'/', key:'disk_root', stroke:'#58a6ff'},
            {label:'/mnt', key:'disk_share', stroke:'#d29922'}
        ]}
    ];

    // Create containers on first run
    if (Mon._chartContainers.length === 0) {
        el.innerHTML = '';
        panels.forEach(function(){
            var wrap = document.createElement('div');
            wrap.className = 'mon-ch';
            wrap.style.minHeight = '220px';
            el.appendChild(wrap);
            Mon._chartContainers.push(wrap);
        });
    }

    panels.forEach(function(p, idx){
        var container = Mon._chartContainers[idx];
        if (!container) return;

        var data = [xs];
        p.series.forEach(function(s){
            data.push(H.map(function(r){
                var v = r[s.key] || 0;
                return s.transform ? s.transform(v) : v;
            }));
        });

        if (!container.dataset.clickSet) {
            container.dataset.clickSet = '1';
            container.style.cursor = 'pointer';
            container.title = 'Клик для подробного просмотра';
            container.addEventListener('click', function(){
                var modalSeries = p.series.map(function(s){
                    return { label: s.label, stroke: s.stroke, fill: s.fill };
                });
                Mon.openModal(idx, p.title + (p.unit ? ' ('+p.unit+')' : ''), data, modalSeries, p.unit || '');
            });
        }

        var u = Mon._uplots[idx];
        if (u) {
            u.setData(data);
        } else {
            var isDark = !document.body.classList.contains('light-theme');
            var axisColor = isDark ? '#8b949e' : '#57606a';
            var gridColor = isDark ? '#21262d' : '#d0d7de';
            var tickColor = isDark ? '#30363d' : '#d0d7de';

            var opts = {
                width: 0,
                height: 200,
                title: p.title + (p.unit ? ' ('+p.unit+')' : ''),
                titleColor: axisColor,
                scales: { x: { time: true }, y: { auto: true } },
                axes: [
                    { stroke: axisColor, grid: { stroke: gridColor }, ticks: { stroke: tickColor } },
                    { stroke: axisColor, grid: { stroke: gridColor }, ticks: { stroke: tickColor }, label: p.unit || '', labelSize: 10, size: 56, gap: 6 }
                ],
                series: [{ label: 'Time' }].concat(p.series.map(function(s){
                    return {
                        label: s.label,
                        stroke: s.stroke,
                        fill: s.fill || 'transparent',
                        width: 1.5,
                        points: { show: false }
                    };
                })),
                legend: { live: true, font: '11px monospace' }
            };

            u = new uPlot(opts, data, container);
            Mon._uplots[idx] = u;

            // Resize after layout
            requestAnimationFrame(function(){
                var w = container.offsetWidth;
                if (w > 0) u.setSize({width: w, height: 200});
            });
        }
    });
};

Mon.renderReport = function(r) {
    var el = document.getElementById('mReport');
    if (!el || !r) return;
    var fmtU = function(s){var d=Math.floor(s/86400),h=Math.floor((s%86400)/3600),m=Math.floor((s%3600)/60);return d+'d '+h+'h '+m+'m';};
    var fmtG = function(v){return v.toFixed(1)+' GiB';};
    var h = r.host, m = r.memory, g = r.gpu, d = r.disks, n = r.network, gr = r.gailray, t = r.top_processes;

    // Host panel
    var hostHtml = '<div class="mon-panel">'+
        '<h4>🖥 Host</h4>'+
        '<table>'+
        '<tr><td>Hostname</td><td><b>'+Admin.esc(h.hostname)+'</b></td></tr>'+
        '<tr><td>Kernel</td><td><b>'+Admin.esc(h.kernel)+'</b></td></tr>'+
        '<tr><td>Uptime</td><td><b>'+fmtU(h.uptime_seconds)+'</b></td></tr>'+
        '<tr><td>CPU</td><td><b>'+Admin.esc(h.cpu_model)+'</b></td></tr>'+
        '<tr><td>Cores</td><td><b>'+h.cpu_cores_physical+'</b> phys / <b>'+h.cpu_cores_logical+'</b> log</td></tr>'+
        '<tr><td>Load avg</td><td><b>'+h.load_1m.toFixed(1)+' / '+h.load_5m.toFixed(1)+' / '+h.load_15m.toFixed(1)+'</b></td></tr>'+
        '<tr><td>CPU usage</td><td><b>'+Math.round(h.cpu_percent)+'%</b></td></tr>'+
        '<tr><td>CPU temp</td><td><b>'+h.cpu_temp_max+'°C</b></td></tr>'+
        '</table></div>';

    // Memory panel
    var memHtml = '<div class="mon-panel">'+
        '<h4>💾 Memory</h4>'+
        '<table>'+
        '<tr><td>Total</td><td><b>'+fmtG(m.total_gib)+'</b></td></tr>'+
        '<tr><td>Used</td><td><b>'+fmtG(m.used_gib)+'</b> ('+Math.round(m.percent)+'%)</td></tr>'+
        '<tr><td>Available</td><td><b>'+fmtG(m.available_gib)+'</b></td></tr>'+
        '<tr><td>Free</td><td><b>'+fmtG(m.free_gib)+'</b></td></tr>'+
        '<tr><td>Cached/Buffers</td><td><b>'+fmtG(m.cached_gib)+'</b></td></tr>'+
        (m.swap_total_gib>0 ? '<tr><td>Swap</td><td><b>'+fmtG(m.swap_used_gib)+'</b> / '+fmtG(m.swap_total_gib)+'</td></tr>' : '<tr><td>Swap</td><td><b>none</b></td></tr>')+
        '</table></div>';

    // GPU panel
    var gpuProcs = (g.processes||[]).map(function(p){
        return '<tr><td colspan="2" style="padding-left:8px;font-size:10px">'+Admin.esc(p.name)+' PID='+p.pid+' VRAM='+p.vram_mb+' MB</td></tr>';
    }).join('');
    var gpuHtml = '<div class="mon-panel">'+
        '<h4>🎮 GPU</h4>'+
        '<table>'+
        '<tr><td>Model</td><td><b>'+Admin.esc(g.name)+'</b></td></tr>'+
        '<tr><td>Driver</td><td><b>'+Admin.esc(g.driver)+'</b></td></tr>'+
        '<tr><td>PCIe</td><td><b>'+g.pcie_gen+'x'+g.pcie_width+'</b></td></tr>'+
        '<tr><td>Load</td><td><b>'+Math.round(g.load_pct)+'%</b></td></tr>'+
        '<tr><td>Temp</td><td><b>'+g.temp_c+'°C</b></td></tr>'+
        '<tr><td>VRAM</td><td><b>'+(g.vram_used_mb/1024).toFixed(1)+' / '+(g.vram_total_mb/1024).toFixed(0)+' GiB</b> ('+Math.round(g.vram_used_mb/g.vram_total_mb*100)+'%)</td></tr>'+
        '<tr><td>Power</td><td><b>'+Math.round(g.power_w)+' W</b></td></tr>'+
        '<tr><td>Fan</td><td><b>'+Math.round(g.fan_pct)+'%</b></td></tr>'+
        '<tr><td>SM clock</td><td><b>'+Math.round(g.sm_clock_mhz)+' MHz</b></td></tr>'+
        '<tr><td>Mem clock</td><td><b>'+Math.round(g.mem_clock_mhz)+' MHz</b></td></tr>'+
        gpuProcs+
        '</table></div>';

    // Disks panel
    var disksHtml = '<div class="mon-panel">'+
        '<h4>💿 Disks</h4>'+
        '<table>'+
        d.map(function(dk){
            return '<tr><td colspan="2"><b>'+Admin.esc(dk.mount)+'</b><br>'+
                '<span style="font-size:10px;color:#6e7681">'+Admin.esc(dk.device)+' ('+Admin.esc(dk.fstype)+')</span><br>'+
                '<span style="font-size:11px;color:#c9d1d9">'+
                '<b>'+fmtG(dk.total_gib)+'</b> total &nbsp;|&nbsp; used <b>'+fmtG(dk.used_gib)+'</b> ('+Math.round(dk.percent)+'%) &nbsp;|&nbsp; free <b>'+fmtG(dk.free_gib)+'</b>'+
                '</span></td></tr>';
        }).join('')+
        '</table></div>';

    // Network panel
    var netHtml = '<div class="mon-panel">'+
        '<h4>🌐 Network</h4>'+
        '<table>'+
        '<tr><td>RX total</td><td><b>'+n.rx_gb.toFixed(2)+' GB</b> ('+n.packets_recv+' pkt)</td></tr>'+
        '<tr><td>TX total</td><td><b>'+n.tx_gb.toFixed(2)+' GB</b> ('+n.packets_sent+' pkt)</td></tr>'+
        '<tr><td>RX speed</td><td><b>'+(n.rx_mbps||0).toFixed(1)+' Mbps</b></td></tr>'+
        '<tr><td>TX speed</td><td><b>'+(n.tx_mbps||0).toFixed(1)+' Mbps</b></td></tr>'+
        '</table></div>';

    // Disk IO panel
    var io = r.disk_io || {};
    var ioHtml = '<div class="mon-panel">'+
        '<h4>📀 Disk I/O</h4>'+
        '<table>'+
        '<tr><td>Read</td><td><b>'+(io.read_mbps||0).toFixed(1)+' MB/s</b></td></tr>'+
        '<tr><td>Write</td><td><b>'+(io.write_mbps||0).toFixed(1)+' MB/s</b></td></tr>'+
        '</table></div>';

    // Top processes panel
    var procsHtml = '<div class="mon-panel">'+
        '<h4>⚡ Top Processes</h4>'+
        '<table>'+
        (t||[]).map(function(p){
            return '<tr><td>'+Admin.esc(p.name)+' <span style="font-size:10px;color:#6e7681">PID='+p.pid+'</span></td>'+
                '<td>RAM <b>'+p.mem_pct.toFixed(1)+'%</b> | CPU <b>'+p.cpu_pct.toFixed(1)+'%</b></td></tr>';
        }).join('')+
        '</table></div>';

    // Gailray DB panel
    var dbHtml = '<div class="mon-panel">'+
        '<h4>🗃 Gailray DB</h4>'+
        '<table>'+
        '<tr><td>Photos</td><td><b>'+gr.photos+'</b></td></tr>'+
        '<tr><td>Persons</td><td><b>'+gr.persons+'</b></td></tr>'+
        '<tr><td>Faces</td><td><b>'+gr.faces+'</b></td></tr>'+
        '<tr><td>Catalog files</td><td><b>'+gr.catalog_files+'</b></td></tr>'+
        '<tr><td>SQLite</td><td><b>'+gr.db_size_mb.toFixed(0)+' MB</b></td></tr>'+
        '<tr><td>LanceDB</td><td><b>'+gr.lancedb_size_mb.toFixed(0)+' MB</b></td></tr>'+
        '</table></div>';

    el.innerHTML = hostHtml + memHtml + gpuHtml + disksHtml + netHtml + ioHtml + procsHtml + dbHtml;
};
