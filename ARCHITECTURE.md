# Architecture — Gym Membership Portal

Diagrams and data flows: the DevOps pipeline, the running containers, the database, and the key request flows.

---

## 1. Deployment Pipeline (the DevOps part)

```mermaid
flowchart TD
    A[Developer's Laptop] -->|git push| B[GitHub Repository]
    B --> C{Terraform}
    C -->|creates| D[AWS EC2 Instance<br/>+ Security Group]
    D --> E{Ansible}
    E -->|installs Docker, git<br/>clones repo, deploys| F[Docker Compose on the VM]
    F --> G[frontend container<br/>nginx, port 80]
    F --> H[backend container<br/>Flask, port 5000]
    F --> I[db container<br/>MySQL, internal only]
    G <--> H
    H <--> I
    J[Browser] -->|http://VM public IP| G
    J -->|http://VM public IP:5000| H
```

Code goes to GitHub → Terraform creates the server → Ansible configures it and deploys the app → Docker Compose runs the 3 containers → the browser talks to the frontend and backend directly.

---

## 2. Container & Volume Layout

```mermaid
flowchart LR
    Browser((Browser))

    subgraph VM["AWS EC2 Instance"]
        FE["frontend container<br/>nginx"]
        BE["backend container<br/>Flask"]
        DB["db container<br/>MySQL"]
        VOL[("mysql_data volume")]

        FE -->|"fetch() calls"| BE
        BE -->|SQL queries| DB
        DB -.->|reads/writes tables| VOL
    end

    Browser -->|":80"| FE
    Browser -->|":5000"| BE
```

The `mysql_data` volume lives outside the container's own filesystem, so `docker compose down` then `up` keeps all members, memberships and payments. Only `docker compose down -v` deletes it (and re-seeds the demo data on the next start).

---

## 3. Database Schema (ER Diagram)

```mermaid
erDiagram
    USERS ||--o{ MEMBERSHIPS : holds
    MEMBERSHIP_PLANS ||--o{ MEMBERSHIPS : "is the plan of"
    MEMBERSHIPS ||--o{ PAYMENTS : "is paid by"
    USERS ||--o{ PAYMENTS : makes

    ADMINS {
        int admin_id PK
        string name
        string email
        string password
    }
    USERS {
        int user_id PK
        string name
        string email
        string password
        string phone
        string address
        datetime created_at
    }
    MEMBERSHIP_PLANS {
        int plan_id PK
        string name
        int duration_days
        decimal price
        string description
        bool is_active
    }
    MEMBERSHIPS {
        int membership_id PK
        int user_id FK
        int plan_id FK
        date start_date
        date end_date
        enum status
        datetime created_at
    }
    PAYMENTS {
        int payment_id PK
        int membership_id FK
        int user_id FK
        decimal amount
        enum method
        enum status
        string txn_ref
        datetime payment_date
    }
```

`ADMINS` stands alone: admins are seeded in `schema.sql` and never relate to member data.

---

## 4. Membership Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Pending: member picks a plan and pays (simulated)
    Pending --> Active: admin approves (start/end dates set)
    Pending --> Rejected: admin rejects (payment marked Refunded)
    Active --> Expired: end date passes
    Expired --> [*]
```

- **Renewing** creates a brand-new membership row, so history is kept. If the member is still active, the renewal starts the day after the current one ends — no paid days are lost.
- **Expiry** has no background job: before any read that shows membership status, the backend runs `UPDATE memberships SET status='Expired' WHERE status='Active' AND end_date < CURDATE()`.
- A member can have only one Pending request at a time.

---

## 5. Request Flow — Login & Authorization

```mermaid
sequenceDiagram
    participant B as Browser
    participant F as Flask API
    participant D as MySQL

    B->>F: POST /api/users/login {email, password}
    F->>D: SELECT * FROM users WHERE email=?
    D-->>F: user row (password is a hash)
    F->>F: check_password_hash(stored_hash, given_password)
    F->>F: build JWT {user_id, role: "member", exp}
    F-->>B: {token, name}
    Note over B: token saved in localStorage

    B->>F: GET /api/me/membership<br/>Authorization: Bearer <token>
    F->>F: decode token, check role, take user_id from it (NOT from the URL)
    F->>D: SELECT ... WHERE user_id = (from token)
    D-->>F: only this member's memberships
    F-->>B: JSON response
```

The server never trusts a client-supplied ID for "whose data is this" — only the identity verified through the token's signature.

---

## 6. Request Flow — Buying a Plan and Getting Approved

```mermaid
sequenceDiagram
    participant M as Member (Browser)
    participant F as Flask API
    participant D as MySQL
    participant A as Admin (Browser)

    M->>F: POST /api/memberships {plan_id, method} + JWT
    F->>D: check plan is active, no other Pending request
    F->>D: INSERT membership (Pending) + INSERT payment (Paid) — one transaction
    F-->>M: {txn_ref, "waiting for approval"}

    A->>F: GET /api/admin/memberships?status=Pending + JWT
    F-->>A: pending list
    A->>F: PUT /api/admin/memberships/id {status: "Approved"} + JWT
    F->>D: set start_date, end_date, status = Active
    F-->>A: {message}
    M->>F: GET /api/me/membership
    F-->>M: active membership, days left
```

---

## 7. Security Model Summary

| Boundary | Enforced by |
|---|---|
| Must be logged in | `auth_required` decorator checks a valid JWT on every protected route |
| Must be the right role (member vs admin) | The same decorator compares `payload["role"]` and returns 403 otherwise |
| Members only see their own data | Routes use the `user_id` from the verified token, never one from the request |
| Admins can't be self-registered | There is no admin registration endpoint — admins exist only in the seed data |
| Passwords | Hashed with Werkzeug's `generate_password_hash`, never stored or compared in plain text |
| SQL injection | Every query uses parameterized placeholders (`%s`) |
| XSS | The frontend escapes all data before inserting it into the page (`escapeHtml`) |
| Payments | Simulated — no card data is ever collected or stored |
