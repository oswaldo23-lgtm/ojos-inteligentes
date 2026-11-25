"""Ojos inteligentes · AutoTraffic — interfaz en Streamlit.

Ejecutar:  python -m streamlit run app.py
"""
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

import detector as det
import estilos
import evaluar

st.set_page_config(page_title="Ojos inteligentes", layout="wide")
estilos.aplicar_estilos()

# Los resultados se guardan en la sesión: así sobreviven cuando Streamlit vuelve a
# ejecutar el archivo (al presionar Confirmar, cambiar la vista, etc.).
st.session_state.setdefault("resultados", [])
st.session_state.setdefault("errores", [])
st.session_state.setdefault("analizadas", set())

TEXTO_TOAST = {
    "confirmada": "Alerta confirmada",
    "descartada": "Alerta descartada",
    "pendiente de revisión": "Alerta marcada como pendiente",
}


def cambiar_estado(id_alerta: str, estado: str) -> None:
    """Callback de los botones: corre antes de volver a dibujar la página."""
    det.cambiar_estado(id_alerta, estado)
    st.toast(TEXTO_TOAST.get(estado, "Estado actualizado"))


def resultado_objeto(o: dict) -> str:
    """Por qué un objeto alerta o no (mismo orden que usa marcar())."""
    if o["invade"]:
        return "Alerta"
    if o["tipo"] == "autobus":
        return "Autorizado"
    if not o["en_zona"]:
        return "Fuera de zona"
    if o["tipo"] in det.TIPOS_RIESGO:
        return "Baja confianza"
    return "No cuenta como riesgo"


# ---------------- Barra lateral ----------------
with st.sidebar:
    st.markdown("**AJUSTES**")
    umbral = st.slider("Confianza mínima", 0.0, 1.0, 0.5, 0.05,
                       help="Solo se alerta cuando la IA está al menos así de segura.")
    with st.expander("Opciones avanzadas"):
        modelo = st.text_input("Modelo de Gemini", value=det.MODELO)
    st.caption("Riesgo = auto, moto, camioneta, camión, bicicleta o peatón con su punto de apoyo "
               "dentro de la zona. El autobús autorizado no genera alerta.")

# ---------------- Encabezado e indicadores ----------------
alertas = det.leer_alertas()
cache = evaluar.cargar_cache()
pendientes = sum(a["estado"] == det.ESTADOS[0] for a in alertas)
confirmadas = sum(a["estado"] == "confirmada" for a in alertas)
aciertos, total_eval = None, 30
if cache:
    try:
        resumen, _ = evaluar.metricas(cache, umbral)
        aciertos, total_eval = resumen["aciertos"], resumen["total"]
    except FileNotFoundError:
        pass  # faltan fotos en datos/fotos: se omite el indicador
total_analizadas = len(set(cache) | st.session_state.analizadas | {a["archivo"] for a in alertas})

estilos.encabezado()
estilos.metricas(total_analizadas, pendientes, confirmadas, aciertos, total_eval)
estado_por_id = {a["id"]: a["estado"] for a in alertas}

tab_analizar, tab_alertas, tab_eval = st.tabs(["Analizar", "Alertas", "Evaluación"])

