# Experimento de escalado del recuperador (UCM-51)

Material para la memoria. Mide **cómo se comporta la recuperación semántica conforme crece el
corpus**, usando los catálogos congelados del propio repositorio como puntos de medición: nada aquí
es sintético y nada está estimado.

Todo lo que sigue es **medido**, no predicho. Se produjo el 2026-08-31 ejecutando

```bash
cd server && uv run python scripts/retrieval_scaling.py    # necesita Qdrant en pie
```

sobre `intfloat/multilingual-e5-base` (768 dim, CPU, `EMBEDDING_NUM_THREADS=1`) y `RAG_TOP_K=10`,
en una máquina AMD Ryzen 5 5600X (6 núcleos) con 16 GB de RAM — el extremo alto de la máquina
objetivo de 8–16 GB. Los datos crudos, capacidad a capacidad, están en
[`experimento-escalado-recuperador.json`](experimento-escalado-recuperador.json).

## Resumen

**La hipótesis del ticket no se sostuvo, y ése es el resultado útil.** Se esperaba que la banda plana
de similitud fuese síntoma de un corpus pequeño y que el recuperador empezara a discriminar al
crecer. Ocurrió lo contrario: con 3,3 veces más catálogo la banda **se estrechó** (1.º−10.º de 0,053
a 0,041) y el recall@10 de los mapeos del autor **cayó del 88,5 % al 79,2 %**. La banda plana es una
propiedad del bi-encoder sobre este dominio —todos los controles de ciberseguridad se parecen en el
espacio de e5—, no del tamaño del corpus.

Siete hallazgos, todos medidos:

1. **El corte es cada vez más ciego.** `top_k=10` retiene el 4,4 % del catálogo y descarta ~15
   controles que están a menos de 0,01 del décimo: indistinguibles del último que sí mostró (§4).
2. **Lo que se cae del corte es la diversidad de marco.** CSF pasó de 25 a 106 subcategorías y su
   familia de gobernanza expulsa del top-10 a las lecturas europea y marítima — justo la variedad
   transfronteriza que este motor existe para enfrentar (§5).
3. **La causa no es la calidad del texto ni el solape de palabras**, y ambas cosas se descartaron con
   datos: las descripciones nuevas son más largas (73 vs. 61 caracteres) y los cuatro candidatos en
   disputa comparten exactamente las mismas dos palabras con la consulta. Lo que decide es que el
   *registro* global del pasaje domina sobre su *asunto* concreto (§5).
4. **El recuperador llega a poner controles de otras capacidades por delante de los de ésta**:
   `GV.RR-02` (→ `CAP-GOV-ROLES`) y `GV.PO-01` (→ `CAP-GOV-POLICY`) adelantan a `NIS2 Art. 21`, que
   está mapeado a la capacidad consultada y se titula literalmente *Cybersecurity risk-management
   measures* (§5).
5. **Enriquecer la consulta con el contexto de la zona empeora la recuperación** (−14 a −19 puntos):
   buena parte de ese contexto es negación, y una negación se parece a lo que niega cuando todo se
   comprime en un vector (§8).
6. **Nada de esto pone en riesgo la cobertura.** Omisiones silenciosas: **0** en los cuatro tamaños.
   Lo que se degrada es la calidad de las *sugerencias*, nunca lo que el núcleo determinista ofrece
   (§10). Y el coste no escala: 101 ms de los 109 son el encode, no el índice (§11).
7. **La prioridad sectorial, probada, es la peor política posible** (recall 7,3 %); un **tope por
   marco** mejora recall y diversidad a la vez (§12).

Consecuencias para el plan: UCM-54 sube de prioridad y se convierte en **prerrequisito** de UCM-53
—un juez sobre el top-10 no puede recuperar lo que está en el puesto 20—, y la baseline dorada
necesita re-congelarse antes de UCM-18.

## 1. Verificación previa: los prefijos de e5 ya estaban aplicados

