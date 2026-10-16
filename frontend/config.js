/**
 * Pi Jam FAST — Environment Configuration
 * =========================================
 * This file is the SINGLE place to change the backend URL.
 *
 * HOW IT WORKS:
 *  - In LOCAL development / local testing on phone:
 *      API_BASE = "" (empty) → all /api/... calls go to the same host (localhost or LAN IP)
 *
 *  - In PRODUCTION (cloud-deployed backend, Android APK):
 *      Set PIJAM_API_URL below to your Railway / Render URL.
 *      Example: "https://pijam-fast.up.railway.app"
 *
 * IMPORTANT: When building the Android APK for classroom use, set PRODUCTION_API_URL
 * to your deployed backend URL so the APK always talks to the cloud server.
 * Teachers will not need to run anything on their laptop.
 */

(function () {
  // ─── CHANGE THIS for production cloud deployment ───────────────────────────
  // Leave empty string "" for local development (server running on same machine).
  // Set to your Railway/Render URL for the Android APK build.
  // Example: "https://pijam-fast.up.railway.app"
  const PRODUCTION_API_URL = "";
  // ──────────────────────────────────────────────────────────────────────────

  // Auto-detect: if running inside a Capacitor APK (android/ios), or if the
  // URL is file:// (local APK webview), use the production URL.
  const isCapacitor =
    window.location.protocol === "capacitor:" ||
    window.location.protocol === "file:" ||
    (typeof window.Capacitor !== "undefined" && window.Capacitor.isNativePlatform?.());

  const resolvedBase = isCapacitor && PRODUCTION_API_URL
    ? PRODUCTION_API_URL
    : (PRODUCTION_API_URL || ""); // Empty = same-origin (local server)

  /**
   * window.API_BASE — HTTP base for all REST API calls.
   * Usage in app.js: fetch(`${window.API_BASE}/api/sessions`, ...)
   */
  window.API_BASE = resolvedBase;

  /**
   * window.WS_BASE — WebSocket base for the live scanner.
   * Usage in app.js: new WebSocket(`${window.WS_BASE}/api/ws/scan/${sessionId}`)
   */
  if (resolvedBase) {
    window.WS_BASE = resolvedBase.replace(/^https?:\/\//, (match) =>
      match === "https://" ? "wss://" : "ws://"
    );
  } else {
    // Same-origin websocket — construct from current page location
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    window.WS_BASE = `${proto}//${window.location.host}`;
  }

  console.log(
    `[Pi Jam Config] API_BASE="${window.API_BASE}" | WS_BASE="${window.WS_BASE}" | Capacitor=${isCapacitor}`
  );
})();
