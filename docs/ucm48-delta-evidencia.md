# UCM-48 — Evidencia del delta con corpus legal US, y estado para UCM-50

Anexo de la memoria y **hoja de traspaso para UCM-50**. Verificado a 2026-09-02 sobre el
catálogo `v0.6.0`, reglas `precedence v0.2.0` / `gating v0.3.0`, contra el stack desplegado por
contenedores (backend v0.6.0, Ollama 7B en GPU, Qdrant repoblado).

## Qué aportó UCM-48

La jurisdicción `US` tenía solo marcos técnicos y voluntarios (CIS, CSF). UCM-48 añade la **capa
legal estadounidense**, desglosada obligación a obligación como la NIS2 desglosa el art. 21(2):

- **CIRCIA** (transversal, `applies_to_sectors: []`): cuatro deberes — incidente 72 h `(a)(1)`,
  rescate 24 h `(a)(2)`, suplementario `(a)(3)`, preservación de registros `(a)(4)`.
- **TSA SD Pipeline** (sectorial, `applies_to_sectors: [transport]`): ocho — SD-01 (reporte 12 h,
  coordinador 24/7, evaluación de brechas) y SD-02 (segmentación, MFA, monitorización, parcheo,
  plan aprobado por TSA).

Distinción clave (regla `GATE-SCOPE-LEGAL-OBLIGATION` refinada): obligación de **gobernanza/reporte**
→ diferida a la capa organizativa; obligación que **prescribe mecanismo** (TSA SD-02 segmentación y
MFA) → ejercida en la zona, mueve cobertura. `partial`/`compensatory`, no `contextual`.

## E2E por endpoints desde texto libre (dos activos)

Flujo completo `parse → candidates → compose → audit-log`. El parse (7B en GPU) extrajo los
sectores del texto libre sin intervención: oleoducto `['transport','energy']`, potabilizadora
`['water']`. Selección de controles US en `Z-ENG-STATION`:

| Control US | Oleoducto (`transport`+`energy`) | Potabilizadora (`water`) |
| --- | --- | --- |
| TSA SD-02 segmentación (`CAP-PR-SEGMENT`) | RETENIDO (mecanismo) | `not_applicable / APPLIC-SECTOR` |
| TSA SD-02 MFA (`CAP-PR-MFA`) | COMPENSATORIO (mecanismo) | `not_applicable / APPLIC-SECTOR` |
| TSA SD-01/-02 resto (reporte, coord, eval, monitor, patch, plan) | diferido / overlay | `not_applicable / APPLIC-SECTOR` |
| CIRCIA ×4 (incidente/rescate/suplem./preservación) | diferido | **diferido — sigue aplicando** |

TSA solo al oleoducto (exclusión justificada por ámbito en el activo de agua); CIRCIA transversal a
ambos (degradación elegante). Ambas líneas base se firmaron; el audit-log traza cada exclusión.

## Delta regional sobre `Z-ENG-STATION` (ambos sentidos)

Capturas JSON completas: ver `ucm48-delta-US-EU.json` y `ucm48-delta-EU-US.json` (payloads del
endpoint `POST /delta`, `profile_id: PROFILE-B`).

**`US → +EU`** — base US (técnicamente rica + ley US); +EU añade **19 exigencias NIS2** de
gobernanza/reporte, **0 mecanismos**. 16/37 capacidades cambian, 0 huecos regionales.
UE = amplitud de gobernanza (art. 20, 21(2)(a–j)) y reporte escalonado (art. 23 = 24h/72h/1mes).

**`EU → +US`** — +US añade **2 mecanismos que mueven cobertura** (TSA SD-02 segmentación y MFA) más
10 exigencias US (TSA SD-01/-02 y las 4 de CIRCIA). EE.UU. = prescriptivo (legisla mecanismo) y más
rápido (12 h vs 72 h). 37/37 cambian y 28 huecos regionales — ver la nota siguiente.

`CAP-RS-REPORT`, que antes "comparaba relojes", ahora lleva reporte legal en **ambos** lados: CIRCIA
(72h/24h) + TSA (12h) en US, NIS2 (24h/72h/1mes) en UE. Aceptación #1 de UCM-48 cumplida.

## Estado para UCM-50 (delta simétrico)

Lo que UCM-48 deja resuelto y lo que NO:

1. **Resuelto**: el lado US ya tiene contenido legal (CIRCIA + TSA). El delta deja de comparar
   *base técnica* contra *base técnica + ley UE*.
2. **Pendiente para UCM-50 — el hallazgo a atacar**: el delta de UCM-17 es **acumulativo** y
   asimétrico. El terreno común son las jurisdicciones que no se comparan; **CIS y CSF son de
   jurisdicción `US`**, así que la lectura "EU sola" (`EU → +US`) se queda sin la capa técnica y +US
   la reincorpora entera → 37/37 cambian y 28 huecos. No es un error del motor: es que "apilar" no
   es "comparar dos regímenes legales sobre un terreno técnico compartido".
3. **Trabajo de UCM-50**: comparar `US` vs `EU` de forma **simétrica**, manteniendo constante el
   terreno técnico común (IEC + CIS + CSF), de modo que el delta muestre solo la diferencia
   **legal** (CIRCIA/TSA vs NIS2) sin el ruido de que la técnica viva en una jurisdicción. UCM-48 ya
   dejó el corpus con dos lados de contenido; falta la vista simétrica.
4. **Datos que UCM-50 puede reutilizar**: `app/delta/service.py` (lecturas acumulativas), los dos
   JSON de captura, y los perfiles `PROFILE-A/B` (ya declaran `sectors: [energy, transport]`).

## Nota de reproducibilidad

Medido: parse del oleoducto **267 s en CPU** vs **35 s en GPU** (RTX 3070, 29/29 capas en VRAM). La
ruta GPU y la CPU pueden resolver un empate de logits distinto, así que la reproducibilidad se
sostiene dentro de una ruta, no entre rutas (ver `docker-compose.gpu.yml`).
