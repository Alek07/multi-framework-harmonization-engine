# Guion de la demo — escenarios de prueba

Tres descripciones de activo listas para recorrer el motor de principio a fin. La primera es el caso
de referencia (un gasoducto de transporte, el activo alrededor del cual se escribió el catálogo). La
segunda vuelve al sector de referencia a propósito, para aislar la divergencia entre **tres zonas de
un mismo activo**. La tercera es un activo de un sector **por completo distinto** —una terminal de
contenedores marítima—, para ver la variación: el motor lee **premisas declaradas**, no el
vocabulario de una industria.

## Cómo usarlas en la aplicación

La aplicación es una sola vista con cinco pasos. Para cada escenario:

1. **Describir** — pega el texto del activo en el cuadro y pulsa **Analizar la descripción**. El
   modelo extrae y **cita** cada campo; lo que no logra ubicar lo lista aparte, no lo descarta.
2. **Revisar ◆** — repasa el borrador. Todo campo es editable y `◆` marca tus correcciones. La
   aplicación no deja avanzar mientras quede un valor obligatorio sin decidir.
3. **Elegir** — para cada capacidad aparecen las opciones equivalentes lado a lado (marco,
   jurisdicción, fuerza, tier) y qué ha quitado el gating y por qué. Eliges por zona.
4. **Comparar** — lee una zona bajo una región y bajo otra (US → +EU) para ver el delta regional.
5. **Firmar** — la aplicación verifica que el bloque obligatorio esté completo y firmas. Luego, el
   **registro**: la bitácora encadenada, descargable como declaración de aplicabilidad (SoA / OSCAL).

Componer, firmar y leer la bitácora **no necesitan IA**: funcionan con el modelo apagado. Lo único
que espera al modelo es el paso 1, y también puede rellenarse a mano.

> Plan B declarado: si la interfaz falla, los mismos escenarios se recorren desde Swagger
> (`http://localhost:8000/docs`).

---

## Escenario 1 — Gaseoducto · transporte de gas

**Qué demuestra:** el caso principal. Dos zonas de OT puro y un sistema instrumentado de seguridad
(SIS) como joya de la corona; muestra cómo **una sola premisa declarada** (marcar el SIS como
`crown_jewel`) cambia la línea base, con un motivo escrito para cada mecanismo que se retira.

> Corredor OT de un gasoducto de transporte. En el nivel 1 hay controladores PLC que gobiernan las
> válvulas de corte y la regulación de presión a lo largo de la línea, y están conectados en red con
> el SCADA supervisorio del nivel 2. Exigimos nivel de seguridad objetivo 3 en esa zona. Nadie
> trabaja delante de esos controladores: no hay usuarios interactivos ni puestos de trabajo, el
> equipo es embebido y no tiene sistema operativo de propósito general, ni correo ni navegador.
>
> Aparte, en su propia zona, está el sistema instrumentado de seguridad (SIS) que ejecuta la parada
> de emergencia. Es la joya de la corona del activo y también le exigimos nivel 3. Su función de
> seguridad no se modifica dentro de este alcance. Tomamos TRITON/TRISIS como referencia de amenaza.
>
> El paso hacia la IDMZ no admite ruta directa entre OT e IT. Si alguien manipulase la presión de la
> línea, la consecuencia sería sobrepresión, rotura y fuga de gas. El mantenimiento del corredor lo
> hace el fabricante dos veces al año en ventana de parada.

---

## Escenario 2 — Estación de compresión y regasificación de gas · energía (tres zonas)

**Qué demuestra:** la divergencia más ancha dentro de **un solo activo**. Tres zonas cuyas premisas
declaradas están tan separadas que producen tres líneas base que casi no se solapan, todas desde el
mismo catálogo:

