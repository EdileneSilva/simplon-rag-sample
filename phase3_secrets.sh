set -euo pipefail

PROJECT_ID="simplon-rag-263"
upsert_secret() {
  local name=$1
  local value=$2

  if gcloud secrets describe "${name}" --project="${PROJECT_ID}" &>/dev/null; then
    echo ">>> Nouvelle version pour le secret existant : ${name}"
    echo -n "${value}" | gcloud secrets versions add "${name}" \
      --data-file=- \
      --project="${PROJECT_ID}"
  else
    echo ">>> Création du secret : ${name}"
    echo -n "${value}" | gcloud secrets create "${name}" \
      --data-file=- \
      --replication-policy="automatic" \
      --project="${PROJECT_ID}"
  fi
}
upsert_secret "simplon-rag-mistral-api-key" "1tRZVZQbOaaIoGvvWwvHSmGlJF5sfLUz"

upsert_secret "simplon-rag-jwt-secret" "N3wtKbZgFpV6oyWbYGw5azDLqQRAUIsbEwhStcwZGEu"



echo ""
echo "✅ Secrets enregistrés dans Secret Manager :"
gcloud secrets list --project="${PROJECT_ID}" --filter="name:simplon-rag"
echo ""
echo "Prochaine étape : bash deploy/phase3_iam.sh"
