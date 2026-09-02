# El corte del recuperador (UCM-54)

> Todo corte del motor lleva su regla y su justificación — incluido el del recuperador.

Este documento describe la regla que decide **cuántas sugerencias muestra la búsqueda y cuáles**, por
qué es esa y no otra, y qué se midió al enviarla. La regla vive en
[`server/app/retrieval/cut.py`](../server/app/retrieval/cut.py); sus parámetros, en
[`server/app/core/config.py`](../server/app/core/config.py); su informe, en `CapabilityRetrieval.cut`
y en el evento `candidates_cut` de la bitácora.

## 1. El problema: el único corte sin regla

El gating (UCM-9) declara la regla que excluye un mecanismo de una zona. La precedencia (UCM-8)
declara el orden versionado que resuelve una contradicción. La aplicabilidad (UCM-47) declara el
ámbito que una norma no alcanza. Las tres dicen *qué* dejan fuera y *por qué*.

`top_k` no decía nada. Lo que caía por debajo del puesto diez simplemente no aparecía, y ninguna
parte de la respuesta decía que hubiera estado ahí. El propio código ya había razonado la mitad del
problema: `CatalogIndex.search` rechaza un umbral de *puntuación* —«a threshold drops candidates
without saying so»— y añade que lo que el límite deja fuera «is a **ranking** decision the caller
records». El llamador no registraba nada. `top_k` era el mismo umbral, expresado por rango.

UCM-51 midió que ya no era un riesgo teórico
([`experimento-escalado-recuperador.md`](experimento-escalado-recuperador.md)):

- con 226 controles, `top_k=10` retiene el **4,4 %** del catálogo;
- **~14,8 controles** caen a menos de 0,01 del décimo — indistinguibles del último que sí se mostró;
- lo que se cae del corte es **diversidad de marco**: la familia de gobernanza de CSF expulsa del
  top-10 las lecturas europea y marítima, que es justo la variedad transfronteriza que este motor
  existe para enfrentar.

## 2. La regla

```
profundidad  RAG_RETRIEVAL_DEPTH = 50   (+ los candidatos del catálogo)
suelo        RAG_TOP_K = 10
banda        extiende k mientras score[k] ≥ score[k−1] − RAG_CUT_TIE_EPSILON (0,01)
techo        RAG_MAX_K = 16
tope         RAG_FRAMEWORK_CAP = 4 por marco, sobre los huecos que abrió la banda
cesión       si el tope no llega al suelo, cede huecos hasta alcanzarlo
```

Cada paso tiene su premisa:

**Profundidad.** La consulta ya no pide lo que se va a mostrar. UCM-51 midió que la consulta no
escala con el corpus —101 de los 109 ms son el *encode*, Qdrant se queda en 8-14 ms a cualquier
tamaño— y que el recall por profundidad es 77,1 % a 10, 86,1 % a 20 y 93,1 % a 50. Mirar más ancho es
casi gratis, y es lo que hace el corte **observable**: un candidato que la consulta nunca devolvió no
se puede reportar.

**Suelo.** `RAG_TOP_K`, sin cambios. Lo que ya se enviaba es el punto de partida, no algo que esta
regla tenga que reconquistar.

**Banda.** El corte no separa dos candidatos que el recuperador no distingue. La distancia a la que
deja de distinguir es un dato medido, no una intuición: 0,01, la misma épsilon de UCM-51.

**Techo.** No es una preferencia sino un coste: la capa de explicación (UCM-14) tarda ~4-5 min por
capacidad con ~12 candidatos y escala con lo mostrado. Cuando el techo detiene la extensión con
empates todavía por debajo, el informe lo declara.

**Tope por marco.** El catálogo está desequilibrado por naturaleza —CSF 106, IEC 51, CIS 49, NIS2 13,
IMO 7— porque los marcos voluntarios enumeran y el derecho sectorial no. En un vecindario denso de un
solo marco, el coseno ordena por *registro* y no por *asunto*. Un corte por número fijo no es neutral
ahí: gasta la atención del operador en el marco que más enumera.

