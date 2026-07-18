/**
 * Shared-token auth for the SAHAYI MVP dashboard (no Firebase).
 *
 * The backend authorises doctor requests with a single shared token
 * (DASHBOARD_SHARED_TOKEN). This module stores that token locally and
 * exposes a fake doctor profile so the rest of the UI keeps working.
 *
 * @returns {object} Token store helpers and the fake doctor profile.
 */

const TOKEN_KEY = "sahayi_doctor_token";

// MVP demo token — must match DASHBOARD_SHARED_TOKEN on the backend.
const DEFAULT_TOKEN = import.meta.env.VITE_DASHBOARD_TOKEN || "hackathon_demo_token";

// Dummy doctor profile used across the dashboard (MVP mode).
const DOCTOR_USER = {
  uid: "mvp-doctor-001",
  email: "doctor@sahayi.local",
  displayName: "Demo Doctor",
  photoURL: null,
};

export function getStoredToken() {
  /**
   * Read the saved dashboard token, defaulting to the MVP token.
   * @returns {string} Stored or default token.
   */
  return localStorage.getItem(TOKEN_KEY) || DEFAULT_TOKEN;
}

export function setStoredToken(token) {
  /**
   * Persist the dashboard token to local storage.
   * @param {string} token Shared dashboard token.
   * @returns {void}
   */
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  /**
   * Remove the saved dashboard token (logout).
   * @returns {void}
   */
  localStorage.removeItem(TOKEN_KEY);
}

export function getDoctorUser() {
  /**
   * Return the fake doctor profile used by the dashboard.
   * @returns {object} Doctor profile object.
   */
  return DOCTOR_USER;
}

export function isAuthenticated() {
  /**
   * Whether a token is present (always true in MVP mode).
   * @returns {boolean} True when authenticated.
   */
  return Boolean(getStoredToken());
}

export { DEFAULT_TOKEN };
