// auth.js — Login and registration logic for mcp4xray

(function () {
    "use strict";

    const loginForm = document.getElementById("login-form");
    const registerForm = document.getElementById("register-form");
    const loginSection = document.getElementById("login-section");
    const registerSection = document.getElementById("register-section");
    const showRegisterLink = document.getElementById("show-register");
    const showLoginLink = document.getElementById("show-login");
    const loginError = document.getElementById("login-error");
    const registerError = document.getElementById("register-error");

    // Toggle between login and register views
    function showLogin() {
        loginSection.classList.remove("hidden");
        registerSection.classList.add("hidden");
        loginError.classList.remove("visible");
        registerError.classList.remove("visible");
    }

    function showRegister() {
        loginSection.classList.add("hidden");
        registerSection.classList.remove("hidden");
        loginError.classList.remove("visible");
        registerError.classList.remove("visible");
    }

    if (showRegisterLink) {
        showRegisterLink.addEventListener("click", function (e) {
            e.preventDefault();
            showRegister();
        });
    }

    if (showLoginLink) {
        showLoginLink.addEventListener("click", function (e) {
            e.preventDefault();
            showLogin();
        });
    }

    // Display an error in the given element
    function showError(el, message) {
        el.textContent = message;
        el.classList.add("visible");
    }

    function clearError(el) {
        el.textContent = "";
        el.classList.remove("visible");
    }

    // Store auth data and redirect
    function onAuthSuccess(data) {
        localStorage.setItem("token", data.token);
        localStorage.setItem("username", data.username);
        localStorage.setItem("role", data.role);
        window.location.href = "/";
    }

    // Login handler
    if (loginForm) {
        loginForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            clearError(loginError);

            const username = loginForm.querySelector('[name="username"]').value.trim();
            const password = loginForm.querySelector('[name="password"]').value;

            if (!username || !password) {
                showError(loginError, "Please enter both username and password.");
                return;
            }

            const submitBtn = loginForm.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = "Signing in\u2026";

            try {
                const res = await fetch("/api/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password }),
                });

                if (!res.ok) {
                    const body = await res.json().catch(() => ({}));
                    throw new Error(body.detail || "Login failed");
                }

                const data = await res.json();
                onAuthSuccess(data);
            } catch (err) {
                showError(loginError, err.message);
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = "Sign In";
            }
        });
    }

    // Register handler
    if (registerForm) {
        registerForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            clearError(registerError);

            const username = registerForm.querySelector('[name="username"]').value.trim();
            const password = registerForm.querySelector('[name="password"]').value;
            const inviteCode = registerForm.querySelector('[name="invite_code"]').value.trim();

            if (!username || !password || !inviteCode) {
                showError(registerError, "All fields are required.");
                return;
            }

            if (password.length < 6) {
                showError(registerError, "Password must be at least 6 characters.");
                return;
            }

            const submitBtn = registerForm.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = "Creating account\u2026";

            try {
                const res = await fetch("/api/register", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        username,
                        password,
                        invite_code: inviteCode,
                    }),
                });

                if (!res.ok) {
                    const body = await res.json().catch(() => ({}));
                    throw new Error(body.detail || "Registration failed");
                }

                const data = await res.json();
                onAuthSuccess(data);
            } catch (err) {
                showError(registerError, err.message);
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = "Create Account";
            }
        });
    }
})();