El ticket pedía comprobar si `embeddings.py` aplica los prefijos asimétricos `query:` / `passage:`
con los que se entrenó e5, por si parte de la banda plana fuese un artefacto corregible. **Lo hace**:
`encode_query` y `encode_passages` son entradas separadas y ninguna acepta texto crudo
(`app/retrieval/embeddings.py`). La banda plana no es ese artefacto — es real, y lo que sigue la
mide.

## 2. Corrección de premisa: hay dos puntos de tamaño, no tres

| Versión | Capacidades | Controles | Mapeos | Reglas de gating |
| -- | -- | -- | -- | -- |
| v0.1.0 | 24 | **69** | 77 | `gating.v0.1.0` |
| v0.2.0 | 37 | **225** | 263 | `gating.v0.2.0` |
| v0.3.0 | 37 | 226 | 266 | `gating.v0.2.0` |
| v0.4.0 | 37 | 226 | 266 | `gating.v0.2.0` |

Todo el crecimiento ocurre de una vez, en v0.1.0 → v0.2.0. Entre v0.2.0 y v0.4.0 se añade **un**
control: esos dos últimos puntos no miden tamaño, miden qué pasa al cambiar texto y payload a
tamaño constante (la respuesta, adelantada: nada apreciable en la recuperación). Presentarlos como
cuatro tamaños sería decorar una curva que tiene dos puntos.

**La comparación sí es controlada.** Las 24 capacidades y los 69 controles de v0.1.0 son un
subconjunto estricto de v0.4.0, y los textos de esas 24 capacidades son idénticos byte a byte en
las cuatro versiones: son las mismas 24 consultas contra corpus distintos. El confusor se declara
en lugar de esconderse — **20 de los 69 controles compartidos cambiaron de título o descripción**
después de v0.1.0, y esos 20 aparecen 26 veces en los top-10 de v0.4.0. Es el tamaño de la duda, y
no es despreciable.

También hay un emparejamiento que no es cosmético: cada catálogo se ejecuta con las reglas de
gating de su época. `gating.v0.2.0` nombra controles que no existen en v0.1.0 y **se niega a
validar** contra él, que es la capa de reglas declinando correctamente juzgar un catálogo para el
que no se escribió.

## 3. La banda no se abrió: se estrechó

Media de las 24 capacidades, consulta enviada tal cual la envía el motor:

| Versión | Controles | 1.º | 10.º | 1.º−10.º | último | empates a ≤0,01 del 10.º |
| -- | -- | -- | -- | -- | -- | -- |
| v0.1.0 | 69 | 0,882 | 0,829 | **0,053** | 0,775 | 10,8 (15,6 % del catálogo) |
| v0.2.0 | 225 | 0,880 | 0,839 | **0,041** | 0,762 | 14,7 (6,5 %) |
| v0.3.0 | 226 | 0,880 | 0,839 | 0,041 | 0,762 | 14,8 (6,6 %) |
| v0.4.0 | 226 | 0,880 | 0,839 | 0,041 | 0,762 | 14,8 (6,6 %) |

La hipótesis del ticket era que la banda plana (~0,90 el primero, ~0,83 el décimo) fuese síntoma de
un corpus pequeño y homogéneo, y que se separase al crecer. **No se separó.** El primero se queda
donde estaba (0,882 → 0,880) y el décimo *sube* (0,829 → 0,839): la cabeza del ranking se comprime.
Lo que sí se ensancha es la cola — el último control pasa de 0,775 a 0,762, y la banda completa de
0,107 a 0,118 —, pero eso solo dice que un corpus mayor contiene más cosas irrelevantes, que es
trivialmente cierto y no ayuda a nadie a elegir.

La conclusión es la contraria a la esperada y es la más útil del experimento: **la banda plana es
una propiedad del bi-encoder sobre este dominio, no del tamaño del corpus.** Todos los controles de
ciberseguridad se parecen entre sí en el espacio de e5. Multiplicar el catálogo por 3,3 no le
enseñó al modelo a distinguirlos; le dio más vecinos igual de próximos.

## 4. Dureza del corte

| Versión | Controles | Sobrevive a `top_k=10` | Empatados en el filo |
| -- | -- | -- | -- |
| v0.1.0 | 69 | 14,5 % | 10,8 controles |
| v0.2.0 | 225 | 4,4 % | 14,7 |
| v0.4.0 | 226 | **4,4 %** | **14,8** |

