// admin-plans.js - manage membership plans

let plans = [];
let editingId = null;   // null = the form is adding a new plan

async function loadPlans() {
    if (!requireRole("admin")) return;
    plans = await apiRequest("/api/admin/plans", "GET", null, true);
    const table = document.getElementById("planTable");
    if (plans.length === 0) {
        table.innerHTML = `<p class="empty-state">No plans yet.</p>`;
        return;
    }
    table.innerHTML = `
        <table>
            <tr><th>Name</th><th>Duration</th><th>Price</th><th>Description</th><th>Visible</th><th></th></tr>
            ${plans.map(p => `
                <tr>
                    <td>${escapeHtml(p.name)}</td>
                    <td>${p.duration_days} days</td>
                    <td>${formatMoney(p.price)}</td>
                    <td>${escapeHtml(p.description || "")}</td>
                    <td>${p.is_active ? statusBadge("Active") : `<span class="badge">Hidden</span>`}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="editPlan(${p.plan_id})">Edit</button>
                        <button class="btn btn-sm btn-secondary" onclick="toggleActive(${p.plan_id})">${p.is_active ? "Hide" : "Show"}</button>
                        <button class="btn btn-sm btn-danger" onclick="deletePlan(${p.plan_id})">Delete</button>
                    </td>
                </tr>
            `).join("")}
        </table>
    `;
}

function showForm(title, plan) {
    editingId = plan ? plan.plan_id : null;
    document.getElementById("formTitle").innerText = title;
    document.getElementById("name").value = plan ? plan.name : "";
    document.getElementById("duration").value = plan ? plan.duration_days : "";
    document.getElementById("price").value = plan ? plan.price : "";
    document.getElementById("description").value = plan ? (plan.description || "") : "";
    document.getElementById("message").innerText = "";
    document.getElementById("planFormCard").style.display = "block";
}

function editPlan(planId) {
    showForm("Edit Plan", plans.find(p => p.plan_id === planId));
}

// Hiding a plan keeps its history but stops new members from buying it
async function toggleActive(planId) {
    const plan = plans.find(p => p.plan_id === planId);
    const result = await apiRequest(`/api/admin/plans/${planId}`, "PUT", { is_active: !plan.is_active }, true);
    if (result.error) alert(result.error);
    loadPlans();
}

async function deletePlan(planId) {
    const plan = plans.find(p => p.plan_id === planId);
    if (!confirm(`Delete the ${plan.name} plan?`)) return;
    const result = await apiRequest(`/api/admin/plans/${planId}`, "DELETE", null, true);
    if (result.error) alert(result.error);
    loadPlans();
}

document.getElementById("addBtn").addEventListener("click", () => showForm("Add Plan", null));
document.getElementById("cancelBtn").addEventListener("click", () => {
    document.getElementById("planFormCard").style.display = "none";
});

document.getElementById("planForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    const body = {
        name: document.getElementById("name").value,
        duration_days: document.getElementById("duration").value,
        price: document.getElementById("price").value,
        description: document.getElementById("description").value
    };
    const result = editingId
        ? await apiRequest(`/api/admin/plans/${editingId}`, "PUT", body, true)
        : await apiRequest("/api/admin/plans", "POST", body, true);

    if (result.message) {
        document.getElementById("planFormCard").style.display = "none";
        loadPlans();
    } else {
        document.getElementById("message").innerText = result.error || "Save failed";
    }
});

loadPlans();
