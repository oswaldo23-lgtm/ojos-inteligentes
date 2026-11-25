"""Estilo visual de Ojos inteligentes (inspirado en Apple)."""
from html import escape

import pandas as pd
import streamlit as st

MORADO_OSCURO = "#3B1E5F"
MORADO = "#6A2C91"
LAVANDA = "#EDE6F6"
ROJO = "#D62839"
VERDE = "#2E9E5B"
TEXTO = "#1F1430"
GRIS = "#6B6478"

CSS = """
<style>
html, body, [class*="css"], .stApp, button, input, select, textarea {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
               "Helvetica Neue", Arial, sans-serif !important;
  -webkit-font-smoothing: antialiased;
}
#MainMenu, footer, header [data-testid="stToolbar"] {visibility: hidden;}
.stApp {background: #F7F4FB;}
.block-container {padding-top: 2.5rem; max-width: 1180px;}
h1, h2, h3, h4 {letter-spacing: -0.02em; color: #3B1E5F;}

/* Pestañas como control segmentado */
.stTabs [role="tablist"] {
  background: #EDE6F6; border-radius: 12px; padding: 4px; gap: 4px; width: fit-content;
  border: none !important; box-shadow: none !important;
}
.stTabs [data-testid="stTab"], .stTabs [data-baseweb="tab"] {
  border-radius: 9px; padding: 6px 20px; height: auto; font-weight: 500; color: #551F78;
  border: none !important;
}
.stTabs [data-testid="stTab"][aria-selected="true"], .stTabs [data-baseweb="tab"][aria-selected="true"] {
  background: #6A2C91; color: #FFFFFF; font-weight: 600;
  box-shadow: 0 2px 8px rgba(106,44,145,0.35);
}
.stTabs [data-testid="stTab"]::after, .stTabs [role="tablist"]::after,
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {display: none !important;}

/* Botones en forma de píldora */
.stButton > button, .stDownloadButton > button {
  border-radius: 980px; padding: 0.5rem 1.4rem; min-height: 44px;
  font-weight: 500; border: none; background: #EDE6F6; color: #3B1E5F;
}
.stButton > button[kind="primary"] {background: linear-gradient(120deg, #6A2C91, #8E2C6E); color: #FFFFFF;}
.stButton > button[kind="primary"]:hover {background: linear-gradient(120deg, #551F78, #D62839); color: #FFFFFF;}
.stButton > button[kind="secondary"]:hover {background: #FDE8EA; color: #B01E2E;}

/* Indicadores como tarjetas */
[data-testid="stMetric"] {
  background: #FFFFFF; border-radius: 18px; padding: 18px 20px;
  border-top: 4px solid #6A2C91;
  box-shadow: 0 4px 16px rgba(59,30,95,0.08);
}
[data-testid="stMetricLabel"] {color: #6B6478;}
[data-testid="stMetricValue"] {font-weight: 700; letter-spacing: -0.02em; color: #3B1E5F;}

/* Contenedores con borde → tarjetas blancas (app.py les pone key="oi-card-...") */
[data-testid="stVerticalBlockBorderWrapper"], [class*="st-key-oi-card"] {
  background: #FFFFFF; border: none !important; border-radius: 20px;
  box-shadow: 0 4px 24px rgba(59,30,95,0.08);
}

/* Zona para subir fotos */
[data-testid="stFileUploaderDropzone"] {
  background: #FBF9FD; border: 1.5px dashed #A98BC6; border-radius: 18px;
}

/* Imágenes, tablas y barra lateral */
[data-testid="stImage"] img {border-radius: 14px;}
[data-testid="stDataFrame"] {border-radius: 14px; overflow: hidden;}
[data-testid="stSidebar"] {background: #EDE6F6; border-right: 1px solid #DCCFEA;}

.oi-card {background:#FFFFFF; border-radius:20px; padding:24px; box-shadow:0 4px 24px rgba(59,30,95,0.08); margin-bottom:16px;}
.oi-hero {background: linear-gradient(120deg, #3B1E5F 0%, #6A2C91 55%, #D62839 100%); border-radius:24px; padding:36px 40px; margin-bottom:24px;}
.oi-pill {display:inline-block; font-size:13px; font-weight:600; padding:4px 10px; border-radius:980px;}
.oi-nota {font-size:13px; color:#6B6478;}
</style>
"""