Las dos lecturas del empate cuentan historias opuestas y las dos importan. En términos **absolutos**
el corte empeora: hay 14,8 controles a menos de 0,01 del décimo, es decir, se descartan más
candidatos que el motor no puede distinguir del último que sí mostró. En términos **relativos**
mejora: del 15,6 % del catálogo al 6,6 %. Pero la que le llega al operador es la absoluta —
**`top_k=10` retiene 10 y tira ~15 indistinguibles**, y lo hace sin regla y sin dejar rastro de qué
tiró. Ésta es la entrada que UCM-54 necesitaba, y dice que el corte ya no es benigno.

## 5. El recall cae al crecer el corpus, y se sabe exactamente dónde

Recall de los mapeos del propio autor, contra la **verdad congelada de v0.1.0** (los mismos tres o
cuatro controles esperados por capacidad en todos los puntos, que es lo único comparable). Ésta es
la medida del bi-encoder **a solas, sin ninguna lente**; la cifra corregida por aplicabilidad —la
honesta, y la que debe citar la memoria— está dos apartados más abajo:

| Versión | @1 | @5 | **@10** | @20 | @50 |
| -- | -- | -- | -- | -- | -- |
| v0.1.0 | 32,2 % | 75,9 % | **87,2 %** | 93,1 % | 97,2 % |
| v0.2.0 | 26,7 % | 57,7 % | **77,1 %** | 86,1 % | 93,1 % |
| v0.4.0 | 26,7 % | 57,7 % | **77,1 %** | 86,1 % | 93,1 % |

Contra la verdad de cada versión —no comparable entre puntos, porque el conjunto esperado crece,
pero sí informativa de la situación actual— el recall@10 en v0.4.0 es **59,4 %**.

Se declara qué mide y qué no: los mapeos son la palabra del autor, no un instrumento independiente.
Y **no se reporta precisión**: la recuperación existe para *ampliar* (invariante 2), así que un
acierto fuera de los mapeos es la función, no un error. Contar precisión sería medir lo contrario
de lo que el módulo hace.

### La corrección por aplicabilidad: la cifra honesta es 88,5 % → 79,2 %

La tabla de arriba castiga al motor por acertar, y conviene decirlo con precisión porque el error
era del instrumento. La verdad está congelada en v0.1.0, un catálogo que **no declaraba ámbito
sectorial alguno**, así que mapea `IMO MSC.428(98)` —gobernanza del riesgo cibernético *marítima*,
dentro de un sistema de gestión de la seguridad de buque— a la capacidad de gestión del riesgo de
un gasoducto. UCM-47 declaró después ese ámbito (`applies_to_sectors: [maritime]`) y UCM-52 actúa
sobre él: hoy el motor lo aparta, marcado y trazable, y hace bien. Contarlo como fallo de
recuperación es puntuar al motor como si fallara justo donde acierta.

Aplicando la lente sectorial de los perfiles (`energy`, leída de los perfiles, no fijada en el
código) y descontando del patrón lo que no gobierna este activo — la misma corrección en los cuatro
puntos, porque una vara que cambia entre puntos no mide nada:

| Versión | recall@10 sin lente | con lente | **con lente + verdad corregida** |
| -- | -- | -- | -- |
| v0.1.0 | 87,2 % | 87,2 % | **88,5 %** |
| v0.2.0 | 77,1 % | 77,1 % | **79,2 %** |
| v0.4.0 | 77,1 % | 77,1 % | **79,2 %** |

**La caída real es de 88,5 % a 79,2 % — 9,3 puntos.** Sigue siendo la caída, y la causa sigue
siendo la de la §4: apiñamiento. Pero 77,1 % era la cifra equivocada para la memoria.

Dos cosas más que esta columna deja medidas y que no son obvias:

