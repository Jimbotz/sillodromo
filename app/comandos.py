"""
comandos.py - Comandos personalizados, agrupados por categorías, en app/datos/comandos.json.
Se crean y editan desde la app (editor.py); este módulo solo lee, valida y guarda.

    {"categorias": [
      {"nombre": "Solicitar atención", "icono": "hand",
       "comandos": [{"titulo": "Ir al baño", "frase": "Por favor, llévenme al baño", "icono": "toilet",
                     "accion": ""}]}
    ]}

La frase es exactamente lo que dice la voz. Si empieza por "Alexa", voz.hablar hace la pausa de 1 s
tras "Alexa" para que el altavoz se active (lo que haga la orden se configura en las Rutinas de Alexa).

"accion" es "on", "off" o "" (por defecto, también para comandos guardados antes de que existiera este
campo): colorea el bloque de verde o rojo además de su texto e icono (ver main.crear_vista y
main.clasificar_accion, que además intenta adivinarla del título cuando queda vacía).
"""

import json
import os
import re

import icono

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos", "comandos.json")
MAXIMO = 12  # comandos por categoría: 3 filas de 4, bloques aún grandes para la mirada
EJEMPLO = [
    {"nombre": "Solicitar atención", "icono": "hand", "comandos": [
        {"titulo": "Ir al baño", "frase": "Por favor, llévenme al baño", "icono": "toilet"},
        {"titulo": "Tengo sed", "frase": "Tengo sed, ¿me pueden dar agua, por favor?", "icono": "glass-water"},
        {"titulo": "Tengo hambre", "frase": "Tengo hambre, ¿me pueden dar de comer, por favor?", "icono": "utensils"},
        {"titulo": "Me duele algo", "frase": "Me duele algo, necesito ayuda, por favor", "icono": "heart-pulse"},
        {"titulo": "Quiero descansar", "frase": "Quiero descansar, ¿me pueden llevar a la cama?", "icono": "bed"},
        {"titulo": "Ven, por favor", "frase": "¿Puede venir alguien, por favor?", "icono": "bell-ring"},
    ]},
    {"nombre": "Casa", "icono": "house", "comandos": [
        {"titulo": "Buenas noches", "frase": "Alexa, buenas noches", "icono": "moon"},
        {"titulo": "¿Qué hora es?", "frase": "Alexa, qué hora es", "icono": "clock"},
    ]},
]


def normalizar_frase(frase: str) -> str:
    """Recorta espacios y, si empieza por "Alexa", la deja como "Alexa, <orden>" (voz.hablar parte ahí).
    No añade "Alexa": una frase para una persona ("Por favor, llévenme al baño") se dice tal cual."""
    frase = " ".join(frase.split())
    if re.match(r"alexa\b", frase, flags=re.IGNORECASE):
        return "Alexa, " + re.sub(r"^alexa\b[\s,.:]*", "", frase, flags=re.IGNORECASE)
    return frase


def _texto(valor) -> str:
    return " ".join(valor.split()) if isinstance(valor, str) else ""


def _icono(valor, disponibles) -> str:
    return valor if valor in disponibles else icono.POR_DEFECTO


def _accion(valor) -> str:
    return valor if valor in ("on", "off") else ""


def validar(datos) -> tuple:
    """(categorias limpias, cuántos elementos se descartaron). Acepta también el formato antiguo:
    una lista de {"texto", "frase"}, que pasa a una categoría "Comandos"."""
    disponibles = set(icono.catalogo())
    if isinstance(datos, list):  # formato antiguo
        datos = {"categorias": [{"nombre": "Comandos", "icono": icono.POR_DEFECTO,
                                 "comandos": [{"titulo": d.get("texto"), "frase": d.get("frase")}
                                              for d in datos if isinstance(d, dict)]}]}
    categorias, descartados = [], 0
    for c in datos.get("categorias", []) if isinstance(datos, dict) else []:
        nombre = _texto(c.get("nombre")) if isinstance(c, dict) else ""
        if not nombre:
            descartados += 1
            continue
        comandos = []
        for d in c.get("comandos", []) if isinstance(c.get("comandos"), list) else []:
            titulo = _texto(d.get("titulo")) if isinstance(d, dict) else ""
            frase = normalizar_frase(d["frase"]) if isinstance(d, dict) and isinstance(d.get("frase"), str) else ""
            if not titulo or frase in ("", "Alexa, "):
                descartados += 1
                continue
            comandos.append({"titulo": titulo, "frase": frase, "icono": _icono(d.get("icono"), disponibles),
                             "accion": _accion(d.get("accion"))})
        categorias.append({"nombre": nombre, "icono": _icono(c.get("icono"), disponibles), "comandos": comandos})
    return categorias, descartados


