const loginButton = document.querySelector("#google-login-button");

loginButton?.addEventListener("click", () => {
  loginButton.setAttribute("aria-busy", "true");
  loginButton.classList.add("is-loading");
});