**La cesión.** Si en el vecindario no hay bastantes marcos distintos, el tope cede huecos hasta
alcanzar el suelo. El orden importa y es toda la diferencia entre una preferencia y una restricción:
el tope decide *cuáles* lecturas llenan la lista, el suelo garantiza *cuántas* recibe el operador. Un
tope que ganara aquí haría que el recuperador mostrase menos que antes, que es precisamente el
estrechamiento que esta pasada no puede hacer.

## 3. Lo que la regla no es

- **No es un umbral de puntuación.** Nada se descarta por puntuar poco: todos los límites son de
  cuenta, y todas las cuentas se reportan.
- **No es un juicio del LLM** (invariante 1). Es una función determinista de un dato declarado del
  catálogo —el marco del control— y de un parámetro versionado.
- **No toca la línea base.** Cobertura, conflictos, gating y priorización siguen leyendo el núcleo
  determinista. El corte acota **sugerencias**, y los candidatos del catálogo lo atraviesan intactos:
  las confirmaciones ni siquiera se le entregan a la regla
  (`test_the_cut_never_reaches_the_catalogs_own_candidates`).
- **No es definitiva donde está.** Cuando llegue el juez de UCM-53, el recuperador debe entregarle la
  profundidad entera y el tope debe mudarse al corte final, detrás de él: topar antes le retiraría al
  juez justo los candidatos que existe para sopesar.

## 4. Lo que se reporta

Cada capacidad devuelve un `RetrievalCut`, y las cuentas cierran:
`retained + dropped == evaluated`, con `not_returned` para el resto del catálogo que la profundidad
no llegó a traer. Un lector puede rendir cuentas de los 226 controles contra una sola consulta.

| campo | qué dice |
| -- | -- |
| `policy` | la regla y sus cinco parámetros, con versión |
| `evaluated` / `retained` / `dropped` | evaluadas, mostradas, bajo el corte |
| `band_width` / `band_extension` | cuántos huecos abrió la banda, y cuántos añadió sobre el suelo |
| `ceiling_reached` | el techo detuvo la extensión con empates por debajo |
| `cap_yielded` | huecos que el tope devolvió para no bajar del suelo |
| `near_ties_dropped` | descartados que siguen a ≤0,01 del último mostrado |
| `first_dropped` | el mejor que no entra, con su similitud, su margen y quién lo dejó fuera |
| `displaced` | uno a uno, los que el tope movió, con su similitud y su motivo |
| `not_returned` | controles del catálogo que la profundidad no trajo |

`margin` va **en negativo** cuando el tope desplazó algo que puntuaba por encima del último mostrado.
Es el precio del tope, dicho en vez de escondido.

En la bitácora es un evento `candidates_cut` por capacidad, con el informe completo en `payload` y
`cut_policy` entre las versiones del run: los mismos vectores bajo un corte distinto responden otra
cosa, así que la regla es una versión del run como cualquier otra.

## 5. La medición

Instrumento: [`server/scripts/retrieval_cut.py`](../server/scripts/retrieval_cut.py), sobre el
catálogo activo **v0.4.0** (226 controles, 37 capacidades), con Qdrant y e5 reales. El detalle por
capacidad es dato derivado y no se versiona: el script lo regenera entero, e imprime en pantalla lo
que hay debajo de cada cifra de aquí. Tres brazos sobre el **mismo ranking**, para poder separar dos
efectos que se confunden:

| brazo | mostrados | recall | marcos distintos |
| -- | -- | -- | -- |
| coseno@10 (lo anterior) | 10,0 | 62,2 % | 3,22 |
| coseno@k (los mismos huecos, sin tope) | 15,6 | **68,6 %** | 3,62 |
| **regla enviada** (banda + tope) | 15,6 | 63,7 % | **4,81** |

**El recall es el de los mapeos del propio autor**, la vara más débil, y se nombra como tal igual que
en UCM-51. La baseline dorada vive fuera del repositorio a propósito y el motor no puede leerla
(invariante 9).

### 5.1 Lo que compra y lo que cuesta

Los dos efectos son de signo contrario y hay que decirlo así:

- **La banda compra 6,4 puntos de recall** (62,2 → 68,6). Son huecos, no ordenación: mostrar 15,6 en
  vez de 10 encuentra más de lo que el autor mapeó.
- **El tope cuesta 4,9 puntos de recall** (68,6 → 63,7) **y compra 1,19 marcos** (3,62 → 4,81).
- Neto frente a lo que se enviaba: **+1,5 puntos de recall y +1,59 marcos**.

