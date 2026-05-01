import { initializeApp, getApps, getApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithRedirect,
  getRedirectResult,
  onAuthStateChanged,
  setPersistence,
  browserLocalPersistence,
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js";

const FIREBASE_TOKEN_KEY = "stock_journal_firebase_id_token";
const REDIRECTING_KEY = "firebase_login_redirecting";

function showAuthStatus(message, tone = "info") {
  let box = document.querySelector("#auth-status-box");
  if (!box) {
    box = document.createElement("div");
    box.id = "auth-status-box";
    box.style.marginTop = "12px";
    box.style.padding = "12px";
    box.style.borderRadius = "10px";
    box.style.border = "1px solid #91caff";
    box.style.background = "#e6f4ff";
    box.style.color = "#0958d9";
    box.style.fontSize = "14px";
    box.style.lineHeight = "1.5";
    const anchor = document.querySelector(".auth-card") || document.body;
    anchor.appendChild(box);
  }

  if (tone === "success") {
    box.style.border = "1px solid #95de64";
    box.style.background = "#f6ffed";
    box.style.color = "#237804";
  } else if (tone === "error") {
    box.style.border = "1px solid #ffa39e";
    box.style.background = "#fff1f0";
    box.style.color = "#cf1322";
  } else {
    box.style.border = "1px solid #91caff";
    box.style.background = "#e6f4ff";
    box.style.color = "#0958d9";
  }

  box.textContent = message;
}

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
    showAuthStatus("redirect guard 阻擋導向，暫停跳轉。", "error");
    return false;
  }

  markRedirecting();
  showAuthStatus("/api/auth/me 成功，進入系統...", "success");
  console.log(`[Firebase Login:${source}] redirecting to /`);
  window.location.assign("/");
  return true;
}

async function storeToken(user, source) {
  if (!user) return false;
  showAuthStatus("已取得 Firebase user...");
  console.log(`[Firebase Login:${source}] user uid:`, user.uid || "(no uid)");
  console.log(`[Firebase Login:${source}] user email:`, user.email || "(no email)");

  showAuthStatus("正在取得 ID token...");
  const idToken = await user.getIdToken();

  localStorage.setItem(FIREBASE_TOKEN_KEY, idToken);
  showAuthStatus("token 已寫入 localStorage...");
  console.log(`[Firebase Login:${source}] token key:`, FIREBASE_TOKEN_KEY);
  console.log(`[Firebase Login:${source}] idToken length:`, idToken ? idToken.length : 0);
  return Boolean(idToken);
}

async function validateExistingTokenAndMaybeRedirect() {
  const token = localStorage.getItem(FIREBASE_TOKEN_KEY);
  const loginPage = onLoginPage();

  console.log("[Firebase Login:existing-token] hasToken:", Boolean(token));

  if (!token) return false;

  try {
    showAuthStatus("正在呼叫 /api/auth/me...");
    const response = await fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    console.log("[Firebase Login:existing-token] /api/auth/me status:", response.status);

    if (response.ok) {
      return redirectToApp("existing-token-valid");
    }

    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }

    const code = payload?.error || "unknown_error";
    const message = payload?.message || "";
    showAuthStatus(`/api/auth/me 失敗：${response.status} / ${code} ${message}`.trim(), "error");

    localStorage.removeItem(FIREBASE_TOKEN_KEY);
    clearRedirecting();
    console.log("[Firebase Login:existing-token] token invalid, cleared token + redirecting flag");
    return false;
  } catch (error) {
    console.error("[Firebase Login:existing-token-check-error]", error);
    showAuthStatus(`/api/auth/me 失敗：network / ${error?.message || String(error)}`, "error");
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

async function verifyTokenWithBackend(source) {
  const token = localStorage.getItem(FIREBASE_TOKEN_KEY);
  if (!token) {
    showAuthStatus("/api/auth/me 失敗：no token", "error");
    return false;
  }

  showAuthStatus("正在呼叫 /api/auth/me...");
  try {
    const response = await fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });

    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }

    console.log(`[Firebase Login:${source}] /api/auth/me status:`, response.status, payload);

    if (response.ok) {
      return true;
    }

    const code = payload?.error || "unknown_error";
    const message = payload?.message || "";
    showAuthStatus(`/api/auth/me 失敗：${response.status} / ${code} ${message}`.trim(), "error");
    return false;
  } catch (error) {
    showAuthStatus(`/api/auth/me 失敗：network / ${error?.message || String(error)}`, "error");
    return false;
  }
}