_PILDORAS = {
    "pendiente de revisión": ("Pendiente", "#EDE6F6", "#551F78"),
    "confirmada": ("Confirmada", "#FDE8EA", "#B01E2E"),
    "descartada": ("Descartada", "#F1EFF4", "#4A4458"),
}


def aplicar_estilos():
    """Llamar una vez, justo después de st.set_page_config."""
    st.markdown(CSS, unsafe_allow_html=True)


def encabezado():
    st.markdown(
        "<div class='oi-hero'>"
        "<div style='font-size:13px;font-weight:600;letter-spacing:.12em;color:#F6C9CE'>"
        "AUTOTRAFFIC · RETO 02</div>"
        "<h1 style='font-size:48px;font-weight:700;margin:6px 0 0;line-height:1.05;color:#FFFFFF'>"
        "Ojos inteligentes.</h1>"
        "<p style='font-size:21px;color:#E9DDF5;margin:6px 0 0'>"
        "Detección de riesgos en el carril confinado.</p></div>",
        unsafe_allow_html=True,
    )


def metricas(total, pendientes, confirmadas, aciertos=None, total_eval=30):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fotos analizadas", total)
    c2.metric("Alertas pendientes", pendientes)
    c3.metric("Confirmadas", confirmadas)
    c4.metric("Aciertos (30 fotos)", f"{aciertos} / {total_eval}" if aciertos is not None else "—")


def pildora_estado(estado):
    texto, fondo, color = _PILDORAS.get(estado, (estado, "#F2F2F7", "#3A3A3C"))
    return f"<span class='oi-pill' style='background:{fondo};color:{color}'>{escape(texto)}</span>"


def tarjeta_resultado(riesgo, evento, confianza=None, estado=None, alerta_id=None):
    punto = ROJO if riesgo else VERDE
    etiqueta = "Alerta" if riesgo else "Normal"
    titulo = "Riesgo detectado" if riesgo else "Sin riesgo"
    detalle = ""
    if riesgo:
        conf = f"{confianza:.0%}" if confianza is not None else "—"
        estado_html = pildora_estado(estado) if estado else ""
        id_html = (f"<div style='font-size:13px;color:{GRIS};margin-top:12px'>Alerta #{escape(alerta_id)}</div>"
                   if alerta_id else "")
        detalle = (
            "<div style='display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:20px'>"
            f"<div><div style='font-size:13px;color:{GRIS}'>Confianza</div>"
            f"<div style='font-size:20px;font-weight:600'>{conf}</div></div>"
            f"<div><div style='font-size:13px;color:{GRIS}'>Estado</div>"
            f"<div style='margin-top:4px'>{estado_html}</div></div></div>{id_html}"
        )
    st.markdown(
        f"<div class='oi-card'>"
        f"<div style='display:flex;align-items:center;gap:10px'>"
        f"<span style='width:12px;height:12px;border-radius:50%;background:{punto}'></span>"
        f"<span style='font-size:13px;color:{GRIS};text-transform:uppercase;letter-spacing:.06em;font-weight:600'>{etiqueta}</span></div>"
        f"<div style='font-size:34px;font-weight:700;letter-spacing:-0.02em;margin-top:8px;line-height:1.1;color:{TEXTO}'>{titulo}</div>"
        f"<div style='font-size:17px;color:{GRIS};margin-top:4px'>{escape(evento)}</div>"
        f"{detalle}</div>",
        unsafe_allow_html=True,
    )


def tabla_objetos(filas):
    """filas: lista de dicts con tipo, confianza (0–1), en_zona (bool), resultado (texto)."""
    if not filas:
        st.markdown("<p class='oi-nota'>Gemini no detectó vehículos ni peatones en esta foto.</p>",
                    unsafe_allow_html=True)
        return
    df = pd.DataFrame(filas)
    if "en_zona" in df:
        df["en_zona"] = df["en_zona"].map({True: "Sí", False: "No"})
    st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        column_config={
            "tipo": st.column_config.TextColumn("Tipo"),
            "confianza": st.column_config.ProgressColumn(
                "Confianza", min_value=0.0, max_value=1.0, format="%.2f"
            ),
            "en_zona": st.column_config.TextColumn("En zona"),
            "resultado": st.column_config.TextColumn("Resultado"),
        },
    )
