// subscribe.js - confirm a plan and make the (simulated) payment. Used for both joining and renewing.

const planId = Number(new URLSearchParams(window.location.search).get("plan"));
let selectedPlan = null;

async function loadPlan() {
    if (!requireRole("member")) return;
    const plans = await apiRequest("/api/plans");
    selectedPlan = Array.isArray(plans) ? plans.find(p => p.plan_id === planId) : null;
    const summary = document.getElementById("planSummary");
    if (!selectedPlan) {
        summary.innerHTML = `<p class="message">That plan isn't available. <a href="index.html">Back to plans</a></p>`;
        document.getElementById("payForm").style.display = "none";
        return;
    }
    summary.innerHTML = `
        <div class="info-row"><span>Plan</span><span>${escapeHtml(selectedPlan.name)}</span></div>
        <div class="info-row"><span>Duration</span><span>${selectedPlan.duration_days} days</span></div>
        <div class="info-row"><span>Amount</span><span><strong>${formatMoney(selectedPlan.price)}</strong></span></div>
        <br>`;
    document.getElementById("payBtn").innerText = `Pay ${formatMoney(selectedPlan.price)}`;
}

document.getElementById("payForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    const message = document.getElementById("message");
    const button = document.getElementById("payBtn");
    button.disabled = true;
    const result = await apiRequest("/api/memberships", "POST",
        { plan_id: selectedPlan.plan_id, method: document.getElementById("method").value }, true);

    if (result.membership_id) {
        message.className = "message ok";
        message.innerText = `${result.message} Ref: ${result.txn_ref}`;
        setTimeout(() => { window.location.href = "my-membership.html"; }, 1800);
    } else {
        message.className = "message";
        message.innerText = result.error || "Payment failed";
        button.disabled = false;
    }
});

loadPlan();