* **La lente sectorial no cambia el recall en ningún punto** (columna 2 = columna 1). No es que no
  funcione: es que no puede alcanzar el problema. Solo **20 de 226** controles declaran ámbito, y
  los doce hermanos de CSF que causan el apiñamiento son **transversales**, es decir, controles que
  la lente tiene prohibido apartar —y con razón, porque sí aplican—. Un filtro por payload no
  arregla una competencia entre controles que le está vedado excluir.
* En v0.1.0 la lente tampoco hace nada, pero **por un motivo distinto**: aquel catálogo no declaraba
  ámbito en ningún control. Mismo cero, dos causas: allí no había premisa que aplicar, aquí la
  premisa no alcanza.

### El fallo analizado

El desplome no está repartido: se concentra en las capacidades de **gobernanza**.

| Capacidad | recall@10 v0.1.0 → v0.4.0 |
| -- | -- |
| `CAP-GOV-RISK` | 1,00 → **0,33** |
| `CAP-GOV-SUPPLY` | 1,00 → 0,50 |
| `CAP-ID-RISK` | 1,00 → 0,50 |
| `CAP-PR-BACKUP` | 0,67 → 0,33 |
| `CAP-ID-ASSET` | 1,00 → 1,00 |

`CAP-GOV-RISK` en v0.1.0 recuperaba sus tres controles mapeados en el top-10: `CSF GV.RM-01`,
`IMO 4.2.8/9` y `NIS2 Art. 21`. En v0.4.0 el top-10 es **siete hermanos de la familia CSF GV.\***
(`GV.RR-02`, `GV.PO-01`, `GV.RM-03`, `GV.OC-01`, `GV.RR-03`, `GV.OC-02`, `GV.SC-01`) más `GV.RM-01`,
`NIS2 Art. 21(2)(f)` y un elemento funcional de IMO. Los expulsados son **IMO 4.2.8/9 y NIS2
Art. 21**.

**No es que las descripciones nuevas sean malas.** Es la explicación más natural y es falsa, así que
se midió: los controles añadidos tras v0.1.0 tienen descripciones **más largas**, no más pobres —
73 caracteres de media frente a 61 de los originales (IMO, 102). El texto nuevo es más rico, no más
vago.

**Tampoco es solape de vocabulario.** Los cuatro contendientes comparten con la consulta exactamente
las **mismas dos palabras** (`gestión`, `riesgo`) y aun así se ordenan distinto:

| Puntuación | Control | Palabras en común con la consulta |
| -- | -- | -- |
| 0,8853 | `CSF GV.RM-01` | 4 (incluye `objetivos`, `ciberseguridad`) — es la respuesta correcta |
| 0,8714 | `CSF GV.RR-02` | 2 |
| 0,8675 | `CSF GV.PO-01` | 2 |
| 0,8492 | `IMO MSC.428(98)` | 2 |
| 0,8451 | `NIS2 Art. 21` | 2 |

Lo que decide el orden es la representación densa, y el mecanismo es el mismo *pooling* en un solo
vector que explica la §8: **el registro global del pasaje domina sobre su asunto concreto.** IMO
carga `Maritime`, `Safety Management Systems`, `SMS`; NIS2 carga `exigidas por ley` y `cadena de
suministro`. Cada una de esas señales distintivas arrastra el vector entero fuera del vecindario de
la consulta, aunque la parte pertinente del control dé en el blanco. Los hermanos de CSF, en cambio,
son prosa de gobernanza genérica de principio a fin, así que se quedan en el centro del vecindario.

Que esto es un **error de ordenación** y no un juicio defendible lo prueba dónde mapea el catálogo a
los que ganan:

```
CTL-CSF-GVRR02  -> CAP-GOV-ROLES     (otra capacidad: roles y autoridades)
CTL-CSF-GVPO01  -> CAP-GOV-POLICY    (otra capacidad: política)
CTL-NIS2-A21    -> CAP-GOV-RISK      <- la capacidad consultada
CTL-IMO-42898   -> CAP-GOV-RISK      <- la capacidad consultada
```

El recuperador está poniendo **los controles de otras capacidades por delante de los de ésta**, y
`CAP-GOV-ROLES` y `CAP-GOV-POLICY` existen como capacidades propias con sus propias consultas. Un
control sobre *roles y autoridades* adelanta a uno titulado literalmente *Cybersecurity
risk-management measures*.

