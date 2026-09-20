// auth.js - handles the login and register form submissions

// Runs when the login form is submitted
document.getElementById("loginForm")?.addEventListener("submit", async function (e) {
    e.preventDefault();
    const role = document.getElementById("role").value;
    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;

    const endpoint = role === "admin" ? "/api/admin/login" : "/api/users/login";
    const result = await apiRequest(endpoint, "POST", { email, password });

    if (result.token) {
        saveSession(result.token, role, result.name);
        window.location.href = role === "admin" ? "admin.html" : "my-membership.html";
    } else {
        document.getElementById("message").innerText = result.error || "Login failed";
    }
});

// Runs when the register form is submitted (members only — admins are seeded, not self-registered)
document.getElementById("registerForm")?.addEventListener("submit", async function (e) {
    e.preventDefault();
    const body = {
        name: document.getElementById("name").value,
        email: document.getElementById("email").value,
        password: document.getElementById("password").value,
        phone: document.getElementById("phone").value,
        address: document.getElementById("address").value
    };
    const result = await apiRequest("/api/users/register", "POST", body);

    const message = document.getElementById("message");
    if (result.user_id) {
        message.className = "message ok";
        message.innerText = "Registered! Redirecting to login...";
        setTimeout(() => { window.location.href = "login.html"; }, 1200);
    } else {
        message.className = "message";
        message.innerText = result.error || "Registration failed";
    }
});
