// Тема — двухпозиционный тоггл (как на opencode.ai): светлая ↔ тёмная по клику; иконка меняется CSS-правилом
// по [data-theme] (в разметке обе — sun/moon). Хранение: localStorage('spendtrack-theme') = 'light' | 'dark'
// (легаси 'system'/мусор нормализуются в 'light' — двухтемный режим). CSP: только внешний файл (script-src 'self');
// грузится синхронно в <head> до CSS — без FOUC. Клик — делегированием: htmx boost-свап пересоздаёт кнопку
// в body (регрессия 29.09); после свапа синхронизируем aria-pressed/title.
(function () {
  'use strict';
  var KEY = 'spendtrack-theme';

  function current() {
    try { return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light'; } catch (e) { return 'light'; }
  }
  function other() { return current() === 'dark' ? 'light' : 'dark'; }
  function apply(mode) {
    var dark = mode === 'dark';
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    var btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.setAttribute('aria-pressed', dark ? 'true' : 'false');
      btn.setAttribute('title', dark ? 'Тема: тёмная' : 'Тема: светлая');
    }
    // Смена темы: страницы могут держать палитру в JS (Chart.js) — уведомляем слушателей.
    window.dispatchEvent(new CustomEvent('spendtrack:theme', { detail: { theme: dark ? 'dark' : 'light' } }));
  }

  apply(current());

  document.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('#theme-toggle') : null;
    if (!btn) return;
    var mode = other();
    try { localStorage.setItem(KEY, mode); } catch (err) { /* приватный режим */ }
    apply(mode);
  });
  document.addEventListener('htmx:afterSwap', function () { apply(current()); });
  document.addEventListener('DOMContentLoaded', function () { apply(current()); });
})();
