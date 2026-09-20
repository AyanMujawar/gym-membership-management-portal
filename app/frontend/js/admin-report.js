// admin-report.js - the one-page report (print it, or save it as PDF from the print dialog)

// Turns a list of rows into a table, or a placeholder message if the list is empty
function reportTable(rows, headers, rowHtml, emptyText) {
    if (rows.length === 0) return `<p class="empty-state">${emptyText}</p>`;
    return `<table><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr>${rows.map(rowHtml).join("")}</table>`;
}

async function loadReport() {
    if (!requireRole("admin")) return;
    const report = await apiRequest("/api/admin/report", "GET", null, true);

    document.getElementById("generatedAt").innerText =
        `Generated ${new Date(report.generated_at).toLocaleString("en-IN")} · Total revenue to date: ${formatMoney(report.summary.total_revenue)}`;
    renderStats(document.getElementById("stats"), report.summary);

    document.getElementById("revenueTable").innerHTML = reportTable(
        report.revenue_by_month, ["Month", "Payments", "Revenue"],
        r => `<tr><td>${escapeHtml(r.month)}</td><td>${r.payments}</td><td>${formatMoney(r.revenue)}</td></tr>`,
        "No payments yet.");

    document.getElementById("planTable").innerHTML = reportTable(
        report.plan_popularity, ["Plan", "Memberships", "Revenue"],
        r => `<tr><td>${escapeHtml(r.plan_name)}</td><td>${r.memberships}</td><td>${formatMoney(r.revenue)}</td></tr>`,
        "No plans.");

    document.getElementById("expiringTable").innerHTML = reportTable(
        report.expiring_soon, ["Member", "Contact", "Plan", "Ends", "Days Left"],
        r => `<tr><td>${escapeHtml(r.name)}</td><td>${escapeHtml(r.email)}<br><small>${escapeHtml(r.phone || "")}</small></td><td>${escapeHtml(r.plan_name)}</td><td>${formatDate(r.end_date)}</td><td>${r.days_left}</td></tr>`,
        "No memberships expiring soon.");

    document.getElementById("memberTable").innerHTML = reportTable(
        report.members, ["Name", "Email", "Joined", "Plan", "Status", "Ends"],
        r => `<tr><td>${escapeHtml(r.name)}</td><td>${escapeHtml(r.email)}</td><td>${formatDate(r.created_at)}</td><td>${escapeHtml(r.plan_name || "—")}</td><td>${r.membership_status ? statusBadge(r.membership_status) : "—"}</td><td>${formatDate(r.end_date)}</td></tr>`,
        "No members yet.");
}

loadReport();
