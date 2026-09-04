# Guion de la demo — escenarios de prueba

Cinco descripciones de activo, de cinco sectores distintos, listas para recorrer el motor de
principio a fin. La primera es el caso de referencia (un gasoducto de transporte, el activo alrededor
del cual se escribió el catálogo); las otras cuatro están para poner a prueba la afirmación de que el
motor lee **premisas declaradas**, no el vocabulario de una industria.

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

## Escenario 2 — Subestación eléctrica · transporte de electricidad

**Qué demuestra:** un activo híbrido IT/OT y el **delta regional** en vivo (US → +EU). Al voltear una
premisa en el paso 2 se ve el "mismo catálogo, distinta respuesta": el dominio se relee, el override
de seguridad OT se activa y aparece una contradicción que el motor escala en vez de zanjar.

> Puesto de operación e ingeniería de una subestación eléctrica de transporte de 220 kV, en el nivel
> 3 de la red de la subestación. Es un equipo Windows desde el que se parametrizan y se cargan los
> ajustes de las protecciones IEC 61850 de las posiciones. Trabajan personas delante de él, tiene
> correo corporativo y navegador, está en el dominio de la empresa y se usan memorias USB para llevar
> informes. Le exigimos nivel de seguridad objetivo 3.
>
> La carga de ajustes hacia la red de posiciones pasa mediada por una zona desmilitarizada. El
> fabricante de las protecciones entra en remoto para mantenimiento a través de un equipo de salto
> con doble factor y la sesión queda grabada.
>
> Este puesto no maniobra directamente, pero si lo comprometen se puede llegar a las protecciones y
> provocar la apertura indebida de interruptores y un cero de tensión en la zona. Usamos MITRE ATT&CK
> for ICS como modelo de amenaza y el apagón de Ucrania de 2016 como referencia. Estamos sujetos a la
> directiva NIS2 en España.

---

## Escenario 3 — Terminal de contenedores · puertos y marítimo

**Qué demuestra:** la genericidad ("admite ≠ sabe"). Un activo que el catálogo no contemplaba: el
motor da candidatos donde hay cobertura y **huecos explícitos** donde no, porque condiciona sobre
premisas declaradas, no sobre el vocabulario del sector. La capa marítima (IMO) aparece en las
opciones, no en el gating —y el guion dice cuál es el límite.

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

---

## Escenario 4 — Línea de embotellado · alimentación y bebidas

**Qué demuestra:** el motor negándose a inventar. Con una descripción mínima deja **vacíos** los
campos obligatorios (nivel de seguridad, criticidad), los lista por nombre y **bloquea** el paso 2
hasta que la persona los decide. Un valor que nadie ha elegido produciría una línea base que nadie ha
elegido.

> Tenemos una línea de embotellado con un autómata y un panel de operador. Queremos protegerla mejor.

---

## Escenario 5 — Planta potabilizadora · agua

**Qué demuestra:** un mismo catálogo produciendo **dos líneas base distintas**. Dos zonas con sus
propias premisas, su propio nivel objetivo y su propio lado de la IDMZ —nunca copiados de una a
otra—; el gating retira mecanismos distintos en cada una sin tocar ninguna capacidad.

> Planta potabilizadora de agua. Tiene dos partes bien distintas.
>
> La zona de proceso, en nivel 1: PLC embebidos que gobiernan las bombas de captación y la
> dosificación de cloro. No llevan sistema operativo corriente, no hay nadie trabajando delante de
> ellos y no tienen correo ni navegador. Están en red con la sala de control. Nivel de seguridad
> objetivo 3.
>
> La sala de control, en nivel 2: un servidor Windows con el histórico y dos puestos de operador donde
> el personal de turno entra con su usuario del dominio de la empresa, consulta el correo y saca
> informes en memorias USB. Nivel de seguridad objetivo 2.
>
> Si la dosificación de cloro se altera se contamina el agua de abastecimiento de la ciudad. La sala
> de control tiene salida a la red corporativa a través de una zona desmilitarizada.
