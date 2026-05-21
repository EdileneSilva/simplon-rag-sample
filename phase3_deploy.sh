set -euo pipefail

SA_NAME="simplon-rag-cloudrun"
PROJECT_ID="simplon-rag-263"
REGION="europe-west1"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
DB_INSTANCE_CONNECTION="${PROJECT_ID}:${REGION}:simplon-rag-db"
BUCKET_NAME="${PROJECT_ID}"
REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/simplon-rag"
GIT_SHA=$(git rev-parse --short HEAD)


echo ">>> Déploiement de l'API..."
gcloud run deploy simplon-rag-api \
  --image="${REPO}/api:${GIT_SHA}" \
  --region="${REGION}" \
  --port=8000 \
  --service-account="${SA_EMAIL}" \
  --platform=managed \
  \
  --add-cloudsql-instances="${DB_INSTANCE_CONNECTION}" \
  \
  --set-env-vars="\
APP_ENV=production,\
POSTGRES_HOST=/cloudsql/${DB_INSTANCE_CONNECTION},\
POSTGRES_PORT=5432,\
POSTGRES_DB=rag,\
POSTGRES_USER=rag_user,\
STORAGE_BUCKET=${BUCKET_NAME},\
CORS_ALLOWED_ORIGINS=https://simplon-rag-frontend-HASH-ew.a.run.app" \
  \
  --set-secrets="\
POSTGRES_PASSWORD=simplon-rag-db-password:latest,\
MISTRAL_API_KEY=simplon-rag-mistral-api-key:latest,\
JWT_SECRET_KEY=simplon-rag-jwt-secret:latest" \
  \
  --min-instances=0 \
  --max-instances=3 \
  --concurrency=80 \
  --timeout=300 \
  --memory=1Gi \
  --cpu=1 \
  \
  --allow-unauthenticated \
  --project="${PROJECT_ID}"

API_URL=$(gcloud run services describe simplon-rag-api \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(status.url)")

echo "   ✅ API déployée : ${API_URL}"


echo ">>> Déploiement du Frontend..."
gcloud run deploy simplon-rag-frontend \
  --image="${REPO}/frontend:${GIT_SHA}" \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --platform=managed \
  \
  --set-env-vars="\
RAG_API_URL=${API_URL},\
RAG_API_TIMEOUT_SECONDS=300" \
  \
  --min-instances=0 \
  --max-instances=2 \
  --concurrency=10 \
  --timeout=300 \
  --memory=512Mi \
  --cpu=1 \
  \
  --port=8501 \
  --port=8501 \
  --allow-unauthenticated \
  --project="${PROJECT_ID}"

FRONTEND_URL=$(gcloud run services describe simplon-rag-frontend \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(status.url)")

echo "   ✅ Frontend déployé : ${FRONTEND_URL}"

echo ">>> Mise à jour CORS avec l'URL du frontend..."
gcloud run services update simplon-rag-api \
  --region="${REGION}" \
  --update-env-vars="CORS_ALLOWED_ORIGINS=${FRONTEND_URL}" \
  --project="${PROJECT_ID}"

echo ""
echo "✅ Déploiement Phase 3 terminé"
echo ""
echo "   Frontend  → ${FRONTEND_URL}"
echo "   API       → ${API_URL} (accès authentifié uniquement)"
echo ""
echo "Commandes utiles :"
echo "  Logs API en temps réel :"
echo "    gcloud beta run services logs tail simplon-rag-api --region=${REGION}"
echo ""
echo "  Rollback si nécessaire :"
echo "    gcloud run revisions list --service=simplon-rag-api --region=${REGION}"
echo "    gcloud run services update-traffic simplon-rag-api --region=${REGION} --to-revisions=NOM_REVISION=100"
