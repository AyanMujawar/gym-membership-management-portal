// api.js - shared helper functions for talking to the backend

// Builds the backend's address from whatever host the page was loaded from
// (works on localhost during development AND on a deployed server's public IP).
// Falls back to localhost:5000 if the page was opened directly as a file
// (file://) instead of through Docker/nginx, since window.location.hostname
// is empty in that case and would otherwise produce a broken URL.
const API_BASE_URL = (window.location.protocol === "file:" || !window.location.hostname)
    ? "http://localhost:5000"
    : `${window.location.protocol}//${window.location.hostname}:5000`;

// Saves login info in the browser after a successful login
function saveSession(token, role, name) {
    localStorage.setItem("token", token);
    localStorage.setItem("role", role);
    localStorage.setItem("name", name);
}

// Reads the saved login token
function getToken() {
    return localStorage.getItem("token");
}

// Reads the saved role (member or admin)
function getRole() {
    return localStorage.getItem("role");
}

// Clears the saved login and sends the browser back to the login page
function logout() {
    localStorage.clear();
    window.location.href = "login.html";
}

// Page guard: sends anyone who isn't logged in as this role to the login page
function requireRole(role) {
    if (getRole() !== role || !getToken()) {
        window.location.href = "login.html";
        return false;
    }
    return true;
}

// One reusable function for every API call the frontend makes
async function apiRequest(endpoint, method = "GET", body = null, useAuth = false) {
    const headers = { "Content-Type": "application/json" };
    if (useAuth) {
        headers["Authorization"] = "Bearer " + getToken();
    }
    const response = await fetch(API_BASE_URL + endpoint, {
        method: method,
        headers: headers,
        body: body ? JSON.stringify(body) : null
    });
    // An expired/invalid token on a protected call means the session is over
    if (useAuth && response.status === 401) {
        logout();
    }
    return response.json();
}

// Escapes text before it is put into innerHTML, so user-entered names can't inject markup
function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, ch => (
        { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
    ));
}

// "2026-09-20" -> "20 Sep 2026"; missing dates show as a dash
function formatDate(value) {
    if (!value) return "—";
    const d = new Date(value);
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

// 2700 -> "₹2,700"
function formatMoney(value) {
    return "₹" + Number(value || 0).toLocaleString("en-IN");
}

function statusBadge(status) {
    return `<span class="badge badge-${escapeHtml(status)}">${escapeHtml(status)}</span>`;
}

// Builds the navbar links based on whether someone is logged in, and as what role
function renderNavbar() {
    const role = getRole();
    const navLinks = document.getElementById("navLinks");
    if (!navLinks) return;
    if (role === "member") {
        navLinks.innerHTML = `<a href="index.html">Plans</a> <a href="my-membership.html">My Membership</a> <a href="my-payments.html">Payments</a> <a href="profile.html">Profile</a> <a href="#" onclick="logout()">Logout</a>`;
    } else if (role === "admin") {
        navLinks.innerHTML = `<a href="admin.html">Dashboard</a> <a href="admin-members.html">Members</a> <a href="admin-plans.html">Plans</a> <a href="admin-expired.html">Expired</a> <a href="admin-report.html">Report</a> <a href="#" onclick="logout()">Logout</a>`;
    } else {
        navLinks.innerHTML = `<a href="index.html">Plans</a> <a href="login.html">Login</a> <a href="register.html">Join Now</a>`;
    }
}

// Draws the four headline numbers used on both the admin dashboard and the report
function renderStats(container, stats) {
    const cards = [
        ["Total Members", stats.total_members],
        ["Active Memberships", stats.active_memberships],
        ["Expired Memberships", stats.expired_memberships],
        ["Monthly Revenue", formatMoney(stats.monthly_revenue)]
    ];
    container.innerHTML = cards.map(([label, value]) =>
        `<div class="stat-card"><div class="value">${value}</div><div class="label">${label}</div></div>`
    ).join("");
}

document.addEventListener("DOMContentLoaded", renderNavbar);