async function setupLogin() {
  const loginButton = document.querySelector("#google-login-button");
  if (!loginButton) return;

  showAuthStatus("正在準備 Google 登入...");

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
    showAuthStatus(`登入失敗：${code} / ${message}`, "error");
    return;
  }

  try {
    showAuthStatus("Google 回站，檢查 redirect result...");
    const result = await getRedirectResult(auth);
    console.log("[Firebase Login] getRedirectResult has result:", Boolean(result));
    console.log("[Firebase Login] getRedirectResult has user:", Boolean(result?.user));

    if (result?.user) {
      const hasToken = await storeToken(result.user, "redirect-result");
      if (hasToken) {
        const backendOk = await verifyTokenWithBackend("redirect-result");
        if (backendOk) {
          showAuthStatus("登入成功，準備進入系統...", "success");
          redirectToApp("redirect-result");
          return;
        }
      }
    }

    showAuthStatus("redirect result 為空，改用 auth state 檢查...");
  } catch (error) {
    console.error("[Firebase Redirect Result Error]", error);
    const code = error?.code || "unknown_error";
    const message = error?.message || String(error);
    showAuthError(`登入錯誤：${code} - ${message}`);
    showAuthStatus(`登入失敗：${code} / ${message}`, "error");
  }

  showAuthStatus("Firebase 初始化完成");

  onAuthStateChanged(auth, async (user) => {
    console.log("[Firebase Login] onAuthStateChanged has user:", Boolean(user));
    if (!user) return;
    console.log("[Firebase Login] auth state user email:", user.email || "(no email)");
    console.log("[Firebase Login] auth state user uid:", user.uid || "(no uid)");

    try {
      const hasToken = await storeToken(user, "auth-state");
      if (hasToken) {
        const backendOk = await verifyTokenWithBackend("auth-state");
        if (backendOk) {
          showAuthStatus("登入成功，準備進入系統...", "success");
          redirectToApp("auth-state");
        }
      }
    } catch (error) {
      console.error("[Firebase Auth State Error]", error);
      const code = error?.code || "unknown_error";
      const message = error?.message || String(error);
      showAuthStatus(`登入失敗：${code} / ${message}`, "error");
    }
  });

  const provider = new GoogleAuthProvider();
  console.log("[Firebase Login] provider initialized:", provider?.providerId || "(no providerId)");

  loginButton.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    clearAuthError();
    showAuthStatus("正在跳轉 Google 登入...");

    loginButton.setAttribute("aria-busy", "true");
    loginButton.classList.add("is-loading");

    try {
      console.log("[Firebase Login] login button clicked");
      await setPersistence(auth, browserLocalPersistence);
      console.log("[Firebase Login] persistence set");

      clearRedirecting();
      console.log("before redirect", auth, provider);
      console.log("calling redirect");
      await signInWithRedirect(auth, provider);
      console.log("redirect called");
    } catch (error) {
      console.error("[Firebase Login Redirect Error]", error);
      const code = error?.code || "unknown_error";
      const message = error?.message || String(error);
      alert(`Google 登入失敗\ncode: ${code}\nmessage: ${message}`);
      showAuthError(`登入失敗：${code} - ${message}`);
      showAuthStatus(`登入失敗：${code} / ${message}`, "error");
      loginButton.removeAttribute("aria-busy");
      loginButton.classList.remove("is-loading");
    }
  });
}

setupLogin().catch((error) => {
  console.error("[Firebase Setup Error]", error);
});