# ---------------- Analizar ----------------
with tab_analizar:
    fotos = st.file_uploader("Arrastra fotos aquí o elige archivos (JPG o PNG)",
                             type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    conocidas = det.camaras_conocidas()
    camaras = list(det.ZONAS)
    elegidas = {}

    if fotos:
        st.markdown("<p class='oi-nota'>Revisa la cámara de cada foto antes de analizar.</p>",
                    unsafe_allow_html=True)
        cols = st.columns(min(len(fotos), 4), gap="medium")
        for i, f in enumerate(fotos):
            img = Image.open(f)
            sugerida = conocidas.get(f.name) or det.adivinar_camara(img)
            with cols[i % len(cols)]:
                with st.container(border=True, key=f"oi-card-prev-{i}"):
                    st.image(img, width="stretch")
                    st.markdown(f"<p class='oi-nota'>{f.name}</p>", unsafe_allow_html=True)
                    elegidas[f.name] = st.selectbox("Cámara", camaras, index=camaras.index(sugerida),
                                                    key=f"cam_{f.name}")

        if st.button("Analizar", type="primary"):
            nuevos, errores = [], []
            for f in fotos:
                original = Image.open(f).copy()
                with st.status(f"Analizando {f.name}…", expanded=False) as estado:
                    st.write("Detectando objetos con Gemini…")
                    try:
                        res = det.analizar(original, f.name, elegidas[f.name], umbral, modelo)
                    except Exception as e:
                        estado.update(label=f"{f.name}: error al consultar Gemini", state="error")
                        errores.append(f"{f.name}: {e}")
                        continue
                    st.write("Revisando la zona del carril…")
                    st.write("Generando evidencia…")
                    alerta = det.guardar_alerta(res) if res["resultado"] == "riesgo" else None
                    estado.update(label=f"{f.name} listo", state="complete")
                st.session_state.analizadas.add(f.name)
                nuevos.append({
                    "archivo": f.name,
                    "camara": res["camara"],
                    "original": original,
                    "marcada": res["imagen_marcada"],
                    "riesgo": res["resultado"] == "riesgo",
                    "evento": res["tipo_evento"],
                    "confianza": res["confianza"],
                    "alerta_id": alerta["id"] if alerta else None,
                    "filas": [{
                        "tipo": det.NOMBRES.get(o["tipo"], o["tipo"]).capitalize(),
                        "confianza": round(float(o["confianza"]), 2),
                        "en_zona": o["en_zona"],
                        "resultado": resultado_objeto(o),
                    } for o in res["objetos"]],
                })
            st.session_state.resultados = nuevos
            st.session_state.errores = errores
            st.rerun()  # vuelve a dibujar con los indicadores ya actualizados

    for err in st.session_state.errores:
        st.error(err)

    for i, r in enumerate(st.session_state.resultados):
        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
        col_foto, col_info = st.columns([3, 2], gap="large")
        with col_foto:
            with st.container(border=True, key=f"oi-card-foto-{i}"):
                vista = st.radio("Vista", ["Original", "Marcada"], index=1, horizontal=True,
                                 label_visibility="collapsed", key=f"vista_{i}_{r['archivo']}")
                st.image(r["marcada"] if vista == "Marcada" else r["original"], width="stretch")
        with col_info:
            estado_actual = estado_por_id.get(r["alerta_id"], det.ESTADOS[0]) if r["riesgo"] else None
            estilos.tarjeta_resultado(r["riesgo"], r["evento"], r["confianza"], estado_actual, r["alerta_id"])
            if r["riesgo"] and estado_actual == det.ESTADOS[0]:
                b1, b2 = st.columns(2)
                b1.button("Confirmar", type="primary", key=f"conf_{i}_{r['alerta_id']}", width="stretch",
                          on_click=cambiar_estado, args=(r["alerta_id"], "confirmada"))
                b2.button("Descartar", key=f"desc_{i}_{r['alerta_id']}", width="stretch",
                          on_click=cambiar_estado, args=(r["alerta_id"], "descartada"))
            with st.container(border=True, key=f"oi-card-info-{i}"):
                st.markdown(f"**Archivo** · {r['archivo']}  \n**Cámara** · {r['camara']}")

        st.markdown("#### Objetos detectados")
        estilos.tabla_objetos(r["filas"])

# ---------------- Alertas ----------------
with tab_alertas:
    if not alertas:
        st.info("Todavía no hay alertas.")
    else:
        df = pd.DataFrame(alertas)
        st.dataframe(
            df.drop(columns=["evidencia"]).iloc[::-1], hide_index=True, width="stretch",
            column_config={
                "id": "Alerta", "fecha_hora": "Fecha y hora", "archivo": "Archivo",
                "camara": "Cámara", "tipo_evento": "Tipo de evento", "confianza": "Confianza",
                "objetos": "Objetos", "estado": "Estado",
            },
        )

        st.markdown("#### Revisar una alerta")
        ids = [a["id"] for a in reversed(alertas)]
        elegida = st.selectbox("Alerta", ids,
                               format_func=lambda i: f"{i} · " + next(
                                   f"{a['archivo']} · {a['tipo_evento']} · {a['estado']}"
                                   for a in alertas if a["id"] == i))
        a = next(x for x in alertas if x["id"] == elegida)

        col_img, col_det = st.columns([3, 2], gap="large")
        with col_img:
            ruta = det.BASE / a["evidencia"]
            if Path(ruta).exists():
                with st.container(border=True, key="oi-card-alerta-img"):
                    st.image(str(ruta), width="stretch")
        with col_det:
            with st.container(border=True, key="oi-card-alerta-det"):
                st.markdown(estilos.pildora_estado(a["estado"]), unsafe_allow_html=True)
                st.markdown(f"#### {a['tipo_evento'].capitalize()}")
                st.markdown(f"**Archivo** · {a['archivo']}  \n**Cámara** · {a['camara']}  \n"
                            f"**Confianza** · {a['confianza']}  \n**Fecha** · {a['fecha_hora']}")
                nuevo = st.radio("Estado", det.ESTADOS, index=det.ESTADOS.index(a["estado"]),
                                 key=f"estado_{elegida}")
                st.button("Guardar estado", type="primary", width="stretch",
                          on_click=cambiar_estado, args=(elegida, nuevo))

# ---------------- Evaluación ----------------
with tab_eval:
    st.write("Corre el sistema sobre las fotos de `datos/fotos/` y lo compara con `etiquetas.csv`. "
             "Lo que responde Gemini se guarda en caché: cambiar el umbral ya no gasta llamadas.")
    pausa = st.number_input("Segundos entre llamadas", 0.0, 60.0, 4.0, 1.0)
    if st.button("Analizar las fotos que falten", type="primary"):
        caja = st.empty()
        try:
            evaluar.detectar_todas(pausa, True, modelo, aviso=caja.write)
            caja.success("Listo")
        except Exception as e:
            caja.error(f"Se detuvo por un error de Gemini: {e}. Lo ya analizado quedó guardado.")

    if cache:
        try:
            resumen, filas = evaluar.metricas(cache, umbral)
        except FileNotFoundError:
            st.warning("Faltan fotos en datos/fotos/ para calcular la evaluación.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Aciertos", f"{resumen['aciertos']}/{resumen['total']}")
            c2.metric("Falsos positivos", resumen["falsos_positivos"])
            c3.metric("Falsos negativos", resumen["falsos_negativos"])

            tabla_umbrales = []
            for u in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
                r, _ = evaluar.metricas(cache, u)
                tabla_umbrales.append({"umbral": u, "aciertos": r["aciertos"],
                                       "falsos positivos": r["falsos_positivos"],
                                       "falsos negativos": r["falsos_negativos"]})
            st.markdown("#### Resultados por umbral")
            st.dataframe(pd.DataFrame(tabla_umbrales), hide_index=True)

            st.markdown("#### Detalle por foto")
            st.caption("* = punto de apoyo dentro de la zona")
            st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
    else:
        st.info("Aún no hay resultados. Pon las fotos en datos/fotos/ y presiona el botón.")
