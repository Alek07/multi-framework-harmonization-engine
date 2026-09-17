# Premisas del control — que el catálogo sepa lo que cada control presupone (UCM-53)

> Estado: implementado en la rama `feature/UCM-53_control-presuppositions`.
> Catálogo **v0.5.0** · reglas de gating **v0.2.0** · orden del recuperador **v1**.

## El hueco

El perfil siempre supo que la zona no tiene estaciones de trabajo. El catálogo nunca supo que el
control las necesita. **No había nada que comparar** — y ese es el hueco entero.

Cuando el operador escribe «en esta zona OT no hay ninguna workstation»:

1. `parse` captura la negación correctamente: `nature.general_purpose_os = false`,
   `interactive_users = false`, **por zona**, y el operador lo confirma.
2. El gating lee esos flags, pero solo puede excluir los **108 de 226** controles que alguna de las
   28 reglas escritas a mano nombra. Los otros **118 se retienen para cualquier activo**.
3. El recuperador no ve nada de esto: su consulta es `capability_text(capability)` y nada más. Por
   eso el conjunto recuperado para `Z-SIS` y `Z-OT-CORRIDOR` es **idéntico** — solape 1,000 en las
   cuatro versiones del catálogo medidas en UCM-51.

## Por qué no se arregla con un recuperador mejor

**La ceguera a la negación es estructural en un bi-encoder.** `"no hay workstation"` y
`"workstation"` caen casi en el mismo punto de un vector de 768 dimensiones, y eso no mejora con la
escala del corpus. Está medido: el brazo que enriquecía la consulta con el contexto de zona **costó
14-19 puntos de recall@10** (77,1 % → 57,8 / 61,0 / 62,8 % en las tres zonas), porque buena parte
de ese contexto es negación y el bi-encoder la comprime junto con todo lo demás
([experimento-escalado-recuperador.md §9](experimento-escalado-recuperador.md)).

La vía obvia está cerrada por medición. La que queda es declarar el otro lado de la comparación.

## Qué se ha hecho

### 1. El catálogo declara el hecho

`FrameworkControl.presupposes`: una lista de premisas del vocabulario **cerrado** de `TechNature`
(`general_purpose_os`, `networked`, `hybrid_it_ot`, `interactive_users`, `office_it_surface`), cada
una con el valor que la zona debe tener y una nota que explica por qué.

```json
{
  "id": "CTL-CIS-1001",
  "title": "Deploy and Maintain Anti-Malware Software",
  "presupposes": [
    {
      "premise": "general_purpose_os",
      "expected": true,
      "note": "Requiere un sistema operativo de propósito general donde instalar y mantener el agente."
    }
  ]
}
```

Es un **hecho sobre el control**, no una decisión sobre ningún activo. Una lista vacía no afirma que
el control sea universal: dice que no se le ha declarado ninguna premisa. **La ausencia de premisa
nunca excluye**, así que los catálogos anteriores a v0.5.0 siguen cargando y retienen exactamente lo
que retenían.

### 2. El gating decide

`app/engine/presuppositions.py`, regla `GATE-PREMISE-UNMET`. Una sola regla derivada que cubre todo
control que declare una premisa, en vez de 118 escritas a mano. Produce un `GatingDecision` normal:
salida `not_applicable`, `rule_id`, la premisa leída del perfil como evidencia, y la nota del propio
catálogo dentro de la justificación.

Tres asimetrías la hacen segura:

- **Sin premisa declarada no excluye nada.**
- **Una regla escrita a mano siempre gana.** Quien escribió una regla nombrando el control sabía más
  que su descripción; la determinación derivada queda en `also_matched_rule_ids`, no se pierde.
- **Quita mecanismos, nunca capacidades.** Como todas las demás salidas de gating.

### 3. El recuperador ordena, y nunca quita

