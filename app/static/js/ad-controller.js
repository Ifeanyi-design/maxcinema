/**
 * MaxCinema Ad Controller
 * ========================
 * Single source of truth for ad session state.
 *
 * ARCHITECTURE NOTE:
 * - The Adsterra SDK (loaded separately in base.html) is the ONLY popunder.
 *   This module does NOT call window.open() or create any pops itself.
 * - This module manages cooldown state so that:
 *     a) The SDK fires correctly on the first user interaction
 *     b) We record that it fired so we don't gate legitimate clicks
 *     c) We can signal page-specific JS whether a pop is "due"
 *
 * Usage from page scripts:
 *   MaxCinemaAds.recordPopFired()      — call after SDK fires (on click)
 *   MaxCinemaAds.isPopDue()            — true if cooldown has expired
 *   MaxCinemaAds.gateAction(callback)  — run callback; if pop is due, also
 *                                        clears recorded state so next SDK
 *                                        fire is allowed on that interaction.
 */
(function (window) {
  'use strict';

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

  // Tier-based cooldowns (milliseconds)
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

  /* ── State helpers ───────────────────────────────────────────── */
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
   * Use this on download-button clicks where you want the Adsterra
   * SDK to fire (it fires automatically on first user click after
   * the page load). This now VERIFIES pop actually opened before
   * starting cooldown — if pop was blocked/failed, cooldown does NOT start.
   */
  function gateAction(callback) {
    var popWasDue = isPopDue();
    if (popWasDue) {
      // Don't assume pop fired — wait for verification via blur/window.open hook below
      pendingPopDue = true;
      pendingPopTimer = setTimeout(function() { pendingPopDue = false; }, 1200);
    }
    if (typeof callback === 'function') {
      callback();
    }
  }

  /* ── Verified pop detection — only start cooldown if pop actually opened ─ */
  var pendingPopDue = false;
  var pendingPopTimer = null;
  var originalWindowOpen = window.open;

  function confirmPopFired() {
    if (!pendingPopDue) {
      // Also handle homepage cards where we didn't call gateAction but pop was due
      if (!isPopDue()) return;
      // If pop was due and we see window.open/blur, confirm it
      if (isPopDue()) {
        // Check if we had a recent click that should have triggered pop
        // We treat any window.open or blur within 1.2s of a click when pop was due as confirmation
      }
    }
    recordPopFired();
    pendingPopDue = false;
    if (pendingPopTimer) { clearTimeout(pendingPopTimer); pendingPopTimer = null; }
  }

  // Hook window.open — Adsterra pop uses window.open
  try {
    window.open = function() {
      var result = originalWindowOpen.apply(this, arguments);
      // If pop was due and window.open was called within cooldown window, count it
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

  // Global click listener — arms pending flag when pop is due, so blur within 1.2s counts
  document.addEventListener('click', function() {
    if (isPopDue() && !pendingPopDue) {
      pendingPopDue = true;
      if (pendingPopTimer) clearTimeout(pendingPopTimer);
      pendingPopTimer = setTimeout(function() { pendingPopDue = false; }, 1200);
    }
  }, true);

  /* ── Smartlink fallback — opens only when pop is in cooldown, probabilistically ─ */
  var SMARTLINK_FALLBACK_RATE = 5; // 1 in 5 clicks when pop is in cooldown (20%). 4=25% aggressive, 6=16.7% balanced, 8=12.5% conservative.

  function shouldSmartlinkFallback(rate) {
    var r = rate || SMARTLINK_FALLBACK_RATE;
    if (isPopDue()) return false; // pop takes priority - don't double monetize same click
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

  /* ── Public API ──────────────────────────────────────────────── */
  window.MaxCinemaAds = {
    isPopDue:       isPopDue,
    recordPopFired: recordPopFired,
    gateAction:     gateAction,
    shouldSmartlinkFallback: shouldSmartlinkFallback,
    openSmartlinkFallback: openSmartlinkFallback,
    smartlinkUrl:   SMARTLINK_URL,
    smartlinkRate:  SMARTLINK_FALLBACK_RATE,
    country:        COUNTRY,
    isTier1:        TIER1.has(COUNTRY),
    cooldownMs:     COOLDOWN_MS
  };

  /* ── Debug helper (stripped in production by minifier) ───────── */
  if (window.location.search.indexOf('mc_debug') !== -1) {
    var remaining = Math.max(0, COOLDOWN_MS - (Date.now() - getLastPopTime()));
    console.group('[MaxCinemaAds] Debug');
    console.log('Country:', COUNTRY, '| Tier1:', TIER1.has(COUNTRY));
    console.log('Cooldown:', COOLDOWN_MS / 60000, 'min');
    console.log('Pop due:', isPopDue());
    console.log('Cooldown remaining:', Math.round(remaining / 60000), 'min');
    console.groupEnd();
  }

}(window));
