const FIREBASE_TOKEN_KEY = "stock_journal_firebase_id_token";
const FIREBASE_REDIRECT_GUARD_KEY = "firebase_login_redirecting";
const originalFetch = window.fetch.bind(window);

function isLoginPage() {
  return window.location.pathname === "/login.html" || window.location.pathname === "/login";
}

function isApiRequest(input) {
  const url = typeof input === "string" ? input : input?.url || "";
  if (!url) return false;
  if (url.startsWith("/api/")) return true;
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.origin === window.location.origin && parsed.pathname.startsWith("/api/");
  } catch {
    return false;
  }
}

window.fetch = async (input, init = {}) => {
  if (!isApiRequest(input)) {
    return originalFetch(input, init);
  }

  const token = localStorage.getItem(FIREBASE_TOKEN_KEY);
  if (!token) {
    return originalFetch(input, init);
  }

  const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined) || {});
  if (!headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const nextInit = { ...init, headers };
  return originalFetch(input, nextInit);
};

async function verifyTokenOnPageLoad() {
  const token = localStorage.getItem(FIREBASE_TOKEN_KEY);
  const loginPage = isLoginPage();

  console.log("[Firebase Bridge] page:", window.location.pathname, "hasToken:", Boolean(token));

  if (!token) {
    if (!loginPage) {
      console.log("[Firebase Bridge] no token, redirect to /login.html");
      window.location.assign("/login.html");
    }
    return;
  }

  try {
    const response = await originalFetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });

    console.log("[Firebase Bridge] /api/auth/me status:", response.status);

    if (response.ok) {
      if (loginPage) {
        console.log("[Firebase Bridge] token valid on login page, redirect to /");
        window.location.assign("/");
      }
      return;
    }

    localStorage.removeItem(FIREBASE_TOKEN_KEY);
    console.log("[Firebase Bridge] token invalid, cleared localStorage");
    if (!loginPage) {
      console.log("[Firebase Bridge] token invalid, redirect to /login.html");
      window.location.assign("/login.html");
    }
  } catch (error) {
    console.error("[Firebase Bridge] token verify failed", error);
    localStorage.removeItem(FIREBASE_TOKEN_KEY);
    if (!loginPage) {
      window.location.assign("/login.html");
    }
  }
}

async function firebaseSignOutBestEffort() {
  try {
    const [{ getApps, getApp, initializeApp }, { getAuth, signOut }] = await Promise.all([
      import("https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js"),
      import("https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js"),
    ]);

    let app;
    if (getApps().length > 0) {
      app = getApp();
    } else {
      const configResponse = await originalFetch("/api/auth/config");
      const payload = await configResponse.json().catch(() => ({}));
      const firebaseConfig = payload?.firebase;
      if (!firebaseConfig?.apiKey || !firebaseConfig?.authDomain || !firebaseConfig?.projectId || !firebaseConfig?.appId) {
        throw new Error("Firebase config incomplete");
      }
      app = initializeApp(firebaseConfig);
    }

    await signOut(getAuth(app));
    console.log("[Firebase Bridge] Firebase signOut success");
  } catch (error) {
    console.error("[Firebase Bridge] Firebase signOut failed", error);
  }
}

function initLogoutButton() {
  const logoutButton = document.querySelector("#logout-button");
  if (!logoutButton) return;

  logoutButton.addEventListener("click", async () => {
    logoutButton.disabled = true;
    try {
      await firebaseSignOutBestEffort();
      await originalFetch("/api/auth/logout", { method: "POST" }).catch(() => null);
    } finally {
      localStorage.removeItem(FIREBASE_TOKEN_KEY);
      sessionStorage.removeItem(FIREBASE_REDIRECT_GUARD_KEY);
      window.location.assign("/login.html");
    }
  });
}

initLogoutButton();
verifyTokenOnPageLoad();
