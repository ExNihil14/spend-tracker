// Тема: light (по умолчанию) → dark → system; выбор в localStorage('spendtrack-theme').
// CSP: только внешний файл (script-src 'self'); грузится синхронно в <head> до CSS — без FOUC.
// Клик — делегированием: htmx boost-свап пересоздаёт кнопку в body, прямой обработчик теряется
// (регрессия 29.09), плюс после свапа обновляем подписи новой кнопки.
(function () {
  'use strict';
  var KEY = 'spendtrack-theme';
  var ORDER = ['light', 'dark', 'system'];

  function systemDark() {
    return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  }
  function resolve(mode) {
    return mode === 'system' ? (systemDark() ? 'dark' : 'light') : mode;
  }
  function current() {
    try { return localStorage.getItem(KEY) || 'light'; } catch (e) { return 'light'; }
  }
  function apply(mode) {
    document.documentElement.setAttribute('data-theme', resolve(mode));
    var btn = document.getElementById('theme-toggle');
    if (btn) {
      var label = mode === 'system' ? 'системная' : (mode === 'dark' ? 'тёмная' : 'светлая');
      btn.setAttribute('aria-label', 'Тема: ' + label + ' — переключить');
      btn.setAttribute('title', 'Тема: ' + label);
    }
    // Смена темы: страницы могут держать палитру в JS (Chart.js) — уведомляем слушателей.
    window.dispatchEvent(new CustomEvent('spendtrack:theme', { detail: { theme: resolve(mode) } }));
  }

  apply(current());

  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var onChange = function () { if (current() === 'system') apply('system'); };
    if (mq.addEventListener) mq.addEventListener('change', onChange);
    else if (mq.addListener) mq.addListener(onChange); // старые WebKit
  }

  document.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('#theme-toggle') : null;
    if (!btn) return;
    var mode = ORDER[(ORDER.indexOf(current()) + 1) % ORDER.length];
    try { localStorage.setItem(KEY, mode); } catch (err) { /* приватный режим */ }
    apply(mode);
  });
  document.addEventListener('htmx:afterSwap', function () { apply(current()); });
  document.addEventListener('DOMContentLoaded', function () { apply(current()); });
})();
