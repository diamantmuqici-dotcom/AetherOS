/* site.js — progressive enhancement only.
   Policy: no fetch, no XHR, no analytics, no beacons, no geolocation, no cookies,
   no storage, and no third-party requests. Everything here runs locally. */
(function () {
  'use strict';

  // Smooth-scroll same-page anchors; cross-page links are left alone.
  document.addEventListener('click', function (e) {
    var link = e.target.closest('a[href^="#"]');
    if (!link) return;
    var id = link.getAttribute('href').slice(1);
    if (!id) return;
    var target = document.getElementById(id);
    if (!target) return;
    e.preventDefault();
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
    if (window.history && window.history.replaceState) window.history.replaceState(null, '', '#' + id);
  });

  // Copy a digest/checksum from an input or element named by data-copy-target.
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-copy-target]');
    if (!btn) return;
    var source = document.querySelector(btn.getAttribute('data-copy-target'));
    if (!source) return;
    var text = typeof source.value === 'string' ? source.value : source.textContent.trim();
    if (!text) return;
    var label = btn.textContent;
    var flashed = false;
    function flash() {
      if (flashed) return;
      flashed = true;
      btn.textContent = 'Copied';
      window.setTimeout(function () { btn.textContent = label; }, 1500);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(flash, function () {
        if (source.select) source.select(); // clipboard blocked: leave text selected
      });
    } else if (source.select) {
      source.select();
      flash();
    }
  });
})();
