"""
comandos.py - Comandos personalizados: bloques con un texto y la frase que se le dice a Alexa.
Los escribe quien acompaña en un archivo JSON fuera del repo (actualizar la app no los borra):

    [
      {"texto": "Buenas noches", "frase": "Alexa, buenas noches"},
      {"texto": "Abrir persianas", "frase": "Alexa, abre las persianas"}
    ]

Lo que hace cada frase se configura en la app de Alexa (Rutinas); aquí solo se dice.
"""

import json
import os
import re

RUTA = os.path.join(os.path.expanduser("~"), ".sillodromo", "comandos.json")
MAXIMO = 12  # 3 filas de 4: los bloques siguen siendo grandes para la mirada
EJEMPLO = [
    {"texto": "Buenas noches", "frase": "Alexa, buenas noches"},
    {"texto": "Abrir persianas", "frase": "Alexa, abre las persianas"},
    {"texto": "¿Qué hora es?", "frase": "Alexa, qué hora es"},
]


def normalizar_frase(frase: str) -> str:
    """Deja la frase como "Alexa, <orden>": voz.hablar parte ahí para la pausa de 1 s."""
    resto = re.sub(r"^\s*alexa\b[\s,.:]*", "", frase, flags=re.IGNORECASE).strip()
    return f"Alexa, {resto}"


def cargar(ruta: str = RUTA) -> tuple:
    """Devuelve ([(texto, frase), ...], aviso). Nunca lanza: un archivo mal escrito no debe
    impedir que la app arranque; el problema se explica en el aviso. Si no existe, se crea con EJEMPLO."""
    try:
        if not os.path.exists(ruta):
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(EJEMPLO, f, ensure_ascii=False, indent=2)
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError) as e:
        return [], f"No pude leer los comandos ({e})."
    if not isinstance(datos, list):
        return [], "El archivo de comandos debe ser una lista: [ {\"texto\": ..., \"frase\": ...}, ... ]."

    comandos, descartados = [], 0
    for d in datos:
        texto, frase = (d.get("texto"), d.get("frase")) if isinstance(d, dict) else (None, None)
        if not (isinstance(texto, str) and isinstance(frase, str) and texto.strip() and normalizar_frase(frase) != "Alexa, "):
            descartados += 1
            continue
        comandos.append((texto.strip(), normalizar_frase(frase)))

    avisos = []
    if descartados:
        avisos.append(f"Se ignoraron {descartados} comandos mal escritos (falta \"texto\" o \"frase\").")
    if len(comandos) > MAXIMO:
        avisos.append(f"Se muestran los primeros {MAXIMO} de {len(comandos)}.")
        comandos = comandos[:MAXIMO]
    return comandos, " ".join(avisos)


if __name__ == "__main__":
    import tempfile

    assert normalizar_frase("abre las persianas") == "Alexa, abre las persianas"
    assert normalizar_frase("alexa abre la puerta") == "Alexa, abre la puerta"
    assert normalizar_frase("Alexa, buenas noches") == "Alexa, buenas noches"
    assert normalizar_frase("Alexandra, hola") == "Alexa, Alexandra, hola"  # solo la palabra "Alexa"

    with tempfile.TemporaryDirectory() as carpeta:
        ruta = os.path.join(carpeta, "sub", "comandos.json")
        comandos, aviso = cargar(ruta)  # no existe: se crea con el ejemplo
        assert os.path.exists(ruta) and len(comandos) == len(EJEMPLO) and aviso == ""

        with open(ruta, "w", encoding="utf-8") as f:
            f.write("[{\"texto\": \"Luz\", ")  # JSON roto: no lanza
        comandos, aviso = cargar(ruta)
        assert comandos == [] and aviso.startswith("No pude leer")

        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"texto": "x"}, f)
        assert cargar(ruta)[0] == [] and "lista" in cargar(ruta)[1]

        malos = [{"texto": "Sin frase"}, {"frase": "Alexa, sin texto"}, "no es un objeto", {"texto": " ", "frase": "x"},
                 {"texto": "Solo Alexa", "frase": "Alexa"}]
        buenos = [{"texto": f"C{n}", "frase": f"orden {n}"} for n in range(MAXIMO + 3)]
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(malos + buenos, f)
        comandos, aviso = cargar(ruta)
        assert len(comandos) == MAXIMO and comandos[0] == ("C0", "Alexa, orden 0")
        assert "Se ignoraron 5" in aviso and f"primeros {MAXIMO} de {MAXIMO + 3}" in aviso
    print("comandos: OK")