`ORDERING_VERSION = "v1"`, `sink_gated` en `app/retrieval/schemas.py`, aplicado en el servicio
**después** del corte. Una sugerencia que el gating de la zona ya descartó se lee **la última** y se
lee **marcada** (`gated_out`). Aplicarlo antes del corte cambiaría qué sugerencias sobreviven, y eso
es decisión del corte (UCM-54), no de esta regla. Enterrarla sería la omisión silenciosa que UCM-54
existe para impedir; ocultarla sería peor.

### 4. El etiquetador — el LLM, una vez y fuera del camino de petición

`app/tagging/` + `scripts/tag_presuppositions.py`. Recorre el catálogo una vez, pregunta al modelo
qué presupone cada control, **criba las respuestas de forma determinista** y escribe una
**propuesta**. Nunca toca el catálogo.

La cadena completa es: **el modelo propone → un guard determinista criba → el humano autoriza → una
regla decide.**

El paso «el humano autoriza» tiene su propio comando, `scripts/merge_presuppositions.py`, para que
no sea cinco ficheros JSON editados a mano:

```bash
uv run python scripts/merge_presuppositions.py --dry-run           # qué se mezclaría
uv run python scripts/merge_presuppositions.py                     # mezclar todo lo propuesto
uv run python scripts/merge_presuppositions.py --exclude CTL-CIS-0202   # todo menos ese
```

La mezcla es **textual y quirúrgica** (`app/tagging/merge.py`): las fuentes llevan un control por
línea, y eso es justo lo que hace legible el `git diff` de un cambio como este — el revisor ve el
puñado de controles que ganaron una premisa, no 226 líneas reescritas para decir lo que ya decían.
Un `json.dump` del fichero entero destruiría exactamente eso. `--only` y `--exclude` existen porque
el veredicto del revisor es por control, y la forma honesta de dejar constancia de «estos sí, esos
no» es correr la mezcla con esa lista, no editar la propuesta hasta que dé la razón.

El guard es lo que hace la propuesta revisable sin un segundo modelo: se le exige al LLM que
**cite el fragmento** del texto del control del que leyó la premisa, y `app/tagging/guard.py`
comprueba que la cita aparezca de verdad en el título o la descripción (normalizando acentos,
mayúsculas y puntuación, porque el modelo re-teclea en vez de copiar). Una premisa que el modelo
recordó de su entrenamiento en lugar de leerla en la frase que tiene delante se cae mecánicamente,
con su motivo, y viaja igualmente al fichero como `RejectedPremise` — el revisor es la autoridad y
el guard puede equivocarse.

El riesgo de diseño no es la invención, es el **sobre-etiquetado**: preguntado «¿qué presupone este
control?», un 7B encuentra una presuposición en casi cualquier frase, y un catálogo donde todos los
controles presuponen un SO discrimina exactamente igual de mal que uno donde ninguno lo hace,
mientras parece un avance. El prompt (versión `0.1.0`) empuja en contra con cuatro recursos: la
respuesta por defecto se enuncia primero y como normal, la prueba es física («¿tendría sentido en un
dispositivo sellado, sin SO, sin pantalla y sin nadie delante?»), la cita obligatoria, y la
prohibición explícita de juzgar ningún activo.

## Por qué offline y no en cada petición

| | Etiquetado offline | Juicio en cada petición |
| -- | -- | -- |
| Coste por composición | **0** | minutos por zona en la máquina de 8-16 GB |
| Reproducibilidad | total: es un JSON firmado en Git | temp 0 + seed, pero el modelo en el camino |
| Revisión humana | una vez, sobre 226 controles | imposible de revisar en cada corrida |
| Un 7B en el camino de una línea base | no | sí |

La lectura que hace falta es **la misma para todo activo, toda zona y toda corrida**. Hacerla una
vez, bajo revisión, compra una respuesta determinista para siempre.

## Medición

`uv run python scripts/gating_report.py` da las tres lecturas, antes y después del etiquetado.

**Antes** (catálogo v0.5.0 con `presupposes` vacío en todo — idéntico a v0.4.0 en comportamiento):