Los dos expulsados no son igual de graves, y conviene separarlos. Que IMO baje por leerse como
marítimo es, para un gasoducto, el sistema **comportándose bien** —es justo lo que UCM-47 formalizó
después—; lo discutible es que la verdad de v0.1.0 lo mapeara aquí. **NIS2 Art. 21 no tiene esa
excusa**: aplica a `energy`, está mapeado a esta capacidad, se titula *Cybersecurity risk-management
measures* y está en el puesto 20. Es el caso más limpio de fallo de todo el experimento.

La causa de fondo es de densidad: CSF pasó de 25 a 106 subcategorías, y en un vecindario denso de un
solo marco la similitud coseno ordena por *parecido de registro*, no por *diversidad de marco*. El
efecto es el peor posible para este proyecto en concreto: **el crecimiento de un marco expulsa del
corte precisamente la variedad transfronteriza —la lectura marítima y la europea— que el motor
existe para poner una al lado de la otra.** Un recuperador que ofrece diez formas de decir *CSF
governance* no está sirviendo a una composición soberana.

Coherente con esto, los vecindarios más densos son los que peor se cortan: `CAP-PR-PATCH` tiene 31
empates a ≤0,01 del décimo y la puntuación máxima más baja de todas (0,846); `CAP-PR-MALWARE`, 28.

## 6. Desplazamiento del top-10

De los 10 primeros de v0.1.0, sobreviven **5,3** en v0.4.0; de los 10 primeros de v0.4.0, **4,7** son
controles que no existían en v0.1.0. Es decir: el crecimiento del catálogo **renueva la mitad de lo
que se le muestra al operador** para la misma capacidad. Eso es exactamente lo que se quiere de un
catálogo que crece —hay mecanismos nuevos y mejores— y a la vez la razón de que el corte necesite
una regla: la mitad que se fue no se fue por ser peor, se fue por ser décima.

## 7. Brazo «solo el título»: la descripción parafraseada carga el ranking

| Versión | 1.º texto / título | 10.º texto / título | recall@10 texto / título |
| -- | -- | -- | -- |
| v0.1.0 | 0,882 / 0,862 | 0,829 / 0,819 | 87,2 % / **79,5 %** |
| v0.4.0 | 0,880 / 0,862 | 0,839 / 0,828 | 77,1 % / **62,0 %** |

Retirar la descripción parafraseada del pasaje y dejar solo el título del control cuesta **15 puntos
de recall@10** en el catálogo actual (77,1 % → 62,0 %), y el daño es mayor cuanto más grande es el
corpus (7,7 puntos en v0.1.0, 15,1 en v0.4.0). La descripción no es adorno: es lo que sostiene el
ranking cuando hay 226 controles compitiendo.

(Los brazos secundarios de este apartado y del siguiente se comparan contra el **77,1 % sin lente**,
no contra el 79,2 % corregido, porque se midieron sin lente: la comparación tiene que ser como con
como, y lo que aquí se aísla es el efecto de la plantilla, no el de la aplicabilidad.)

Esto sustituye al brazo de «descripciones expandidas» que pedía el ticket, y responde a la misma
pregunta por el lado barato: ampliar la prosa del catálogo es una subida de versión con trabajo de
autoría, mientras que retirarla mide el mismo gradiente sin tocar el catálogo. La dirección queda
medida y apunta a favor de descripciones más ricas. Lo que **no** se hizo, deliberadamente, es meter
en el pasaje los nombres de las capacidades a las que un control está mapeado: eso filtraría los
mapeos del autor dentro del vector e inflaría de forma circular la métrica de la sección 5.

## 8. Brazo «consulta enriquecida con la zona»: la dilución, medida

Se añade a la consulta el contexto declarado de la zona (dominio, SL-objetivo, naturaleza técnica,
relevancia para la seguridad física), en español:

