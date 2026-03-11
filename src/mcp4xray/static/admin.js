"use strict";

const API_BASE = "/api/admin";
let lastGeneratedCode = "";

function getToken() {
    return localStorage.getItem("token");
}

function authHeaders() {
    return {
        "Authorization": "Bearer " + getToken(),
        "Content-Type": "application/json",
    };
}

function formatDate(epoch) {
    if (!epoch) return "-";
    return new Date(epoch * 1000).toLocaleString();
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

function init() {
    const token = getToken();
    const role = localStorage.getItem("role");
    if (!token || role !== "admin") {
        window.location.href = "/";
        return;
    }
    loadInvites();
    loadUsers();
}

// ---------------------------------------------------------------------------
// Invites
// ---------------------------------------------------------------------------

async function generateInvite() {
    try {
        const res = await fetch(API_BASE + "/invite", {
            method: "POST",
            headers: authHeaders(),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            alert("Failed to generate invite: " + (err.detail || res.statusText));
            return;
        }
        const data = await res.json();
        lastGeneratedCode = data.code;
        const display = document.getElementById("code-display");
        display.textContent = data.code;
        document.getElementById("generated-code").classList.remove("hidden");
        // Refresh invite list
        loadInvites();
    } catch (e) {
        alert("Error generating invite: " + e.message);
    }
}

async function loadInvites() {
    try {
        const res = await fetch(API_BASE + "/invites", {
            headers: authHeaders(),
        });
        if (!res.ok) return;
        const data = await res.json();
        const tbody = document.getElementById("invites-body");
        tbody.innerHTML = "";
        for (const inv of data.invites) {
            const tr = document.createElement("tr");
            const status = inv.used_by ? "used" : "unused";
            tr.innerHTML =
                "<td class=\"code-cell\">" + escapeHtml(inv.code) + "</td>" +
                "<td class=\"status-" + status + "\">" + status + "</td>" +
                "<td>" + formatDate(inv.created_at) + "</td>" +
                "<td>" + (inv.used_by != null ? inv.used_by : "-") + "</td>";
            tbody.appendChild(tr);
        }
    } catch (e) {
        console.error("Failed to load invites:", e);
    }
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

async function loadUsers() {
    try {
        const res = await fetch(API_BASE + "/users", {
            headers: authHeaders(),
        });
        if (!res.ok) return;
        const data = await res.json();
        const tbody = document.getElementById("users-body");
        tbody.innerHTML = "";
        for (const user of data.users) {
            const tr = document.createElement("tr");
            tr.innerHTML =
                "<td>" + escapeHtml(user.username) + "</td>" +
                "<td>" + escapeHtml(user.role) + "</td>" +
                "<td>" + formatDate(user.created_at) + "</td>";
            tbody.appendChild(tr);
        }
    } catch (e) {
        console.error("Failed to load users:", e);
    }
}

// ---------------------------------------------------------------------------
// Clipboard
// ---------------------------------------------------------------------------

async function copyToClipboard() {
    const text = lastGeneratedCode;
    if (!text) return;
    try {
        await navigator.clipboard.writeText(text);
        const btn = document.getElementById("copy-btn");
        const original = btn.textContent;
        btn.textContent = "Copied!";
        setTimeout(() => { btn.textContent = original; }, 1500);
    } catch (e) {
        // Fallback for older browsers / non-HTTPS
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        const btn = document.getElementById("copy-btn");
        const original = btn.textContent;
        btn.textContent = "Copied!";
        setTimeout(() => { btn.textContent = original; }, 1500);
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(str) {
    if (str == null) return "";
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(String(str)));
    return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", init);
