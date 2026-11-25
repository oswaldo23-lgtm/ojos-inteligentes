"""Núcleo de Ojos inteligentes: Gemini detecta objetos y el código decide el riesgo con la zona."""
import csv
import io
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

load_dotenv()

BASE = Path(__file__).parent
DATOS = BASE / "datos"
ALERTAS_DIR = BASE / "alertas"
ALERTAS_CSV = ALERTAS_DIR / "alertas.csv"
EVIDENCIA_DIR = ALERTAS_DIR / "evidencia"

MODELO = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

_zonas_json = json.loads((DATOS / "zonas.json").read_text(encoding="utf-8"))
ZONAS = _zonas_json["camaras"]
ZONA_ANCHO = _zonas_json["ancho"]
ZONA_ALTO = _zonas_json["alto"]

# Lo que cuenta como riesgo si su punto de apoyo cae dentro de la zona.
TIPOS_RIESGO = {"auto", "moto", "camioneta", "camion", "peaton", "bicicleta"}
NOMBRES = {
    "autobus": "autobús", "auto": "auto", "moto": "moto", "camioneta": "camioneta",
    "camion": "camión", "peaton": "peatón", "bicicleta": "bicicleta", "otro": "otro",
}

ESTADOS = ["pendiente de revisión", "confirmada", "descartada"]


# ---------- 1. Gemini: detectar objetos ----------

class Objeto(BaseModel):
    tipo: str          # autobus, auto, moto, camioneta, camion, peaton, bicicleta, otro
    box_2d: list[int]  # [ymin, xmin, ymax, xmax] normalizado 0-1000
    confianza: float   # 0 a 1


class Deteccion(BaseModel):
    objetos: list[Objeto]


PROMPT = """Eres el sistema de visión de una cámara de vigilancia que vigila un carril
confinado de transporte público (BRT). Detecta TODOS los vehículos y peatones visibles,
incluso los pequeños o lejanos, de día, de noche, con lluvia o sombras.

Para cada uno devuelve:
- tipo: uno de autobus, auto, moto, camioneta, camion, peaton, bicicleta, otro.
  Usa "autobus" solo para autobuses de transporte público (normalmente largos o articulados).
  Usa "camion" para camiones de carga, pipas o camiones de reparto.
- box_2d: [ymin, xmin, ymax, xmax] normalizado de 0 a 1000, ajustado al objeto completo
  (de las ruedas o los pies hasta arriba).
- confianza: de 0 a 1, qué tan seguro estás del tipo y de la posición.

No reportes personas que van dentro de un vehículo, ni reflejos, ni sombras.
Si no hay vehículos ni peatones, devuelve la lista vacía."""

_cliente = None


def cliente():
    global _cliente
    if _cliente is None:
        clave = os.getenv("GEMINI_API_KEY")
        if not clave:
            raise RuntimeError("Falta GEMINI_API_KEY en el archivo .env")
        _cliente = genai.Client(api_key=clave, http_options=types.HttpOptions(timeout=60000))
    return _cliente