Esto **no confirma** la sonda de UCM-51 §12, que con otro instrumento —24 capacidades, lente
sectorial, verdad corregida, tope aplicado a 10 huecos— midió que el tope *ganaba* 3 puntos. Aquí,
sobre 37 capacidades y con el tope aplicado a los huecos que abre la banda, el tope pierde recall
contra el mismo número de huecos. Las dos medidas son honestas y miden cosas distintas; ésta mide la
regla que se envía, así que es la que manda.

### 5.2 Por qué ese coste no es coste de cobertura

El recall de este documento mide **calidad de las sugerencias**, no cobertura, y la diferencia es
justo la del apartado 3. Los controles que el autor mapeó a una capacidad son los candidatos que
aporta el núcleo determinista: llegan como *confirmaciones*, se excluyen del corte por construcción y
el operador los ve siempre. Un mapeo que este brazo cuenta como «perdido» no desaparece de la
pantalla — deja de aparecer *también* como sugerencia recuperada.

El caso extremo lo ilustra. `CAP-GOV-CONTEXT` cae de 80 % a 20 % de recall, y lo que «pierde» es
`GV.OC-01` y `GV.OC-05`: dos subcategorías de CSF **mapeadas a esa misma capacidad**, que el núcleo
ofrece igualmente. Lo que el tope hizo allí fue cambiar nueve primos de CSF por cinco marcos
distintos (2 → 5). Dicho de otro modo: el brazo penaliza al tope exactamente por dejar de repetir lo
que el catálogo ya ofrecía.

### 5.3 El caso que motivó el ticket

`CAP-GOV-RISK` es el fallo que UCM-51 diseccionó, y la regla lo corrige:

| | mostrados | recall | marcos |
| -- | -- | -- | -- |
| coseno@10 | 10 | 20 % | 3 — `{CSF 8, NIS2 1, IMO 1}` |
| regla enviada | 16 | **40 %** | **5** — `{CSF 4, NIS2 4, IEC 3, CIS 3, IMO 2}` |

Recupera `NIS2 Art. 21` y `IMO MSC.428(98)` — la lectura europea y la marítima que la densidad de CSF
expulsaba— y no pierde ninguno. Nadie codificó «NIS2 gana»: emergen porque el tope dejó de gastar
ocho huecos en un solo marco. El primero descartado allí es `GV.OC-01`, a 0,8625, **0,038 por encima**
del último mostrado, desplazado por el tope y listado con esos números.

En el conjunto: **17 capacidades recuperan un mapeo** que el coseno puro no mostraba y **14 pierden
uno** de los que sí mostraba — de los cuales, por lo dicho en 5.2, ninguno desaparece de la pantalla.
El script imprime cuáles son, capacidad por capacidad.

### 5.4 Un hallazgo incómodo: la banda satura siempre

**El techo se alcanza en las 37 capacidades**, y de los 34,4 candidatos que caen bajo el corte de
media, **34,0 siguen a menos de 0,01 del último mostrado**. Es decir: en este catálogo la ventana de
50 candidatos es una sola banda plana, la regla de empate nunca encuentra dónde separar, y `k` acaba
siendo el techo en todos los casos.

Es coherente con el hallazgo central de UCM-51 —la banda plana es una propiedad del bi-encoder sobre
este dominio, no del tamaño del corpus— y conviene decirlo sin adornos: **en el catálogo actual, la
regla de banda no discrimina; el número operativo es `RAG_MAX_K`.** Lo que la regla aporta frente a
una constante nueva es que *declara* que ha saturado, capacidad por capacidad (`ceiling_reached`), en
vez de dejar que 16 parezca una decisión de la banda. Sobre un catálogo con la banda separada —o con
un modelo que discrimine mejor— la misma regla cortaría antes sin tocar un parámetro.

## 6. Reproducir

```bash
docker compose up -d qdrant
cd server && uv run python scripts/retrieval_cut.py
```

El script no toca ningún valor por defecto: lee la política de `settings` y llama al mismo
`apply_cut` que llama la API, así que lo que mide es el código que corre. Deja Qdrant como lo
encontró y su salida es reproducible: las cifras de arriba salen idénticas en cada ejecución.
