// plans.js - shows the available membership plans on the home page

// Where a plan's button leads depends on who is looking at it
function planButton(plan) {
    const role = getRole();
    if (role === "admin") return "";
    const target = role === "member" ? `subscribe.html?plan=${plan.plan_id}` : "login.html";
    const label = role === "member" ? "Choose Plan" : "Login to Join";
    return `<a class="btn" href="${target}">${label}</a>`;
}

async function loadPlans() {
    const plans = await apiRequest("/api/plans");
    const grid = document.getElementById("planGrid");
    if (!Array.isArray(plans) || plans.length === 0) {
        grid.innerHTML = `<p class="empty-state">No plans available right now.</p>`;
        return;
    }
    grid.innerHTML = plans.map(plan => `
        <div class="plan-card">
            <h3>${escapeHtml(plan.name)}</h3>
            <div class="price">${formatMoney(plan.price)}</div>
            <div class="duration">${plan.duration_days} days</div>
            <p class="desc">${escapeHtml(plan.description)}</p>
            ${planButton(plan)}
        </div>
    `).join("");
}

loadPlans();
