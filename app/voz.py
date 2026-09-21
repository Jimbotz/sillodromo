"""
voz.py - Servicio de texto a voz (pyttsx3).
Cada parte de una frase se dice en su propio proceso: runAndWait() bloquea, en macOS deja de
responder fuera del hilo principal, un segundo runAndWait() vuelve sin hablar y encolar varias
partes en un mismo motor solo decía la primera. Así la interfaz nunca se congela.
"""

import importlib.util
import subprocess
import sys
import threading
import time

DISPONIBLE = importlib.util.find_spec("pyttsx3") is not None
# Silencio (segundos) entre "Alexa" y la orden, para que el altavoz se active antes de escucharla
PAUSA_ALEXA = 1.0

# Proceso hijo: prepara el motor y espera una línea por stdin antes de hablar. Arrancar
# pyttsx3 tarda ~1 s, así que todas las partes se lanzan a la vez y cada una habla al recibir
# la señal: la pausa entre partes es PAUSA_ALEXA y no PAUSA_ALEXA + arranque.
# Elige una voz en español si el sistema tiene alguna; se prefieren las que no son "eloquence"
# (en macOS son voces de novedad, poco naturales).
_SCRIPT = """
import sys, pyttsx3
motor = pyttsx3.init()
es = [v for v in motor.getProperty("voices")
      if any(m in (v.id + str(v.languages)).lower() for m in ("es_", "es-", "spanish"))]
es.sort(key=lambda v: "eloquence" in v.id)
if es:
    motor.setProperty("voice", es[0].id)
sys.stdin.readline()
motor.say(sys.argv[1])
motor.runAndWait()
"""

_cerrojo = threading.Lock()
_proceso = None  # parte que está sonando
_turno = 0  # cada frase nueva invalida las partes pendientes de la anterior


def _decir(partes, turno):
    global _proceso
    procesos = [subprocess.Popen([sys.executable, "-c", _SCRIPT, p], stdin=subprocess.PIPE) for p in partes]
    for i, proceso in enumerate(procesos):
        if i:
            time.sleep(PAUSA_ALEXA)
        with _cerrojo:
            if turno != _turno:
                break
            _proceso = proceso
        proceso.communicate(b"\n")  # señal para hablar; vuelve cuando termina
    for proceso in procesos:  # partes que no llegaron a sonar por una frase nueva
        if proceso.poll() is None:
            proceso.kill()


def hablar(texto: str) -> bool:
    """Dice el texto sin bloquear. Corta la frase anterior si aún suena. False si no hay pyttsx3."""
    global _turno
    if not DISPONIBLE:
        return False
    with _cerrojo:
        _turno += 1
        if _proceso is not None and _proceso.poll() is None:
            _proceso.terminate()
        turno = _turno
    # "Alexa, encender foco 1" se dice como "Alexa" + pausa + "encender foco 1"
    partes = texto.split(", ", 1) if texto.startswith("Alexa, ") else [texto]
    threading.Thread(target=_decir, args=(partes, turno), daemon=True).start()
    return True
