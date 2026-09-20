# How To Run This Project

A copy-paste reference for running the Gym Membership Portal — locally, and on AWS. For diagrams, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Prerequisites

| Tool | Needed for | Install |
|---|---|---|
| Docker Desktop | Running locally | `winget install --id Docker.DockerDesktop -e` (then start it and wait for the engine) |
| Terraform | Creating the AWS server | `winget install --id Hashicorp.Terraform -e --source winget` |
| AWS CLI | Talking to your AWS account | `winget install --id Amazon.AWSCLI -e` |
| WSL (Ubuntu) + Ansible | Configuring/deploying to the server | `wsl --install -d Ubuntu`, then inside it: `sudo apt update && sudo apt install -y ansible` |
| Git | Version control | Usually already installed |

**Ansible + Windows:** Ansible cannot run directly on Windows as a control machine — run every `ansible` / `ansible-playbook` command inside WSL. Terraform and the AWS CLI run fine natively on Windows.

---

## A. Run It Locally (Docker Compose)

```bash
docker compose up --build -d
```

Open:
- `http://localhost` — the app
- `http://localhost:5000/api/health` — backend health check

Log in with the demo accounts listed in [README.md](README.md).

```bash
docker compose ps                        # status
docker compose logs backend --tail 50    # backend logs
docker compose down                      # stop, keeping data
docker compose down -v                   # full reset: wipes the database and re-seeds it
docker compose up -d --build backend frontend   # rebuild after editing code
```

---

## B. Deploy To AWS From Scratch

### 1. One-time AWS account setup
1. In the AWS console, create an IAM user (e.g. `gym-deployer`) with the `AmazonEC2FullAccess` policy — **not root credentials**
2. Create an access key for that user (Security credentials tab → Create access key → "Command Line Interface")
3. Configure your machine (paste the keys here, never into chat or a file in the repo):
   ```bash
   aws configure
   # Default region name: ap-south-1
   # Default output format: json
   ```
4. Confirm it worked:
   ```bash
   aws sts get-caller-identity
   ```

### 2. Push the project to your own GitHub repo
Ansible clones the app from GitHub onto the server, so the code must be there. Then set `repo_url` in `ansible/deploy.yml` to your repo's URL.

### 3. Generate an SSH key (one-time)
```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/gym-portal-key -N "" -C "ubuntu"
```
Terraform registers the public half with AWS automatically.

### 4. Create the server with Terraform
```bash
cd terraform
terraform init
terraform plan
terraform apply
terraform output public_ip
```

### 5. Configure and deploy with Ansible (from WSL)
```bash
wsl -d Ubuntu
```
Inside WSL:
```bash
cd "/mnt/c/<path to project>/ansible"

# copy the SSH key into WSL's own filesystem with the strict permissions SSH requires
cp /mnt/c/Users/<you>/.ssh/gym-portal-key ~/.ssh_gym_key
chmod 600 ~/.ssh_gym_key
```
Edit `inventory.ini`, replacing `<EC2_PUBLIC_IP>` with the IP from step 4, then:
```bash
ansible all -i inventory.ini -m ping         # should return "pong"
ansible-playbook -i inventory.ini deploy.yml
```

### 6. Verify it's live
```bash
curl http://<EC2_PUBLIC_IP>/
curl http://<EC2_PUBLIC_IP>:5000/api/health
```
Or open `http://<EC2_PUBLIC_IP>` in a browser.

---

## C. Redeploy After A Code Change

```bash
git add .
git commit -m "your change"
git push
```
Then, from WSL: `ansible-playbook -i inventory.ini deploy.yml`. This pulls the latest code and re-runs `docker compose up --build -d` — safe to run repeatedly.

---

## D. Checking On The Live Server

```bash
ssh -i ~/.ssh/gym-portal-key ubuntu@<EC2_PUBLIC_IP>
cd gym-membership-management-portal
docker compose ps
docker compose logs backend --tail 50
```

---

## E. Tearing Down (to stop AWS charges)

```bash
cd terraform
terraform destroy
```
Type `yes` to confirm. Running `terraform apply` again later gives a new public IP — update `inventory.ini` and re-run Ansible. After the project is done, delete the IAM user and its access key too.

---

## Quick Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `port is already allocated` on `docker compose up`, and every feature fails | Port 80 or 5000 is already used, so a container never started | `netstat -ano \| findstr :5000` to find the process, free the port, run `docker compose up --build -d` again |
| SSH `Permission denied (publickey)` | Wrong key path, or key permissions too open (common on `/mnt/c` paths in WSL) | Copy the key into WSL's own filesystem and `chmod 600` it |
| `terraform apply` fails with `InvalidParameterCombination... Free Tier` | Instance type isn't free-tier eligible on this account/region | `aws ec2 describe-instance-types --filters "Name=free-tier-eligible,Values=true" --region ap-south-1`, then set `instance_type` in `terraform/variables.tf` |
| Site loads but plans/login fail | Frontend can't reach the backend | Access via the IP or `localhost`, not `file://`; check port 5000 is open in the security group |
| Fresh deploy has only the demo data | Expected — a new server gets a fresh database seeded from `schema.sql` | Register members or add data as admin |
