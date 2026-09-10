// NEXUS Wealth Dashboard renderer
(function () {
  const fmtINR = (n, opts = {}) => {
    if (n === null || n === undefined || isNaN(n)) return '—';
    const abs = Math.abs(n);
    if (opts.compact) {
      if (abs >= 1e7) return '₹' + (n / 1e7).toFixed(2) + ' Cr';
      if (abs >= 1e5) return '₹' + (n / 1e5).toFixed(2) + ' L';
    }
    return '₹' + n.toLocaleString('en-IN', { maximumFractionDigits: 0 });
  };
  const fmtPct = (n, d = 1) => (n === null || n === undefined || isNaN(n)) ? '—' : (n * 100).toFixed(d) + '%';
  const fmtSignedPct = (n, d = 1) => (n === null || n === undefined || isNaN(n)) ? '—' : (n >= 0 ? '+' : '') + (n * 100).toFixed(d) + '%';
  const fmtUsd = (n) => '$' + n.toLocaleString('en-US', { maximumFractionDigits: 2 });

  const CHART_COLORS = {
    cyan: '#3b82f6', violet: '#8b5cf6', amber: '#d97706', green: '#16a34a',
    pink: '#db2777', red: '#dc2626', slate: '#64748b', blue: '#3b82f6',
  };

  Chart.defaults.color = '#8ea3c9';
  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';

  const charts = {}; // registry so range/mode toggles can update in place

  function boot() {
    const data = window.DASHBOARD_DATA;
    const app = document.getElementById('app');
    if (!data) {
      app.innerHTML = `<div class="panel" style="text-align:center;padding:60px;">
        <i class="fa-solid fa-triangle-exclamation" style="font-size:32px;color:#ffb84d;"></i>
        <h2 style="font-family:'Manrope';margin-top:16px;">No data.js found</h2>
        <p style="color:#8ea3c9;">Run <code>python refresh_data.py</code> in this folder to generate the dashboard data, then reload this page.</p>
      </div>`;
      return;
    }

    const tpl = document.getElementById('tpl-root');
    app.innerHTML = '';
    app.appendChild(tpl.content.cloneNode(true));

    initTopbarControls(data);

    // ---- sync pill ----
    document.getElementById('syncText').textContent =
      'Synced ' + new Date(data.generatedAt).toLocaleString();
    document.getElementById('lastRefreshed').textContent = new Date(data.generatedAt).toLocaleString();
    document.getElementById('fxTag').textContent = `USD/INR ${data.fx.usdinr.toFixed(2)}`;
    if (data.dataSources) {
      document.getElementById('dataSourceNote').textContent =
        `Stocks: ${data.dataSources.stocks} · Crypto: ${data.dataSources.crypto} · FX: ${data.dataSources.fx}`;
    }

    // ---- KPIs ----
    document.getElementById('kpiNetWorth').textContent = fmtINR(data.netWorth.combined, { compact: true });
    const savingsRate = data.monthlySavings.combined / data.income.combined.salary;
    document.getElementById('kpiSavingsRate').textContent = fmtPct(savingsRate);
    document.getElementById('kpiSavingsAmt').textContent = fmtINR(data.monthlySavings.combined) + ' / month';
    document.getElementById('kpiRisk').textContent = data.risk.level;
    document.getElementById('kpiRiskScore').textContent = `Score ${data.risk.score}/100`;
    document.getElementById('kpiReturn').textContent = fmtPct(data.assumptions.blendedPortfolioReturn);
    initKpiDetails(data);

    renderAlerts(data);
    renderMacroPanel(data);
    renderProjection(data);
    initWhatIf(data);
    renderAllocation(data);
    renderGoals(data);
    renderTrendAndDrawdown(data);
    renderAlpha(data);
    renderRiskReturn(data);
    renderTreemap(data);
    renderDrift(data);
    renderCashFlowDiagram(data);
    renderContributions(data);
    renderTickers(data);
    renderTopHoldings(data);
    renderCashFlow(data);
    renderInsights(data);
    initNlQuery(data);
    initExport(data);
    initTickerTape(data);
    initDeepData(data);
  }

  // -------------------------------------------------------------- kpi detail
  function initKpiDetails(data) {
    const allocLabels = { emergency: 'Emergency Fund', pension: 'Pension Fund', debt: 'Debt Funds', indianEquity: 'Indian Equity', foreignEquity: 'Foreign Equity (Stocks/ETFs)', crypto: 'Crypto' };
    const husbandTotal = data.netWorth.husband || 0;
    const allocRows = Object.entries(data.allocation).map(([k, v]) => `<div class="kpi-detail-row"><span class="kdr-label">${allocLabels[k] || k}</span><div class="kdr-line"><b class="priv-num">${fmtINR(v, { compact: true })}</b><span class="kpi-detail-pct">${husbandTotal ? (v / husbandTotal * 100).toFixed(1) : '—'}%</span></div></div>`).join('');
    const wifeRow = `<div class="kpi-detail-row"><span class="kdr-label">Wife's Corpus (cached, external tracker)</span><div class="kdr-line"><b class="priv-num">${fmtINR(data.netWorth.wifeCached, { compact: true })}</b><span class="kpi-detail-pct">${data.netWorth.combined ? (data.netWorth.wifeCached / data.netWorth.combined * 100).toFixed(1) : '—'}%</span></div></div>`;
    document.getElementById('kpiDetailNetworth').innerHTML =
      `<div class="kpi-detail-caption">Breakdown of Husband's tracked portfolio (₹${(husbandTotal / 1e5).toFixed(1)}L), plus Wife's separately-tracked corpus — together these sum to Combined Net Worth above.</div>`
      + allocRows + wifeRow;

    document.getElementById('kpiDetailSavings').innerHTML = `
      <div class="kpi-detail-row"><span class="kdr-label"><i class="fa-solid fa-user-astronaut"></i> Husband</span><div class="kdr-line"><b class="priv-num">${fmtINR(data.monthlySavings.sb)}</b></div></div>
      <div class="kpi-detail-row"><span class="kdr-label"><i class="fa-solid fa-user-nurse"></i> Wife</span><div class="kdr-line"><b class="priv-num">${fmtINR(data.monthlySavings.jb)}</b></div></div>`;


    document.getElementById('kpiDetailRisk').innerHTML = data.risk.factors.map(f => `<div class="kpi-detail-row risk-row"><i class="fa-solid fa-triangle-exclamation"></i><span>${f}</span></div>`).join('');

    const arLabels = { emergency: 'Emergency Fund', pension: 'Pension Fund', debt: 'Debt Funds', indianEquity: 'Indian Equity', foreignEquity: 'Foreign Equity', indian_equity: 'Indian Equity', foreign_equity: 'Foreign Equity', crypto: 'Crypto' };
    document.getElementById('kpiDetailReturn').innerHTML =
      `<div class="kpi-detail-caption">Assumed annual return by asset class (used for projections) — not a portfolio-weight breakdown, so these don't sum to 100%.</div>`
      + Object.entries(data.assumptions.assetReturns || {}).map(([k, v]) =>
      `<div class="kpi-detail-row"><span class="kdr-label">${arLabels[k] || k}</span><div class="kdr-line"><b>${fmtPct(v)}</b></div></div>`).join('');


    document.querySelectorAll('.kpi-card').forEach(card => {
      const toggle = () => {
        const willOpen = !card.classList.contains('expanded');
        card.classList.toggle('expanded', willOpen);
        card.setAttribute('aria-expanded', String(willOpen));
      };
      card.addEventListener('click', toggle);
      card.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
    });
  }

  // ---------------------------------------------------------------- topbar
  function initTopbarControls() {
    const privacyBtn = document.getElementById('privacyToggle');
    privacyBtn.addEventListener('click', () => {
      const on = document.body.classList.toggle('privacy-on');
      privacyBtn.innerHTML = `<i class="fa-solid fa-eye${on ? '-slash' : ''}"></i>`;
      privacyBtn.classList.toggle('active', on);
    });

    const themeBtn = document.getElementById('themeToggle');
    themeBtn.addEventListener('click', () => {
      const light = document.body.getAttribute('data-theme') === 'light';
      document.body.setAttribute('data-theme', light ? 'dark' : 'light');
      themeBtn.innerHTML = `<i class="fa-solid fa-${light ? 'moon' : 'sun'}"></i>`;
    });
  }

  // ---------------------------------------------------------------- alerts
  function renderAlerts(data) {
    const el = document.getElementById('alertsList');
    (data.alerts || []).forEach(a => {
      el.insertAdjacentHTML('beforeend', `
        <div class="alert-item ${a.severity}">
          <span class="alert-badge">${a.severity}</span>
          <span>${a.message}</span>
        </div>`);
    });
  }

  // ---------------------------------------------------------- macro backdrop
  function renderMacroPanel(data) {
    const grid = document.getElementById('macroGrid');
    if (grid && Array.isArray(data.macro) && data.macro.length) {
      const macroHtml = data.macro.map(m => buildTickerCard(
        m.ticker, m.ticker, m.price, m.changePct, '',
        m.name || '', null, data.macroHistory && data.macroHistory[m.ticker], m.low52, m.high52,
      )).join('');
      grid.innerHTML = macroHtml;
      wireTickerExpand(grid, data.macroHistory || {});
    } else if (grid) {
      grid.innerHTML = '<p class="ticker-nohist">Global indicators unavailable this refresh.</p>';
    }

    const im = data.indiaMacro;
    if (im && im.inflation && im.inflation.latestPct != null) {
      document.getElementById('indiaCpiValue').textContent = im.inflation.latestPct.toFixed(1) + '% (' + im.inflation.latestYear + ')';
      document.getElementById('indiaCpiFoot').textContent = `World Bank Open Data · latest available ${im.inflation.latestYear}`;
      const years = im.inflation.years || [], values = im.inflation.values || [];
      charts.indiaCpi = new Chart(document.getElementById('chartIndiaCpi'), {
        type: 'bar',
        data: { labels: years, datasets: [{ data: values, backgroundColor: CHART_COLORS.amber, borderRadius: 4 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => ctx.parsed.y.toFixed(1) + '%' } } },
          scales: { x: { grid: { display: false } }, y: { ticks: { callback: (v) => v + '%' }, grid: { color: 'rgba(255,255,255,0.04)' } } } },
      });
    }
    if (im && im.gdp && im.gdp.years && im.gdp.years.length) {
      const latestReal = im.gdp.latestRealPct, latestNominal = im.gdp.latestNominalPct;
      document.getElementById('indiaGdpValue').textContent =
        (latestReal != null ? 'Real ' + latestReal.toFixed(1) + '%' : '—') + (latestNominal != null ? ' · Nominal ' + latestNominal.toFixed(1) + '%' : '');
      document.getElementById('indiaGdpFoot').textContent = `World Bank Open Data · latest available ${im.gdp.years[im.gdp.years.length - 1]}`;
      charts.indiaGdp = new Chart(document.getElementById('chartIndiaGdp'), {
        type: 'line',
        data: {
          labels: im.gdp.years,
          datasets: [
            { label: 'Real GDP growth', data: im.gdp.real, borderColor: CHART_COLORS.cyan, backgroundColor: 'transparent', tension: 0.3, pointRadius: 2 },
            { label: 'Nominal GDP growth', data: im.gdp.nominal, borderColor: CHART_COLORS.violet, backgroundColor: 'transparent', tension: 0.3, pointRadius: 2, borderDash: [4, 3] },
          ],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%` } } },
          scales: { x: { grid: { display: false } }, y: { ticks: { callback: (v) => v + '%' }, grid: { color: 'rgba(255,255,255,0.04)' } } } },
      });
    }

    initInrDepreciation(data);
  }

  // ------------------------------------------------------- INR depreciation
  function initInrDepreciation(data) {
    const fxd = data.fxDepreciation;
    const toggle = document.getElementById('inrRangeToggle');
    if (!fxd || !fxd.dates || fxd.dates.length < 2 || !toggle) return;
    const horizons = fxd.horizons || [];
    if (!horizons.length) return;

    function drawForYears(years) {
      const h = horizons.find(x => x.years === years);
      const monthsBack = years * 12;
      const startIdx = Math.max(0, fxd.dates.length - monthsBack - 1);
      const dates = fxd.dates.slice(startIdx);
      const rates = fxd.rates.slice(startIdx);
      const up = h ? h.changePct >= 0 : true;
      document.getElementById('inrYoyValue').innerHTML = h
        ? `${fmtSignedPct(h.changePct / 100, 1)} over ${years}Y <span class="ticker-change ${up ? 'up' : 'down'}" style="font-size:13px;"><i class="fa-solid fa-caret-${up ? 'up' : 'down'}"></i></span>`
        : '—';
      document.getElementById('inrYoyFoot').textContent = h
        ? `₹${h.pastRate.toFixed(2)} (${h.pastDate}) → ₹${h.currentRate.toFixed(2)} today · Yahoo Finance USD/INR`
        : 'Yahoo Finance USD/INR spot history';
      if (charts.inrTrend) charts.inrTrend.destroy();
      charts.inrTrend = new Chart(document.getElementById('chartInrTrend'), {
        type: 'line',
        data: { labels: dates, datasets: [{ data: rates, borderColor: up ? CHART_COLORS.red : CHART_COLORS.green, backgroundColor: 'transparent', borderWidth: 1.5, tension: 0.2, pointRadius: 0 }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => '₹' + ctx.parsed.y.toFixed(2) } } },
          scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 6 } }, y: { ticks: { callback: (v) => '₹' + v.toFixed(1) }, grid: { color: 'rgba(255,255,255,0.04)' } } },
        },
      });
    }

    toggle.innerHTML = horizons.map(h => `<button data-range="${h.years}">${h.years}Y</button>`).join('');
    toggle.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', () => {
        toggle.querySelectorAll('button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        drawForYears(parseInt(btn.dataset.range, 10));
      });
    });
    const defaultHorizon = horizons.find(h => h.years === 5) || horizons[0];
    const defaultBtn = toggle.querySelector(`button[data-range="${defaultHorizon.years}"]`);
    if (defaultBtn) defaultBtn.classList.add('active');
    drawForYears(defaultHorizon.years);
  }

  // ------------------------------------------------------------ projection
  function renderProjection(data) {
    const years = data.projections.years;
    charts.projection = new Chart(document.getElementById('chartProjection'), {
      type: 'line',
      data: {
        labels: years.map(y => `+${y}y`),
        datasets: [
          {
            label: 'Savings only (real)',
            data: data.projections.scenario1.map(p => p.real),
            borderColor: CHART_COLORS.slate, backgroundColor: 'transparent',
            borderDash: [6, 4], tension: 0.35, pointRadius: 3,
          },
          {
            label: 'Savings + growth (real)',
            data: data.projections.scenario2.map(p => p.real),
            borderColor: CHART_COLORS.cyan, backgroundColor: 'rgba(56,242,255,0.08)',
            fill: true, tension: 0.35, pointRadius: 3,
          },
          {
            label: 'Savings + growth +10% YoY step-up (real)',
            data: data.projections.scenario3.map(p => p.real),
            borderColor: CHART_COLORS.green, backgroundColor: 'rgba(61,255,176,0.10)',
            fill: true, tension: 0.35, pointRadius: 3,
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${fmtINR(ctx.parsed.y, { compact: true })}` } },
        },
        scales: {
          y: { ticks: { callback: (v) => fmtINR(v, { compact: true }) }, grid: { color: 'rgba(255,255,255,0.04)' } },
          x: { grid: { display: false } },
        },
      },
    });
  }

  // ------------------------------------------------------------- what-if
  function initWhatIf(data) {
    const els = {
      savings: document.getElementById('wiSavings'),
      ret: document.getElementById('wiReturn'),
      inflation: document.getElementById('wiInflation'),
      years: document.getElementById('wiYears'),
    };
    const labels = {
      savings: document.getElementById('wiSavingsVal'),
      ret: document.getElementById('wiReturnVal'),
      inflation: document.getElementById('wiInflationVal'),
      years: document.getElementById('wiYearsVal'),
    };
    const resultEl = document.getElementById('wiResult');
    const baseMonthly = data.monthlySavings.combined;
    const baseReturn = data.assumptions.blendedPortfolioReturn;

    function recompute() {
      const savingsAdjPct = Number(els.savings.value) / 100;
      const returnAdjPts = Number(els.ret.value) / 100;
      const inflation = Number(els.inflation.value) / 100;
      const yearsN = Number(els.years.value);

      labels.savings.textContent = (savingsAdjPct >= 0 ? '+' : '') + (savingsAdjPct * 100).toFixed(0) + '%';
      labels.ret.textContent = (returnAdjPts >= 0 ? '+' : '') + (returnAdjPts * 100).toFixed(1) + 'pt';
      labels.inflation.textContent = (inflation * 100).toFixed(1) + '%';
      labels.years.textContent = yearsN + 'y';

      const monthly = baseMonthly * (1 + savingsAdjPct);
      const nominalReturn = Math.max(0, baseReturn + returnAdjPts);
      const realMonthlyRate = ((1 + nominalReturn) / (1 + inflation)) - 1;
      const rMonthly = Math.pow(1 + realMonthlyRate, 1 / 12) - 1;
      const nMonths = yearsN * 12;
      let fv = data.netWorth.combined;
      if (Math.abs(rMonthly) > 1e-9) {
        fv = fv * Math.pow(1 + rMonthly, nMonths) + monthly * ((Math.pow(1 + rMonthly, nMonths) - 1) / rMonthly);
      } else {
        fv = fv + monthly * nMonths;
      }
      resultEl.innerHTML = `Projected net worth in <b>${yearsN} years</b> (today's purchasing power): <b style="color:var(--cyan)">${fmtINR(fv, { compact: true })}</b>` +
        ` <span class="priv-num" style="display:none">${fmtINR(fv)}</span>`;
      resultEl.classList.toggle('priv-num', false);
    }
    Object.values(els).forEach(el => el.addEventListener('input', recompute));
    recompute();
  }

  // ------------------------------------------------------------- allocation
  function renderAllocation(data) {
    const alloc = data.allocation;
    const allocKeys = ['emergency', 'pension', 'debt', 'indianEquity', 'foreignEquity', 'crypto'];
    const allocLabels = ['Emergency Fund', 'Pension Fund', 'Debt Funds', 'Indian Equity', 'Foreign Equity', 'Crypto'];
    const allocValues = allocKeys.map(k => alloc[k]);
    const allocColors = [CHART_COLORS.slate, CHART_COLORS.violet, CHART_COLORS.amber, CHART_COLORS.pink, CHART_COLORS.cyan, CHART_COLORS.green];
    const total = allocValues.reduce((a, b) => a + b, 0);

    const drillEl = document.getElementById('allocDrill');
    charts.allocation = new Chart(document.getElementById('chartAllocation'), {
      type: 'doughnut',
      data: { labels: allocLabels, datasets: [{ data: allocValues, backgroundColor: allocColors, borderColor: '#0c1224', borderWidth: 3 }] },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '65%',
        onClick: (evt, elements) => {
          if (!elements.length) return;
          const idx = elements[0].index;
          const key = allocKeys[idx];
          drillEl.innerHTML = `<div class="drill-row"><b>${allocLabels[idx]} drill-down</b><span>${fmtINR(allocValues[idx], { compact: true })} (${(allocValues[idx] / total * 100).toFixed(1)}%)</span></div>`;
          if (key === 'foreignEquity') {
            [...data.stocks].sort((a, b) => b.valueInr - a.valueInr).forEach(h => {
              drillEl.insertAdjacentHTML('beforeend', `<div class="drill-row"><span>${h.ticker}</span><b>${fmtINR(h.valueInr, { compact: true })}</b></div>`);
            });
          } else if (key === 'crypto') {
            data.crypto.forEach(c => drillEl.insertAdjacentHTML('beforeend', `<div class="drill-row"><span>${c.symbol}</span><b>${fmtINR(c.valueInr, { compact: true })}</b></div>`));
          } else {
            drillEl.insertAdjacentHTML('beforeend', `<div class="drill-row"><span>Manually tracked in Savings sheet</span><b>—</b></div>`);
          }
        },
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 10, padding: 14 } },
          tooltip: { callbacks: { label: (ctx) => ` ${ctx.label}: ${fmtINR(ctx.parsed, { compact: true })} (${(ctx.parsed / total * 100).toFixed(1)}%)` } },
        },
      },
    });

    charts.allocationBar = new Chart(document.getElementById('chartAllocationBar'), {
      type: 'bar',
      data: { labels: allocLabels, datasets: [{ data: allocValues, backgroundColor: allocColors, borderRadius: 8 }] },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => fmtINR(ctx.parsed.x, { compact: true }) } } },
        scales: {
          x: { ticks: { callback: (v) => fmtINR(v, { compact: true }) }, grid: { color: 'rgba(255,255,255,0.04)' } },
          y: { grid: { display: false } },
        },
      },
    });
  }

  // ------------------------------------------------------------------ goals
  function renderGoals(data) {
    const grid = document.getElementById('goalsGrid');
    (data.goals || []).forEach((g, i) => {
      const pct = Math.min(100, g.progressPct * 100);
      const cid = `goalRing${i}`;
      grid.insertAdjacentHTML('beforeend', `
        <div class="goal-card">
          <div class="goal-ring"><canvas id="${cid}"></canvas><div class="goal-ring-label">${pct.toFixed(0)}%</div></div>
          <div class="goal-info">
            <div class="goal-name"><i class="fa-solid fa-flag-checkered"></i> ${g.name}</div>
            <div class="goal-nums priv-num">${fmtINR(g.current, { compact: true })} / ${fmtINR(g.target, { compact: true })}</div>
          </div>
        </div>`);
      new Chart(document.getElementById(cid), {
        type: 'doughnut',
        data: { datasets: [{ data: [pct, 100 - pct], backgroundColor: [CHART_COLORS.green, 'rgba(255,255,255,0.06)'], borderWidth: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '72%', plugins: { legend: { display: false }, tooltip: { enabled: false } } },
      });
    });
  }

  // --------------------------------------------------------- trend/drawdown
  function renderTrendAndDrawdown(data) {
    const h = data.history;
    if (!h || !h.available) return;
    const rangeDays = { '1M': 22, '3M': 66, '6M': 132, '1Y': h.dates.length };
    let currentRange = '1Y', currentMode = 'value';

    function slice(arr, n) { return arr.slice(Math.max(0, arr.length - n)); }
    function rebase(arr) { const base = arr[0] || 1; return arr.map(v => (v / base - 1)); }

    function draw() {
      const n = rangeDays[currentRange];
      const dates = slice(h.dates, n);
      let port = slice(h.portfolioInr, n);
      let bench = slice(h.benchmarkNormalized, n);
      let yFmt = (v) => fmtINR(v, { compact: true });
      if (currentMode === 'pct') {
        port = rebase(port); bench = rebase(bench);
        yFmt = (v) => fmtSignedPct(v);
      }
      if (charts.trend) charts.trend.destroy();
      charts.trend = new Chart(document.getElementById('chartTrend'), {
        type: 'line',
        data: {
          labels: dates,
          datasets: [
            { label: 'Portfolio', data: port, borderColor: CHART_COLORS.cyan, backgroundColor: 'rgba(56,242,255,0.10)', fill: true, tension: 0.25, pointRadius: 0 },
            { label: h.benchmarkLabel || 'Benchmark', data: bench, borderColor: CHART_COLORS.violet, backgroundColor: 'transparent', borderDash: [5, 4], tension: 0.25, pointRadius: 0 },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
          plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${yFmt(ctx.parsed.y)}` } } },
          scales: {
            y: { ticks: { callback: yFmt }, grid: { color: 'rgba(255,255,255,0.04)' } },
            x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
          },
        },
      });

      const dd = slice(h.drawdownPct, n);
      if (charts.drawdown) charts.drawdown.destroy();
      charts.drawdown = new Chart(document.getElementById('chartDrawdown'), {
        type: 'line',
        data: { labels: dates, datasets: [{ label: 'Drawdown', data: dd, borderColor: CHART_COLORS.red, backgroundColor: 'rgba(255,77,109,0.15)', fill: true, tension: 0.2, pointRadius: 0 }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => fmtSignedPct(ctx.parsed.y) } } },
          scales: { y: { ticks: { callback: (v) => fmtSignedPct(v, 0) }, grid: { color: 'rgba(255,255,255,0.04)' } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } } },
        },
      });
    }

    document.querySelectorAll('#rangeToggle button').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#rangeToggle button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentRange = btn.dataset.range;
        draw();
      });
    });
    document.querySelectorAll('#modeToggle button').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#modeToggle button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentMode = btn.dataset.mode;
        draw();
      });
    });
    draw();
  }

  // ------------------------------------------------------------------ alpha
  function renderAlpha(data) {
    const rows = data.alphaByPeriod || [];
    charts.alpha = new Chart(document.getElementById('chartAlpha'), {
      type: 'bar',
      data: {
        labels: rows.map(r => r.period),
        datasets: [{ label: 'Alpha', data: rows.map(r => r.alpha), backgroundColor: rows.map(r => r.alpha >= 0 ? CHART_COLORS.green : CHART_COLORS.red), borderRadius: 8 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `Alpha: ${fmtSignedPct(ctx.parsed.y)}` } } },
        scales: { y: { ticks: { callback: (v) => fmtSignedPct(v, 0) }, grid: { color: 'rgba(255,255,255,0.04)' } }, x: { grid: { display: false } } },
      },
    });
  }

  // ------------------------------------------------------------ risk/return
  function renderRiskReturn(data) {
    const rows = data.riskReturnBubble || [];
    const maxW = Math.max(...rows.map(r => r.weight), 1);
    const palette = [CHART_COLORS.slate, CHART_COLORS.violet, CHART_COLORS.amber, CHART_COLORS.pink, CHART_COLORS.cyan, CHART_COLORS.green];
    charts.riskReturn = new Chart(document.getElementById('chartRiskReturn'), {
      type: 'bubble',
      data: {
        datasets: rows.map((r, i) => ({
          label: r.label,
          data: [{ x: r.riskPct, y: r.returnPct, r: 6 + (r.weight / maxW) * 24 }],
          backgroundColor: palette[i % palette.length] + 'aa',
          borderColor: palette[i % palette.length],
        })),
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 8 } }, tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: risk ${ctx.parsed.x.toFixed(1)}%, return ${ctx.parsed.y.toFixed(1)}%` } } },
        scales: {
          x: { title: { display: true, text: 'Volatility / Risk (%)' }, grid: { color: 'rgba(255,255,255,0.04)' } },
          y: { title: { display: true, text: 'Expected Return (%)' }, grid: { color: 'rgba(255,255,255,0.04)' } },
        },
      },
    });
  }

  // --------------------------------------------------------------- treemap
  function renderTreemap(data) {
    const rows = data.treemap || [];
    if (!window.ChartTreemap && !Chart.registry.controllers.get('treemap')) {
      // plugin failed to load - fallback simple bar
      charts.treemap = new Chart(document.getElementById('chartTreemap'), {
        type: 'bar',
        data: { labels: rows.map(r => r.ticker), datasets: [{ data: rows.map(r => r.value), backgroundColor: CHART_COLORS.cyan, borderRadius: 8 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
      });
      return;
    }
    charts.treemap = new Chart(document.getElementById('chartTreemap'), {
      type: 'treemap',
      data: {
        datasets: [{
          tree: rows, key: 'value',
          groups: ['sector'],
          labels: {
            display: true,
            formatter: (ctx) => {
              if (!ctx.raw || !ctx.raw._data) return '';
              const w = ctx.raw.w || 0, h = ctx.raw.h || 0;
              const name = ctx.raw._data.ticker || ctx.raw.g || '';
              // Tiny tiles: skip the label entirely rather than render unreadable overflow text
              if (w < 42 || h < 26) return '';
              // Small tiles: name only, no value line (keeps text inside the box)
              if (w < 92 || h < 46) return [name];
              return [name, fmtINR(ctx.raw.v, { compact: true })];
            },
            color: '#0c1224', font: (ctx) => {
              const w = (ctx.raw && ctx.raw.w) || 0, h = (ctx.raw && ctx.raw.h) || 0;
              const size = Math.max(9, Math.min(14, Math.floor(Math.min(w, h) / 6)));
              return { family: "'Rajdhani', sans-serif", weight: '600', size };
            },
          },
          backgroundColor: (ctx) => {
            const palette = ['#38f2ff', '#a066ff', '#ffb84d', '#3dffb0', '#ff5ea8', '#7d8bab', '#ff4d6d'];
            return palette[(ctx.dataIndex || 0) % palette.length];
          },
          borderColor: '#0c1224', borderWidth: 2, spacing: 2,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => {
            const d = ctx.raw && ctx.raw._data;
            if (!d) return '';
            return `${d.ticker} (${d.sector}, ${d.geo}): ${fmtINR(ctx.raw.v, { compact: true })}`;
          } } },
        },
      },
    });
  }

  // ------------------------------------------------------------------ drift
  function renderDrift(data) {
    const rows = data.drift || [];
    charts.drift = new Chart(document.getElementById('chartDrift'), {
      type: 'bar',
      data: {
        labels: rows.map(r => r.label),
        datasets: [
          { label: 'Current', data: rows.map(r => r.current * 100), backgroundColor: CHART_COLORS.cyan, borderRadius: 6 },
          { label: 'Target', data: rows.map(r => r.target * 100), backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 6 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%` } } },
        scales: { y: { ticks: { callback: (v) => v + '%' }, grid: { color: 'rgba(255,255,255,0.04)' } }, x: { grid: { display: false } } },
      },
    });
  }

  // ----------------------------------------------------------- cashflow-flow
  function renderCashFlowDiagram(data) {
    const el = document.getElementById('cashFlowDiagram');
    if (!el) return;
    const sb = data.income.sb, jb = data.income.jb;
    const fixed = data.expenseBreakdown.fixedMonthly || 0;
    const savings = data.monthlySavings.combined || 0;
    const totalIncome = (sb.salary || 0) + (jb.salary || 0);
    // sb.expenses (living) already contains the Fixed Expenses amount (Husband_Expense row 10
    // "Term Life Insurance" literally references Fixed Expenses!I2) — subtract it here so the
    // dedicated "Fixed Expenses" node below isn't counted twice.
    const sbOtherLiving = Math.max((sb.expenses || 0) - fixed, 0);
    const leftover = Math.max(totalIncome - fixed - sbOtherLiving - (jb.expenses || 0) - savings, 0);

    const sources = [
      { label: 'Husband Income', value: sb.salary || 0, color: CHART_COLORS.cyan },
      { label: 'Wife Income', value: jb.salary || 0, color: CHART_COLORS.pink },
    ].filter(x => x.value > 0);

    const uses = [
      { label: 'Fixed Expenses', value: fixed, color: CHART_COLORS.amber, icon: 'fa-house' },
      { label: 'Husband Living Expenses', value: sbOtherLiving, color: CHART_COLORS.cyan, icon: 'fa-user-astronaut' },
      { label: 'Wife Living Expenses', value: jb.expenses || 0, color: CHART_COLORS.pink, icon: 'fa-user-nurse' },
      { label: 'Savings & Investments', value: savings, color: CHART_COLORS.green, icon: 'fa-piggy-bank' },
      { label: 'Uncommitted Cash', value: leftover, color: CHART_COLORS.violet || '#8b7cf6', icon: 'fa-wallet' },
    ].filter(x => x.value > 0);


    const total = totalIncome || uses.reduce((a, b) => a + b.value, 0) || 1;
    const segStyle = (x) => `flex: ${Math.max(x.value, 0.0001)} 0 0; background:${x.color};`;

    el.innerHTML = `
      <div class="flow-row flow-row-top">
        <span class="flow-row-label">Income Sources</span>
        <div class="flow-bar">
          ${sources.map(s => `<div class="flow-seg" style="${segStyle(s)}" title="${s.label}: ${fmtINR(s.value, { compact: true })}"></div>`).join('')}
        </div>
      </div>
      <div class="flow-connector"><i class="fa-solid fa-angles-down"></i></div>
      <div class="flow-node-total">
        <i class="fa-solid fa-house-chimney"></i>
        <div><span>Household Income</span><b class="priv-num">${fmtINR(totalIncome, { compact: true })}</b></div>
      </div>
      <div class="flow-connector"><i class="fa-solid fa-angles-down"></i></div>
      <div class="flow-row flow-row-bottom">
        <span class="flow-row-label">Allocation</span>
        <div class="flow-bar">
          ${uses.map(u => `<div class="flow-seg" style="${segStyle(u)}" title="${u.label}: ${fmtINR(u.value, { compact: true })}"></div>`).join('')}
        </div>
      </div>
      <div class="flow-legend">
        ${[...sources, ...uses].map(x => `
          <div class="flow-legend-item">
            <span class="dot" style="background:${x.color}"></span>
            ${x.icon ? `<i class="fa-solid ${x.icon}"></i>` : ''}
            <span>${x.label}</span>
            <b class="priv-num">${fmtINR(x.value, { compact: true })}</b>
            <span class="flow-legend-pct">${fmtPct(x.value / total, 0)}</span>
          </div>`).join('')}
      </div>`;
  }

  // ---------------------------------------------------------- contributions
  function renderContributions(data) {
    const cf = data.contributionsForecast;
    if (!cf) return;
    charts.contrib = new Chart(document.getElementById('chartContributions'), {
      type: 'bar',
      data: {
        labels: cf.months,
        datasets: [
          { label: 'Husband', data: cf.sb, backgroundColor: CHART_COLORS.cyan, stack: 's' },
          { label: 'Wife', data: cf.jb, backgroundColor: CHART_COLORS.pink, stack: 's' },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${fmtINR(ctx.parsed.y, { compact: true })}` } } },
        scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, ticks: { callback: (v) => fmtINR(v, { compact: true }) }, grid: { color: 'rgba(255,255,255,0.04)' } } },
      },
    });
  }

  // ----------------------------------------------------------------- tickers
  function analystChipClass(consensus) {
    if (!consensus) return 'slate';
    const c = consensus.toLowerCase();
    if (c.includes('buy')) return 'green';
    if (c.includes('sell') || c.includes('underperform')) return 'red';
    return 'amber';
  }

  function intelBadgesHtml(analyst, dividend, earnings) {
    const chips = [];
    if (analyst && analyst.consensus) {
      chips.push(`<div class="intel-chip intel-${analystChipClass(analyst.consensus)}">
        <i class="fa-solid fa-comments-dollar"></i>
        <span>Analyst: <b>${analyst.consensus}</b> (${analyst.numAnalysts} analysts)</span>
      </div>`);
    }
    if (earnings && (earnings.nextFiscalQuarterEnd || earnings.lastReportedDate)) {
      chips.push(`<div class="intel-chip intel-slate">
        <i class="fa-solid fa-calendar-days"></i>
        <span>${earnings.nextFiscalQuarterEnd ? `Next qtr end ${earnings.nextFiscalQuarterEnd}` : ''}${earnings.consensusEps ? ` · Est. EPS $${earnings.consensusEps}` : ''}${earnings.lastReportedDate ? ` · Last reported ${earnings.lastReportedDate}` : ''}</span>
      </div>`);
    }
    if (dividend && dividend.exDividendDate) {
      chips.push(`<div class="intel-chip intel-violet">
        <i class="fa-solid fa-hand-holding-dollar"></i>
        <span>Ex-Div ${dividend.exDividendDate}${dividend.yield ? ` · Yield ${dividend.yield}` : ''}</span>
      </div>`);
    }
    return chips.join('');
  }

  function buildTickerCard(id, symbolHtml, priceUsd, changePct, changeSuffix, metaHtml, valueInr, hist, low52, high52, intel) {
    const up = changePct >= 0;
    const hasHist = hist && hist.dates && hist.dates.length > 1;
    const hasRange = low52 != null && high52 != null && high52 > low52;
    const intelHtml = intel ? intelBadgesHtml(intel.analyst, intel.dividend, intel.earnings) : '';
    const expandable = hasHist || hasRange || !!intelHtml;
    const rangePct = hasRange ? Math.min(100, Math.max(0, ((priceUsd - low52) / (high52 - low52)) * 100)) : null;
    return `
      <div class="ticker-card${expandable ? ' expandable' : ''}" data-ticker-id="${id}" tabindex="0" role="button" aria-expanded="false">
        <div class="ticker-card-head">
          <div class="ticker-symbol">${symbolHtml}</div>
          ${expandable ? '<i class="fa-solid fa-chevron-down ticker-caret"></i>' : ''}
        </div>
        <div class="ticker-price">${fmtUsd(priceUsd)}</div>
        <div class="ticker-change ${up ? 'up' : 'down'}">
          <i class="fa-solid fa-caret-${up ? 'up' : 'down'}"></i> ${fmtSignedPct(changePct, 2)}${changeSuffix || ''}
        </div>
        <div class="ticker-meta">${metaHtml}</div>
        ${valueInr != null ? `<div class="ticker-value priv-num">${fmtINR(valueInr, { compact: true })}</div>` : ''}
        ${expandable ? `
        <div class="ticker-expand">
          ${hasRange ? `
          <div class="ticker-52w">
            <div class="ticker-52w-labels"><span>52w Low ${fmtUsd(low52)}</span><span>52w High ${fmtUsd(high52)}</span></div>
            <div class="ticker-52w-track"><div class="ticker-52w-marker" style="left:${rangePct}%"></div></div>
          </div>` : ''}
          ${hasHist ? `<div class="ticker-spark-wrap"><canvas id="spark-${id}"></canvas></div>` : '<p class="ticker-nohist">1y history unavailable right now.</p>'}
          ${intelHtml ? `<div class="intel-chips">${intelHtml}</div>` : ''}
        </div>` : ''}
      </div>`;
  }

  function wireTickerExpand(container, historyMap) {
    container.querySelectorAll('.ticker-card.expandable, .wl-card.expandable').forEach(card => {
      const toggle = () => {
        const id = card.dataset.tickerId;
        const willExpand = !card.classList.contains('expanded');
        container.querySelectorAll('.ticker-card.expanded, .wl-card.expanded').forEach(c => { if (c !== card) c.classList.remove('expanded'); });
        card.classList.toggle('expanded', willExpand);
        card.setAttribute('aria-expanded', String(willExpand));
        if (willExpand && !charts['spark-' + id]) {
          const hist = historyMap[id];
          const canvas = document.getElementById('spark-' + id);
          if (hist && canvas) {
            const up = hist.closes[hist.closes.length - 1] >= hist.closes[0];
            charts['spark-' + id] = new Chart(canvas, {
              type: 'line',
              data: {
                labels: hist.dates,
                datasets: [{ data: hist.closes, borderColor: up ? CHART_COLORS.green : CHART_COLORS.red, backgroundColor: 'transparent', borderWidth: 1.5, tension: 0.25, pointRadius: 0 }],
              },
              options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => fmtUsd(ctx.parsed.y), title: (ctx) => ctx[0].label } } },
                scales: { x: { display: false }, y: { display: false } },
                interaction: { intersect: false, mode: 'index' },
              },
            });
          }
        }
      };
      card.addEventListener('click', toggle);
      card.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
    });
  }

  function renderTickers(data) {
    const stockGrid = document.getElementById('stockGrid');
    const stockHtml = data.stocks.slice(0, 24).map(s => buildTickerCard(
      s.ticker, s.ticker, s.priceUsd, s.changePct, '',
      `Qty ${s.qty.toLocaleString('en-IN', { maximumFractionDigits: 4 })}`,
      s.valueInr, data.tickerHistory && data.tickerHistory[s.ticker], s.low52, s.high52,
      { analyst: s.analyst, dividend: s.dividend, earnings: s.earnings },
    )).join('');
    stockGrid.insertAdjacentHTML('beforeend', stockHtml);
    wireTickerExpand(stockGrid, data.tickerHistory || {});

    const cryptoGrid = document.getElementById('cryptoGrid');
    const cryptoIcons = { BTC: 'fa-brands fa-bitcoin', ETH: 'fa-brands fa-ethereum' };
    const cryptoHtml = data.crypto.map(c => buildTickerCard(
      c.symbol, `<i class="${cryptoIcons[c.symbol] || 'fa-solid fa-coins'}"></i> ${c.symbol}`, c.priceUsd, c.changePct, ' (24h)',
      `Qty ${c.qty}`, c.valueInr, data.cryptoHistory && data.cryptoHistory[c.symbol], c.low52, c.high52,
    )).join('');
    cryptoGrid.insertAdjacentHTML('beforeend', cryptoHtml);

    const commodityIcons = { GOLD: 'fa-solid fa-coins', SILVER: 'fa-solid fa-ring', USOIL: 'fa-solid fa-oil-well' };
    const commodityMeta = { GOLD: 'Per troy oz (Futures)', SILVER: 'Per troy oz (Futures)', USOIL: 'Per barrel (WTI Futures)' };
    const commodityHtml = (data.commodities || []).map(c => buildTickerCard(
      c.symbol, `<i class="${commodityIcons[c.symbol] || 'fa-solid fa-cubes-stacked'}"></i> ${c.name}`, c.priceUsd, c.changePct, '',
      commodityMeta[c.symbol] || 'Commodity (not held)', null, data.commodityHistory && data.commodityHistory[c.symbol], c.low52, c.high52,
    )).join('');
    cryptoGrid.insertAdjacentHTML('beforeend', commodityHtml);
    wireTickerExpand(cryptoGrid, { ...(data.cryptoHistory || {}), ...(data.commodityHistory || {}) });
  }


  function renderTopHoldings(data) {
    const topHoldings = [...data.stocks].sort((a, b) => b.valueInr - a.valueInr).slice(0, 8);
    charts.topHoldings = new Chart(document.getElementById('chartTopHoldings'), {
      type: 'bar',
      data: { labels: topHoldings.map(s => s.ticker), datasets: [{ data: topHoldings.map(s => s.valueInr), backgroundColor: CHART_COLORS.violet, borderRadius: 8 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => fmtINR(ctx.parsed.y, { compact: true }) } } },
        scales: { y: { ticks: { callback: (v) => fmtINR(v, { compact: true }) }, grid: { color: 'rgba(255,255,255,0.04)' } }, x: { grid: { display: false } } },
      },
    });
  }

  // ---------------------------------------------------------------- cashflow
  function renderCashFlow(data) {
    function fillCard(prefix, d) {
      const income = d.salary || 0;
      const expPct = income ? (d.expenses / income * 100) : 0;
      const savPct = income ? (d.savingsInvestments / income * 100) : 0;
      const leftPct = Math.max(0, 100 - expPct - savPct);
      document.getElementById(`${prefix}Salary`).textContent = fmtINR(d.salary);
      document.getElementById(`${prefix}Expenses`).textContent = fmtINR(d.expenses);
      document.getElementById(`${prefix}Savings`).textContent = fmtINR(d.savingsInvestments) + ` (${expPct >= 0 ? savPct.toFixed(1) : '—'}%)`;
      document.getElementById(`${prefix}Leftover`).textContent = fmtINR(d.leftover) + ` (${leftPct.toFixed(1)}%)`;
      document.getElementById(`${prefix}BarExp`).style.width = `${expPct}%`;
      document.getElementById(`${prefix}BarSav`).style.width = `${savPct}%`;
      document.getElementById(`${prefix}BarLeft`).style.width = `${leftPct}%`;
    }
    fillCard('sb', data.income.sb);
    fillCard('jb', data.income.jb);

    function expenseChart(canvasId, breakdown, color) {
      const sorted = [...breakdown].sort((a, b) => b.amount - a.amount).slice(0, 10);
      charts[canvasId] = new Chart(document.getElementById(canvasId), {
        type: 'bar',
        data: { labels: sorted.map(x => x.name), datasets: [{ data: sorted.map(x => x.amount), backgroundColor: color, borderRadius: 8 }] },
        options: {
          indexAxis: 'y', responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => fmtINR(ctx.parsed.x) } } },
          scales: { x: { ticks: { callback: (v) => fmtINR(v, { compact: true }) }, grid: { color: 'rgba(255,255,255,0.04)' } }, y: { grid: { display: false } } },
        },
      });
    }
    expenseChart('chartSbExpenses', data.expenseBreakdown.sb, CHART_COLORS.cyan);
    expenseChart('chartJbExpenses', data.expenseBreakdown.jb, CHART_COLORS.pink);
  }

  // ---------------------------------------------------------------- insights
  function renderInsights(data) {
    const insightsList = document.getElementById('insightsList');
    data.insights.forEach(txt => {
      insightsList.insertAdjacentHTML('beforeend', `<div class="insight-item"><i class="fa-solid fa-bolt"></i><span>${txt}</span></div>`);
    });
    const riskFactors = document.getElementById('riskFactors');
    data.risk.factors.forEach(txt => {
      riskFactors.insertAdjacentHTML('beforeend', `<div class="risk-item"><i class="fa-solid fa-triangle-exclamation"></i><span>${txt}</span></div>`);
    });
  }

  // -------------------------------------------------------------- NL query
  function initNlQuery(data) {
    const input = document.getElementById('nlQuery');
    const btn = document.getElementById('nlQueryBtn');
    const answerEl = document.getElementById('nlAnswer');

    const handlers = [
      { keys: ['net worth', 'networth', 'wealth'], run: () => `Combined net worth is ${fmtINR(data.netWorth.combined, { compact: true })}. See the KPI row and Net Worth Trend chart above.` },
      { keys: ['drawdown', 'dip', 'peak'], run: () => { document.getElementById('chartDrawdown').scrollIntoView({ behavior: 'smooth', block: 'center' }); const dd = data.history && data.history.drawdownPct ? Math.min(...data.history.drawdownPct) : null; return `Max drawdown over the last year is ${dd !== null ? fmtSignedPct(dd) : 'unavailable'}. Scrolled to the chart.`; } },
      { keys: ['alpha', 'benchmark', 'outperform'], run: () => { document.getElementById('chartAlpha').scrollIntoView({ behavior: 'smooth', block: 'center' }); const a = (data.alphaByPeriod || []).find(x => x.period === '1Y'); return a ? `1Y alpha vs ${data.history.benchmarkLabel}: ${fmtSignedPct(a.alpha)}.` : 'Alpha data unavailable.'; } },
      { keys: ['drift', 'rebalance'], run: () => { document.getElementById('chartDrift').scrollIntoView({ behavior: 'smooth', block: 'center' }); return 'Scrolled to Portfolio Drift chart — bars show current vs target allocation.'; } },
      { keys: ['goal', 'retirement', 'fi', 'independence'], run: () => { document.getElementById('goalsGrid').scrollIntoView({ behavior: 'smooth', block: 'center' }); const g = (data.goals || [])[0]; return g ? `${g.name}: ${(g.progressPct * 100).toFixed(1)}% there (${fmtINR(g.current, { compact: true })} of ${fmtINR(g.target, { compact: true })}).` : 'No goal data.'; } },
      { keys: ['alert', 'risk', 'concentration'], run: () => { document.getElementById('alertsList').scrollIntoView({ behavior: 'smooth', block: 'center' }); return `${(data.alerts || []).length} active alert(s). Portfolio risk score: ${data.risk.score}/100 (${data.risk.level}).`; } },
      { keys: ['crypto', 'bitcoin', 'btc', 'eth'], run: () => { document.getElementById('cryptoGrid').scrollIntoView({ behavior: 'smooth', block: 'center' }); return 'Scrolled to crypto holdings.'; } },
      { keys: ['fee', 'expense ratio'], run: () => 'Fee-impact analysis is out of scope — the workbook has no expense-ratio / fee data to compute this against.' },
      { keys: ['dividend'], run: () => { document.getElementById('watchlistGrid').scrollIntoView({ behavior: 'smooth', block: 'center' }); return 'Scrolled to Watchlist — expand any card for its next ex-dividend date and yield (where NASDAQ has dividend data for that ticker).'; } },
      { keys: ['news', 'macro', 'headline'], run: () => { document.getElementById('newsList').scrollIntoView({ behavior: 'smooth', block: 'center' }); return 'Scrolled to World & Macro-Economic News.'; } },
      { keys: ['analyst', 'rating', 'recommendation'], run: () => { document.getElementById('watchlistGrid').scrollIntoView({ behavior: 'smooth', block: 'center' }); return 'Scrolled to Watchlist — each card shows the NASDAQ analyst consensus rating when covered.'; } },
      { keys: ['earnings', 'quarterly results'], run: () => { document.getElementById('watchlistGrid').scrollIntoView({ behavior: 'smooth', block: 'center' }); return 'Scrolled to Watchlist — expand a card for next fiscal quarter-end / consensus EPS and last reported date.'; } },
    ];

    function answer() {
      const q = input.value.toLowerCase().trim();
      if (!q) return;
      const match = handlers.find(h => h.keys.some(k => q.includes(k)));
      answerEl.classList.add('has-answer');
      answerEl.textContent = match ? match.run() : `I couldn't map that to a specific chart. Try: net worth, drawdown, alpha, drift, goal, alerts, crypto.`;
    }
    btn.addEventListener('click', answer);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') answer(); });
  }

  // ----------------------------------------------------------------- export
  function initExport(data) {
    document.getElementById('exportBtn').addEventListener('click', () => {
      const rows = [['Ticker', 'Qty', 'Price (USD)', 'Change %', 'Value (INR)']];
      data.stocks.forEach(s => rows.push([s.ticker, s.qty, s.priceUsd, (s.changePct * 100).toFixed(2), s.valueInr.toFixed(0)]));
      rows.push([]);
      rows.push(['Crypto', 'Qty', 'Price (USD)', 'Change % (24h)', 'Value (INR)']);
      data.crypto.forEach(c => rows.push([c.symbol, c.qty, c.priceUsd, (c.changePct * 100).toFixed(2), c.valueInr.toFixed(0)]));
      const csv = rows.map(r => r.join(',')).join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `nexus-wealth-export-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
    });
  }

  // ------------------------------------------------------------- ticker tape
  const LIVE_SERVER = 'http://localhost:8787';
  const MARKET_STATUS_META = {
    'open': { cls: 'status-open', label: 'Online' },
    'pre-market': { cls: 'status-pre', label: 'Online (Pre-Market)' },
    'after-hours': { cls: 'status-after', label: 'Online (After-Hours)' },
    'closed': { cls: 'status-closed', label: 'Offline' },
  };

  function renderTapeItems(items) {
    const track = document.getElementById('tapeTrack');
    if (!items || !items.length) return;
    const chip = (it) => {
      const up = it.changePct >= 0;
      return `<span class="tape-item ${up ? 'up' : 'down'}"><b>${it.ticker}</b> ${fmtUsd(it.price)} <i class="fa-solid fa-caret-${up ? 'up' : 'down'}"></i>${fmtSignedPct(it.changePct, 2)}</span>`;
    };
    // duplicate the sequence so the CSS marquee loops seamlessly
    track.innerHTML = items.map(chip).join('') + items.map(chip).join('');
  }

  function setTapeStatus(marketStatus, online) {
    const el = document.getElementById('tapeStatus');
    const segIndia = document.getElementById('marketSegIndia');
    const segUs = document.getElementById('marketSegUs');
    if (!online) {
      el.className = 'tape-status status-offline';
      segIndia.className = 'market-seg status-offline';
      segIndia.querySelector('.market-seg-label').textContent = 'India: Offline';
      segIndia.title = 'Snapshot data · live updates paused';
      segUs.className = 'market-seg status-offline';
      segUs.querySelector('.market-seg-label').textContent = 'US: Offline';
      segUs.title = 'Snapshot data · live updates paused';
      return;
    }
    const usMeta = MARKET_STATUS_META[marketStatus.status] || MARKET_STATUS_META.closed;
    el.className = 'tape-status';
    segUs.className = 'market-seg ' + usMeta.cls;
    segUs.querySelector('.market-seg-label').textContent = `US: ${usMeta.label}`;
    segUs.title = `${marketStatus.label} · ${marketStatus.istTime || marketStatus.etTime}`;

    const india = marketStatus.india;
    if (india) {
      const indiaMeta = MARKET_STATUS_META[india.status] || MARKET_STATUS_META.closed;
      const shortLabel = india.status === 'open' ? 'Online' : 'Offline';
      segIndia.className = 'market-seg ' + indiaMeta.cls;
      segIndia.querySelector('.market-seg-label').textContent = `India: ${shortLabel}`;
      segIndia.title = `NSE/BSE · ${india.label} · ${india.istTime}`;
    } else {
      segIndia.className = 'market-seg status-offline';
      segIndia.querySelector('.market-seg-label').textContent = 'India: —';
    }
  }

  let _liveServerPillState = null;
  function setLiveServerPill(online) {
    if (_liveServerPillState === online) return; // avoid needless re-render/flicker
    _liveServerPillState = online;
    const el = document.getElementById('liveServerPill');
    const text = document.getElementById('liveServerText');
    if (!el || !text) return;
    if (online) {
      el.className = 'live-pill online';
      text.textContent = 'Live Server: Online';
      el.title = 'live_server.py is running and serving fresh ticker/watchlist data.';
    } else {
      el.className = 'live-pill offline';
      text.textContent = 'Live Server: Offline';
      el.title = 'live_server.py isn\'t reachable — run Start_Live_Server.bat for real-time prices. Showing last saved snapshot.';
    }
  }

  function staticTapeFallback(data) {
    // one-time static fill from the last data.json snapshot, used only when
    // the local live server isn't running. Covers full watchlist (held +
    // watching + ETFs) + crypto + macro indicators, deduped by ticker.
    const seen = new Set();
    const items = [];
    (data.watchlist || []).forEach(w => {
      if (w.priceUsd && !seen.has(w.ticker)) { seen.add(w.ticker); items.push({ ticker: w.ticker, price: w.priceUsd, changePct: w.changePct }); }
    });
    data.stocks.forEach(s => {
      if (s.priceUsd && !seen.has(s.ticker)) { seen.add(s.ticker); items.push({ ticker: s.ticker, price: s.priceUsd, changePct: s.changePct }); }
    });
    (data.macro || []).forEach(m => {
      if (m.price != null && !seen.has(m.ticker)) { seen.add(m.ticker); items.push({ ticker: m.ticker, price: m.price, changePct: m.changePct }); }
    });
    data.crypto.forEach(c => items.push({ ticker: c.symbol, price: c.priceUsd, changePct: c.changePct }));
    renderTapeItems(items);
  }

  function initTickerTape(data) {
    let liveOk = false;
    async function pollTape() {
      try {
        const res = await fetch(`${LIVE_SERVER}/api/tape.json`, { cache: 'no-store' });
        if (!res.ok) throw new Error('bad response');
        const json = await res.json();
        if (json && json.items && json.items.length) {
          liveOk = true;
          renderTapeItems(json.items);
          setTapeStatus(json.marketStatus, true);
          setLiveServerPill(true);
        }
      } catch (e) {
        setLiveServerPill(false);
        if (!liveOk) {
          setTapeStatus(null, false);
          staticTapeFallback(data);
        }
      }
    }
    pollTape();
    setInterval(pollTape, 60000);
  }

  // -------------------------------------------------------------- deep data
  function renderWatchlist(watchlist, watchlistHistory) {
    const grid = document.getElementById('watchlistGrid');
    if (!grid || !watchlist) return;
    grid.innerHTML = watchlist.map(w => {
      const up = (w.changePct || 0) >= 0;
      const priceHtml = w.unavailable ? '<span class="wl-unavailable">Price unavailable</span>' : `${fmtUsd(w.priceUsd)} <span class="wl-change ${up ? 'up' : 'down'}"><i class="fa-solid fa-caret-${up ? 'up' : 'down'}"></i>${fmtSignedPct(w.changePct, 2)}</span>`;
      const badges = intelBadgesHtml(w.analyst, w.dividend, w.earnings);
      const id = 'wl-' + w.ticker;
      const hist = watchlistHistory && watchlistHistory[w.ticker];
      const hasHist = !!(hist && hist.dates && hist.dates.length > 1);
      const hasRange = w.low52 != null && w.high52 != null && w.high52 > w.low52;
      const expandable = hasHist || hasRange || !!badges;
      const rangePct = hasRange ? Math.min(100, Math.max(0, ((w.priceUsd - w.low52) / (w.high52 - w.low52)) * 100)) : null;
      return `
      <div class="wl-card${expandable ? ' expandable' : ''}" data-held="${w.isHeld}" data-etf="${w.isEtf}" data-ticker-id="${id}" tabindex="0" role="button" aria-expanded="false">
        <div class="wl-card-head">
          <div><div class="wl-name">${w.name}</div><div class="wl-ticker">${w.ticker}${w.isHeld ? ' <span class="wl-tag-held">HELD</span>' : ''}${w.isEtf ? ' <span class="wl-tag-etf">ETF</span>' : ''}</div></div>
          ${expandable ? '<i class="fa-solid fa-chevron-down ticker-caret"></i>' : ''}
        </div>
        <div class="wl-price">${priceHtml}</div>
        ${expandable ? `
        <div class="ticker-expand">
          ${hasRange ? `<div class="ticker-52w"><div class="ticker-52w-labels"><span>52w Low ${fmtUsd(w.low52)}</span><span>52w High ${fmtUsd(w.high52)}</span></div><div class="ticker-52w-track"><div class="ticker-52w-marker" style="left:${rangePct}%"></div></div></div>` : ''}
          ${hasHist ? `<div class="ticker-spark-wrap"><canvas id="spark-${id}"></canvas></div>` : '<p class="ticker-nohist">1y history unavailable right now.</p>'}
          ${badges ? `<div class="intel-chips">${badges}</div>` : '<p class="ticker-nohist">No analyst/earnings coverage found.</p>'}
        </div>` : ''}
      </div>`;
    }).join('');

    const historyMap = {};
    watchlist.forEach(w => { if (watchlistHistory && watchlistHistory[w.ticker]) historyMap['wl-' + w.ticker] = watchlistHistory[w.ticker]; });
    wireTickerExpand(grid, historyMap);

    document.querySelectorAll('#watchlistFilters .wf-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#watchlistFilters .wf-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const f = btn.dataset.filter;
        grid.querySelectorAll('.wl-card').forEach(card => {
          const held = card.dataset.held === 'true', etf = card.dataset.etf === 'true';
          const show = f === 'all' || (f === 'held' && held) || (f === 'watching' && !held) || (f === 'etf' && etf);
          card.style.display = show ? '' : 'none';
        });
      });
    });
  }

  function timeAgo(pubDate) {
    if (!pubDate) return '';
    const d = new Date(pubDate);
    if (isNaN(d)) return '';
    const hrs = Math.round((Date.now() - d.getTime()) / 3600000);
    if (hrs < 1) return 'just now';
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.round(hrs / 24)}d ago`;
  }

  function sortByNewest(items) {
    return [...items].sort((a, b) => {
      const da = new Date(a.pubDate), db = new Date(b.pubDate);
      const ta = isNaN(da) ? 0 : da.getTime();
      const tb = isNaN(db) ? 0 : db.getTime();
      return tb - ta; // newest first
    });
  }

  function renderNews(macroNews) {
    const tabsEl = document.getElementById('newsTabs');
    const listEl = document.getElementById('newsList');
    if (!tabsEl || !macroNews) return;
    const regions = Object.keys(macroNews);
    if (!regions.length) { listEl.innerHTML = '<p class="ticker-nohist">News unavailable right now.</p>'; return; }

    function paint(region) {
      let items;
      if (region === 'All') {
        items = sortByNewest(regions.flatMap(r => (macroNews[r] || []).map(n => ({ ...n, _region: r }))));
      } else {
        items = sortByNewest(macroNews[region] || []);
      }
      listEl.innerHTML = items.length ? items.map(n => `
        <a class="news-item" href="${n.link}" target="_blank" rel="noopener">
          <i class="fa-solid fa-newspaper"></i>
          <div><div class="news-title">${n.title}</div><div class="news-meta">${n._region ? `<span class="news-region">${n._region}</span> · ` : ''}${n.source || ''} · ${timeAgo(n.pubDate)}</div></div>
          <i class="fa-solid fa-arrow-up-right-from-square news-ext"></i>
        </a>`).join('') : '<p class="ticker-nohist">No headlines available for this region right now.</p>';
    }
    const tabList = ['All', ...regions];
    tabsEl.innerHTML = tabList.map((r, i) => `<button class="wf-btn${i === 0 ? ' active' : ''}" data-region="${r}">${r}</button>`).join('');
    tabsEl.querySelectorAll('.wf-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        tabsEl.querySelectorAll('.wf-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        paint(btn.dataset.region);
      });
    });
    paint('All');
  }

  function initDeepData(data) {
    async function pollDeep() {
      try {
        const res = await fetch(`${LIVE_SERVER}/api/deep.json`, { cache: 'no-store' });
        if (!res.ok) throw new Error('bad response');
        const json = await res.json();
        if (json && json.watchlist && json.watchlist.length) {
          renderWatchlist(json.watchlist, data.watchlistHistory);
          renderNews(json.macroNews);
          document.getElementById('deepSyncTag').textContent = `Synced ${new Date(json.generatedAt).toLocaleTimeString()}`;
          document.getElementById('newsSyncTag').textContent = `Synced ${new Date(json.generatedAt).toLocaleTimeString()}`;
          return;
        }
      } catch (e) { /* fall through to static data.json snapshot below */ }
      // fallback: static snapshot from the last full refresh_data.py run
      if (data.watchlist && data.watchlist.length) {
        renderWatchlist(data.watchlist, data.watchlistHistory);
        document.getElementById('deepSyncTag').textContent = `Static snapshot (${new Date(data.generatedAt).toLocaleString()})`;
      }
      if (data.macroNews) {
        renderNews(data.macroNews);
        document.getElementById('newsSyncTag').textContent = `Static snapshot (${new Date(data.generatedAt).toLocaleString()})`;
      }
    }
    pollDeep();
    setInterval(pollDeep, 5 * 60000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
