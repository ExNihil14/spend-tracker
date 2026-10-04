// Клиентские обработчики spend-tracker. Вынесены из inline-скриптов/`hx-on::*`
// (строгий CSP: script-src 'self', htmx.config.allowEval=false — см. base.html).
(function () {
  'use strict';

  // Тост: показать сообщение после OOB-свопа (htmx:oobAfterSwap)
  document.body.addEventListener('htmx:oobAfterSwap', function () {
    var t = document.getElementById('toast');
    if (!t || t.dataset.flash !== '1') return;
    t.dataset.flash = '0';
    t.classList.remove('opacity-0');
    clearTimeout(window.__toastTimer);
    window.__toastTimer = setTimeout(function () { t.classList.add('opacity-0'); }, 1800);
  });

  // Wave 1-preview: count-up ЦЕЛЫХ счётчиков (счётчик очереди, проценты бюджета). Деньги не анимируем —
  // их формат живёт только на сервере (fmt_money: U+2212/NBSP); клиентская интерполяция
  // денежной строки может разойтись с серверной (дефект доверия). Reduced-motion → сразу значение.
  // Суффикс («%») задаётся data-countup-suffix и сохраняется при интерполяции.
  function animateCount(el, from, to) {
    var suffix = el.getAttribute('data-countup-suffix') || '';
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (from === to || reduce || !window.requestAnimationFrame) {
      el.textContent = String(to) + suffix;
      return;
    }
    var start = null;
    var dur = 400;
    function frame(ts) {
      if (start === null) start = ts;
      var p = Math.min(1, (ts - start) / dur);
      var eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
      el.textContent = String(Math.round(from + (to - from) * eased)) + suffix;
      if (p < 1) requestAnimationFrame(frame); else el.textContent = String(to) + suffix;
    }
    requestAnimationFrame(frame);
    if (el.animate) { // лёгкий «поп» без layout-сдвига (transform)
      el.animate(
        [{ transform: 'scale(0.92)' }, { transform: 'scale(1.06)' }, { transform: 'scale(1)' }],
        { duration: 260, easing: 'ease-out' });
    }
  }

  // Wave 1: count-up процентов бюджета — элементы [data-countup] (целые; один раз на элемент).
  function initCountups() {
    var els = document.querySelectorAll('[data-countup]:not([data-countup-done])');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var to = parseInt(el.getAttribute('data-countup'), 10);
      if (isNaN(to)) continue;
      el.setAttribute('data-countup-done', '1');
      animateCount(el, 0, to);
    }
  }

  var prevPending = null;
  document.body.addEventListener('htmx:oobBeforeSwap', function () {
    var cnt = document.getElementById('pending-count');
    prevPending = cnt ? parseInt(cnt.textContent, 10) : null;
  });
  document.body.addEventListener('htmx:oobAfterSwap', function () {
    var cnt = document.getElementById('pending-count');
    if (!cnt) return;
    var to = parseInt(cnt.textContent, 10);
    if (isNaN(to)) return;
    var from = (prevPending === null || isNaN(prevPending)) ? to : prevPending;
    animateCount(cnt, from, to);
  });

  // Wave 1: проценты бюджета — при загрузке и после htmx-свапов (boost-навигация не перезапускает app.js).
  initCountups();
  document.body.addEventListener('htmx:afterSwap', function () { initCountups(); });

  // После запросов форм главной: обновить список и счётчик очереди
  document.body.addEventListener('htmx:afterRequest', function (e) {
    var el = e.detail && e.detail.elt;
    if (!el || !el.id) return;
    if (el.id === 'add-form') {
      if (!e.detail.successful) return; // при ошибке форму не сбрасываем
      el.reset();
      fetch('/api/pending-count')
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var cnt = document.getElementById('pending-count');
          if (!cnt) return;
          // S2 (Astra 02.10): не доверяем форме ответа — null/строка давали «NaN» в счётчике.
          var to = (d && typeof d.count === 'number' && isFinite(d.count)) ? Math.round(d.count) : null;
          if (to === null) return; // S6 (wave5): невалидный ответ не обнуляет счётчик
          var from = parseInt(cnt.textContent, 10);
          animateCount(cnt, isNaN(from) ? to : from, to);
        })
        .catch(function () { /* счётчик не критичен */ });
      htmx.trigger('body', 'refresh-list');
    } else if (el.id === 'import-form') {
      htmx.trigger('body', 'refresh-list');
    }
  });

  // Панели «Импорт»/«Добавить» на главной (M-6): формы свёрнуты в кнопки шапки таблицы.
  function setPanel(btn, open) {
    var panel = document.getElementById(btn.getAttribute('aria-controls'));
    if (!panel) return;
    panel.toggleAttribute('hidden', !open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  document.body.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('[data-toggle]') : null;
    if (!btn) return;
    setPanel(btn, btn.getAttribute('aria-expanded') !== 'true');
  });

  // Отмена переименования категории (Astra 02.10): allowEval:false — hx-on:click больше не работает,
  // поведение живёт здесь (кнопка помечена data-rename-cancel в rename_confirm.html).
  document.body.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('[data-rename-cancel]') : null;
    if (!btn) return;
    var box = document.getElementById('rename-confirm');
    if (box) box.innerHTML = '';
  });

  // Ссылки /#import и /#add (лендинг, чек-лист, дашборд) открывают панель, а не «немой» якорь.
  function openFromHash() {
    var btn = document.getElementById((location.hash || '').replace('#', ''));
    if (btn && btn.hasAttribute('data-toggle')) setPanel(btn, true);
  }
  openFromHash();
  window.addEventListener('hashchange', openFromHash);

  // Drop-zone импорта: файл можно перетащить в зону.
  // Ревью 24.09 (P2): дроп мимо зоны не должен открывать файл в браузере, а подсветка —
  // мигать при проходе над дочерними элементами (счётчик входов).
  ['dragover', 'drop'].forEach(function (t) {
    window.addEventListener(t, function (e) { e.preventDefault(); });
  });
  var drop = document.getElementById('import-drop');
  if (drop) {
    var fileInput = drop.querySelector('input[type=file]');
    var depth = 0;
    drop.addEventListener('dragenter', function (e) {
      e.preventDefault();
      depth += 1;
      drop.classList.add('border-accent');
    });
    drop.addEventListener('dragover', function (e) { e.preventDefault(); });
    drop.addEventListener('dragleave', function () {
      depth -= 1;
      if (depth <= 0) { depth = 0; drop.classList.remove('border-accent'); }
    });
    drop.addEventListener('drop', function (e) {
      e.preventDefault();
      depth = 0;
      drop.classList.remove('border-accent');
      if (fileInput && e.dataTransfer && e.dataTransfer.files.length) fileInput.files = e.dataTransfer.files;
    });
  }

  // Wave 1.4: конфетти, когда очередь подтверждения опустела (свап в пустоту). Одноразовый декор:
  // aria-hidden-контейнер, только transform/opacity; при reduced-motion не создаётся вовсе.
  var confettiDone = false;
  function maybeConfetti() {
    if (confettiDone || !document.getElementById('review-empty')) return;
    confettiDone = true;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var poster = document.querySelector('#review-empty .poster');
    if (!poster) return;
    var rect = poster.getBoundingClientRect();
    var host = document.createElement('div');
    host.id = 'confetti';
    host.setAttribute('aria-hidden', 'true');
    var colors = ['var(--accent)', 'var(--accent-2)', 'var(--income)', 'var(--warn)', 'var(--danger)'];
    for (var i = 0; i < 18; i++) {
      var piece = document.createElement('span');
      piece.className = 'confetti-piece';
      piece.style.left = Math.round(rect.left + 24 + Math.random() * Math.max(80, rect.width - 48)) + 'px';
      piece.style.top = Math.round(rect.top + 6) + 'px';
      piece.style.background = colors[i % colors.length];
      piece.style.animationDelay = Math.round(Math.random() * 140) + 'ms';
      piece.style.animationDuration = (800 + Math.round(Math.random() * 350)) + 'ms';
      host.appendChild(piece);
    }
    document.body.appendChild(host);
    setTimeout(function () { if (host.parentNode) host.parentNode.removeChild(host); }, 1700);
  }
  document.body.addEventListener('htmx:afterSwap', maybeConfetti);
  document.body.addEventListener('htmx:oobAfterSwap', maybeConfetti);
})();