```
controles nombrados por alguna regla:     108/226 (48%)
controles que declaran alguna premisa:      0/226 (0%)
controles que ni regla ni premisa miran:  118

Discriminación (controles que cambian de salida entre zonas)
  Z-OT-CORRIDOR  vs Z-SIS            6/226
  Z-OT-CORRIDOR  vs Z-ENG-STATION   23/226
  Z-SIS          vs Z-ENG-STATION   28/226
```

**Después de la primera corrida del etiquetador** (prompt `0.1.0`, 226 controles, ~15 s cada uno):

```
controles con alguna premisa tras el guard:   9/226 (4%)
premisas: networked 3 · interactive_users 3 · general_purpose_os 2 · hybrid_it_ot 1
por marco: CIS 5 · CSF 4 · IEC62443 0 · NIS2 0 · IMO 0
rechazadas por el guard: 2
```

**Y el resultado es negativo, que es un dato y se declara como tal.** De las 9 propuestas, **8 caen
sobre controles que ya tienen una regla escrita a mano**, y la precedencia hace que gane la regla:
no cambian nada. La novena, `CTL-CIS-0202`, es la más discutible de todas — «asegurar que el
software autorizado sigue teniendo soporte» no presupone un sistema operativo de propósito general,
porque el firmware también tiene soporte de fabricante. **Efecto neto sobre la línea base: cero, o
una exclusión equivocada.** No se ha mezclado nada en el catálogo.

Dos propuestas eran directamente erróneas: `CTL-CSF-GVRM05` («vías de comunicación del riesgo») →
`networked`, que confunde comunicación organizativa con una red, y `CTL-CSF-GVSC08` («proveedores en
respuesta a incidentes») → `hybrid_it_ot`, que no viene a cuento.

**Diagnóstico.** El prompt `0.1.0` se pasó de frenada contra el sobre-etiquetado: la prueba del
«dispositivo sellado» es tan vívida que el modelo responde «nada» al 96 % del catálogo, incluidos
los **51 SR de IEC 62443** —controles técnicos, donde las premisas realmente viven— de los que
etiquetó **cero**. Lo poco que produjo se concentró en gobernanza y formación, que el gating ya
trata como `wrong_scope`. Calibrar entre «no inventes» y «no calles» es el problema real de esta
etapa, y una sola frase del prompt lo mueve de un extremo al otro.

**Lo que sí funcionó**, y es lo que hace la etapa defendible:

- El **guard** rechazó 2 propuestas, una de ellas con una cita inventada que llevaba hasta la errata
  («programa de concienciaccín»). Exigir la cita convierte una alucinación en un rechazo mecánico.
- La **precedencia** impidió que 8 premisas dudosas tocaran una sola decisión del motor. «Quien
  escribió una regla nombrando el control sabía más» dejó de ser una frase y fue la salvaguarda que
  absorbió un mal resultado del modelo.
- La **reproducibilidad**: el mismo control preguntado dos veces devuelve la misma respuesta, así
  que la corrida es citable y comparable contra la siguiente versión del prompt.

### La calibración: prompt 0.2.0 y 0.2.1

Lo que compró la primera corrida no fue un catálogo etiquetado: fue **saber en qué dirección estaba
descalibrado el prompt**. Y como el prompt es una entrada versionada del resultado, corregirlo es un
acto trazable, no un retoque.

**0.2.0** ataca el diagnóstico con tres cambios: la prueba pasa a dos pasos y pregunta por el
**mecanismo** que el control nombra, no por el objetivo que persigue; las familias que el gating ya
resuelve (gobernanza, política, inventarios, proveedores, formación, planificación de incidentes)
se saltan de entrada, para que el modelo no gaste su respuesta donde una regla escrita a mano va a
ganarle; y un ejemplo resuelto enseña un control técnico leído bien al lado de uno leído mal.