| Versión | Zona | 1.º | 10.º | recall@10 | top-10 igual al llano |
| -- | -- | -- | -- | -- | -- |
| v0.4.0 | `Z-OT-CORRIDOR` | 0,854 | 0,827 | **57,8 %** | 6,9/10 |
| v0.4.0 | `Z-SIS` | 0,856 | 0,829 | 61,0 % | 7,2/10 |
| v0.4.0 | `Z-ENG-STATION` | 0,858 | 0,830 | 62,8 % | 7,2/10 |

Frente al 77,1 % de la consulta llana, enriquecer con la zona **pierde entre 14 y 19 puntos de
recall** y cambia 3 de cada 10 candidatos. Se ejecutó para medir la dilución, no esperando que
ganara, y perdió por el margen esperado y por el motivo esperado: un bi-encoder comprime toda la
cadena en un único vector, y buena parte del contexto de una zona es **negación** («sin sistema
operativo de propósito general», «sin usuarios interactivos»). El vector de una negación se parece
al vector de la afirmación que niega. Añadir premisas verdaderas empeoró la recuperación.

Esto es lo que hace la respuesta a la pregunta secundaria del ticket **independiente de la escala**:
la ceguera a la negación es estructural en el modelo, no un síntoma de corpus pequeño. Un e5 con
5.000 controles seguirá sin entender esa frase. La arquitectura que se sigue es la que el proyecto
ya declara: **el recuperador estrecha, el juicio razona** (UCM-53) — y el juez queda como
re-rankeador sobre lo recuperado, nunca como sustituto del recuperador.

## 9. Discriminación entre zonas: 1,000

Ejecutando el servicio completo (núcleo determinista + gating + lente sectorial de UCM-52), el
solape medio del conjunto recuperado entre las dos zonas de `PROFILE-A` es **1,000 en las cuatro
versiones**: el conjunto es idéntico. `PROFILE-B` tiene una sola zona y no admite la comparación.

No es un defecto de la medición, es el estado del sistema medido con un número: la consulta se
construye solo con el texto de la capacidad, así que dos zonas del mismo perfil preguntan lo mismo;
y la lente sectorial de UCM-52 es idéntica en ambas porque los sectores se declaran a nivel de
perfil (`energy` en los dos), no de zona. El activo **todavía no cambia lo que se recupera** — solo
cambia lo que el gating marca después. Cerrar esa distancia es trabajo de UCM-52, y ahora tiene una
línea base contra la que demostrarse.

## 10. La invariante, en cada punto

| Versión | Perfil | Pares capacidad-zona | Huecos declarados | Candidatos del catálogo perdidos |
| -- | -- | -- | -- | -- |
| v0.1.0 | A / B | 48 / 24 | 0 / 0 | **0 / 0** |
| v0.2.0 | A / B | 74 / 37 | 0 / 0 | **0 / 0** |
| v0.3.0 | A / B | 74 / 37 | 0 / 0 | **0 / 0** |
| v0.4.0 | A / B | 74 / 37 | 0 / 0 | **0 / 0** |

Omisiones silenciosas: **0**, en los cuatro tamaños. Es la invariante 2 medida a lo largo de toda la
curva, no solo en la versión activa. Nótese que convive con el recall del 59,4 %: no hay
contradicción, porque los candidatos del catálogo los aporta el núcleo determinista y la
recuperación solo añade. Un recall bajo del recuperador significa **peores sugerencias**, nunca
cobertura perdida.

## 11. Coste y latencia en la máquina objetivo

| Versión | Controles | Construir el índice | encode de la consulta | Qdrant | Consulta total |
| -- | -- | -- | -- | -- | -- |
| v0.1.0 | 69 | 4,3 s | 101 ms | 13,5 ms | 114 ms |
| v0.2.0 | 225 | 14,9 s | 104 ms | 13,2 ms | 117 ms |
| v0.4.0 | 226 | **14,9 s** | **101 ms** | **8,2 ms** | **109 ms** |

