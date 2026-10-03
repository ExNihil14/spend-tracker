// Графики дашборда. Данные — в #dashboard-data (data-* JSON); Chart.js грузится ТОЛЬКО здесь
// (динамически, с версионированным URL из data-chart-src), а не на всех страницах.
(function () {
  'use strict';

  var CUR = '₽';  // символ базовой валюты: ставится из #dashboard-data (data-currency-symbol)

  function readData() {
    var el = document.getElementById('dashboard-data');
    if (!el || !el.dataset) return null;
    try {
      return {
        daily: JSON.parse(el.dataset.daily || '[]'),
        cats: JSON.parse(el.dataset.cats || '[]'),
        colors: JSON.parse(el.dataset.colors || '{}'),
        chartSrc: el.dataset.chartSrc || '/static/chart.umd.min.js',
        currencySymbol: el.dataset.currencySymbol || '₽'
      };
    } catch (e) {
      return null;
    }
  }

  function ensureChart(src, cb) {
    if (window.Chart) return cb();
    if (window.__spendtrackChartFailed) return;  // S3: не ретраим бесконечно битый chart-src
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
      // S3 (Astra 02.10): не копим колбэки/теги <script> и говорим пользователю правду —
      // «пустые канвасы» не должны выглядеть как «расходов нет» (данные есть в таблицах ниже).
      window.__spendtrackChartLoading = false;
      window.__spendtrackChartQueue = [];
      window.__spendtrackChartFailed = true;
      s.remove();
      var box = document.querySelector('[data-chart-box]');
      if (box) box.textContent = 'График недоступен — данные есть в таблицах ниже';
    };
    document.head.appendChild(s);
  }

  function initCharts() {
    var data = readData();
    if (!data) return;
    CUR = data.currencySymbol || CUR;
    drawSparkline(data.daily);
    drawHeat(data.daily);
    var dailyEl = document.getElementById('dailyChart');
    if (!dailyEl || dailyEl.dataset.init === '1') return;
    ensureChart(data.chartSrc, function () {
      // S8 (Astra 02.10): за время загрузки Chart.js мог пройти boost-свап на другой месяц —
      // перечитываем данные, иначе в новый канвас попадут суммы устаревшего месяца.
      var fresh = readData();
      if (fresh) draw(fresh);
    });
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

  // Формат денег для canvas (в DOM — только fmt_money сервером): запятая, NBSP-разряды, U+2212.
  function fmtRub(v) {
    var parts = Math.abs(v).toFixed(2).split('.');
    var int = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');
    return (v < 0 ? '\u2212' : '') + int + ',' + parts[1];
  }

  // Wave 1-preview: тултип в семантических токенах (фон — fg-strong, текст — surface;
  // контраст ≥15:1 в обеих темах). Интерактив чартов не заменяет данные: значения дублируются
  // в таблицах/подписях (SC 1.4.1), тултип — дополнение.
  function makeTooltip(callbacks) {
    return {
      backgroundColor: cssVar('--fg-strong', '#0b1220'),
      titleColor: cssVar('--surface', '#ffffff'),
      bodyColor: cssVar('--surface', '#ffffff'),
      borderColor: cssVar('--line-strong', '#6f7d94'),
      borderWidth: 1,
      padding: 10,
      cornerRadius: 10,
      displayColors: false,
      titleFont: { weight: '600' },
      callbacks: callbacks
    };
  }

  // Попадание курсора в элемент легенды не нужно: Chart.js зовёт chart-level onHover только внутри
  // plot-area, а легенда обрабатывается собственными onHover/onLeave плагина (см. draw ниже).

  // Спарклайн «Расход» — мягкая сглаженная area-кривая (SVG, без Chart.js); карта дней — ниже.
  // Монотонная кубическая интерполяция (Fritsch–Carlson): без «зубцов» и перехлёстов —
  // профиль читается как мягкая динамика, а не как кардиограмма.
  function smoothPath(pts) {
    var n = pts.length;
    if (n < 2) return '';
    if (n === 2) {
      return 'M' + pts[0][0].toFixed(1) + ',' + pts[0][1].toFixed(1)
        + 'L' + pts[1][0].toFixed(1) + ',' + pts[1][1].toFixed(1);
    }
    var dx = [], m = [];
    for (var i = 0; i < n - 1; i++) {
      dx.push(pts[i + 1][0] - pts[i][0]);
      m.push((pts[i + 1][1] - pts[i][1]) / dx[i]);
    }
    var t = [m[0]];
    for (var j = 1; j < n - 1; j++) {
      if (m[j - 1] * m[j] <= 0) {
        t.push(0);
      } else {
        var w1 = 2 * dx[j] + dx[j - 1];
        var w2 = dx[j] + 2 * dx[j - 1];
        t.push((w1 + w2) / (w1 / m[j - 1] + w2 / m[j]));
      }
    }
    t.push(m[n - 2]);
    var d = 'M' + pts[0][0].toFixed(1) + ',' + pts[0][1].toFixed(1);
    for (var k = 0; k < n - 1; k++) {
      var x1 = pts[k][0] + dx[k] / 3;
      var y1 = pts[k][1] + (t[k] * dx[k]) / 3;
      var x2 = pts[k + 1][0] - dx[k] / 3;
      var y2 = pts[k + 1][1] - (t[k + 1] * dx[k]) / 3;
      d += 'C' + x1.toFixed(1) + ',' + y1.toFixed(1) + ' ' + x2.toFixed(1) + ',' + y2.toFixed(1)
         + ' ' + pts[k + 1][0].toFixed(1) + ',' + pts[k + 1][1].toFixed(1);
    }
    return d;
  }

  function drawSparkline(daily) {
    var svg = document.getElementById('spark-expense');
    var line = svg ? svg.querySelector('path.spark-line') : null;
    var area = svg ? svg.querySelector('path.spark-area') : null;
    if (!line || !daily.length) return;
    // «Динамика расходов» — расход дня (доходные дни = 0), а не знаковый итог.
    var vals = daily.map(function (d) { return Math.max(0, -d.total_k) / 100; });
    var max = Math.max.apply(null, vals) || 1;
    var n = vals.length;
    var top = 3, base = 30;
    var pts = vals.map(function (v, i) {
      return [n > 1 ? (i * 120) / (n - 1) : 0, base - (v / max) * (base - top)];
    });
    var d = smoothPath(pts);
    line.setAttribute('d', d);
    if (area) {
      area.setAttribute('d', d + 'L' + pts[n - 1][0].toFixed(1) + ',' + base + 'L0,' + base + 'Z');
    }
  }

  function drawHeat(daily) {
    var box = document.getElementById('heat-strip');
    if (!box || !daily.length) return;
    var byDate = {};
    var max = 0;
    // C1 (Astra 02.10): карта дней — про РАСХОДЫ (как и спарклайн): total_k знаковый (расходы < 0),
    // из-за чего все ячейки получали level 0, а aria-label показывал «максимум 0 CUR» и минус-суммы.
    daily.forEach(function (d) {
      var spend = Math.max(0, -d.total_k);
      byDate[d.date] = spend;
      if (spend > max) max = spend;
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
      cell.title = iso.slice(5) + ': ' + fmtRub(v / 100) + ' ' + CUR;  // единый формат денег
      cell.setAttribute('aria-hidden', 'true');
      frag.appendChild(cell);
    }
    box.textContent = '';
    box.appendChild(frag);
    box.setAttribute('aria-label', 'Карта расходов по дням: ' + days + ' дн, всего '
      + fmtRub(total / 100) + ' ' + CUR + ', максимум ' + fmtRub(max / 100) + ' ' + CUR);
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
    var accent = cssVar('--accent', '#0e7490');
    var accentBg = cssVar('--accent-bg', '#0e7490');
    var surfaceBg = cssVar('--surface', '#ffffff');
    var lineStrong = cssVar('--line-strong', '#6f7d94');
    var reduce = prefersReducedMotion();
    var tick = function (v) { return fmtRub(v) + ' ' + CUR; }; // в datasets уже рубли (total_k/100 ниже)

    if (daily.length) {
      new Chart(dailyEl, {
        type: 'bar',
        data: {
          labels: daily.map(function (d) { return d.date.slice(5); }),
          datasets: [{
            label: 'Сумма, ' + CUR,
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
            borderRadius: 6,
            hoverBorderColor: accent, // hover: кромка «аква/неон» из токена
            hoverBorderWidth: 2
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false, // иначе чарт перерастает контейнер h-56 при перерисовке
          // каскадное появление баров (только первичная отрисовка, не hover/resize)
          animation: reduce ? false : {
            duration: 400,
            easing: 'easeOutQuart',
            delay: function (ctx) {
              return ctx.type === 'data' && ctx.mode === 'default' ? ctx.dataIndex * 18 : 0;
            }
          },
          plugins: {
            legend: { display: false },
            tooltip: makeTooltip({
              title: function (items) {
                var l = items.length ? String(items[0].label) : '';
                var p = l.split('-');
                return p.length === 2 ? p[1] + '.' + p[0] : l;
              },
              label: function (ctx) { return 'Сумма: ' + fmtRub(ctx.parsed.y) + ' ' + CUR; }
            })
          },
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
            borderColor: surfaceBg,   // граница секторов по поверхности карточки (v2 §4.5)
            borderWidth: 2,
            hoverOffset: 6,           // hover: сектор «выдвигается» (декор, значения не меняются)
            hoverBorderColor: lineStrong
          }]
        },
        options: {
          maintainAspectRatio: false,
          animation: reduce ? false : { duration: 400, easing: 'easeOutQuart' },
          // Клик по сектору → список операций с фильтром категории (тот же маршрут, что у бейджей
          // категорий: /?month=YYYY-MM&category=slug). Легенда кликабельна штатно (скрыть/показать
          // категорию) — курсор над ней ставится её собственными onHover/onLeave (ниже): chart-level
          // onHover вызывается только внутри plot-area и легенду не видит.
          onHover: function (event, elements) {
            var t = event.native && event.native.target;
            if (t) t.style.cursor = elements && elements.length ? 'pointer' : 'default';
          },
          onClick: function (event, elements) {
            if (!elements || !elements.length) return;
            var seg = expenses[elements[0].index];
            if (!seg) return;
            var month = new URLSearchParams(window.location.search).get('month') || '';
            window.location.href = '/?category=' + encodeURIComponent(seg.key)
              + (month ? '&month=' + encodeURIComponent(month) : '');
          },
          plugins: {
            legend: {
              labels: { color: fg },
              // Легенда кликабельна (скрыть/показать категорию) — это неочевидно, поэтому даём
              // явный курсор-указатель; подсказка — в шапке карточки (dashboard.html).
              onHover: function (event) {
                var t = event.native && event.native.target;
                if (t) t.style.cursor = 'pointer';
              },
              onLeave: function (event) {
                var t = event.native && event.native.target;
                if (t) t.style.cursor = 'default';
              }
            },
            tooltip: makeTooltip({
              label: function (ctx) {
                var total = ctx.dataset.data.reduce(function (a, b) { return a + b; }, 0) || 1;
                var pct = Math.round((ctx.parsed / total) * 100);
                return ctx.label + ': ' + fmtRub(ctx.parsed) + ' ' + CUR + ' (' + pct + '%)';
              }
            })
          }
        }
      });
    }
  }

  // Обработчики регистрируем один раз на JS-контекст (boost-свапы перезапускают скрипт),
  // старые Chart-инстансы уничтожаем перед свапом — иначе утечка и «пляшущие» графики.
  if (!window.__spendtrackChartHooks) {
    window.__spendtrackChartHooks = true;
    // S2 (Astra 02.10): события htmx всплывают до document — не зависим от window.htmx на момент
    // исполнения (порядок/defer/кэш) и от существования document.body.
    document.addEventListener('htmx:load', function () { initCharts(); });
    document.addEventListener('htmx:beforeSwap', function () {
      ['dailyChart', 'catsChart'].forEach(function (id) {
        var el = document.getElementById(id);
        var c = el && window.Chart && window.Chart.getChart(el);
        if (c) c.destroy();
        // S1 (Astra 02.10): сброс init — при частичном свапе (canvas не заменён) без него
        // draw() навсегда выходит по dataset.init === '1' и графики остаются пустыми.
        if (el) delete el.dataset.init;
      });
    });
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
