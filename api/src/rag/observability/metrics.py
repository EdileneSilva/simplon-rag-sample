"""
Observabilité — Métriques Prometheus.

Deux catégories :
- Métriques HTTP RED (Request rate, Errors, Duration) : instrumentées dans le
  middleware, couvrent tous les endpoints.
- Métriques métier RAG : instrumentées dans les nœuds LangGraph (nodes.py).

Règle cardinalité :
  Les labels sont limités à des valeurs à faible cardinalité.
  JAMAIS de conversation_id, user_id, ou contenu textuel en label.

Endpoints normalisés (label `endpoint`) :
  health     → GET /api/v1/health
  messages   → POST /api/v1/conversations/{id}/messages
  conversations → POST /api/v1/conversations
  ingest     → POST /api/v1/documents/ingest-*
  eval       → POST /api/v1/eval/run
  other      → tout le reste
"""

from prometheus_client import Counter, Histogram

# ---------------------------------------------------------------------------
# Normalisation du chemin HTTP → label endpoint
# ---------------------------------------------------------------------------

def normalize_endpoint(path: str) -> str:
    """Réduit un path HTTP en une étiquette à faible cardinalité.

    Exemples :
      /api/v1/health                             → health
      /api/v1/conversations/abc-123/messages     → messages
      /api/v1/conversations                      → conversations
      /api/v1/documents/ingest-urls              → ingest
      /api/v1/documents/ingest                   → ingest
      /api/v1/eval/run                           → eval
      /metrics                                   → metrics
      (tout autre chose)                         → other
    """
    if path == "/api/v1/health":
        return "health"
    if path.endswith("/messages"):
        return "messages"
    if path == "/api/v1/conversations":
        return "conversations"
    if "/documents/ingest" in path:
        return "ingest"
    if path.startswith("/api/v1/eval"):
        return "eval"
    if path == "/metrics":
        return "metrics"
    return "other"


# ---------------------------------------------------------------------------
# Métriques HTTP — méthode RED
# ---------------------------------------------------------------------------

# R — Request rate : nombre de requêtes par endpoint × méthode × statut
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Nombre total de requêtes HTTP reçues",
    ["method", "endpoint", "status_code"],
)

# E — Errors : sous-ensemble de http_requests_total où status_code >= 400.
#   Pas de métrique séparée : on calcule dans Prometheus avec
#   http_requests_total{status_code=~"4..|5.."}

# D — Duration : distribution des temps de réponse par endpoint
#   Buckets différenciés :
#   - health/conversations/ingest : réponses rapides (< 5 s)
#   - messages : inclut les appels LLM Ollama (jusqu'à 120 s)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "Durée des requêtes HTTP en secondes",
    ["method", "endpoint"],
    # Buckets couvrant des réponses rapides (healthcheck ~10 ms)
    # jusqu'aux appels LLM lents (Ollama local peut prendre 120 s).
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
)

# ---------------------------------------------------------------------------
# Métriques métier RAG
# ---------------------------------------------------------------------------

# Distribution des décisions guard_route (in_scope / out_of_scope × catégorie)
# Permet de détecter une dérive de thématique ou un taux de rejet anormal.
RAG_GUARD_ROUTE_DECISIONS_TOTAL = Counter(
    "rag_guard_route_decisions_total",
    "Décisions du nœud guard_route",
    ["decision", "category"],
    # decision : in_scope | out_of_scope
    # category : admission | programme | vie_apprenant | chitchat | out_of_scope | …
)

# Taux d'escalade : si ce compteur croît rapidement par rapport à
# rag_guard_route_decisions_total{decision="in_scope"}, le modèle se dégrade.
RAG_ESCALATIONS_TOTAL = Counter(
    "rag_escalations_total",
    "Nombre de tours escaladés vers le support humain",
)

# Nombre de retries (décision rewrite dans evaluate)
RAG_RETRIES_TOTAL = Counter(
    "rag_retries_total",
    "Nombre de rewrites déclenchés par le nœud evaluate",
)

# Distribution des scores d'évaluation (0–10)
# Un glissement vers les scores bas (< 6) signale une dégradation qualité.
RAG_EVAL_SCORE = Histogram(
    "rag_eval_score",
    "Distribution des scores du nœud evaluate (0–10)",
    # Buckets = intervalles de score, pas des secondes
    buckets=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
)

# Nombre de chunks récupérés par requête de retrieval
RAG_CHUNKS_RETRIEVED = Histogram(
    "rag_chunks_retrieved_total",
    "Nombre de chunks récupérés par appel au retriever pgvector",
    buckets=[0, 1, 2, 3, 5, 8, 10, 15, 20],
)

# Latence par nœud du graphe LangGraph
# Le label `node` a une cardinalité fixe et faible :
# guard_route | retrieve | generate | evaluate | escalate | save_turn
RAG_NODE_DURATION_SECONDS = Histogram(
    "rag_node_duration_seconds",
    "Durée d'exécution de chaque nœud LangGraph en secondes",
    ["node"],
    buckets=[0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
)