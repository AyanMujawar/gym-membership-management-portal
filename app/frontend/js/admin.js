// admin.js - dashboard numbers and the queue of memberships waiting for approval

async function loadDashboard() {
    if (!requireRole("admin")) return;
    const stats = await apiRequest("/api/admin/dashboard", "GET", null, true);
    renderStats(document.getElementById("stats"), stats);
    await loadPending();
}

async function loadPending() {
    const pending = await apiRequest("/api/admin/memberships?status=Pending", "GET", null, true);
    const table = document.getElementById("pendingTable");
    if (pending.length === 0) {
        table.innerHTML = `<p class="empty-state">Nothing waiting for approval.</p>`;
        return;
    }
    table.innerHTML = `
        <table>
            <tr><th>Member</th><th>Plan</th><th>Paid</th><th>Requested</th><th></th></tr>
            ${pending.map(m => `
                <tr>
                    <td>${escapeHtml(m.user_name)}<br><small>${escapeHtml(m.email)}</small></td>
                    <td>${escapeHtml(m.plan_name)}</td>
                    <td>${formatMoney(m.price)}</td>
                    <td>${formatDate(m.created_at)}</td>
                    <td>
                        <button class="btn btn-sm btn-approve" onclick="decide(${m.membership_id}, 'Approved')">Approve</button>
                        <button class="btn btn-sm btn-danger" onclick="decide(${m.membership_id}, 'Rejected')">Reject</button>
                    </td>
                </tr>
            `).join("")}
        </table>
    `;
}

// Approve starts the membership; reject refunds the payment
async function decide(membershipId, status) {
    if (status === "Rejected" && !confirm("Reject this request? The payment will be marked as refunded.")) return;
    const result = await apiRequest(`/api/admin/memberships/${membershipId}`, "PUT", { status }, true);
    if (result.error) alert(result.error);
    loadDashboard();
}

loadDashboard();
