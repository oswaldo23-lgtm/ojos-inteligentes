"""Evalúa el sistema con las 30 fotos etiquetadas.

Uso:
    python evaluar.py                 # analiza las fotos (usa caché si ya se analizaron)
    python evaluar.py --sin-cache     # vuelve a preguntar a Gemini por todas
    python evaluar.py --pausa 5       # segundos entre llamadas (para no pasar el límite)

Guarda lo que responde Gemini en datos/cache_detecciones.json, así se pueden probar
umbrales distintos sin gastar más llamadas.
"""
import argparse
import json
import time

from PIL import Image

import detector as det

CACHE = det.DATOS / "cache_detecciones.json"


def cargar_cache():
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def detectar_todas(pausa: float, usar_cache: bool, modelo: str, aviso=print):
    """Regresa {archivo: objetos crudos de Gemini} para todas las fotos con etiqueta."""
    cache = cargar_cache() if usar_cache else {}
    camaras = det.camaras_conocidas()
    for i, archivo in enumerate(sorted(camaras), 1):
        ruta = det.DATOS / "fotos" / archivo
        if not ruta.exists():
            aviso(f"[{i}/{len(camaras)}] falta {archivo}")
            continue
        if archivo in cache:
            continue
        aviso(f"[{i}/{len(camaras)}] analizando {archivo}…")
        cache[archivo] = det.detectar(Image.open(ruta), modelo)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(pausa)
    return cache


def metricas(cache: dict, umbral: float):
    """Compara la predicción con etiquetas.csv. Positivo = riesgo."""
    import csv
    with open(det.DATOS / "etiquetas.csv", encoding="utf-8") as f:
        etiquetas = {r["archivo"]: r for r in csv.DictReader(f)}
    filas = []
    for archivo, objetos in cache.items():
        if archivo not in etiquetas:
            continue
        real = etiquetas[archivo]["etiqueta"].strip()
        camara = etiquetas[archivo]["camara"].strip()
        with Image.open(det.DATOS / "fotos" / archivo) as im:
            ancho, alto = im.size
        evaluados = det.evaluar_objetos(objetos, camara, ancho, alto, umbral)
        invasores = [o for o in evaluados if o["invade"]]
        pred = "riesgo" if invasores else "normal"
        if pred == real:
            caso = "acierto"
        elif pred == "riesgo":
            caso = "falso positivo"
        else:
            caso = "falso negativo"
        filas.append({
            "archivo": archivo, "camara": camara, "real": real, "prediccion": pred, "caso": caso,
            "invasores": ", ".join(f"{o['tipo']} {o['confianza']:.2f}" for o in invasores),
            "detectados": ", ".join(
                f"{o['tipo']}{'*' if o['en_zona'] else ''} {o['confianza']:.2f}" for o in evaluados),
        })
    total = len(filas)
    resumen = {
        "total": total,
        "aciertos": sum(f["caso"] == "acierto" for f in filas),
        "falsos_positivos": sum(f["caso"] == "falso positivo" for f in filas),
        "falsos_negativos": sum(f["caso"] == "falso negativo" for f in filas),
    }
    return resumen, filas


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pausa", type=float, default=4.0)
    p.add_argument("--sin-cache", action="store_true")
    p.add_argument("--umbral", type=float, default=0.5)
    p.add_argument("--modelo", default=det.MODELO)
    a = p.parse_args()

    cache = detectar_todas(a.pausa, not a.sin_cache, a.modelo)

    print("\nUmbral | Aciertos | Falsos positivos | Falsos negativos")
    for u in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        r, _ = metricas(cache, u)
        print(f"  {u:.1f}  |  {r['aciertos']:>2}/{r['total']}   |        {r['falsos_positivos']:>2}        |       {r['falsos_negativos']:>2}")

    r, filas = metricas(cache, a.umbral)
    print(f"\nErrores con umbral {a.umbral} (* = punto de apoyo dentro de la zona):")
    for f in filas:
        if f["caso"] != "acierto":
            print(f"  {f['archivo']} ({f['camara']}): real={f['real']} pred={f['prediccion']} | {f['detectados']}")


if __name__ == "__main__":
    main()
