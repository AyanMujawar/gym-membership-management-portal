#!/usr/bin/env bash
# Deploys the Gym Portal to whichever Kubernetes cluster kubectl currently points at.
#   BACKEND_IMAGE=... FRONTEND_IMAGE=... scripts/k8s-deploy.sh
# Secrets are generated here and kept only in the cluster; nothing secret is stored in the repo.
set -euo pipefail
cd "$(dirname "$0")/.."

NS=gym-portal
BACKEND_IMAGE="${BACKEND_IMAGE:-gym-portal-backend:local}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-gym-portal-frontend:local}"

kubectl apply -f k8s/namespace.yaml

# Create the secrets once; re-running the script keeps the existing ones (and so the database keeps working)
if ! kubectl -n "$NS" get secret gym-secrets >/dev/null 2>&1; then
  kubectl -n "$NS" create secret generic gym-secrets \
    --from-literal=DB_PASSWORD="$(openssl rand -hex 16)" \
    --from-literal=SECRET_KEY="$(openssl rand -hex 32)"
fi

# The schema and demo data MySQL loads on its first start
kubectl -n "$NS" create configmap gym-schema --from-file=schema.sql=app/backend/schema.sql \
  --dry-run=client -o yaml | kubectl apply -f -

# Render the manifests, point them at the images to run, and apply
kubectl kustomize k8s \
  | sed -e "s#image: gym-portal-backend:local#image: ${BACKEND_IMAGE}#" \
        -e "s#image: gym-portal-frontend:local#image: ${FRONTEND_IMAGE}#" \
  | kubectl apply -f -

for deployment in mysql backend frontend; do
  kubectl -n "$NS" rollout status "deployment/${deployment}" --timeout=300s
done
echo "Deployed. Reach it with: kubectl -n $NS port-forward svc/frontend 8081:80"