- En la zona sellada de compresión, el gating retira **por premisa** (`GATE-PREMISE-UNMET`) toda la
  pila de identidad interactiva e higiene de endpoint ofimático —MFA, antimalware, bloqueo de
  sesión, allowlisting, gestión de cuentas— porque cada uno de esos controles declara que presupone
  usuarios interactivos o un sistema operativo de propósito general, y la zona no los tiene. Cada
  retirada es un `no-aplica` justificado, con su motivo escrito, nunca un silencio.
- La estación de ingeniería conserva esa pila entera (sí hay personas, Windows y superficie
  ofimática) y, al ser zona **híbrida**, la ordena además por grupo de implementación (IG) de CIS.
- El SIS añade el **refuerzo de prioridad por consecuencia física** (safety) sobre el mínimo
  anti-TRITON.

Buen input para repetir el análisis: el texto trae señales claras para las tres zonas, así que
sirve para comprobar que la extracción del modelo es estable entre ejecuciones. El eje regional
(NIS2 en la UE frente a TSA/CIRCIA en EE. UU.) queda disponible para el delta del paso 4.

> Estación de compresión y regasificación de gas. Tiene tres zonas muy distintas entre sí.
>
> La zona de compresión, en nivel 1: controladores PLC embebidos que gobiernan los compresores y la
> regulación de presión de la línea. Son equipos sellados, sin sistema operativo de propósito
> general, no hay nadie trabajando delante de ellos y no tienen correo ni navegador. Están en red con
> el SCADA supervisorio. Le exigimos nivel de seguridad objetivo 3.
>
> La estación de ingeniería, en el nivel 3 al norte de la IDMZ: un portátil Windows desde el que los
> ingenieros parametrizan y descargan la lógica a los PLC. Trabajan personas delante de él, tiene
> correo corporativo y navegador, está en el dominio de la empresa y se usan memorias USB. El
> fabricante entra en remoto por un equipo de salto con doble factor y la sesión queda grabada. Nivel
> de seguridad objetivo 3.
>
> Aparte, en su propia zona, el sistema instrumentado de seguridad (SIS) que ejecuta la parada de
> emergencia de la estación. Es la joya de la corona del activo y también le exigimos nivel 3; su
> función de seguridad no se modifica dentro de este alcance. Tomamos TRITON/TRISIS como referencia
> de amenaza.
>
> No hay ruta directa entre OT e IT: todo pasa mediado por la IDMZ. Si se manipulase la presión de la
> línea, la consecuencia sería sobrepresión, rotura y fuga de gas. Estamos en la UE y nos aplica la
> NIS2; como operador de gasoducto también reportamos en EE. UU. bajo las directivas de la TSA y
> CIRCIA.

---

## Escenario 3 — Terminal de contenedores · puertos y marítimo

**Qué demuestra:** la genericidad ("admite ≠ sabe"). Un activo de un sector por completo distinto, que
el catálogo no contemplaba: el motor da candidatos donde hay cobertura y **huecos explícitos** donde
no, porque condiciona sobre premisas declaradas, no sobre el vocabulario del sector. La capa marítima
(IMO) aparece en las opciones, no en el gating —y el guion dice cuál es el límite.

> Terminal de contenedores. La zona de patio controla las grúas pórtico de muelle y los sistemas de
> posicionamiento y anticolisión con PLC dedicados en nivel 1, sin sistema operativo corriente y sin
> nadie sentado delante; están en red con el sistema de gestión del terminal. Le exigimos nivel de
> seguridad objetivo 3.
>
> Durante la escala se conecta el enlace buque-tierra con el portacontenedores: se intercambian datos
> de estiba y de carga con el sistema de a bordo, que está fuera de nuestra administración y se rige
> por el sistema de gestión de la seguridad del buque bajo la resolución MSC.428(98) de la OMI.
>
> Un fallo de la anticolisión con la grúa en movimiento provocaría el vuelco de la carga y
> aplastamiento en el muelle. El terminal está en la UE y le aplica la NIS2. El código PBIP/ISPS ya
> cubre la seguridad física del recinto.
