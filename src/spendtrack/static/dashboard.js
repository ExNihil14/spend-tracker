// Графики дашборда. Данные — в #dashboard-data (data-* JSON); Chart.js грузится ТОЛЬКО здесь
// (динамически, с версионированным URL из data-chart-src), а не на всех страницах.
(function () {
  'use strict';

  function readData() {
    var el = document.getElementById('dashboard-data');
    if (!el || !el.dataset) return null;
    try {
      return {
        daily: JSON.parse(el.dataset.daily || '[]'),
        cats: JSON.parse(el.dataset.cats || '[]'),
        colors: JSON.parse(el.dataset.colors || '{}'),
        chartSrc: el.dataset.chartSrc || '/static/chart.umd.min.js'
      };
    } catch (e) {
      return null;
    }
  }

  function ensureChart(src, cb) {
    if (window.Chart) return cb();
    var queue = window.__spendtrackChartQueue = window.__spendtrackChartQueue || [];
    queue.push(cb);
    if (window.__spendtrackChartLoading) return;
    window.__spendtrackChartLoading = true;
    var s = document.createElement('script');
    s.src = src;
    s.onload = function () {
      window.__spendtrackChartLoading = false;
      window.__spendtrackChartQueue = [];
      queue.forEach(function (fn) { fn(); });
    };
    s.onerror = function () {
      // Chart не загрузился: не копим колбэки (иначе утечка и «вечное ожидание»)
      window.__spendtrackChartLoading = false;
      window.__spendtrackChartQueue = [];
    };
    document.head.appendChild(s);
  }

  function initCharts() {
    var data = readData();
    if (!data) return;
    drawSparkline(data.daily);
    drawHeat(data.daily);
    var dailyEl = document.getElementById('dailyChart');
    if (!dailyEl || dailyEl.dataset.init === '1') return;
    ensureChart(data.chartSrc, function () { draw(data); });
  }

  // Цвета графиков — из semantic-токенов (tokens.css): JS не хардкодит палитру.
  function cssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function withAlpha(color, alphaHex) {
    return color.charAt(0) === '#' && color.length === 7 ? color + alphaHex : color;
  }

  // Ребрендинг 29.09: анимации графиков — 300 мс (дефолт Chart.js 1000) и отключаются
  // при reduced-motion (WCAG 2.3.3 / SCR40).
  function prefersReducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  // Спарклайн «Расход» (SVG polyline) и карта дней (heat strip) — из data-daily, без Chart.js.
  function drawSparkline(daily) {
    var el = document.querySelector('#spark-expense polyline');
    if (!el || !daily.length) return;
    var vals = daily.map(function (d) { return d.total_k / 100; });
    var max = Math.max.apply(null, vals) || 1;
    var stepX = 96 / Math.max(vals.length - 1, 1);
    el.setAttribute('points', vals.map(function (v, i) {
      return (i * stepX).toFixed(1) + ',' + (26 - (v / max) * 24).toFixed(1);
    }).join(' '));
  }

  function drawHeat(daily) {
    var box = document.getElementById('heat-strip');
    if (!box || !daily.length) return;
    var byDate = {};
    var max = 0;
    daily.forEach(function (d) {
      byDate[d.date] = d.total_k;
      if (d.total_k > max) max = d.total_k;
    });
    var first = daily[0].date; // ISO YYYY-MM-DD (days отсортированы по дате)
    var days = new Date(+first.slice(0, 4), +first.slice(5, 7), 0).getDate();
    var total = 0;
    var frag = document.createDocumentFragment();
    for (var day = 1; day <= days; day++) {
      var iso = first.slice(0, 8) + (day < 10 ? '0' + day : String(day));
      var v = byDate[iso] || 0;
      total += v;
      var cell = document.createElement('span');
      var level = v <= 0 ? 0 : Math.min(4, Math.max(1, Math.ceil((v / (max || 1)) * 4)));
      cell.className = 'heat-cell';
      cell.dataset.level = String(level);
      cell.title = iso.slice(5) + ': ' + (v / 100).toFixed(2) + ' ₽';
      cell.setAttribute('aria-hidden', 'true');
      frag.appendChild(cell);
    }
    box.textContent = '';
    box.appendChild(frag);
    box.setAttribute('aria-label', 'Карта расходов по дням: ' + days + ' дн, всего '
      + (total / 100).toFixed(0) + ' ₽, максимум ' + (max / 100).toFixed(0) + ' ₽');
  }

  function draw(data) {
    var dailyEl = document.getElementById('dailyChart');
    if (!dailyEl || dailyEl.dataset.init === '1') return;
    dailyEl.dataset.init = '1';
    var daily = data.daily;
    var cats = data.cats;
    var catColorMap = data.colors;
    var fg = cssVar('--fg', '#e2e8f0');
    var fgMuted = cssVar('--fg-muted', '#94a3b8');
    var accentBg = cssVar('--accent-bg', '#2563eb');
    var canvasBg = cssVar('--canvas', '#16120f');
    var reduce = prefersReducedMotion();
    var tick = function (v) { return v.toFixed(2) + ' ₽'; }; // в datasets уже рубли (total_k/100 ниже)

    if (daily.length) {
      new Chart(dailyEl, {
        type: 'bar',
        data: {
          labels: daily.map(function (d) { return d.date.slice(5); }),
          datasets: [{
            label: 'Сумма, ₽',
            data: daily.map(function (d) { return d.total_k / 100; }),
            // градиент по высоте бара — «объём» без искажения значений (3D-графики не читаются)
            backgroundColor: function (context) {
              var chart = context.chart;
              var area = chart.chartArea;
              if (!area) return withAlpha(accentBg, '8c');
              var g = chart.ctx.createLinearGradient(0, area.bottom, 0, area.top);
              g.addColorStop(0, withAlpha(accentBg, '40'));
              g.addColorStop(1, withAlpha(accentBg, 'cc'));
              return g;
            },
            borderColor: accentBg,
            borderWidth: 1,
            borderRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false, // иначе чарт перерастает контейнер h-56 при перерисовке
          animation: reduce ? false : { duration: 300, easing: 'easeOutQuart' },
          plugins: { legend: { display: false } },
          scales: { y: { ticks: { callback: tick, color: fgMuted } },
                    x: { ticks: { color: fgMuted, maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } } }
        }
      });
    }

    var catsEl = document.getElementById('catsChart');
    // label — RU-имя категории (display_name), color — по слагу (cat_colors)
    var expenses = cats.filter(function (c) { return c.total_k < 0; })
      .map(function (c) {
        return { key: c.category, label: c.label || c.category, value: -c.total_k / 100 };
      });
    if (expenses.length && catsEl) {
      new Chart(catsEl, {
        type: 'doughnut',
        data: {
          labels: expenses.map(function (e) { return e.label; }),
          datasets: [{
            data: expenses.map(function (e) { return e.value; }),
            backgroundColor: expenses.map(function (e) { return catColorMap[e.key] || '#9ca3af'; }),
            borderColor: canvasBg,
            borderWidth: 2
          }]
        },
        options: {
          maintainAspectRatio: false,
          animation: reduce ? false : { duration: 300, easing: 'easeOutQuart' },
          plugins: { legend: { labels: { color: fg } } }
        }
      });
    }
  }

  // Обработчики регистрируем один раз на JS-контекст (boost-свапы перезапускают скрипт),
  // старые Chart-инстансы уничтожаем перед свапом — иначе утечка и «пляшущие» графики.
  if (!window.__spendtrackChartHooks) {
    window.__spendtrackChartHooks = true;
    if (window.htmx) {
      htmx.onLoad(initCharts);
      document.body.addEventListener('htmx:beforeSwap', function () {
        ['dailyChart', 'catsChart'].forEach(function (id) {
          var el = document.getElementById(id);
          var c = el && window.Chart && window.Chart.getChart(el);
          if (c) c.destroy();
        });
      });
    }
    // Смена темы (theme.js → 'spendtrack:theme'): Chart.js держит палитру в датасете — перерисовываем.
    window.addEventListener('spendtrack:theme', function () {
      ['dailyChart', 'catsChart'].forEach(function (id) {
        var el = document.getElementById(id);
        var c = el && window.Chart && window.Chart.getChart(el);
        if (c) c.destroy();
        if (el) delete el.dataset.init;
      });
      requestAnimationFrame(initCharts);
    });
  }
  // rAF: при boost-свопе скрипт исполняется до завершения раскладки — иначе Chart.js
  // замеряет контейнер как 0 и оставляет канвас дефолтной высоты (150px вместо h-56).
  requestAnimationFrame(initCharts);
})();