La construcción del índice escala linealmente con el corpus (~66 ms por control, un hilo) y se paga
una vez al arrancar. La consulta **no escala con el catálogo**: 101 ms de los 109 son el encode de
la consulta —un coste fijo del modelo en esta CPU, independiente del tamaño— y la parte de Qdrant se
queda entre 8 y 14 ms en todos los tamaños, con la variación dominada por el ruido de medida y no
por el corpus. Multiplicar el catálogo por 3,3 no encareció la recuperación de forma observable. El
cuello de botella del recuperador es el modelo de embeddings, no el índice.

Un apunte de reproducibilidad, obtenido gratis: el experimento se ejecutó dos veces con
reconstrucción completa de los índices, y **todas las métricas deterministas salieron idénticas**
(banda, empates, recall, desplazamiento). Solo se movieron las latencias, que es exactamente lo que
`app/retrieval/embeddings.py` promete y lo que la invariante 3 exige.

## 12. Sonda: ¿y si el corte no fuera «los diez primeros»?

Los apartados anteriores miden el recuperador **tal como está**. Éste es distinto y se etiqueta como
lo que es: una **sonda de un solo punto** (v0.4.0, 24 capacidades, lente sectorial aplicada, verdad
corregida), ejecutada para responder a una pregunta concreta —*¿conviene dar prioridad a los
controles de ámbito sectorial sobre los transversales?*— antes de que UCM-54 elija una regla. No es
la curva de los apartados 3–11 y no debe citarse como si lo fuera.

| Política de corte | recall@10 | marcos distintos en el top-10 |
| -- | -- | -- |
| coseno puro (lo actual) | 79,2 % | 3,04 |
| **primero los de ámbito sectorial** | **7,3 %** | **1,00** |
| reservar 2 huecos a los sectoriales | 77,3 % | 3,46 |
| máximo 3 por marco | 79,4 % | **4,00** |
| **máximo 4 por marco** | **82,2 %** | 3,67 |

**La prioridad sectorial es la peor política posible, y por un motivo estructural.** En este catálogo
el ámbito sectorial está perfectamente confundido con el marco: los 20 controles que lo declaran son
**exactamente IMO (7) y NIS2 (13)** —CIS, CSF e IEC son transversales por naturaleza, porque son
marcos voluntarios y no derecho sectorial—. Filtrado a `energy` quedan **13 artículos de NIS2**, así
que «primero los sectoriales» convierte el top-10 en diez de esos trece **para cualquier consulta**:
los mismos controles para MFA, para copias de seguridad y para parcheo. Deja de ser recuperación y
pasa a ser una lista constante. Es el fallo de la §3 llevado a su límite.

Lo que sí funciona es atacar la enfermedad en vez de un indicador suyo. **Un tope por marco mejora
recall y diversidad a la vez.** En `CAP-GOV-RISK`, el top-10 de hoy es `[CSF ×9, NIS2 ×1]` sin
Art. 21; con tope 3 pasa a `[CSF ×3, NIS2 ×3, IEC ×3, CIS ×1]` y **NIS2 Art. 21 aparece en el puesto
5** — la respuesta correcta emerge sin que nadie codifique «NIS2 gana». Encaja además con las
invariantes mejor que una regla sectorial: es una regla determinista sobre datos declarados
(invariante 1) y es auditable mientras lo desplazado siga visible, como ya hace `set_aside`
(invariante 2).

Dos cautelas antes de que esto sea una decisión: son 24 capacidades medidas contra los mapeos del
propio autor, así que +3 puntos es indicativo y no concluyente, y la diferencia entre tope 3 y tope 4
cae dentro del ruido esperable a este tamaño de muestra. Y un tope interactúa con la otra pregunta
abierta de UCM-54: si se recupera ancho para que un juez reordene (§13.3), el tope va en el **corte
final**, no en la recuperación, o se le retiran al juez justo los candidatos que debía sopesar.

## 13. Qué se sigue de esto

1. **El recuperador ya tiene trabajo real** (4,4 % del catálogo por consulta) **y a la vez discrimina
   peor que cuando tenía menos**. Las dos cosas son ciertas y la segunda es la que manda.
