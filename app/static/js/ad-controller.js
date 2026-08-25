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
   * the page load). This function:
   *   1. Records the pop as fired (starts cooldown)
   *   2. Runs your callback (e.g., navigate to download page)
   *
   * If the pop is NOT due (cooldown active), it just runs the callback
   * without recording a new pop — the SDK is suppressed by Adsterra's
   * own internal frequency capping anyway.
   */
  function gateAction(callback) {
    if (isPopDue()) {
      recordPopFired();
    }
    if (typeof callback === 'function') {
      callback();
    }
  }

  /* ── Smartlink fallback — opens only when pop is in cooldown, probabilistically ─ */
  var SMARTLINK_FALLBACK_RATE = 8; // 1 in 8 clicks when pop is in cooldown (~12.5%). Tune 6-10 conservative, 4-6 aggressive.

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
