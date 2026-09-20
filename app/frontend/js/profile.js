// profile.js - view and update the member's own profile

async function loadProfile() {
    if (!requireRole("member")) return;
    const me = await apiRequest("/api/me", "GET", null, true);
    document.getElementById("email").value = me.email;
    document.getElementById("name").value = me.name;
    document.getElementById("phone").value = me.phone || "";
    document.getElementById("address").value = me.address || "";
}

document.getElementById("profileForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    const body = {
        name: document.getElementById("name").value,
        phone: document.getElementById("phone").value,
        address: document.getElementById("address").value
    };
    const newPassword = document.getElementById("newPassword").value;
    if (newPassword) {
        body.new_password = newPassword;
        body.current_password = document.getElementById("currentPassword").value;
    }
    const result = await apiRequest("/api/me", "PUT", body, true);

    const message = document.getElementById("message");
    if (result.message) {
        localStorage.setItem("name", body.name);
        message.className = "message ok";
        message.innerText = "Profile updated";
        document.getElementById("currentPassword").value = "";
        document.getElementById("newPassword").value = "";
    } else {
        message.className = "message";
        message.innerText = result.error || "Update failed";
    }
});

loadProfile();
