/**
 * MaxCinema Ad Controller
 * ========================
 * Single source of truth for ad session state.
 *
 * MODES (controlled by AD_SMARTLINK_MODE):
 *   "standard"  — Adsterra-recommended setup. No custom click handlers opening
 *                 Smartlinks, no popunder wrappers, no probabilistic fallback.
 *                 The Adsterra SDK popunder fires on its own; Smartlink is
 *                 used as a plain <a href> link in templates.
 *   "optimized" — legacy behavior: smartlink-trigger click handler (loaded
 *                 separately via ads/popunder.html), probabilistic content-
 *                 card fallback, and popunder cooldown observers all active.
 *                 Flip the env var to roll back without redeploying code.
 *
 * ARCHITECTURE NOTE:
 * - The Adsterra SDK (loaded separately in base.html) is the ONLY popunder.
 *   This module does NOT call window.open() or create any pops itself.
 * - In "optimized" mode this module manages cooldown state so that:
 *     a) The SDK fires correctly on the first user interaction
 *     b) We record that it fired so we don't gate legitimate clicks
 *     c) The probabilistic smartlink fallback can decide whether pop is "due"
 */
(function (window, document) {
  'use strict';

  var MODE = (document.body && (
    document.body.dataset.smartlinkMode ||
    document.body.getAttribute('data-smartlink-mode') ||
    'standard'
  ).toLowerCase()) || 'standard';
  var OPTIMIZED = MODE === 'optimized';

  /* ── Constants ───────────────────────────────────────────────── */
  var LS_LAST_POP   = 'mc_pop_last';   // timestamp of last SDK fire
  var LS_POP_COUNT  = 'mc_pop_count';  // lifetime pop count (for analytics)

  /* ── Read config from <body> data attributes ─────────────────── */
  var body      = document.body || document.documentElement;
  var COUNTRY   = (body.dataset.country || 'XX').toUpperCase();
  var SMARTLINK_URL = (body.dataset.smartlinkUrl || body.getAttribute('data-smartlink-url') || '').trim();

  var TIER1 = new Set([
    'US','GB','CA','AU','DE','FR','NL','NO','SE','FI','BE','CH','AT','IE','NZ','DK'
  ]);

  // Tier-based cooldowns (milliseconds) — only used in optimized mode
  var COOLDOWN_MS = TIER1.has(COUNTRY)
    ? 75 * 60 * 1000   // Tier 1 → 75 minutes
    : 25 * 60 * 1000;  // Others  → 25 minutes

  /* ── localStorage helpers ────────────────────────────────────── */
  function lsGet(key, fallback) {
    try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; }
  }
  function lsSet(key, value) {
    try { localStorage.setItem(key, String(value)); } catch (e) {}
  }

  /* ── State helpers (used by optimized-mode fallback only) ────── */
  function getLastPopTime() {
    return parseInt(lsGet(LS_LAST_POP, '0'), 10);
  }

  function isPopDue() {
    return (Date.now() - getLastPopTime()) > COOLDOWN_MS;
  }

  /**
   * Call this whenever you know the Adsterra SDK has fired a pop.
   * Stamps the current timestamp so cooldown starts now.
   */
  function recordPopFired() {
    lsSet(LS_LAST_POP, Date.now());
    lsSet(LS_POP_COUNT, parseInt(lsGet(LS_POP_COUNT, '0'), 10) + 1);
  }

  /**
   * gateAction(callback)
   * --------------------
   * Optimized-mode helper for download-button clicks where you want the
   * Adsterra SDK to fire (it fires automatically on first user click after
   * the page load).  Verifies pop actually opened before starting cooldown —
   * if pop was blocked/failed, cooldown does NOT start.
   */
  function gateAction(callback) {
    var popWasDue = isPopDue();
    if (popWasDue) {
      pendingPopDue = true;
      pendingPopTimer = setTimeout(function() { pendingPopDue = false; }, 1200);
    }
    if (typeof callback === 'function') {
      callback();
    }
  }

  /* ── Optimized-mode: verified pop detection ──────────────────── */
  var pendingPopDue = false;
  var pendingPopTimer = null;
  var originalWindowOpen = window.open;

  function confirmPopFired() {
    if (!pendingPopDue) {
      if (!isPopDue()) return;
    }
    recordPopFired();
    pendingPopDue = false;
    if (pendingPopTimer) { clearTimeout(pendingPopTimer); pendingPopTimer = null; }
  }

  function installOptimizedObservers() {
    // Hook window.open — Adsterra pop uses window.open
    try {
      window.open = function() {
        var result = originalWindowOpen.apply(this, arguments);
        if (pendingPopDue || isPopDue()) {
          confirmPopFired();
        }
        return result;
      };
    } catch(e) {}

    // Detect pop via page blur/visibility — popunder causes page to lose focus
    function handlePopSignal() {
      if (isPopDue() || pendingPopDue) {
        confirmPopFired();
      }
    }
    window.addEventListener('blur', handlePopSignal, false);
    document.addEventListener('visibilitychange', function() {
      if (document.hidden) handlePopSignal();
    }, false);

    // Global click listener — arms pending flag when pop is due
    document.addEventListener('click', function() {
      if (isPopDue() && !pendingPopDue) {
        pendingPopDue = true;
        if (pendingPopTimer) clearTimeout(pendingPopTimer);
        pendingPopTimer = setTimeout(function() { pendingPopDue = false; }, 1200);
      }
    }, true);

    // ── Site-wide content card smartlink fallback (1 in 5 during cooldown) ──
    // Covers: Homepage Featured/RecentlyAdded/Sidebar, Search Results, Genre,
    // Trending Charts, All Movies/All Series, Movie detail Recommended.
    // Excludes: .smartlink-trigger dedicated cards (100% already),
    // nav/search/pagination.
    document.addEventListener('click', function(e) {
      var card = e.target.closest(
        '#featurecontain a:not(.smartlink-trigger), ' +
        '#RecentlyAddedbox a:not(.smartlink-trigger), ' +
        '#SeriesGridBox a:not(.smartlink-trigger), ' +
        '#ResultsGrid a:not(.smartlink-trigger), ' +
        '#TrendingCol div[onclick], ' +
        'a.download-ad-trigger:not(.smartlink-trigger)'
      );
      if (!card) return;
      if (card.closest('#header, #NavMenu, #MobilegenreMenu, #genreMenu')) return;
      openSmartlinkFallback();
    }, false);
  }

  /* ── Optimized-mode: smartlink fallback ──────────────────────── */
  // Dynamic rate: each click picks a random 1-in-N where N is between MIN
  // and MAX.  2..5 → per-click chance between 50% and 20% (avg ~32%).
  var SMARTLINK_RATE_MIN = 2;
  var SMARTLINK_RATE_MAX = 5;

  function pickSmartlinkRate() {
    var lo = Math.max(2, SMARTLINK_RATE_MIN);
    var hi = Math.max(lo, SMARTLINK_RATE_MAX);
    return Math.floor(Math.random() * (hi - lo + 1)) + lo;
  }

  function shouldSmartlinkFallback(rate) {
    var r = rate || pickSmartlinkRate();
    if (isPopDue()) return false;
    if (!SMARTLINK_URL) return false;
    return Math.random() < (1 / r);
  }

  function openSmartlinkFallback(rate) {
    if (!shouldSmartlinkFallback(rate)) return false;
    var url = SMARTLINK_URL;
    var ua = navigator.userAgent;
    var isSafari = /Safari/i.test(ua) && !/Chrome|Chromium|Edg|OPR|CriOS|FxiOS|Android/i.test(ua);
    try {
      if (isSafari) {
        var a = document.createElement('a');
        a.href = url;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } else {
        var w = window.open(url, '_blank', 'noopener,noreferrer');
        if (w) { try { w.opener = null; } catch(e) {} }
      }
      return true;
    } catch(e) { return false; }
  }

  /* ── Mode wiring ─────────────────────────────────────────────── */
  if (OPTIMIZED) {
    installOptimizedObservers();
  }

  /* ── Public API ──────────────────────────────────────────────── */
  // In standard mode the smartlink/popunder helpers are still exposed but
  // become harmless no-ops; no page script currently consumes them, but we
  // keep the shape stable so nothing breaks if a template references one.
  window.MaxCinemaAds = {
    mode:             MODE,
    isPopDue:         isPopDue,
    recordPopFired:   recordPopFired,
    gateAction:       gateAction,
    shouldSmartlinkFallback: OPTIMIZED ? shouldSmartlinkFallback : function () { return false; },
    openSmartlinkFallback:   OPTIMIZED ? openSmartlinkFallback   : function () { return false; },
    smartlinkUrl:     SMARTLINK_URL,
    smartlinkRate:    OPTIMIZED
      ? (SMARTLINK_RATE_MIN + '-' + SMARTLINK_RATE_MAX + ' (dynamic)')
      : 'disabled (standard mode)',
    pickSmartlinkRate:      OPTIMIZED ? pickSmartlinkRate : function () { return 0; },
    country:          COUNTRY,
    isTier1:          TIER1.has(COUNTRY),
    cooldownMs:       COOLDOWN_MS
  };

  /* ── Debug helper (stripped in production by minifier) ───────── */
  if (window.location.search.indexOf('mc_debug') !== -1) {
    var remaining = Math.max(0, COOLDOWN_MS - (Date.now() - getLastPopTime()));
    console.group('[MaxCinemaAds] Debug');
    console.log('Mode:', MODE, '| Standard =', !OPTIMIZED);
    console.log('Country:', COUNTRY, '| Tier1:', TIER1.has(COUNTRY));
    console.log('Cooldown:', COOLDOWN_MS / 60000, 'min');
    console.log('Pop due:', isPopDue());
    console.log('Cooldown remaining:', Math.round(remaining / 60000), 'min');
    console.groupEnd();
  }

}(window, document));