**0.2.1** corrige un fallo que solo se ve corriendo: el ejemplo del antimalware era casi literal un
control real del catálogo (`CTL-CIS-1001`), y sobre ese control el modelo **copió la cita del
ejemplo** en lugar de leerla del control que tenía delante — cosa que el guard rechazó, con razón,
perdiendo una premisa que 0.1.0 sí había acertado. Un ejemplo que un modelo puede plagiar es una
trampa, así que los ejemplos pasan a ser controles inventados que no aparecen en ningún catálogo.
De paso, es la segunda vez que el guard atrapa algo que ningún test habría visto.

Sonda sobre los nueve casos que 0.1.0 falló o no miró (mismo modelo, temp 0, seed fijo):

| Control | 0.1.0 | 0.2.1 | Correcto |
| -- | -- | -- | -- |
| `CTL-CSF-GVRM05` (vías de comunicación) | networked | networked | nada |
| `CTL-CSF-GVSC08` (proveedores en incidentes) | hybrid_it_ot | **nada** | nada |
| `CTL-CSF-PRAT01` (formación) | interactive_users | **nada** | nada |
| `CTL-CIS-0202` (soporte del software) | general_purpose_os | general_purpose_os | discutible |
| `CTL-CIS-1001` (antimalware) | general_purpose_os | general_purpose_os | general_purpose_os |
| `CTL-CIS-1207` (VPN/AAA) | networked | networked | networked |
| `CTL-IEC-SR11` (autenticación de usuarios) | *no lo miró* | **interactive_users** | interactive_users |
| `CTL-IEC-SR32` (protección frente a código malicioso) | *no lo miró* | **nada** | nada |
| `CTL-IEC-SR24` (código móvil) | *no lo miró* | nada | discutible |

**3 aciertos de 9 → 7 de 9.** Y lo importante no es el marcador: es que 0.2.1 **lee por fin la IEC
62443**, y que distingue `SR 3.2` («proteger frente a código malicioso» — un objetivo) de un control
que nombra un agente. Esa distinción es exactamente lo que separa una premisa real de una inventada.

`CTL-CSF-GVRM05` sigue mal en 0.2.1, y se declara: ya tiene `GATE-SCOPE-GOVERNANCE`, así que la
precedencia lo deja inerte de todas formas. Es el caso que muestra por qué la precedencia no es una
formalidad.

### Con las premisas ya mezcladas

Tras mezclar las 25 premisas revisadas, medido sobre los dos perfiles de referencia con
`scripts/gating_report.py`:

| Medida | Antes | Después |
| -- | --: | --: |
| Controles que ni regla ni premisa miran | 118 | **107** |
| Controles que solo la premisa mira | 0 | **11** |
| Discriminación `Z-OT-CORRIDOR` vs `Z-ENG-STATION` | 23/226 | **30/226** |
| Discriminación `Z-SIS` vs `Z-ENG-STATION` | 28/226 | **34/226** |

Controles retenidos por zona, que es donde se ve que el efecto cae exactamente donde debe:

| Zona | Premisas de la zona | Retenidos |
| -- | -- | --: |
| `PROFILE-A` / `Z-OT-CORRIDOR` | sin SO de propósito general, sin usuarios | 117 → **110** (−7) |
| `PROFILE-A` / `Z-SIS` | ídem, y además *crown jewel* | 112 → **106** (−6) |
| `PROFILE-B` / `Z-ENG-STATION` | las cinco a `true` | 140 → **140** (0) |

**La estación de ingeniería no pierde ni un control.** Una premisa solo excluye donde la zona
declara lo contrario, y aquí eso se comprueba en vez de prometerse: las exclusiones nuevas se
concentran enteras en las dos zonas OT, que son las que no tienen ni sistema operativo de propósito
general ni a nadie conectado. La discriminación entre perfiles —la métrica de UCM-55— sube en las
dos parejas que la admiten.

### La revisión humana no fue un trámite

Las 28 premisas propuestas no entraron enteras. **Tres se rechazaron**, y no por capricho: las tres
están redactadas como **objetivos**, que es el error que el prompt 0.2.0 debía eliminar y solo
eliminó a medias.

