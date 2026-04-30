import { initializeApp, getApps, getApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  onAuthStateChanged,
  setPersistence,
  browserLocalPersistence,
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js";

const FIREBASE_TOKEN_KEY = "stock_journal_firebase_id_token";
const REDIRECTING_KEY = "firebase_login_redirecting";

function showAuthError(message) {
  let box = document.querySelector("#auth-error-box");
  if (!box) {
    box = document.createElement("div");
    box.id = "auth-error-box";
    box.style.marginTop = "12px";
    box.style.padding = "12px";
    box.style.borderRadius = "10px";
    box.style.background = "#fff1f0";
    box.style.border = "1px solid #ffa39e";
    box.style.color = "#cf1322";
    box.style.fontSize = "14px";
    box.style.lineHeight = "1.5";
    const anchor = document.querySelector(".auth-card") || document.body;
    anchor.appendChild(box);
  }
  box.textContent = message;
}

function clearAuthError() {
  const box = document.querySelector("#auth-error-box");
  if (box) box.remove();
}

function onLoginPage() {
  return window.location.pathname === "/login.html" || window.location.pathname === "/login";
}

function isRedirectingFlagSet() {
  const raw = sessionStorage.getItem(REDIRECTING_KEY);
  if (!raw) return false;

  const ts = Number(raw);
  if (!Number.isFinite(ts)) {
    sessionStorage.removeItem(REDIRECTING_KEY);
    return false;
  }

  const ageMs = Date.now() - ts;
  if (ageMs > 8000) {
    sessionStorage.removeItem(REDIRECTING_KEY);
    return false;
  }

  return true;
}

function markRedirecting() {
  sessionStorage.setItem(REDIRECTING_KEY, String(Date.now()));
}

function clearRedirecting() {
  sessionStorage.removeItem(REDIRECTING_KEY);
}

function redirectToApp(source) {
  const shouldRedirect = onLoginPage();
  const blockedByGuard = isRedirectingFlagSet();
  console.log(`[Firebase Login:${source}] shouldRedirect=${shouldRedirect}, blockedByGuard=${blockedByGuard}`);

  if (!shouldRedirect) return false;
  if (blockedByGuard) {
    console.log(`[Firebase Login:${source}] redirect blocked by guard`);
    return false;
  }

  markRedirecting();
  console.log(`[Firebase Login:${source}] redirecting to /`);
  window.location.assign("/");
  return true;
}

async function storeToken(user, source) {
  if (!user) return false;
  const idToken = await user.getIdToken();
  localStorage.setItem(FIREBASE_TOKEN_KEY, idToken);
  console.log(`[Firebase Login:${source}] user email:`, user.email || "(no email)");
  console.log(`[Firebase Login:${source}] idToken length:`, idToken ? idToken.length : 0);
  return Boolean(idToken);
}

async function validateExistingTokenAndMaybeRedirect() {
  const token = localStorage.getItem(FIREBASE_TOKEN_KEY);
  const loginPage = onLoginPage();

  console.log("[Firebase Login:existing-token] hasToken:", Boolean(token));

  if (!token) return false;

  try {
    const response = await fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    console.log("[Firebase Login:existing-token] /api/auth/me status:", response.status);

    if (response.ok) {
      return redirectToApp("existing-token-valid");
    }

    localStorage.removeItem(FIREBASE_TOKEN_KEY);
    clearRedirecting();
    console.log("[Firebase Login:existing-token] token invalid, cleared token + redirecting flag");
    return false;
  } catch (error) {
    console.error("[Firebase Login:existing-token-check-error]", error);
    if (!loginPage) {
      localStorage.removeItem(FIREBASE_TOKEN_KEY);
      clearRedirecting();
    }
    return false;
  }
}

async function loadAuthConfig() {
  const response = await fetch("/api/auth/config");
  if (!response.ok) {
    throw new Error(`無法讀取登入設定，HTTP ${response.status}`);
  }

  const payload = await response.json();
  const firebase = payload?.firebase || {};
  const requiredFields = ["apiKey", "authDomain", "projectId", "appId"];
  const missingFields = requiredFields.filter((key) => !firebase[key]);

  if (missingFields.length > 0) {
    const message = `Firebase 設定不完整，缺少欄位：${missingFields.join(", ")}。請檢查後端 /api/auth/config 與 .env。`;
    showAuthError(message);
    throw new Error(message);
  }

  return firebase;
}

async function initAuth() {
  const firebaseConfig = await loadAuthConfig();
  const app = getApps().length ? getApp() : initializeApp(firebaseConfig);
  console.log("[Firebase Login] app initialized count:", getApps().length);
  const auth = getAuth(app);
  return auth;
}

async function setupLogin() {
  const loginButton = document.querySelector("#google-login-button");
  if (!loginButton) return;

  if (onLoginPage()) {
    // 若因前一次導向中斷而殘留 guard，進入 login 頁時先清掉，避免卡住無法回到首頁
    clearRedirecting();
    const redirected = await validateExistingTokenAndMaybeRedirect();
    if (redirected) return;
  }

  let auth;
  try {
    auth = await initAuth();
  } catch (error) {
    console.error("[Firebase Init Error]", error);
    const code = error?.code || "config_error";
    const message = error?.message || String(error);
    showAuthError(`初始化失敗：${code} - ${message}`);
    return;
  }

  onAuthStateChanged(auth, async (user) => {
    console.log("[Firebase Login] onAuthStateChanged has user:", Boolean(user));
    if (!user) return;
    try {
      const hasToken = await storeToken(user, "auth-state");
      if (hasToken) {
        redirectToApp("auth-state");
      }
    } catch (error) {
      console.error("[Firebase Auth State Error]", error);
    }
  });

  loginButton.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    clearAuthError();

    loginButton.setAttribute("aria-busy", "true");
    loginButton.classList.add("is-loading");

    try {
      console.log("[Firebase Login] login button clicked");
      await setPersistence(auth, browserLocalPersistence);
      console.log("[Firebase Login] persistence set");

      const provider = new GoogleAuthProvider();
      clearRedirecting();
      console.log("[Firebase Login] signInWithPopup called");
      const result = await signInWithPopup(auth, provider);
      console.log("[Firebase Login] signInWithPopup resolved");

      const hasToken = await storeToken(result.user, "popup");
      if (hasToken) {
        redirectToApp("popup");
      }
    } catch (error) {
      console.error("[Firebase Login Popup Error]", error);
      const code = error?.code || "unknown_error";
      const message = error?.message || String(error);
      alert(`Google 登入失敗\ncode: ${code}\nmessage: ${message}`);
      showAuthError(`登入失敗：${code} - ${message}`);
    } finally {
      loginButton.removeAttribute("aria-busy");
      loginButton.classList.remove("is-loading");
    }
  });
}

setupLogin().catch((error) => {
  console.error("[Firebase Setup Error]", error);
});
