"""
voz.py - Servicio de texto a voz (pyttsx3).
Cada frase se dice en un proceso aparte: runAndWait() bloquea y, en macOS, deja de
responder si se llama desde un hilo que no es el principal. Así la interfaz nunca se congela.
"""

import importlib.util
import subprocess
import sys

DISPONIBLE = importlib.util.find_spec("pyttsx3") is not None

# Se ejecuta en el proceso hijo. Elige una voz en español si el sistema tiene alguna;
# se prefieren las que no son "eloquence" (en macOS son voces de novedad, poco naturales).
_SCRIPT = """
import sys, pyttsx3
motor = pyttsx3.init()
es = [v for v in motor.getProperty("voices")
      if any(m in (v.id + str(v.languages)).lower() for m in ("es_", "es-", "spanish"))]
es.sort(key=lambda v: "eloquence" in v.id)
if es:
    motor.setProperty("voice", es[0].id)
motor.say(sys.argv[1])
motor.runAndWait()
"""

_proceso = None


def hablar(texto: str) -> bool:
    """Dice el texto sin bloquear. Corta la frase anterior si aún suena. False si no hay pyttsx3."""
    global _proceso
    if not DISPONIBLE:
        return False
    if _proceso is not None and _proceso.poll() is None:
        _proceso.terminate()
    _proceso = subprocess.Popen([sys.executable, "-c", _SCRIPT, texto])
    return True
