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
    var dailyEl = document.getElementById('dailyChart');
    if (!dailyEl || dailyEl.dataset.init === '1') return;
    var data = readData();
    if (!data) return;
    ensureChart(data.chartSrc, function () { draw(data); });
  }

  function draw(data) {
    var dailyEl = document.getElementById('dailyChart');
    if (!dailyEl || dailyEl.dataset.init === '1') return;
    dailyEl.dataset.init = '1';
    var daily = data.daily;
    var cats = data.cats;
    var catColorMap = data.colors;
    var tick = function (v) { return v.toFixed(2) + ' ₽'; }; // в datasets уже рубли (total_k/100 ниже)

    if (daily.length) {
      new Chart(dailyEl, {
        type: 'bar',
        data: {
          labels: daily.map(function (d) { return d.date.slice(5); }),
          datasets: [{
            label: 'Сумма, ₽',
            data: daily.map(function (d) { return d.total_k / 100; }),
            backgroundColor: 'rgba(59,130,246,0.55)',
            borderColor: 'rgba(59,130,246,1)',
            borderWidth: 1
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false, // иначе чарт перерастает контейнер h-56 при перерисовке
          plugins: { legend: { display: false } },
          scales: { y: { ticks: { callback: tick, color: '#94a3b8' } },
                    x: { ticks: { color: '#94a3b8', maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } } }
        }
      });
    }

    var catsEl = document.getElementById('catsChart');
    var expenses = cats.filter(function (c) { return c.total_k < 0; })
      .map(function (c) { return { label: c.category, value: -c.total_k / 100 }; });
    if (expenses.length && catsEl) {
      new Chart(catsEl, {
        type: 'doughnut',
        data: {
          labels: expenses.map(function (e) { return e.label; }),
          datasets: [{
            data: expenses.map(function (e) { return e.value; }),
            backgroundColor: expenses.map(function (e) { return catColorMap[e.label] || '#9ca3af'; }),
            borderWidth: 0
          }]
        },
        options: { maintainAspectRatio: false, plugins: { legend: { labels: { color: '#cbd5e1' } } } }
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
  }
  // rAF: при boost-свопе скрипт исполняется до завершения раскладки — иначе Chart.js
  // замеряет контейнер как 0 и оставляет канвас дефолтной высоты (150px вместо h-56).
  requestAnimationFrame(initCharts);
})();