def cargar(ruta: str = None) -> tuple:
    """(categorias, aviso). Nunca lanza: un archivo dañado no debe impedir que la app arranque (el
    problema se explica en el aviso). Si no existe, se crea con EJEMPLO."""
    ruta = ruta or RUTA
    try:
        if not os.path.exists(ruta):
            guardar(EJEMPLO, ruta)
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError) as e:
        return [], f"No pude leer los comandos ({e})."
    categorias, descartados = validar(datos)
    aviso = f"Se ignoraron {descartados} comandos o categorías sin nombre o sin frase." if descartados else ""
    return categorias, aviso


def guardar(categorias: list, ruta: str = None) -> bool:
    """Escribe en un temporal y lo renombra: un corte a medias no deja el archivo roto."""
    ruta = ruta or RUTA
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"categorias": categorias}, f, ensure_ascii=False, indent=2)
        os.replace(ruta + ".tmp", ruta)
        return True
    except OSError as e:
        print(f"No pude guardar los comandos ({e})", flush=True)
        return False


if __name__ == "__main__":
    import tempfile

    assert normalizar_frase("  Por favor,   llévenme al baño ") == "Por favor, llévenme al baño"  # sin "Alexa"
    assert normalizar_frase("alexa abre la puerta") == "Alexa, abre la puerta"
    assert normalizar_frase("Alexa, buenas noches") == "Alexa, buenas noches"
    assert normalizar_frase("Alexandra, hola") == "Alexandra, hola"  # solo la palabra "Alexa"

    faltantes = {i for c in EJEMPLO for i in [c["icono"]] + [d["icono"] for d in c["comandos"]]} - set(icono.catalogo())
    assert not faltantes, f"iconos del ejemplo que no existen: {faltantes}"

    with tempfile.TemporaryDirectory() as carpeta:
        ruta = os.path.join(carpeta, "datos", "comandos.json")
        categorias, aviso = cargar(ruta)  # no existe: se crea con el ejemplo
        assert os.path.exists(ruta) and aviso == "" and [c["nombre"] for c in categorias] == ["Solicitar atención", "Casa"]
        assert categorias[0]["comandos"][0] == {"titulo": "Ir al baño", "frase": "Por favor, llévenme al baño",
                                                 "icono": "toilet", "accion": ""}  # sin accion: "" por defecto

        categorias[0]["comandos"].append({"titulo": "Encender la luz del pasillo", "frase": "Alexa, enciende el pasillo",
                                          "icono": "phone", "accion": "on"})
        assert guardar(categorias, ruta) and cargar(ruta)[0] == categorias  # ida y vuelta, con accion incluida

        with open(ruta, "w", encoding="utf-8") as f:  # formato antiguo: lista suelta
            json.dump([{"texto": "Buenas noches", "frase": "alexa buenas noches"}, {"texto": "Sin frase"}], f)
        categorias, aviso = cargar(ruta)
        assert categorias == [{"nombre": "Comandos", "icono": icono.POR_DEFECTO,
                               "comandos": [{"titulo": "Buenas noches", "frase": "Alexa, buenas noches",
                                             "icono": icono.POR_DEFECTO, "accion": ""}]}]
        assert "Se ignoraron 1" in aviso

        with open(ruta, "w", encoding="utf-8") as f:  # nombres vacíos, icono inexistente, basura, accion inválida
            json.dump({"categorias": [{"nombre": " "}, "x", {"nombre": "A", "icono": "no-existe",
                                       "comandos": [{"titulo": "T", "frase": "Hola", "icono": "nada", "accion": "verde"}, 5]}]}, f)
        categorias, aviso = cargar(ruta)
        assert categorias == [{"nombre": "A", "icono": icono.POR_DEFECTO,
                               "comandos": [{"titulo": "T", "frase": "Hola", "icono": icono.POR_DEFECTO, "accion": ""}]}]
        assert "Se ignoraron 3" in aviso

        with open(ruta, "w", encoding="utf-8") as f:
            f.write("{roto")
        categorias, aviso = cargar(ruta)
        assert categorias == [] and aviso.startswith("No pude leer")
    print("comandos: OK")
