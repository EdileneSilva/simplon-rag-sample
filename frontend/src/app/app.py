import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import streamlit as st
from pythonjsonlogger.json import JsonFormatter

from app.api_client import create_conversation, send_message
from app.config import API_BASE_URL

# ---------------------------------------------------------------------------
# Logging JSON structuré — frontend
# Appelé une fois au démarrage du module (Streamlit ré-exécute le script
# à chaque interaction, mais l'état du module est conservé dans le process).
# ---------------------------------------------------------------------------

def _setup_frontend_logging() -> logging.Logger:
    """Configure un logger JSON structuré pour le frontend Streamlit.

    Règles RGPD : le contenu des messages utilisateur et des réponses
    de l'API ne doit JAMAIS apparaître dans les logs.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger",
            },
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    frontend_logger = logging.getLogger("simplon.frontend")
    if not frontend_logger.handlers:          # éviter les doublons lors des reruns Streamlit
        frontend_logger.addHandler(handler)
        frontend_logger.setLevel(logging.INFO)
        frontend_logger.propagate = False     # ne pas remonter au root logger uvicorn-free
    return frontend_logger


_log = _setup_frontend_logging()

# ---------------------------------------------------------------------------
# Simplon brand palette
# ---------------------------------------------------------------------------

SIMPLON_RED = "#CE0033"
SIMPLON_CORAL = "#F26F5C"
SIMPLON_TEAL = "#123744"
SIMPLON_CREAM = "#FFF1EE"

ASSETS_DIR = Path(__file__).parent / "assets"
LOGO_SVG = (ASSETS_DIR / "simplon-logo.svg").read_text(encoding="utf-8")

# --- Page config (must be first Streamlit call) ---
st.set_page_config(
    page_title="Simplon — Assistant IA",
    page_icon="🎓",
    layout="centered",
)

# --- Brand CSS ---
_USER_BUBBLE = "[data-testid=\"stChatMessage\"]:has([data-testid=\"chatAvatarIcon-user\"]) [data-testid=\"stChatMessageContent\"]"  # noqa: E501
_ASST_BUBBLE = "[data-testid=\"stChatMessage\"]:has([data-testid=\"chatAvatarIcon-assistant\"]) [data-testid=\"stChatMessageContent\"]"  # noqa: E501
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"], [data-testid="stChatMessageContent"] p,
    [data-testid="stChatMessageContent"] li, .stMarkdown p, .stMarkdown li,
    [data-testid="stChatInput"] textarea {{
        font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
    }}

    {_USER_BUBBLE} {{
        background-color: {SIMPLON_RED} !important;
        color: #FFFFFF !important;
        border-radius: 14px;
        padding: 0.75rem 1rem;
    }}

    {_ASST_BUBBLE} {{
        background-color: {SIMPLON_CREAM} !important;
        color: {SIMPLON_TEAL} !important;
        border-radius: 14px;
        padding: 0.75rem 1rem;
        border-left: 3px solid {SIMPLON_CORAL};
    }}

    [data-testid="stExpander"] summary {{
        color: {SIMPLON_TEAL} !important;
    }}
    [data-testid="stExpander"] summary:hover {{
        color: {SIMPLON_CORAL} !important;
    }}

    [data-testid="stChatInput"] textarea:focus {{
        border-color: {SIMPLON_RED} !important;
        box-shadow: 0 0 0 1px {SIMPLON_RED} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Header ---
st.markdown(
    f"""
    <div style="display:flex; flex-direction:column; align-items:center;
                gap:0.4rem; padding: 1.25rem 0 0.25rem 0;">
        <div style="width:220px;">{LOGO_SVG}</div>
        <span style="font-family:'Inter',sans-serif; font-weight:500;
                     font-size:1rem; color:{SIMPLON_TEAL}; letter-spacing:0.02em;">
            Assistant IA — Support apprenants
        </span>
    </div>
    <hr style="border:none; border-top:2px solid {SIMPLON_CORAL};
               margin: 1rem 0 1.5rem 0;">
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session initialisation
# ---------------------------------------------------------------------------

if "conversation_id" not in st.session_state:
    try:
        conv_id = create_conversation(API_BASE_URL)
        st.session_state.conversation_id = conv_id
        st.session_state.messages = []
        _log.info(
            "conversation.created",
            extra={"conversation_id": str(conv_id), "api_base_url": API_BASE_URL},
        )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        _log.error("api.unreachable", extra={"api_base_url": API_BASE_URL})
        st.error("Impossible de joindre l'API. Vérifiez que le serveur FastAPI est démarré.")
        st.stop()
    except httpx.ReadTimeout:
        _log.error("api.read_timeout", extra={"api_base_url": API_BASE_URL})
        st.error("L'API a mis trop de temps à répondre. Rafraîchissez la page pour réessayer.")
        st.stop()
    except Exception:
        _log.exception("conversation.creation_failed", extra={"api_base_url": API_BASE_URL})
        st.error("Erreur inattendue lors de la création de la conversation.")
        st.stop()

# --- Render conversation history ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("sources"):
            with st.expander(f"📎 Sources ({len(msg['sources'])})"):
                for chunk_id in msg["sources"]:
                    st.caption(f"Chunk : {chunk_id}")

# ---------------------------------------------------------------------------
# Handle new user input
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Posez votre question…"):
    conv_id = st.session_state.conversation_id
    st.session_state.messages.append({"role": "user", "content": prompt, "sources": []})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        content: str = ""
        sources: list[str] = []

        with st.spinner("Génération en cours…"):
            t0 = time.perf_counter()
            try:
                response = send_message(API_BASE_URL, conv_id, prompt)
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)

                content = response["content"] or "Aucune réponse reçue."
                sources = response.get("sources", [])

                # Log de résultat — SANS le contenu du message ni de la réponse
                _log.info(
                    "message.sent",
                    extra={
                        "conversation_id": str(conv_id),
                        "sources_count": len(sources),
                        "latency_ms": latency_ms,
                    },
                )

            except httpx.HTTPStatusError as e:
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                _log.error(
                    "api.http_error",
                    extra={
                        "conversation_id": str(conv_id),
                        "status_code": e.response.status_code,
                        "latency_ms": latency_ms,
                    },
                )
                st.error(f"Erreur API : {e.response.status_code}")
                st.stop()
            except httpx.ReadTimeout:
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                _log.error(
                    "api.read_timeout",
                    extra={"conversation_id": str(conv_id), "latency_ms": latency_ms},
                )
                st.error(
                    "L'API n'a pas répondu dans le délai imparti. La requête est "
                    "peut-être encore en cours côté serveur — réessayez dans un "
                    "instant ou augmentez `RAG_API_TIMEOUT_SECONDS`."
                )
                st.stop()
            except (httpx.ConnectError, httpx.ConnectTimeout):
                _log.error(
                    "api.unreachable",
                    extra={"conversation_id": str(conv_id), "api_base_url": API_BASE_URL},
                )
                st.error("Impossible de joindre l'API (connexion refusée).")
                st.stop()
            except Exception:
                _log.exception(
                    "api.unexpected_error",
                    extra={"conversation_id": str(conv_id)},
                )
                st.error("Erreur inattendue lors de l'appel à l'API.")
                st.stop()

        st.markdown(content)
        if sources:
            with st.expander(f"📎 Sources ({len(sources)})"):
                for chunk_id in sources:
                    st.caption(f"Chunk : {chunk_id}")

    st.session_state.messages.append(
        {"role": "assistant", "content": content, "sources": sources}
    )