def detectar(img: Image.Image, modelo: str = MODELO, reintentos: int = 5) -> list[dict]:
    """Manda la foto a Gemini y regresa la lista de objetos detectados."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90)
    parte_img = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=Deteccion,
        temperature=0,
    )
    for intento in range(reintentos):
        try:
            r = cliente().models.generate_content(
                model=modelo, contents=[parte_img, PROMPT], config=config
            )
            datos = r.parsed if r.parsed is not None else Deteccion.model_validate_json(r.text)
            return [o.model_dump() for o in datos.objetos]
        except Exception as e:  # 429 (límite) u otros errores temporales
            if intento == reintentos - 1:
                raise
            espera = 20 if ("429" in str(e) or "503" in str(e)) else 3
            time.sleep(espera)
    return []


# ---------- 2. Regla: punto de apoyo dentro de la zona ----------

def zona_en_pixeles(camara: str, ancho: int, alto: int) -> list[tuple[float, float]]:
    """Polígono de la cámara escalado al tamaño real de la foto."""
    sx, sy = ancho / ZONA_ANCHO, alto / ZONA_ALTO
    return [(x * sx, y * sy) for x, y in ZONAS[camara]]


def punto_en_poligono(x: float, y: float, poligono) -> bool:
    """Ray casting: cuenta cuántas veces una línea horizontal cruza los bordes."""
    dentro = False
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cruce = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cruce:
                dentro = not dentro
    return dentro


def evaluar_objetos(objetos: list[dict], camara: str, ancho: int, alto: int, umbral: float):
    """Convierte cajas a píxeles y marca qué objetos invaden la zona."""
    zona = zona_en_pixeles(camara, ancho, alto)
    resultado = []
    for o in objetos:
        if len(o.get("box_2d", [])) != 4:
            continue
        ymin, xmin, ymax, xmax = o["box_2d"]
        caja = (xmin / 1000 * ancho, ymin / 1000 * alto, xmax / 1000 * ancho, ymax / 1000 * alto)
        apoyo = ((caja[0] + caja[2]) / 2, caja[3])  # centro de la base = donde toca el piso
        tipo = o["tipo"].strip().lower().replace("ó", "o").replace("ú", "u")
        en_zona = punto_en_poligono(apoyo[0], apoyo[1], zona)
        invade = en_zona and tipo in TIPOS_RIESGO and o["confianza"] >= umbral
        resultado.append({**o, "tipo": tipo, "caja": caja, "apoyo": apoyo,
                          "en_zona": en_zona, "invade": invade})
    return resultado


def tipo_evento(invasores: list[dict]) -> str:
    if not invasores:
        return "sin riesgo"
    if any(o["tipo"] == "peaton" for o in invasores):
        if all(o["tipo"] == "peaton" for o in invasores):
            return "peatón en zona de riesgo"
        return "invasión de zona y peatón en zona de riesgo"
    return "invasión de zona restringida"


# ---------- 3. Evidencia: foto marcada ----------

_FUENTE_CON_ACENTOS = True


def _fuente(tam: int):
    """Busca una fuente con acentos (Windows, Mac, Linux); si no hay, usa la de Pillow."""
    global _FUENTE_CON_ACENTOS
    for nombre in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "Arial.ttf",
                   "/System/Library/Fonts/Supplemental/Arial.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(nombre, tam)
        except OSError:
            continue
    _FUENTE_CON_ACENTOS = False
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:
        return ImageFont.load_default()


def _texto(t: str) -> str:
    if _FUENTE_CON_ACENTOS:
        return t
    import unicodedata
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()


ROJO = (214, 40, 57)  # rojo AutoTraffic
GRIS = (209, 209, 214)
BLANCO = (255, 255, 255)
GRIS_TEXTO = (60, 60, 67)


def _pildora(d: ImageDraw.ImageDraw, texto: str, caja, ancho_img: int, f,
             fondo, color_texto, borde=None) -> None:
    """Etiqueta en forma de píldora arriba del recuadro (o abajo si no cabe)."""
    x0, y0, x1, y1 = caja
    texto = _texto(texto)
    bb = d.textbbox((0, 0), texto, font=f)
    pad_x, pad_y = 10, 5
    pw, ph = bb[2] - bb[0] + 2 * pad_x, bb[3] - bb[1] + 2 * pad_y
    px = max(4, min(x0, ancho_img - pw - 4))      # que no se salga por los lados
    py = y0 - ph - 6 if y0 >= ph + 6 else y1 + 6  # arriba del recuadro, o abajo si no cabe
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=ph // 2, fill=fondo,
                        outline=borde, width=1 if borde else 0)
    d.text((px + pad_x - bb[0], py + pad_y - bb[1]), texto, fill=color_texto, font=f)


def marcar(img: Image.Image, objetos: list[dict], camara: str, estado: str | None) -> Image.Image:
    """Dibuja la zona, las cajas y las etiquetas sobre la foto (estilo de sistema)."""
    base = img.convert("RGBA")
    capa = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    zona = zona_en_pixeles(camara, *base.size)
    d.polygon(zona, fill=ROJO + (56,), outline=ROJO + (255,), width=2)
    base = Image.alpha_composite(base, capa)

    d = ImageDraw.Draw(base)
    f = _fuente(18)
    # Primero los que no alertan y al final los que alertan, para que estos queden encima.
    for o in sorted(objetos, key=lambda o: o["invade"]):
        x0, y0, x1, y1 = o["caja"]
        nombre = NOMBRES.get(o["tipo"], o["tipo"]).capitalize()
        ax, ay = o["apoyo"]
        if o["invade"]:
            d.rounded_rectangle([x0, y0, x1, y1], radius=8, outline=ROJO, width=3)
            d.ellipse([ax - 7, ay - 7, ax + 7, ay + 7], fill=ROJO, outline=BLANCO, width=2)
            _pildora(d, f"{nombre} en zona · {o['confianza']:.2f}", o["caja"], base.width, f,
                     ROJO, BLANCO)
        else:
            motivo = "autorizado" if o["tipo"] == "autobus" else (
                "fuera de zona" if not o["en_zona"] else "baja confianza")
            d.rounded_rectangle([x0, y0, x1, y1], radius=8, outline=GRIS, width=2)
            d.ellipse([ax - 5, ay - 5, ax + 5, ay + 5], fill=GRIS, outline=BLANCO, width=2)
            _pildora(d, f"{nombre} · {motivo}", o["caja"], base.width, f,
                     BLANCO, GRIS_TEXTO, borde=GRIS)
    return base.convert("RGB")



# ---------- 4. Análisis completo de una foto ----------

def analizar(img: Image.Image, archivo: str, camara: str, umbral: float = 0.5,
             modelo: str = MODELO) -> dict:
    objetos = detectar(img, modelo)
    evaluados = evaluar_objetos(objetos, camara, img.width, img.height, umbral)
    invasores = [o for o in evaluados if o["invade"]]
    es_riesgo = bool(invasores)
    estado = ESTADOS[0] if es_riesgo else None
    return {
        "archivo": archivo,
        "camara": camara,
        "resultado": "riesgo" if es_riesgo else "normal",
        "tipo_evento": tipo_evento(invasores),
        "confianza": max((o["confianza"] for o in invasores), default=None),
        "estado": estado,
        "objetos": evaluados,
        "imagen_marcada": marcar(img, evaluados, camara, estado),
    }


# ---------- 5. Cámara de cada foto ----------

def camaras_conocidas() -> dict[str, str]:
    """archivo -> cámara, según etiquetas.csv (las fotos de desarrollo)."""
    ruta = DATOS / "etiquetas.csv"
    if not ruta.exists():
        return {}
    with open(ruta, encoding="utf-8") as f:
        return {fila["archivo"].strip(): fila["camara"].strip() for fila in csv.DictReader(f)}


def adivinar_camara(img: Image.Image) -> str:
    """Compara la foto con las imágenes de referencia de datos/zonas/ (aproximado).
    Si no hay referencias, regresa la primera cámara."""
    refs = {c: DATOS / "zonas" / f"{c}.jpg" for c in ZONAS}
    refs = {c: p for c, p in refs.items() if p.exists()}
    if not refs:
        return next(iter(ZONAS))

    def huella(im):
        g = im.convert("L").resize((64, 48))
        px = list(g.getdata())
        m = sum(px) / len(px)
        return [p - m for p in px]  # se resta el brillo medio para tolerar día/noche

    h = huella(img)
    mejor, menor = None, float("inf")
    for c, p in refs.items():
        dist = sum(abs(a - b) for a, b in zip(h, huella(Image.open(p))))
        if dist < menor:
            mejor, menor = c, dist
    return mejor


# ---------- 6. Alertas ----------

CAMPOS_ALERTA = ["id", "fecha_hora", "archivo", "camara", "tipo_evento", "confianza",
                 "objetos", "estado", "evidencia"]


def guardar_alerta(res: dict) -> dict:
    EVIDENCIA_DIR.mkdir(parents=True, exist_ok=True)
    id_alerta = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    ruta_img = EVIDENCIA_DIR / f"{id_alerta}_{Path(res['archivo']).stem}.jpg"
    res["imagen_marcada"].save(ruta_img, quality=90)
    fila = {
        "id": id_alerta,
        "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "archivo": res["archivo"],
        "camara": res["camara"],
        "tipo_evento": res["tipo_evento"],
        "confianza": f"{res['confianza']:.2f}",
        "objetos": ", ".join(NOMBRES.get(o["tipo"], o["tipo"]) for o in res["objetos"] if o["invade"]),
        "estado": ESTADOS[0],
        "evidencia": str(ruta_img.relative_to(BASE)),
    }
    nuevo = not ALERTAS_CSV.exists()
    with open(ALERTAS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_ALERTA)
        if nuevo:
            w.writeheader()
        w.writerow(fila)
    return fila


def leer_alertas() -> list[dict]:
    if not ALERTAS_CSV.exists():
        return []
    with open(ALERTAS_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cambiar_estado(id_alerta: str, estado: str) -> None:
    filas = leer_alertas()
    for fila in filas:
        if fila["id"] == id_alerta:
            fila["estado"] = estado
    with open(ALERTAS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_ALERTA)
        w.writeheader()
        w.writerows(filas)
