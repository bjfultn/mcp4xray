/* mcp4xray Admin Dashboard */

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
    if (!epoch) return "--";
    return new Date(epoch * 1000).toLocaleString();
}

// --- Init ---

function init() {
    const token = getToken();
    const role = localStorage.getItem("role");
    if (!token || role !== "admin") {
        window.location.href = "/";
        return;
    }

    document.getElementById("admin-user-name").textContent =
        localStorage.getItem("username") || "";

    document.getElementById("generate-btn").addEventListener("click", generateInvite);
    document.getElementById("copy-btn").addEventListener("click", copyToClipboard);

    loadInvites();
    loadUsers();
}

// --- Invites ---

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
        document.getElementById("code-display").textContent = data.code;
        document.getElementById("generated-code").classList.remove("hidden");
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
                '<td class="code-cell">' + escapeHtml(inv.code) + "</td>" +
                '<td class="status-' + status + '">' + status + "</td>" +
                "<td>" + formatDate(inv.created_at) + "</td>" +
                "<td>" + (inv.used_by != null ? escapeHtml(String(inv.used_by)) : "--") + "</td>";
            tbody.appendChild(tr);
        }
    } catch (e) {
        console.error("Failed to load invites:", e);
    }
}

// --- Users ---

async function loadUsers() {
    const currentUsername = localStorage.getItem("username") || "";
    try {
        const res = await fetch(API_BASE + "/users", {
            headers: authHeaders(),
        });
        if (!res.ok) return;
        const data = await res.json();
        const tbody = document.getElementById("users-body");
        tbody.innerHTML = "";
        for (const user of data.users) {
            const isSelf = user.username === currentUsername;
            const isAdmin = user.role === "admin";
            const tr = document.createElement("tr");
            tr.innerHTML =
                "<td>" + escapeHtml(user.username) + "</td>" +
                "<td>" + escapeHtml(user.role) + "</td>" +
                "<td>" + formatDate(user.created_at) + "</td>" +
                '<td><label class="admin-toggle">' +
                    '<input type="checkbox"' + (isAdmin ? " checked" : "") +
                    (isSelf ? " disabled" : "") +
                    ' data-user-id="' + user.id + '">' +
                    '<span class="slider"></span>' +
                '</label></td>';

            const checkbox = tr.querySelector('input[type="checkbox"]');
            if (!isSelf) {
                checkbox.addEventListener("change", async function () {
                    const userId = this.dataset.userId;
                    const makeAdmin = this.checked;
                    try {
                        const resp = await fetch(API_BASE + "/users/" + userId, {
                            method: "PATCH",
                            headers: authHeaders(),
                            body: JSON.stringify({ is_admin: makeAdmin }),
                        });
                        if (!resp.ok) {
                            this.checked = !makeAdmin;
                            console.error("Failed to update admin status");
                        }
                    } catch (err) {
                        this.checked = !makeAdmin;
                        console.error("Failed to update admin status:", err);
                    }
                });
            }

            tbody.appendChild(tr);
        }
    } catch (e) {
        console.error("Failed to load users:", e);
    }
}

// --- Clipboard ---

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

// --- Helpers ---

function escapeHtml(str) {
    if (str == null) return "";
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(String(str)));
    return div.innerHTML;
}

// --- Boot ---

document.addEventListener("DOMContentLoaded", init);
