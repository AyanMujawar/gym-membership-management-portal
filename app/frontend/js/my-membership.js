// my-membership.js - shows the member's current membership, any pending request, and history

async function loadMembership() {
    if (!requireRole("member")) return;
    const data = await apiRequest("/api/me/membership", "GET", null, true);

    if (data.pending) {
        document.getElementById("pendingNotice").innerHTML =
            `<div class="notice">Your <strong>${escapeHtml(data.pending.plan_name)}</strong> request is paid and waiting for admin approval.</div>`;
    }

    const card = document.getElementById("currentCard");
    const shown = data.active || data.latest_expired;
    if (!shown) {
        card.innerHTML = `<p class="empty-state">You don't have a membership yet.</p><a class="btn" href="index.html">Browse Plans</a>`;
    } else {
        const isActive = shown.status === "Active";
        const daysText = isActive ? `${shown.days_left} day${shown.days_left === 1 ? "" : "s"} left` : "Expired";
        const renewBtn = data.pending ? "" :
            `<a class="btn" href="subscribe.html?plan=${shown.plan_id}">${isActive ? "Renew Early" : "Renew Membership"}</a>
             <a class="btn btn-secondary" href="index.html">Choose a Different Plan</a>`;
        card.innerHTML = `
            <h3>Current Membership ${statusBadge(shown.status)}</h3>
            <div class="info-row"><span>Plan</span><span>${escapeHtml(shown.plan_name)}</span></div>
            <div class="info-row"><span>Started</span><span>${formatDate(shown.start_date)}</span></div>
            <div class="info-row"><span>Ends</span><span>${formatDate(shown.end_date)}</span></div>
            <div class="info-row"><span>Time left</span><span>${daysText}</span></div>
            ${renewBtn}
        `;
    }

    const history = document.getElementById("historyTable");
    if (data.history.length === 0) {
        history.innerHTML = `<p class="empty-state">No memberships yet.</p>`;
        return;
    }
    history.innerHTML = `
        <table>
            <tr><th>Plan</th><th>Price</th><th>Start</th><th>End</th><th>Status</th></tr>
            ${data.history.map(m => `
                <tr>
                    <td>${escapeHtml(m.plan_name)}</td>
                    <td>${formatMoney(m.price)}</td>
                    <td>${formatDate(m.start_date)}</td>
                    <td>${formatDate(m.end_date)}</td>
                    <td>${statusBadge(m.status)}</td>
                </tr>
            `).join("")}
        </table>
    `;
}

loadMembership();
