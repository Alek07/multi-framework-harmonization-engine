# Precisión de aplicabilidad — el otro lado del recall

Material para la memoria (sección de evaluación) y los anexos.

La evaluación mide **omisiones silenciosas = 0**: el error de dejar fuera algo que debía
estar. Este documento define y mide el **error contrario**, que hasta ahora ninguna métrica
señalaba: **ofrecer un control donde no corresponde**. Ofrecer no es neutralidad —es afirmar «esto
es un candidato para ti»—, así que una norma sectorial ofrecida a un activo que no rige es un
defecto tan real como una omisión. El caso IMO (norma de buques ofrecida a un gaseoducto terrestre)
llevaba ahí desde el principio sin que nada lo detectara; el motor lo corrigió y esta métrica lo
cuantifica.

Las dos métricas son **los dos lados del mismo compromiso** y se reportan **juntas**, nunca una en
lugar de la otra.

## Definiciones

Se miden **por control**, contra dos referencias: el **juicio experto** de qué marcos rigen cada
activo (`server/eval/applicability_ground_truth.json`, instrumento externo por el invariante 9) y el
**ámbito declarado** de cada control (`applies_to_sectors`). Un control se considera
*ofrecido* cuando el gating lo retiene (o lo marca como compensatorio); *excluido por ámbito* cuando
lleva una decisión de gating con la regla `APPLIC-SECTOR`.

Sobre el conjunto de normas que el experto declara **fuera de sector** para el activo:

| Desenlace | Qué es | Meta |
| -- | -- | -- |
| **Inclusión espuria** | fuera de sector, pero **ofrecida** como candidato | **0** |
| **Exclusión por ámbito** | fuera de sector, correctamente excluida (`APPLIC-SECTOR`) | — (el acierto) |
| **Silencio** | fuera de sector, ni ofrecida ni excluida con razón | **0** |

Y su simétrica, sobre las normas que el experto declara **en sector**:

| Desenlace | Qué es | Meta |
| -- | -- | -- |
| **Exclusión indebida** | en sector, pero excluida por ámbito (sobre-restricción) | **0** |

De ahí:

- **Tasa de inclusiones espurias** = inclusiones espurias / normas fuera de sector en juego. Meta **0**.
- **Precisión de aplicabilidad** = exclusiones por ámbito / (exclusiones por ámbito + inclusiones
  espurias). Meta **1,00**.

La precisión se calcula solo sobre las **normas sectoriales evaluadas**, no sobre todo el catálogo:
la mayoría de los controles son transversales (CSF, CIS, IEC 62443) y siempre aciertan, así que
mezclarlos diluiría la señal justo en el punto que la métrica existe para vigilar.

## Casos de prueba: activos fuera de sector

Dos activos deliberadamente ajenos al gaseoducto, dados en **texto libre** y recorridos de punta a
punta (`scripts/e2e_flow.py`, `make e2e`):

- **Planta potabilizadora** (`ESC-WATER`, sector `water`).
- **Hospital** (`ESC-HOSPITAL`, sector `health`).

Para ambos, **IMO** (marítimo) y **TSA** (transporte) deben aparecer como **exclusión justificada
por ámbito**, no como candidato ni como silencio; **NIS2** (que rige agua y salud) y los marcos
transversales sí aplican. El activo positivo de contraste es la **terminal portuaria** (`ESC-PORT`,
marítimo/transporte/energía), donde IMO y TSA **sí rigen** y no deben excluirse por ámbito —así la
métrica vigila también la sobre-restricción.

Cada inclusión espuria se analiza como se analiza cada omisión: qué control, de qué marco, qué
sectores rige, en qué zona se ofreció y con qué sectores declarados —para poder decir *por qué*
ocurrió y *qué regla faltaba*.

## Dónde se mide

`make e2e` corre el flujo completo desde el texto libre y vuelca consola + resumen JSON a
`server/eval/runs/` (ignorado por git). La métrica sale en el paso `2b/7` por activo y en la tabla
comparativa final (columnas `f/sec`, `esp`, `prec`), y se verifica además que la exclusión por
ámbito **llega a la declaración de aplicabilidad firmada**.
