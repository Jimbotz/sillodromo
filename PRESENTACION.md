# Prompt para generar la presentación en Gamma

Este archivo tiene un prompt listo para pegar en [Gamma](https://gamma.app) ("Generate" → "Paste in text")
y que arme una presentación técnica de Sillódromo: qué problema resuelve, cómo lo usa la persona
en la silla, y cómo está construido por dentro. Los datos (contrastes, tiempos, protocolos, nombres
de archivo) vienen del código y del README/CLAUDE.md del repo — si el código cambia, actualiza este
prompt antes de regenerar la presentación para que no quede desactualizado.

---

## Prompt (copiar todo lo de abajo en Gamma)

```
Crea una presentación técnica de 14-16 diapositivas sobre "Sillódromo", una aplicación de
escritorio (Python + PyQt5) que le permite a una persona con movilidad reducida controlar
dispositivos del hogar (vía Alexa) y, en desarrollo, su propia silla de ruedas eléctrica, usando
solo la cabeza, la mirada y la boca — sin usar las manos. La audiencia es técnica (desarrolladores,
evaluadores de un proyecto de accesibilidad); tono claro y directo, con diagramas de flujo donde
ayuden a entender un proceso, sin relleno de marketing. Todo el contenido en español.

Usa esta estructura y estos datos exactos (no inventes cifras que no estén aquí):

1. PORTADA
   "Sillódromo — Control accesible sin usar las manos". Subtítulo: aplicación de escritorio
   PyQt5, WCAG 2.1 AA/AAA, control por cabeza y mirada.

2. EL PROBLEMA
   Una persona con movilidad reducida (parálisis, ELA, lesión medular, etc.) necesita controlar
   su entorno (luces, TV, música, pedir ayuda) y potencialmente su silla de ruedas, sin poder usar
   un mouse, teclado ni pantalla táctil convencional. Las soluciones de accesibilidad existentes
   suelen ignorar el daltonismo, la baja visión o la fotofobia.

3. QUÉ ES SILLÓDROMO (resumen)
   App de escritorio en Python 3 + PyQt5, multiplataforma (Windows, macOS, Linux, Raspberry Pi),
   corre nativa o en Docker con X11 forwarding. Dos entradas de control: la cabeza (una "cruceta"
   direccional) y los ojos (un puntero con activación por permanencia). Salida: comandos de voz a
   Alexa (con pyttsx3) y, en desarrollo, movimiento físico de la silla vía un Arduino.

4. DISEÑO ACCESIBLE: LOS 5 PRINCIPIOS
   1) Fondo azul grisáceo (#BFC9DA) y texto azul casi negro (#111B31): nunca blanco/negro puros,
      37% menos brillo reflejado que un blanco casi puro — menos deslumbramiento y menos halo con
      astigmatismo.
   2) Contraste medido: todo el texto en nivel AAA (7:1 o más); el texto de los bloques llega a
      11,9:1; bordes con 4,1:1 (WCAG 1.4.11 pide 3:1).
   3) La selección no depende del tono: el bloque seleccionado pasa a azul oscuro (#1D4C8F) con
      texto blanco (8,5:1) y borde el doble de grueso — se distingue por luminosidad y grosor, no
      solo color, así funciona igual con cualquier tipo de daltonismo (deuteranopía, protanopía,
      tritanopía).
   4) Nada se comunica solo con color: mientras una acción está en curso, los bloques se atenúan
      Y aparece el texto "Espera a que termine la acción".
   5) Iconos vectoriales de Lucide que siempre acompañan al texto, nunca lo sustituyen.
   Todo esto se verifica en código: `python app/tools/palette.py` calcula la luminancia relativa y
   el ratio de contraste WCAG de cada par de colores de la interfaz y falla si alguno no cumple.

5. ENTRADA 1: LA CRUCETA DE LA CABEZA
   Cámara + MediaPipe Face Landmarker detectan el rostro en un hilo aparte (no bloquea la interfaz).
   Girar la cabeza (izquierda/derecha/arriba/abajo) mueve la selección al bloque vecino en esa
   dirección; cada giro cuenta una sola vez y hay que volver al centro antes del siguiente (evita
   activar por temblor). Abrir la boca pulsa el bloque seleccionado. Los ojos no se usan en este modo.

6. ENTRADA 2: MIRADA + PERMANENCIA (DWELL)
   Tras calibrar, el modelo de mirada convierte la posición de los iris y la cabeza en un punto de
   pantalla. Se selecciona el bloque más cercano al puntero. Mirarlo fijo 1,5 segundos
   (TIEMPO_PERMANENCIA) lo activa; una barra se va llenando como retroalimentación visual. Salidas
   cortas de menos de 0,3 s (un parpadeo) no reinician el progreso. La barra solo carga si la
   mirada está quieta (si se mueve más del 5% de la pantalla en 0,3 s, la carga se pausa sin
   perderse). Tras activar algo, nada se vuelve a activar hasta que la mirada se mueve (evita
   activaciones en cadena si el siguiente bloque queda justo debajo). El puntero se suaviza con un
   filtro 1€ (quita el temblor cuando la mirada está quieta, casi no suaviza cuando salta).

7. FLUJO DE CALIBRACIÓN (diagrama de flujo)
   Arranque → ¿hay calibración guardada? → si falta la cara: calibrar luz (una vez, CLAHE si hace
   falta) → centro de reposo y boca cerrada → rangos de giro (izquierda/derecha/arriba/abajo, cada
   uno al 30% de lo que el usuario alcanza) → apertura máxima de la boca → guardar. Si falta la
   pantalla: 16 puntos en el borde (5 arriba, 5 abajo, 3 a cada lado) → mirar cada uno moviendo ojos
   y/o cabeza → ajustar el modelo de regresión → si el error medio supera 15% de la pantalla, se
   usa la cruceta en vez del puntero. Todo el texto de la calibración se lee en voz alta y cada
   paso espera a que termine de leerse antes de medir. Esc en cualquier momento omite y usa valores
   por defecto (no se guardan, así que se vuelve a pedir la próxima vez).

8. FLUJO DE USO: PANTALLAS DE LA APP (diagrama)
   Menú → [Navegación | Activadores | Volver a calibrar]. Navegación: la cabeza conduce (girar solo
   mueve una flecha indicadora, no selecciona nada, para no salir sin querer); abrir la boca es la
   única forma de volver al menú. Activadores: elegir dispositivo (Focos, Enchufes, Televisiones,
   Música, Comandos) → elegir acción → la app dice la orden de voz para Alexa.

9. COMANDOS PERSONALIZADOS Y ALEXA
   Cada acción es una frase que la app dice en voz alta empezando por "Alexa" (con una pausa de 1s
   para que el altavoz se active); lo que hace esa orden se configura en las Rutinas de la app de
   Alexa. Además de los dispositivos fijos, "Comandos" permite crear categorías y frases libres
   (ej. "Ir al baño" → "Por favor, llévenme al baño") desde una pantalla de edición aparte, pensada
   para quien acompaña (teclado y mouse; la mirada y la cruceta no actúan ahí, para que no se borre
   nada sin querer). Todo se guarda en `app/datos/comandos.json`.

10. COLOR SEMÁNTICO: VERDE/ROJO POR ACCIÓN
    Los bloques de "Encender" se colorean verde y los de "Apagar" rojo (y lo mismo en los comandos
    personalizados que se marquen así), como apoyo visual extra — nunca el único, el texto y el
    icono (power / power-off) siguen ahí, así que sigue funcionando igual para daltonismo
    rojo-verde. Los tonos pasan los mismos mínimos de contraste WCAG que el resto de la paleta.

11. CONTROL DE LA SILLA DE RUEDAS (en desarrollo)
    Protocolo serial de 2 bytes [vertical, horizontal] a un Arduino, 128 = posición neutra. En la
    vista de Navegación, las flechas del teclado mueven la silla mientras se mantienen apretadas y
    frena sola al soltarlas (igual que w-a-s-d en el prototipo original, `movement.py`); frena
    también si la ventana pierde el foco con una flecha apretada, por seguridad. Abrir la boca
    frena y es la única forma de volver al menú desde ahí.

12. ARQUITECTURA DE SOFTWARE (diagrama de paquetes)
    `app/main.py` (arranca la app) → `app/window.py` (VentanaPrincipal: qué pantalla está activa,
    hilo de cámara, calibración, puntero). Paquetes: `views/` (una pantalla por archivo: menú,
    navegación, activadores, calibración, editor), `widgets/` (componentes reutilizables: círculo
    de cámara, capa del puntero, puntos de calibración), `buttons/` (cómo se ve un bloque: iconos,
    expandir, color por acción), `features/` (lógica sin interfaz: `tracking.py` con MediaPipe,
    `commands.py` con el JSON de comandos, `voice.py` con pyttsx3), `tools/` (utilidades sin
    estado: `palette.py` con el contraste WCAG, `scale.py` con el escalado de pantalla).

13. ESCALADO DE PANTALLA Y ACCESIBILIDAD DE HARDWARE
    La interfaz se pensó para una pantalla de referencia; al arrancar mide la resolución real
    disponible y escala tamaños de fuente, iconos y espaciado en la misma proporción (con un piso y
    un techo para no quedar ilegible ni desproporcionada), así ningún texto ni columna se corta en
    pantallas más chicas o con más escala de Windows. Con varias cámaras conectadas, una variable
    de entorno (`SILLODROMO_CAMARA`) permite fijar cuál usar.

14. STACK TECNOLÓGICO
    Python 3, PyQt5 (interfaz), MediaPipe (landmarks faciales), OpenCV (captura de cámara),
    pyttsx3 (texto a voz, con proceso aparte por frase para no bloquear macOS), pyserial (Arduino),
    Docker + X11 forwarding para desplegar igual en Windows/macOS/Linux; en Raspberry Pi corre
    nativo con los paquetes de apt.

15. CIERRE / PRÓXIMOS PASOS
    Estado actual: control de dispositivos del hogar vía Alexa, completo y accesible bajo WCAG
    2.1 AA/AAA. En desarrollo: control físico de la silla de ruedas. Próximo: llevar el control de
    movimiento también a la cabeza/mirada (hoy solo funciona por teclado).

Para cada diapositiva de flujo (calibración, pantallas de la app) usa un diagrama de pasos o
flowchart, no solo texto. Para la de arquitectura usa un diagrama de cajas con las flechas de
dependencia entre paquetes. Mantén una paleta de colores propia de la presentación (no necesita
ser la misma que la de la app), pero con buen contraste de texto.
```

---

## Notas

- Actualizá los datos numéricos (contraste, tiempos de calibración, tamaños) desde `README.md` y
  `app/tools/palette.py` si cambian — este prompt es un snapshot de lo que hay al momento de
  escribirlo.
- Gamma también acepta pegar este archivo completo como "texto" en vez de solo el bloque de
  prompt; en ese caso puede ignorar el encabezado y quedarse con la sección del prompt igual.