2. **UCM-54 (el top-k auditable) sube de prioridad y tiene datos, incluida una regla candidata.**
   ~15 controles indistinguibles caen en cada corte, y lo que cae es sistemáticamente la diversidad
   de marco. Un corte por número fijo no es neutral en un catálogo desequilibrado (CSF=106, IEC=51,
   CIS=49, NIS2=13, IMO=7). La sonda de la §12 apunta a un **tope por marco** como regla —mejora
   recall y diversidad a la vez— y descarta la prioridad sectorial, que es catastrófica.
3. **UCM-53 (juicio LLM) queda justificado como re-rankeador**, y por las razones medidas en §5 y §8
   —el registro del pasaje domina sobre su asunto, y la negación es estructuralmente invisible— no
   por una intuición sobre el tamaño. Con una salvedad que el dato impone: **un re-rankeador sobre
   el top-10 no puede arreglar lo que aquí se mide.** `NIS2 Art. 21` está en el puesto 20 y
   `IMO MSC.428(98)` en el 17: alimentado con diez candidatos, el juez reordenaría diez hermanos de
   CSF y la respuesta correcta seguiría ausente. El recall por profundidad dice a qué precio se
   arregla — 77,1 % a 10, 86,1 % a 20, 93,1 % a 50 —, así que la arquitectura que se sigue es
   **recuperar ancho y juzgar hacia abajo**: pedir 25-50 candidatos y que el juez los ordene a 10.
   Eso convierte a UCM-54 en **prerrequisito** de UCM-53, no en ticket paralelo.
4. **UCM-52 tiene su línea base**: solape 1,000 entre zonas es el número que su trabajo debe mover.
   Y sabe además cuál es su techo: la lente sectorial no mueve el recall (§5), porque solo 20 de 226
   controles declaran ámbito y los que apiñan el corte son transversales.
5. **Descripciones más ricas ayudan** (§7): 15 puntos de recall@10 dependen de la prosa del catálogo.
6. **La baseline dorada hay que re-congelarla antes de UCM-18**, con la aplicabilidad sectorial
   incorporada al juicio del autor. Ver el apartado siguiente.

## Lo que este experimento no midió

**Precisión y recall contra la baseline dorada.** El instrumento **existe** (UCM-5, cerrado el
2026-07-23) pero vive fuera del repositorio a propósito: se construyó ciego al catálogo, en sesión
limpia, y lo mantiene y congela el autor de su lado. La invariante 9 impide además que el motor lo
lea. Lo que aquí se llama «recall» es contra los mapeos del propio autor, que es una vara más débil
y se nombra como tal en todo el documento.

Pero hay algo que este experimento sí puede decir sobre esa medición, y es una advertencia con
número: **la baseline dorada está congelada contra el mundo de v0.1.0** —24 capacidades, 69
controles— y el catálogo activo tiene 37 y 226. La métrica de «verdad congelada» de la §5 tiene
exactamente esa forma —juzgar un corpus de 226 con la vara de 69— y ya se vio lo que produce: un
recall que cae del 88,5 % al 79,2 % **sin que el motor haya empeorado en nada**, solo porque
aparecieron controles que la vara no conoce. Si UCM-18 enfrenta el motor actual a la baseline de
v0.1.0 sin re-congelarla, medirá una regresión de ~9 puntos que es un artefacto del instrumento,
y además no dirá absolutamente nada sobre las 13 capacidades nuevas, que quedarían fuera de la
evaluación sin que ningún número lo delate. **Antes de UCM-18, la baseline dorada hay que
re-congelarla contra v0.4.0** — y esa segunda versión, por el mismo método ciego, sigue siendo un
instrumento válido.

La corrección por aplicabilidad de la §5 es **la misma enfermedad en pequeño, ya diagnosticada**: un
solo control (`IMO MSC.428(98)`) que la vara de v0.1.0 exige y que el motor aparta con razón, y que
por sí solo valía 1,3 puntos de recall mal atribuidos. La baseline dorada, congelada en la misma
época y por tanto también ciega al ámbito sectorial de UCM-47, tendrá ese mismo defecto repartido
por todo el documento. Al re-congelarla, la aplicabilidad sectorial debe formar parte del juicio del
autor: si un control no gobierna el sector del activo, no pertenece al patrón de oro de ese activo.