| Control | Premisa propuesta | Por qué se rechaza |
| -- | -- | -- |
| `CTL-CSF-PRPS05` | `general_purpose_os` + `interactive_users` | «Se impide la instalación y ejecución de software no autorizado» es un objetivo: en un PLC sellado se cumple con arranque seguro y firma de firmware |
| `CTL-CSF-DECM09` | `general_purpose_os` + `networked` | Vigilar la integridad del software de un embebido sigue aplicando |
| `CTL-CIS-0202` | `general_purpose_os` | El firmware también tiene soporte del fabricante |

**Quien las cazó fue la baseline congelada, no el guard.** El guard comprueba que la cita esté
anclada en el texto del control; una premisa bien citada pero mal razonada le pasa por delante. Lo
que la detuvo fue `tests/engine/test_gating.py`, al ver que `CAP-PR-MEDIA` se quedaba **sin su único
control compensatorio** en el corredor OT. Es el argumento de por qué la baseline dorada se congela
en un test: es un instrumento de medida del contenido del catálogo, no solo del código.

### Lo que las premisas costaron, declarado

Dos consecuencias que la suite obligó a mirar de frente en vez de absorber:

- **`CAP-PR-MFA` baja de 0,6 a 0,5 de cobertura** en el corredor OT. La causa es `SR 1.7`, que gradúa
  la robustez de la autenticación **por contraseña** y ahora declara que presupone usuarios
  interactivos. La partición dentro de FR1 queda limpia: `SR 1.7` (contraseñas, humanas) se va por
  premisa, y `SR 1.9` (clave pública, que es como se autentica un dispositivo) se va por la regla
  criptográfica que ya existía.
- **Los mandatos abiertos de `PROFILE-A` pasan de 11 a 13.** `CAP-PR-SESSION` se abre en las **dos**
  zonas OT: `SR 2.5` y `SR 2.6` presuponen usuarios interactivos, y sin nadie conectado no hay sesión
  que bloquear ni que terminar. El mecanismo se va y **el mandato sigue abierto**, que es la regla de
  oro del gating hecha visible en la bitácora: el requisito no desapareció con su mecanismo, aterrizó
  en el humano, que ha de compensarlo o aceptar el hueco por escrito.

### Lo que el segundo prompt cambió, en números

| | prompt 0.1.0 | prompt 0.2.1 |
| -- | --: | --: |
| Controles con premisa propuesta | 9/226 | **28/226** |
| De ellos, en IEC 62443 | **0** | **8** |
| Sobre controles sin regla previa (los que deciden algo) | 1 | **14** |
| Rechazados por el guard | 2 | 0 |
| Rechazados por el revisor humano | — | **3** |
| Premisas finalmente en el catálogo | 0 | **25** |

Los que deciden algo son de los que se esperan: `SR 1.1` (autenticación de usuarios humanos),
`SR 1.5` (gestión de autenticadores), `SR 1.7` (robustez de contraseñas), `SR 2.5` (bloqueo de
sesión) → `interactive_users`; `SR 5.1` (segmentación), `PR.IR-01`, `DE.CM-01`, `CIS 12.2` →
`networked`.

Y la mitad de las propuestas caen sobre controles que **ya tenían regla escrita a mano y coinciden
con ella** (antimalware → SO, MFA remoto → red, bloqueo de sesión → usuarios). No cambian nada, por
precedencia, pero son una validación cruzada independiente de reglas que un humano escribió antes.

## Lo que esto NO arregla

El juicio nunca elimina, así que **el conjunto recuperado sigue siendo el mismo en ambas zonas**: el
solape 1,000 se queda como está. Lo que cambia es la salida del gating por zona, el orden y la
anotación. La métrica que se mueve es la de discriminación de UCM-55, no el solape del recuperador.

Filtrar de verdad en la recuperación exigiría una lente declarada por el operador, con su
`set_aside` para que lo apartado siguiera siendo visible. Queda como trabajo futuro escrito, no como
un descuido.
