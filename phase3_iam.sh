
set -euo pipefail

PROJECT_ID="simplon-rag-263"
REGION="europe-west1"
SA_NAME="simplon-rag-cloudrun"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET_NAME="${PROJECT_ID}"
DB_INSTANCE_NAME="simplon-rag-db"

echo ">>> Création du service account..."
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="Simplon RAG — Cloud Run runtime" \
  --description="Service account utilisé par les services Cloud Run API et Frontend" \
  --project="${PROJECT_ID}" 2>/dev/null || echo "Service account déjà existant, on continue."

echo ">>> Droit Cloud SQL Client..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudsql.client" \
  --condition=None


echo ">>> Droit lecture objets GCS (objectViewer)..."
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectViewer"

echo ">>> Droit écriture objets GCS (objectCreator)..."
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectCreator"


echo ">>> Droits Secret Manager (secretAccessor par secret)..."
for SECRET in \
  "simplon-rag-mistral-api-key" \
  "simplon-rag-jwt-secret" \
  "simplon-rag-db-password"
do
  gcloud secrets add-iam-policy-binding "${SECRET}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="${PROJECT_ID}"
  echo "   ✓ ${SECRET}"
done

echo ">>> Droit Cloud Logging..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/logging.logWriter" \
  --condition=None

echo ""
echo "✅ Service account configuré : ${SA_EMAIL}"
echo "   Droits accordés :"
echo "   - cloudsql.client         (projet)"
echo "   - storage.objectViewer    (bucket: ${BUCKET_NAME})"
echo "   - storage.objectCreator   (bucket: ${BUCKET_NAME})"
echo "   - secretmanager.secretAccessor (par secret)"
echo "   - logging.logWriter       (projet)"
echo ""

