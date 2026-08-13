# Nota de alineación con marcos reconocidos

Material para la memoria (UCM-24) y los anexos (UCM-25). Producto de UCM-46.

El motor no persigue la conformidad con ninguna norma: es un POC de investigación. Lo que sí hace
—y esto es lo que esta nota declara— es **implementar las disciplinas que los marcos reconocidos
exigen para documentar una línea base**, y emitirlas como el artefacto documental que un revisor
espera ver (`GET /api/v1/baseline/{id}/statement`). Cada cláusula citada aquí se ha verificado
contra su fuente antes de escribirse; las fuentes están al final.

## Criterios cumplidos y su norma de referencia

| Criterio | Norma de referencia | Dónde se implementa |
| -- | -- | -- |
| **Inclusión y exclusión justificadas, control a control** | ISO/IEC 27001:2022, cl. **6.1.3 d)**: la declaración de aplicabilidad contiene los controles necesarios, la **justificación de su inclusión**, si están implantados o no, y la **justificación de la exclusión** de controles del Anexo A | `app/baseline/statement.py`; cada mecanismo lleva `disposition`, `rule_id`, `evidence` y la razón escrita registrada |
| **Ajuste de una línea base a un sistema concreto** (*tailoring*) | NIST **SP 800-53B**, guía de *tailoring*: designar controles comunes, aplicar consideraciones de alcance (*scoping*), **seleccionar controles compensatorios**, asignar parámetros y suplementar la línea base. Recogido como control en **SP 800-53 Rev. 5 PL-11** (*Baseline Tailoring*) | `app/engine/gating.py` (UCM-9): los tres desenlaces son *no aplica*, *objetivo sin mecanismo* (compensatorio debido) y *ámbito equivocado* |
| **Plan de seguridad del sistema como documento** | NIST **SP 800-53 Rev. 5 PL-2** (*System Security and Privacy Plans*) | el documento firmado, exportable además como SSP parcial de OSCAL |
| **Documento legible por máquina** | NIST **OSCAL 1.1.3**, modelo `system-security-plan` | `app/baseline/oscal.py`; crosswalk completo en [`oscal-crosswalk.md`](oscal-crosswalk.md) |
| **Requisitos derivados del nivel de seguridad objetivo por zona** | **IEC 62443-3-2**: ZCR 3 particiona el sistema en zonas y conductos, ZCR 5 fija el SL-T de cada zona, **ZCR 6 documenta la CRS** (*cybersecurity requirements specification*) | `app/engine/zones.py` y `app/engine/prioritization.py`: el Tier 0 se lee del SL-objetivo (vector por FR) de cada zona |
| **Correspondencia requisito ↔ nivel de seguridad** | **IEC 62443-3-3**: cada SR es exigible a partir de un SL | `ControlStrength(kind="sl_baseline", level=n)` en el catálogo; el mandato registra `required_at_sl` frente a `zone_sl_target` |
| **Perfil como instrumento de priorización** | **NIST CSF 2.0**: los *Organizational Profiles* describen la postura actual y la objetivo en términos de los resultados del *Core* (seis funciones, con **Govern** añadida en 2.0) | el perfil del activo + la hoja de ruta por fases (Tier 1) son la lectura «actual → objetivo» de este motor |
| **Priorización sin cifras inventadas** | Gordon-Loeb **en espíritu**, con escalas ordinales; grupos de implantación **CIS v8 (IG1/2/3)** como priorización TI ya hecha | `app/engine/prioritization_rules.py` |
| **Revisión independiente de la línea base** | práctica común a ISO 27001 (cl. 9.2) y a los tres anteriores | firma humana con actor, razón y momento; revisión con el CISO de la ACP (UCM-6) |
| **Trazabilidad de punta a punta y no repudio del registro** | disciplina transversal (ISO/IEC 27001 cl. 7.5 *información documentada*) | bitácora *append-only* encadenada por hash (UCM-11), verificable desde el propio documento |
| **Reproducibilidad de la evidencia** | no es exigencia de ninguna de las normas citadas — es una exigencia de este TFM | catálogo, reglas, *prompt* y modelo versionados; temp 0 + *seed* fija; el documento se proyecta de la bitácora y refleja las versiones que rigieron la firma |

## Dónde el motor no encaja con la norma, y por qué

Tres desajustes, declarados porque son parte del resultado y no defectos que ocultar.

1. **La unidad no es el control, es la capacidad.** El SoA de ISO/IEC 27001 pregunta por cada
   control del Anexo A si aplica. Aquí el *gating* quita mecanismos y **nunca capacidades
   exigidas**, así que ninguna fila del documento puede declarar que un requisito no aplica: lo que
   varía es *cómo* se satisface, y las exclusiones justificadas viven un nivel más abajo, en cada
   mecanismo. La correspondencia es exacta en la disciplina (inclusión justificada, exclusión
   justificada, nada omitido en silencio) y deliberadamente inexacta en la unidad.

2. **OSCAL no tiene estado para «hueco asumido por escrito».** Ninguno de los cinco valores de
   `implementation-status` describe un requisito que sigue exigido, sin mecanismo, y asumido con
   una justificación firmada: no es `planned` (no hay plan), ni `not-applicable` (la capacidad
   sigue exigida), ni `alternative` (no hay alternativa). El export lo emite como `partial` y lo
   desambigua con una propiedad de extensión y una nota que explica el desajuste. Es un hallazgo
   sobre el formato, no un problema del motor: **en este punto el motor es más estricto que el
   estándar que lo transporta.**

3. **El motor no clasifica la información del activo.** `system-information` es obligatorio en el
   modelo SSP; el export declara un único tipo genérico sin niveles de impacto en vez de inventar
   una tripleta FIPS-199 que nadie ha calculado.

## Qué añade este motor a lo que las normas ya piden

Un *crosswalk* traduce (A ≈ B). Las normas citadas dicen **qué** documentar. Ninguna de ellas
resuelve el problema que este TFM aborda: qué hacer cuando varios marcos con distinta jurisdicción
y distinta granularidad concurren sobre la misma capacidad de un activo OT/IT. La aportación es la
**composición soberana** — opciones equivalentes lado a lado, con marco, jurisdicción, exigencia
declarada y tipo de mapeo, para que **la persona elija por zona y firme** — y el documento que
resulta la deja registrada: quién eligió, entre qué, por qué, bajo qué catálogo y contra qué
entrada de la bitácora.

## Fuentes verificadas

* ISO/IEC 27001:2022, cl. 6.1.3 d) — declaración de aplicabilidad.
* NIST SP 800-53B, *Control Baselines for Information Systems and Organizations* —
  <https://csrc.nist.gov/pubs/sp/800/53/b/upd1/final>
* NIST SP 800-53 Rev. 5, PL-2 y PL-11 — <https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final>
* NIST OSCAL, modelo SSP v1.1.3 —
  <https://pages.nist.gov/OSCAL-Reference/models/v1.1.3/system-security-plan/>
* IEC 62443-3-2:2020, pasos ZCR 3 / ZCR 5 / ZCR 6 —
  <https://webstore.ansi.org/preview-pages/IEC/preview_iec62443-3-2%7Bed1.0%7Den.pdf>
* NIST CSF 2.0, *Organizational Profiles* — <https://www.nist.gov/cyberframework/profiles>

> Nota de honestidad sobre las citas de IEC 62443: la atribución de SL a cada SR en el catálogo
> procede de fuentes secundarias públicas y está pendiente de contraste con la norma comprada, tal
> y como ya declara cada mandato en la propia bitácora. Esta nota no mejora esa situación: la
> hereda y la repite.
