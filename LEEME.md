# Ojos inteligentes · Reto 02 AutoTraffic

Detecta si un vehículo no autorizado o un peatón invade el carril confinado del BRT.

**Cómo funciona:**
1. **Gemini** detecta vehículos y peatones en la foto y devuelve su tipo, recuadro y confianza.
2. **El código** toma el punto de apoyo de cada objeto (centro de la base del recuadro) y revisa si cae dentro del polígono de su cámara (`zonas.json`).
3. Si un auto, moto, camioneta, camión, bicicleta o peatón con confianza ≥ umbral está dentro de la zona, el resultado es **riesgo** y se genera una alerta con la foto marcada y el estado «pendiente de revisión». El autobús autorizado no genera alerta.

## Instalación (una vez)

```bash
cd ojos-inteligentes
pip install -r requirements.txt
```

Copia `.env.example` como `.env` y pega tu API key de Google AI Studio.

## Poner los datos

```
datos/
  fotos/       ← foto_001.jpg … foto_030.jpg
  zonas/       ← camara_A.jpg … camara_D.jpg (ayudan a adivinar la cámara)
  zonas.json   ← ya incluido
  etiquetas.csv← ya incluido
```

## Usar

```bash
streamlit run app.py
```

- **Analizar fotos:** sube una o varias fotos. La cámara se toma de `etiquetas.csv` o se adivina; si sale mal, se cambia en el menú.
- **Alertas:** tabla de alertas, foto de evidencia y cambio de estado (pendiente, confirmada, descartada). Se guardan en `alertas/alertas.csv`.
- **Evaluación:** corre las 30 fotos y muestra aciertos, falsos positivos y falsos negativos por umbral.

También desde la terminal: `python evaluar.py`

## Afinar (lo que más sube la calificación)

1. Corre la evaluación una vez. Lo que responde Gemini queda en caché.
2. Mira la tabla por umbral y elige el que dé más aciertos.
3. Revisa cada error en el detalle por foto:
   - **Falso positivo con autobús visto como camión:** mejora la descripción de "autobus" en `PROMPT` (`detector.py`).
   - **Falso negativo con objeto no detectado** (noche o lluvia): pide en el prompt fijarse en los faros y siluetas.
   - **Objeto detectado pero fuera de zona:** el recuadro quedó corto; revisa que el prompt pida la caja hasta las ruedas o los pies.
4. Si cambias el prompt, corre `python evaluar.py --sin-cache`.

## Problemas comunes

| Error | Solución |
| --- | --- |
| Falta GEMINI_API_KEY | Crea el archivo `.env` (no `.env.example`) |
| 429 / RESOURCE_EXHAUSTED | Límite gratuito: sube la pausa entre llamadas o usa otra key |
| Model not found | Cambia `GEMINI_MODEL` en `.env` por el Flash que muestre AI Studio |
