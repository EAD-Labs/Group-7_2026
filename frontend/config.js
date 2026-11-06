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
 *      Set PIJAM_API_URL below to your Render URL.
 *      Example: "https://pi-jam-fast.onrender.com"
 *
 * IMPORTANT: When building the Android APK for classroom use, set PRODUCTION_API_URL
 * to your deployed backend URL so the APK always talks to the cloud server.
 * Teachers will not need to run anything on their laptop.
 */

(function () {
  // ─── Production Cloud URL (for Android APK and Deployed Web) ─────────────
  const PRODUCTION_API_URL = "https://pi-jam-fast.onrender.com";
  // ──────────────────────────────────────────────────────────────────────────

  // Detect if running inside a local development server (python run_server.py on port 8000)
  const isLocalDevServer =
    typeof window !== "undefined" &&
    window.location &&
    (window.location.port === "8000" || window.location.port === "8080");

  // If running on local development server (port 8000) -> use same-origin ""
  // In ALL other cases (Capacitor Android APK, live cloud deployment) -> use PRODUCTION_API_URL
  const resolvedBase = isLocalDevServer ? "" : PRODUCTION_API_URL;

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
