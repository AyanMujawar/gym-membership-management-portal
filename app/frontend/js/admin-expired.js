// admin-expired.js - members whose membership has lapsed (so staff can follow up for renewals)

async function loadExpired() {
    if (!requireRole("admin")) return;
    const expired = await apiRequest("/api/admin/expired", "GET", null, true);
    const table = document.getElementById("expiredTable");
    if (expired.length === 0) {
        table.innerHTML = `<p class="empty-state">No expired memberships.</p>`;
        return;
    }
    table.innerHTML = `
        <table>
            <tr><th>Member</th><th>Contact</th><th>Last Plan</th><th>Expired On</th><th>Days Ago</th></tr>
            ${expired.map(m => `
                <tr>
                    <td>${escapeHtml(m.name)}</td>
                    <td>${escapeHtml(m.email)}<br><small>${escapeHtml(m.phone || "")}</small></td>
                    <td>${escapeHtml(m.plan_name)}</td>
                    <td>${formatDate(m.end_date)}</td>
                    <td>${m.days_expired}</td>
                </tr>
            `).join("")}
        </table>
    `;
}

loadExpired();
