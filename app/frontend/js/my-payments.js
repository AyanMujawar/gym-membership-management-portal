// my-payments.js - the member's payment history

async function loadPayments() {
    if (!requireRole("member")) return;
    const payments = await apiRequest("/api/me/payments", "GET", null, true);
    const table = document.getElementById("paymentTable");
    if (payments.length === 0) {
        table.innerHTML = `<p class="empty-state">No payments yet.</p>`;
        return;
    }
    table.innerHTML = `
        <table>
            <tr><th>Date</th><th>Plan</th><th>Amount</th><th>Method</th><th>Reference</th><th>Status</th></tr>
            ${payments.map(p => `
                <tr>
                    <td>${formatDate(p.payment_date)}</td>
                    <td>${escapeHtml(p.plan_name)}</td>
                    <td>${formatMoney(p.amount)}</td>
                    <td>${escapeHtml(p.method)}</td>
                    <td>${escapeHtml(p.txn_ref)}</td>
                    <td>${statusBadge(p.status)}</td>
                </tr>
            `).join("")}
        </table>
    `;
}

loadPayments();
