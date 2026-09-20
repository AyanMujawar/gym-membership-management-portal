// admin-members.js - list, search, add, edit and delete members

let members = [];
let editingId = null;   // null = the form is adding a new member

async function loadMembers() {
    if (!requireRole("admin")) return;
    const search = document.getElementById("search").value.trim();
    members = await apiRequest("/api/admin/members" + (search ? `?search=${encodeURIComponent(search)}` : ""), "GET", null, true);
    const table = document.getElementById("memberTable");
    if (members.length === 0) {
        table.innerHTML = `<p class="empty-state">No members found.</p>`;
        return;
    }
    table.innerHTML = `
        <table>
            <tr><th>Name</th><th>Contact</th><th>Plan</th><th>Status</th><th>Ends</th><th></th></tr>
            ${members.map(m => `
                <tr>
                    <td>${escapeHtml(m.name)}</td>
                    <td>${escapeHtml(m.email)}<br><small>${escapeHtml(m.phone || "")}</small></td>
                    <td>${escapeHtml(m.plan_name || "—")}</td>
                    <td>${m.membership_status ? statusBadge(m.membership_status) : "—"}</td>
                    <td>${formatDate(m.end_date)}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="editMember(${m.user_id})">Edit</button>
                        <button class="btn btn-sm btn-danger" onclick="deleteMember(${m.user_id})">Delete</button>
                    </td>
                </tr>
            `).join("")}
        </table>
    `;
}

function showForm(title, member) {
    editingId = member ? member.user_id : null;
    document.getElementById("formTitle").innerText = title;
    document.getElementById("name").value = member ? member.name : "";
    document.getElementById("email").value = member ? member.email : "";
    document.getElementById("phone").value = member ? (member.phone || "") : "";
    document.getElementById("address").value = member ? (member.address || "") : "";
    document.getElementById("password").value = "";
    document.getElementById("password").required = !member;
    document.getElementById("passwordLabel").innerText = member ? "New password (leave blank to keep current)" : "Password (min 6 characters)";
    document.getElementById("message").innerText = "";
    document.getElementById("memberFormCard").style.display = "block";
}

function editMember(userId) {
    showForm("Edit Member", members.find(m => m.user_id === userId));
}

async function deleteMember(userId) {
    const member = members.find(m => m.user_id === userId);
    if (!confirm(`Delete ${member.name}? Their memberships and payments will be deleted too.`)) return;
    const result = await apiRequest(`/api/admin/members/${userId}`, "DELETE", null, true);
    if (result.error) alert(result.error);
    loadMembers();
}

document.getElementById("addBtn").addEventListener("click", () => showForm("Add Member", null));
document.getElementById("cancelBtn").addEventListener("click", () => {
    document.getElementById("memberFormCard").style.display = "none";
});
document.getElementById("search").addEventListener("input", loadMembers);

document.getElementById("memberForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    const body = {
        name: document.getElementById("name").value,
        email: document.getElementById("email").value,
        phone: document.getElementById("phone").value,
        address: document.getElementById("address").value
    };
    const password = document.getElementById("password").value;
    if (password) body.password = password;

    const result = editingId
        ? await apiRequest(`/api/admin/members/${editingId}`, "PUT", body, true)
        : await apiRequest("/api/admin/members", "POST", body, true);

    if (result.message) {
        document.getElementById("memberFormCard").style.display = "none";
        loadMembers();
    } else {
        document.getElementById("message").innerText = result.error || "Save failed";
    }
});

loadMembers();
