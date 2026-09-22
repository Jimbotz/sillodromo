"""
camara.py - Captura de la cámara con detección de rostro (MediaPipe FaceLandmarker).
Se importa aparte para que la interfaz arranque aunque falten OpenCV o MediaPipe.
"""

import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field

import cv2
import numpy as np

# Las ruedas de OpenCV para Linux traen sus propios plugins de Qt y apuntan esta
# variable hacia ellos, lo que impide arrancar PyQt5 ("Could not load the Qt platform plugin").
os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision
from mediapipe.tasks.python.vision import drawing_styles, drawing_utils
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage

MODELO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelos", "face_landmarker.task")
# Siempre CPU (el delegado por defecto). En macOS se usa MediaPipe 0.10.35 (ver requirements.txt):
# la 1.0.1 aborta allí con CPU, y con GPU retiene una copia de cada cuadro (~100 MB/s).

MAX_CAMARAS = 4  # índices de OpenCV que se prueban al buscar una cámara
# Con varias cámaras conectadas (p. ej. la integrada del portátil y una externa), fija cuál usar
# sin depender de qué índice pruebe primero: SILLODROMO_CAMARA=1 python app/main.py
CAMARA_FORZADA = os.environ.get("SILLODROMO_CAMARA")
MENSAJE_SIN_CAMARA = "No se pudo abrir ninguna cámara."
if sys.platform == "darwin":
    # macOS atribuye el permiso a la app que lanza el proceso (Terminal, VS Code...), no a Python
    MENSAJE_SIN_CAMARA += (
        " Permite el acceso a la app desde la que lanzas Sillódromo en"
        " Ajustes del Sistema > Privacidad y seguridad > Cámara."
    )

# Puntos del modelo de 468: punta de la nariz, mejillas (lados de la cara), frente y mentón
NARIZ, MEJILLA_A, MEJILLA_B, FRENTE, MENTON = 1, 234, 454, 10, 152
# Valores por defecto (sin calibrar): cuánto debe girar la cabeza (fracción del ancho/alto de la
# cara) para contar como dirección, y dónde queda la nariz en vertical al mirar de frente.
UMBRAL_GIRO = 0.08  # una cara de frente quieta se desvía ~0,03 del centro por defecto: queda margen
CENTRO_VERTICAL = 0.55
# jawOpen de MediaPipe va de 0 (boca cerrada) a 1; una sonrisa amplia da ~0,12.
BOCA_ABIERTA = 0.5  # por encima: "pulsar"
BOCA_CERRADA = 0.25  # por debajo cuentan las direcciones; entre ambos valores no se hace nada
CUADROS_ESTABLES = 4  # ~130 ms a 30 fps: un estado debe mantenerse para contar (filtra el temblor)
DIRECCIONES = ("izquierda", "derecha", "arriba", "abajo")


@dataclass
class Perfil:
    """Referencia de un usuario: su postura de reposo y cuánto debe moverse hacia cada lado.
    Sin calibrar (valores por defecto) se comporta igual que los umbrales fijos de antes."""

    centro_h: float = 0.0  # posición horizontal de la nariz en reposo (-0,5 a 0,5)
    centro_v: float = CENTRO_VERTICAL  # posición vertical de la nariz en reposo (0 = frente, 1 = mentón)
    umbrales: dict = field(default_factory=lambda: dict.fromkeys(DIRECCIONES, UMBRAL_GIRO))
    boca_abierta: float = BOCA_ABIERTA
    boca_cerrada: float = BOCA_CERRADA
    sin_calibrar: tuple = ()  # direcciones (o "boca") sin movimiento suficiente: usan el valor por defecto

    def a_dict(self) -> dict:
        return {**asdict(self), "sin_calibrar": list(self.sin_calibrar)}

    @classmethod
    def desde_dict(cls, d: dict) -> "Perfil":
        """Perfil guardado. Lanza KeyError, TypeError o ValueError si falta algo o no es un número."""
        umbrales = {k: float(d["umbrales"][k]) for k in DIRECCIONES}
        if min(umbrales.values()) <= 0:
            raise ValueError("umbral no positivo")
        return cls(float(d["centro_h"]), float(d["centro_v"]), umbrales, float(d["boca_abierta"]),
                   float(d["boca_cerrada"]), tuple(str(x) for x in d.get("sin_calibrar", ())))

    def resumen(self) -> str:
        giros = " · ".join(f"{d} {self.umbrales[d]:.2f}" for d in DIRECCIONES)
        texto = f"Umbrales de giro: {giros} · boca: pulsa desde {self.boca_abierta:.2f}"
        return texto + (f" · sin calibrar: {', '.join(self.sin_calibrar)}" if self.sin_calibrar else "")


PERFIL_BASE = Perfil()


def medidas_cara(puntos) -> tuple:
    """Posición de la nariz dentro de la cara: (horizontal, vertical).
    horizontal: -0,5 (borde izquierdo) a 0,5; vertical: 0 (frente) a 1 (mentón)."""
    nariz = puntos[NARIZ]
    lado_izq, lado_der = sorted((puntos[MEJILLA_A].x, puntos[MEJILLA_B].x))
    horizontal = (nariz.x - lado_izq) / max(lado_der - lado_izq, 1e-6) - 0.5
    vertical = (nariz.y - puntos[FRENTE].y) / max(puntos[MENTON].y - puntos[FRENTE].y, 1e-6)
    return horizontal, vertical


def direccion_cabeza(puntos, perfil: Perfil = PERFIL_BASE) -> str:
    """Devuelve "izquierda", "derecha", "arriba", "abajo" o "centro" según cuánto se aleja la nariz
    del reposo del usuario, medido en umbrales de cada dirección. La imagen ya viene en espejo,
    así que izquierda es la de la persona."""
    h, v = medidas_cara(puntos)
    h, v = h - perfil.centro_h, v - perfil.centro_v
    # Cada eje en "umbrales": 1 = justo en el umbral de esa dirección
    nh = h / perfil.umbrales["izquierda" if h < 0 else "derecha"]
    nv = v / perfil.umbrales["arriba" if v < 0 else "abajo"]
    # ponytail: sin suavizado; añadir media móvil si la flecha parpadea
    if max(abs(nh), abs(nv)) < 1:
        return "centro"
    if abs(nh) >= abs(nv):
        return "izquierda" if nh < 0 else "derecha"
    return "arriba" if nv < 0 else "abajo"


def estado_cara(puntos, mandibula: float, perfil: Perfil = PERFIL_BASE) -> str:
    """Resume una cara en "pulsar", una dirección, "centro" o "" (boca a medio abrir)."""
    if mandibula >= perfil.boca_abierta:
        return "pulsar"
    if mandibula > perfil.boca_cerrada:
        return ""  # abrir la boca baja el mentón y parecería "arriba": no se lee la dirección
    return direccion_cabeza(puntos, perfil)


# Perillas de la luz: por debajo de cualquiera de los dos se corrige la imagen con CLAHE.
# Con buena luz no se corrige: la imagen retocada no ayuda y le cuesta más a MediaPipe (~+3,5 % CPU).
LUZ_MINIMA = 60  # brillo medio (0-255) del cuadro en gris
CONTRASTE_MINIMO = 40  # desviación estándar del gris


def curva_si_hace_falta(bgr):
    """Curva de corrección si el cuadro está oscuro o sin contraste; None si la luz ya es buena."""
    gris = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    if gris.mean() >= LUZ_MINIMA and gris.std() >= CONTRASTE_MINIMO:
        return None
    return curva_clahe(bgr)


def curva_clahe(bgr) -> np.ndarray:
    """Aplica CLAHE (ecualización adaptativa de contraste) una sola vez y resume su efecto en una
    curva de tono global de 256 valores. Después cada cuadro se corrige con cv2.LUT, que es solo
    una tabla de consulta: casi gratis, frente a CLAHE completo en cada cuadro."""
    gris = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    mejorada = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gris)
    # Para cada nivel de gris original, el valor medio que CLAHE le asignó
    suma = np.bincount(gris.ravel(), weights=mejorada.ravel(), minlength=256)
    cuenta = np.bincount(gris.ravel(), minlength=256)
    niveles = np.arange(256)
    presentes = cuenta > 0
    curva = np.interp(niveles, niveles[presentes], suma[presentes] / cuenta[presentes])
    # Creciente: un tono más claro nunca queda más oscuro que otro
    return np.maximum.accumulate(curva).clip(0, 255).astype(np.uint8)


# Calibración inicial: (clave, instrucción, segundos). El tiempo solo corre con la cara a la vista
# (salvo "luz"), así que nadie queda calibrado a medias por salirse del cuadro.
PASOS_CALIBRACION = [
    ("luz", "Ajustando la iluminación...", 1.0),
    ("centro", "Mira al frente y quédate quieto", 3.0),
    ("izquierda", "Gira la cabeza a la izquierda todo lo que puedas y mantenla", 3.0),
    ("volver", "Vuelve al centro", 1.5),
    ("derecha", "Gira la cabeza a la derecha todo lo que puedas y mantenla", 3.0),
    ("volver", "Vuelve al centro", 1.5),
    ("arriba", "Levanta la cabeza todo lo que puedas y mantenla", 3.0),
    ("volver", "Vuelve al centro", 1.5),
    ("abajo", "Baja la cabeza todo lo que puedas y mantenla", 3.0),
    ("volver", "Vuelve al centro", 1.5),
    ("boca", "Abre la boca todo lo que puedas y mantenla", 3.0),
]
# Perillas de la calibración
FRACCION_RANGO = 0.3  # el umbral de cada dirección es esta fracción de lo que el usuario alcanza
UMBRAL_MINIMO = 0.04  # piso: por debajo, el temblor natural dispararía gestos. Un movimiento
# menor que esto en la calibración se toma como "no se movió" (es ruido de la detección)
PERCENTIL_PICO = 0.8  # "máximo" robusto de cada paso: ignora picos sueltos de un cuadro
BOCA_RANGO_MINIMO = 0.15  # si la boca abre menos que esto sobre el reposo, se dejan los valores por defecto
FRACCION_BOCA_ABIERTA, FRACCION_BOCA_CERRADA = 0.6, 0.3  # sobre el rango reposo -> máximo
# Eje de cada dirección en (horizontal, vertical) y su signo
EJES = {"izquierda": (0, -1), "derecha": (0, 1), "arriba": (1, -1), "abajo": (1, 1)}


def _pico(valores):
    orden = sorted(valores)
    return orden[min(len(orden) - 1, int(PERCENTIL_PICO * len(orden)))] if orden else None


class Calibracion:
    """Guía la calibración inicial paso a paso y construye el Perfil del usuario."""

    def __init__(self, perfil_guardado: "Perfil" = None):
        # Con un perfil guardado solo queda el paso "luz": la iluminación cambia de un día a otro
        self.guardado = perfil_guardado
        self.pasos = PASOS_CALIBRACION[:1] if perfil_guardado is not None else PASOS_CALIBRACION
        self.i, self.tiempo = 0, 0.0
        self.muestras = {clave: [] for clave, _, _ in PASOS_CALIBRACION}  # (h, v, mandíbula)
        self.omitida = False  # tecla Esc: se usan los valores por defecto

    @property
    def terminada(self) -> bool:
        return self.omitida or self.i >= len(self.pasos)

    @property
    def paso(self) -> str:
        return "" if self.terminada else self.pasos[self.i][0]

    @property
    def instruccion(self) -> str:
        return "" if self.terminada else self.pasos[self.i][1]

    @property
    def progreso(self) -> float:
        """0 a 1 sobre toda la calibración."""
        if self.terminada:
            return 1.0
        return (self.i + self.tiempo / self.pasos[self.i][2]) / len(self.pasos)

    def agregar(self, dt: float, medidas=None, mandibula: float = 0.0):
        """Un cuadro de la cámara. medidas: (h, v) de medidas_cara, o None si no hay cara."""
        if self.terminada:
            return
        clave, _, duracion = self.pasos[self.i]
        if medidas is None and clave != "luz":
            return  # sin cara el tiempo no corre
        if medidas is not None:
            self.muestras[clave].append((*medidas, mandibula))
        self.tiempo += dt
        if self.tiempo >= duracion:
            self.i, self.tiempo = self.i + 1, 0.0

    def perfil(self) -> Perfil:
        if self.guardado is not None:
            return self.guardado
        reposo = self.muestras["centro"]
        if self.omitida or not reposo:
            return Perfil()
        centro = (statistics.median(m[0] for m in reposo), statistics.median(m[1] for m in reposo))
        umbrales, sin_calibrar = {}, []
        for direccion, (eje, signo) in EJES.items():
            pico = _pico([signo * (m[eje] - centro[eje]) for m in self.muestras[direccion]])
            if pico is not None and pico >= UMBRAL_MINIMO:
                umbrales[direccion] = max(UMBRAL_MINIMO, FRACCION_RANGO * pico)
            else:  # no se movió hacia ese lado: valor por defecto (esa dirección pedirá un giro mayor)
                umbrales[direccion] = UMBRAL_GIRO
                sin_calibrar.append(direccion)
        boca_reposo = statistics.median(m[2] for m in reposo)
        boca_max = _pico([m[2] for m in self.muestras["boca"]])
        abierta, cerrada = BOCA_ABIERTA, BOCA_CERRADA
        if boca_max is not None and boca_max - boca_reposo >= BOCA_RANGO_MINIMO:
            rango = boca_max - boca_reposo
            abierta = boca_reposo + FRACCION_BOCA_ABIERTA * rango
            cerrada = boca_reposo + FRACCION_BOCA_CERRADA * rango
        else:
            sin_calibrar.append("boca")
        return Perfil(centro[0], centro[1], umbrales, abierta, cerrada, tuple(sin_calibrar))


class Cruceta:
    """Convierte estados cuadro a cuadro en gestos sueltos, como una cruceta: cada movimiento
    cuenta una sola vez y hay que volver al centro con la boca cerrada antes del siguiente."""

    def __init__(self):
        self.armada = False  # si arranca con la cabeza girada, no dispara hasta pasar por el centro
        self.estado, self.cuadros = None, 0

    def actualizar(self, estado: str):
        """estado: una dirección, "centro", "pulsar" o "" (sin cara o boca a medias; no cambia nada).
        Devuelve el gesto ("izquierda", "derecha", "arriba", "abajo", "pulsar") o None."""
        self.cuadros = self.cuadros + 1 if estado == self.estado else 1
        self.estado = estado
        if self.cuadros != CUADROS_ESTABLES:  # justo al estabilizarse: mantenerlo no repite el gesto
            return None
        if estado == "centro":
            self.armada = True
        elif estado and self.armada:
            self.armada = False
            return estado
        return None


# ---------------------------------------------------------------------------
# Puntero con ojos y cara: mirar un bloque lo selecciona y quedarse en él lo activa
# ---------------------------------------------------------------------------
# Modelo de 478 puntos: (centro del iris, esquina, esquina, párpado superior, párpado inferior)
OJOS = ((468, 33, 133, 159, 145), (473, 362, 263, 386, 374))
RIDGE = 1e-2  # regularización del ajuste: evita que un punto mal mirado deforme todo
TIEMPO_PERMANENCIA = 1.5  # segundos mirando un bloque para activarlo
GRACIA = 0.3  # segundos que la mirada puede salirse del bloque sin reiniciar el tiempo (parpadeo, temblor)
# Filtro 1€ del puntero (posición en fracción de pantalla, velocidad en pantallas por segundo)
# Elegidos comparando con el suavizado fijo anterior (0,25 por cuadro) con ruido simulado de 1 a 4 % de
# pantalla: ~30 % menos temblor con la mirada quieta y la mitad de retraso en los saltos (0,13 s vs 0,25 s).
CORTE_MIN = 0.5  # Hz con la mirada quieta: más bajo = puntero más estable (y algo más lento al empezar a moverse)
BETA = 1.0  # cuánto sube el corte con la velocidad: más alto = menos retraso en los saltos (y más temblor)
CORTE_DERIVADA = 1.0  # Hz del suavizado de la velocidad (el valor del artículo original)


def rasgos_mirada(puntos) -> np.ndarray:
    """Lo que mueve el puntero: dónde está cada iris dentro de su ojo (4 valores) y hacia dónde
    apunta la cabeza (2 valores de medidas_cara). Así el usuario puede apuntar con los ojos,
    con la cabeza o con ambos, según lo que pueda mover."""
    valores = []
    for iris, a, b, arriba, abajo in OJOS:
        valores.append((puntos[iris].x - puntos[a].x) / max(puntos[b].x - puntos[a].x, 1e-6))
        valores.append((puntos[iris].y - puntos[arriba].y) / max(puntos[abajo].y - puntos[arriba].y, 1e-6))
    return np.array([*valores, *medidas_cara(puntos)])


class ModeloMirada:
    """Ajuste lineal (con ridge) de rasgos_mirada -> posición en pantalla, de 0 a 1 en x e y.
    Se entrena con las muestras de la calibración de pantalla."""

    def __init__(self, rasgos, posiciones):
        x = np.asarray(rasgos, float)
        self.media, self.escala = x.mean(axis=0), x.std(axis=0) + 1e-9
        a = self._diseno(x)
        # ponytail: lineal; si las esquinas quedan cortas, añadir términos cuadráticos en _diseno
        self.pesos = np.linalg.solve(a.T @ a + RIDGE * np.eye(a.shape[1]), a.T @ np.asarray(posiciones, float))

    def _diseno(self, x):
        x = (np.atleast_2d(x) - self.media) / self.escala
        return np.hstack([np.ones((len(x), 1)), x])

    def predecir(self, rasgos) -> tuple:
        x, y = (self._diseno(rasgos) @ self.pesos)[0]
        return float(np.clip(x, 0, 1)), float(np.clip(y, 0, 1))

    def a_dict(self) -> dict:
        return {"media": self.media.tolist(), "escala": self.escala.tolist(), "pesos": self.pesos.tolist()}

    @classmethod
    def desde_dict(cls, d: dict) -> "ModeloMirada":
        """Modelo guardado. Lanza KeyError, TypeError o ValueError si no tiene la forma esperada."""
        modelo = cls.__new__(cls)
        modelo.media, modelo.escala, modelo.pesos = (np.asarray(d[k], float) for k in ("media", "escala", "pesos"))
        n = 2 * len(OJOS) + 2  # rasgos_mirada: 2 por ojo más 2 de la cabeza
        if (modelo.media.shape != (n,) or modelo.escala.shape != (n,) or modelo.pesos.shape != (n + 1, 2)
                or not all(np.all(np.isfinite(a)) for a in (modelo.media, modelo.escala, modelo.pesos))
                or np.any(modelo.escala <= 0)):
            raise ValueError("el modelo de mirada guardado no tiene la forma esperada")
        return modelo

    def error_medio(self, rasgos, posiciones) -> float:
        """Distancia media (fracción de pantalla) entre lo predicho y los puntos mirados."""
        return float(np.mean([np.hypot(*(np.array(self.predecir(r)) - p)) for r, p in zip(rasgos, posiciones)]))


class FiltroUnEuro:
    """Filtro 1€ (Casiez, Roussel y Vogel, CHI 2012) para el puntero de la mirada. Es un suavizado
    exponencial cuyo corte depende de la velocidad: con la mirada quieta suaviza mucho (quita el
    temblor, que es lo que necesita la permanencia) y cuando la mirada salta a otro sitio casi no
    suaviza (no hay retraso). Usa la misma velocidad para x e y, así el puntero no se tuerce."""

    def __init__(self, corte_min: float = CORTE_MIN, beta: float = BETA, corte_derivada: float = CORTE_DERIVADA):
        self.corte_min, self.beta, self.corte_derivada = corte_min, beta, corte_derivada
        self.x, self.dx = None, np.zeros(2)

    @staticmethod
    def _alfa(dt: float, corte: float) -> float:
        tau = 1 / (2 * np.pi * corte)
        return 1 / (1 + tau / dt)

    def __call__(self, x, dt: float) -> tuple:
        x = np.asarray(x, float)
        if self.x is None or dt <= 0:
            self.x = x if self.x is None else self.x
            return tuple(self.x)
        self.dx = self.dx + self._alfa(dt, self.corte_derivada) * ((x - self.x) / dt - self.dx)
        corte = self.corte_min + self.beta * float(np.hypot(*self.dx))
        self.x = self.x + self._alfa(dt, corte) * (x - self.x)
        return tuple(self.x)


def dispersion(puntos) -> float:
    """Distancia máxima de los puntos a su centro: pequeña si la mirada está quieta (fijación)."""
    if not puntos:
        return 0.0
    centro = np.mean(puntos, axis=0)
    return float(np.max(np.hypot(*(np.asarray(puntos) - centro).T)))


class Permanencia:
    """Temporizador de permanencia: activa un bloque cuando la mirada se queda en él
    TIEMPO_PERMANENCIA segundos. Salidas de menos de GRACIA no reinician el tiempo. Tras activarlo
    hay que salir del bloque para poder activarlo otra vez (no se repite solo)."""

    def __init__(self):
        self.bloque, self.tiempo, self.fuera, self.usado = None, 0.0, 0.0, False

    def actualizar(self, bloque, dt: float, cargar: bool = True) -> bool:
        """bloque: el seleccionado por la mirada (o None). cargar=False pausa el tiempo sin perder
        lo acumulado (p. ej. mientras la mirada se mueve). Devuelve True cuando toca activarlo."""
        if bloque is not self.bloque:
            self.fuera += dt
            if self.bloque is not None and self.fuera < GRACIA:
                return False  # salida breve: se conserva el tiempo acumulado
            self.bloque, self.tiempo, self.fuera, self.usado = bloque, 0.0, 0.0, False
        else:
            self.fuera = 0.0
        if self.bloque is None or self.usado or not cargar:
            return False
        self.tiempo += dt
        if self.tiempo >= TIEMPO_PERMANENCIA:
            self.usado = True
            return True
        return False

    @property
    def progreso(self) -> float:
        """0 a 1 hacia la activación del bloque actual."""
        return 0.0 if self.bloque is None or self.usado else min(1.0, self.tiempo / TIEMPO_PERMANENCIA)


# ---------------------------------------------------------------------------
# Calibración guardada: perfil de la cara y modelo de la mirada, para no calibrar en cada arranque
# ---------------------------------------------------------------------------
# En la carpeta del proyecto (app/datos, fuera de git: es de cada equipo); Docker la ve por el volumen ./app
RUTA_CALIBRACION = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos", "calibracion.json")
VERSION_CALIBRACION = 1  # cambiarla si cambia el formato: lo guardado con otra versión se ignora


def cargar_calibracion(ruta: str = None) -> tuple:
    """(perfil o None, modelo de mirada o None). Nunca lanza: si el archivo falta o está dañado,
    la parte que no se pueda leer se vuelve a calibrar."""
    ruta = ruta or RUTA_CALIBRACION
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as e:
        print(f"Calibración guardada ilegible ({e}): se vuelve a calibrar", flush=True)
        return None, None
    if not isinstance(datos, dict) or datos.get("version") != VERSION_CALIBRACION:
        print("Calibración guardada con otro formato: se vuelve a calibrar", flush=True)
        return None, None
    partes = []
    for clave, clase in (("perfil", Perfil), ("mirada", ModeloMirada)):
        try:
            partes.append(clase.desde_dict(datos[clave]) if clave in datos else None)
        except (KeyError, TypeError, ValueError) as e:
            print(f"Calibración guardada: '{clave}' dañado ({e}), se vuelve a calibrar esa parte", flush=True)
            partes.append(None)
    return tuple(partes)


def guardar_calibracion(ruta: str = None, perfil: Perfil = None, modelo: "ModeloMirada" = None) -> bool:
    """Guarda las partes dadas y conserva las otras. Escribe en un temporal y lo renombra, así
    un corte a medias no deja el archivo roto. Devuelve False si no se pudo (y sigue sin guardar)."""
    ruta = ruta or RUTA_CALIBRACION
    try:
        try:
            with open(ruta, encoding="utf-8") as f:
                datos = json.load(f)
            if not isinstance(datos, dict) or datos.get("version") != VERSION_CALIBRACION:
                datos = {}
        except (FileNotFoundError, ValueError):
            datos = {}
        datos["version"] = VERSION_CALIBRACION
        if perfil is not None:
            datos["perfil"] = perfil.a_dict()
        if modelo is not None:
            datos["mirada"] = modelo.a_dict()
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta + ".tmp", "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.replace(ruta + ".tmp", ruta)
        return True
    except OSError as e:
        print(f"No pude guardar la calibración ({e})", flush=True)
        return False


def borrar_calibracion(ruta: str = None):
    try:
        os.remove(ruta or RUTA_CALIBRACION)
    except FileNotFoundError:
        pass


class HiloCamara(QThread):
    """Lee la cámara y ejecuta MediaPipe fuera del hilo de la interfaz."""

    fotograma = pyqtSignal(QImage, int, float, str)  # imagen, rostros detectados, fps, dirección
    error = pyqtSignal(str)
    gesto = pyqtSignal(str)  # "izquierda", "derecha", "arriba", "abajo" o "pulsar"
    calibrando = pyqtSignal(str, str, float, bool)  # paso, instrucción, progreso 0-1, cara a la vista
    calibrado = pyqtSignal(str, tuple, object)  # resumen, lo que quedó sin calibrar, Perfil; desde aquí, cruceta
    rasgos = pyqtSignal(object)  # rasgos_mirada de cada cuadro con cara, tras la calibración inicial

    def __init__(self, parent=None, con_imagen=True, perfil_guardado: Perfil = None):
        super().__init__(parent)
        self.reiniciar = False  # "Volver a calibrar": el bucle empieza de cero (con self.calibracion nueva)
        # False: solo se calcula la dirección; no se dibuja la malla ni se crea la QImage
        self.con_imagen = con_imagen
        self.calibracion = Calibracion(perfil_guardado)  # corre al arrancar, antes de la cruceta
        # Mientras devuelva True, la calibración no avanza (la interfaz lo usa mientras lee en voz alta)
        self.pausa = lambda: False
        # Se abre en el hilo principal: en macOS OpenCV solo puede pedir el permiso de cámara desde ahí.
        # Se prueban los primeros índices hasta dar con una cámara que entregue imagen.
        self.cap, self.indice = None, None
        indices = [int(CAMARA_FORZADA)] if CAMARA_FORZADA is not None else range(MAX_CAMARAS)
        for i in indices:
            cap = cv2.VideoCapture(i)
            if cap.isOpened() and cap.read()[0]:
                self.cap, self.indice = cap, i
                break
            cap.release()

    def run(self):
        if self.cap is None:
            self.error.emit(MENSAJE_SIN_CAMARA)
            return
        try:
            self._procesar(self.cap)
        except Exception as e:  # p. ej. falta el modelo .task
            self.error.emit(f"Error de MediaPipe: {e}")
        finally:
            self.cap.release()

    def _procesar(self, cap):
        opciones = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODELO),
            running_mode=vision.RunningMode.VIDEO,
            output_face_blendshapes=True,  # jawOpen: abrir la boca pulsa
        )
        cruceta, perfil, listo = Cruceta(), PERFIL_BASE, False
        curva, luz_revisada = None, False
        with vision.FaceLandmarker.create_from_options(opciones) as detector:
            marca_ms = 0
            anterior = time.monotonic()
            while not self.isInterruptionRequested():
                if self.reiniciar:  # todo desde cero, también la revisión de la luz
                    self.reiniciar = False
                    cruceta, perfil, listo, curva, luz_revisada = Cruceta(), PERFIL_BASE, False, None, False
                ok, bgr = cap.read()
                if not ok:
                    self.error.emit("La cámara dejó de enviar imagen")
                    break
                ahora = time.monotonic()
                dt, anterior = max(ahora - anterior, 1e-6), ahora

                # La luz se revisa una sola vez, al terminar el paso "luz" (la exposición automática
                # ya se asentó). Si hace falta, CLAHE se calcula entonces y después solo se aplica
                # su curva, que cuesta una consulta en tabla por píxel.
                if not luz_revisada and self.calibracion.paso != "luz":
                    curva, luz_revisada = curva_si_hace_falta(bgr), True
                if curva is not None:
                    bgr = cv2.LUT(bgr, curva)

                rgb = cv2.cvtColor(cv2.flip(bgr, 1), cv2.COLOR_BGR2RGB)  # espejo, como un selfie
                # VIDEO exige marcas de tiempo estrictamente crecientes
                marca_ms = max(marca_ms + 1, int(time.monotonic() * 1000))
                entrada = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                resultado = detector.detect_for_video(entrada, marca_ms)

                for rostro in resultado.face_landmarks if self.con_imagen else ():
                    drawing_utils.draw_landmarks(
                        rgb,
                        rostro,
                        vision.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=drawing_styles.get_default_face_mesh_tesselation_style(),
                    )

                # Primera cara; sin nadie, dirección y estado vacíos
                cara = resultado.face_landmarks[0] if resultado.face_landmarks else None
                mandibula = 0.0
                if cara:
                    mandibula = next(c.score for c in resultado.face_blendshapes[0] if c.category_name == "jawOpen")
                direccion = direccion_cabeza(cara, perfil) if cara else ""

                if not listo:  # calibración: no hay gestos hasta terminarla
                    if not self.pausa():
                        self.calibracion.agregar(dt, medidas_cara(cara) if cara else None, mandibula)
                    if self.calibracion.terminada:
                        perfil, cruceta, listo = self.calibracion.perfil(), Cruceta(), True
                        luz = "corregida con CLAHE" if curva is not None else "buena, sin corrección"
                        self.calibrado.emit(f"{perfil.resumen()} · luz: {luz}", perfil.sin_calibrar, perfil)
                    else:
                        self.calibrando.emit(self.calibracion.paso, self.calibracion.instruccion,
                                             self.calibracion.progreso, cara is not None)
                else:
                    gesto = cruceta.actualizar(estado_cara(cara, mandibula, perfil) if cara else "")
                    if gesto:
                        self.gesto.emit(gesto)
                    if cara:
                        self.rasgos.emit(rasgos_mirada(cara))

                fps = 1.0 / dt
                imagen = QImage()
                if self.con_imagen:
                    alto, ancho, _ = rgb.shape
                    # .copy(): QImage no copia el buffer de numpy, que se reutiliza en la siguiente vuelta
                    imagen = QImage(rgb.data, ancho, alto, 3 * ancho, QImage.Format_RGB888).copy()
                self.fotograma.emit(imagen, len(resultado.face_landmarks), fps, direccion)



if __name__ == "__main__":
    # Autoverificación de direccion_cabeza con caras sintéticas (x, y normalizados)
    from types import SimpleNamespace as P

    def cara(nx, ny):
        puntos = [P(x=0.5, y=0.5)] * 468
        puntos[MEJILLA_A], puntos[MEJILLA_B] = P(x=0.3, y=0.5), P(x=0.7, y=0.5)
        puntos[FRENTE], puntos[MENTON] = P(x=0.5, y=0.2), P(x=0.5, y=0.8)
        puntos[NARIZ] = P(x=nx, y=ny)
        return puntos

    assert direccion_cabeza(cara(0.5, 0.53)) == "centro"
    assert direccion_cabeza(cara(0.38, 0.53)) == "izquierda"
    assert direccion_cabeza(cara(0.62, 0.53)) == "derecha"
    assert direccion_cabeza(cara(0.5, 0.40)) == "arriba"
    assert direccion_cabeza(cara(0.5, 0.66)) == "abajo"
    print("direccion_cabeza: OK")

    assert estado_cara(cara(0.62, 0.53), 0.1) == "derecha"
    assert estado_cara(cara(0.62, 0.53), 0.3) == ""  # boca a medias: no se lee la dirección
    assert estado_cara(cara(0.5, 0.53), 0.6) == "pulsar"
    print("estado_cara: OK")

    c = Cruceta()
    gestos = lambda estados: [g for g in map(c.actualizar, estados) if g]
    n = CUADROS_ESTABLES
    assert gestos(["derecha"] * (n + 2)) == []  # arranca girada: nada hasta pasar por el centro
    assert gestos(["centro"] * n + ["derecha"] * (n * 3)) == ["derecha"]  # mantenerla no repite
    assert gestos(["izquierda"] * (n + 2)) == []  # sin volver al centro no hay otro gesto
    assert gestos(["centro"] * n + [""] * 3 + ["pulsar"] * (n + 1)) == ["pulsar"]  # abrir la boca
    assert gestos(["centro"] * n + ["arriba"] * (n - 1) + ["centro"] * n) == []  # temblor corto
    assert gestos([""] * 10 + ["abajo"] * n) == ["abajo"]  # perder la cara no desarma
    print("Cruceta: OK")

    # Calibración con un usuario que gira poco a la derecha y casi nada hacia arriba
    cal, dt = Calibracion(), 1 / 30
    reposo = (0.02, 0.50)
    postura = {"luz": None, "centro": reposo, "volver": reposo, "izquierda": (-0.20, 0.50),
               "derecha": (0.10, 0.50), "arriba": (0.02, 0.49), "abajo": (0.02, 0.62), "boca": reposo}
    while not cal.terminada:
        cal.agregar(dt, postura[cal.paso], 0.7 if cal.paso == "boca" else 0.05)
        if cal.paso == "centro" and cal.tiempo < 0.5:
            cal.agregar(dt, None)  # perder la cara no hace avanzar el paso
    p = cal.perfil()
    assert abs(p.centro_h - 0.02) < 1e-9 and abs(p.centro_v - 0.50) < 1e-9
    assert abs(p.umbrales["izquierda"] - max(UMBRAL_MINIMO, FRACCION_RANGO * 0.22)) < 1e-9  # alcanzó 0,22
    assert abs(p.umbrales["derecha"] - max(UMBRAL_MINIMO, FRACCION_RANGO * 0.08)) < 1e-9  # alcanzó 0,08
    assert p.umbrales["arriba"] == UMBRAL_GIRO and p.sin_calibrar == ("arriba",)  # casi no subió
    assert abs(p.umbrales["abajo"] - max(UMBRAL_MINIMO, FRACCION_RANGO * 0.12)) < 1e-9
    assert abs(p.boca_abierta - (0.05 + 0.6 * 0.65)) < 1e-9 and abs(p.boca_cerrada - (0.05 + 0.3 * 0.65)) < 1e-9
    # Con el perfil, un giro pequeño a la derecha ya cuenta, pero el mismo a la izquierda no
    assert direccion_cabeza(cara(0.5 + 0.4 * (0.02 + 0.05), 0.2 + 0.6 * 0.50), p) == "derecha"
    assert direccion_cabeza(cara(0.5 + 0.4 * (0.02 - 0.05), 0.2 + 0.6 * 0.50), p) == "centro"
    assert Calibracion().perfil() == Perfil()  # sin datos (o con Esc): valores por defecto
    print("Calibracion: OK")

    # CLAHE: en una imagen oscura y de poco contraste, la curva aclara y es creciente
    oscura = np.tile(np.linspace(20, 70, 640, dtype=np.uint8), (480, 1))
    curva = curva_clahe(cv2.merge([oscura] * 3))
    assert curva.shape == (256,) and np.all(np.diff(curva.astype(int)) >= 0)
    assert cv2.LUT(oscura, curva).std() > oscura.std()  # más contraste
    assert curva_si_hace_falta(cv2.merge([oscura] * 3)) is not None  # oscura: se corrige
    buena = np.tile(np.linspace(0, 255, 640).astype(np.uint8), (480, 1))  # brillo 127, contraste 74
    assert curva_si_hace_falta(cv2.merge([buena] * 3)) is None  # buena luz: no se toca
    print("curva_clahe: OK")

    # ModeloMirada: con rasgos que dependen (con ruido) de la posición mirada, la recupera
    azar = np.random.default_rng(0)
    objetivos = azar.uniform(0, 1, (400, 2))
    mezcla = azar.normal(size=(2, 6))
    rasgos = objetivos @ mezcla + azar.normal(scale=0.01, size=(400, 6))
    modelo = ModeloMirada(rasgos, objetivos)
    error = max(np.hypot(*(np.array(modelo.predecir(r)) - o)) for r, o in zip(rasgos, objetivos))
    assert error < 0.05, error
    assert modelo.predecir(np.array([9.0, 9, 9, 9, 9, 9]) * 100) in {(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)}
    assert modelo.error_medio(rasgos, objetivos) < 0.02
    quieto = azar.normal(scale=0.001, size=(400, 6))  # no movió los ojos ni la cabeza: el ajuste no sirve
    assert ModeloMirada(quieto, objetivos).error_medio(quieto, objetivos) > 0.15
    print("ModeloMirada: OK")

    # Permanencia a 30 cuadros por segundo
    per, dt, A, B = Permanencia(), 1 / 30, "bloque A", "bloque B"
    activaciones = lambda bloques: sum(per.actualizar(b, dt) for b in bloques)
    n = round(TIEMPO_PERMANENCIA * 30)
    assert activaciones([A] * (n - 2)) == 0 and 0.9 < per.progreso < 1  # aún no
    assert activaciones([A] * 3) == 1 and per.progreso == 0  # se activa una vez
    assert activaciones([A] * n * 2) == 0  # quedarse no la repite
    assert activaciones([None] * 15 + [A] * (n + 1)) == 1  # salir y volver la rehabilita
    assert activaciones([B] * 5) == 0 and per.bloque == A  # pasar a otro bloque también espera GRACIA
    per = Permanencia()
    assert activaciones([B] * (n // 2) + [None] * 5 + [B] * (n // 2 + 2)) == 1  # parpadeo corto: no reinicia
    per = Permanencia()
    assert activaciones([B] * (n // 2) + [None] * 15 + [B] * (n // 2 + 2)) == 0  # salida larga: reinicia
    per = Permanencia()
    activaciones([B] * 10)
    antes = per.progreso
    assert not any(per.actualizar(B, dt, cargar=False) for _ in range(n * 2)) and per.progreso == antes  # pausa
    assert activaciones([B] * (n - 10)) == 1  # al volver a cargar sigue donde iba
    assert dispersion([(0.5, 0.5)] * 5) == 0 and abs(dispersion([(0.4, 0.5), (0.6, 0.5)]) - 0.1) < 1e-9

    # Filtro 1€: mirada quieta con ruido y luego un salto al otro lado de la pantalla, a 30 cuadros/s
    filtro, dt = FiltroUnEuro(), 1 / 30
    ruido = azar.normal(scale=0.02, size=(150, 2))
    quieta = [filtro((0.3, 0.5) + r, dt) for r in ruido[:90]]
    salto = [filtro((0.7, 0.5) + r, dt) for r in ruido[90:]]
    temblor_crudo, temblor = ruido[30:90].std(axis=0).mean(), np.array(quieta[30:]).std(axis=0).mean()  # por eje
    retraso = next(i for i, p in enumerate(salto) if p[0] > 0.3 + 0.9 * 0.4) * dt  # hasta el 90 % del salto
    assert temblor < temblor_crudo / 3, (temblor, temblor_crudo)  # quieta: tiembla mucho menos
    assert retraso < 0.2, retraso  # salto: llega en menos de 0,2 s
    print(f"FiltroUnEuro: OK (temblor {temblor:.4f} vs {temblor_crudo:.4f} sin filtro; llega al 90 % en {retraso:.2f} s)")
    print("Permanencia: OK")

    # Calibración guardada: ida y vuelta, archivo roto, partes sueltas y formas incorrectas
    import tempfile
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = os.path.join(carpeta, "sub", "calibracion.json")
        assert cargar_calibracion(ruta) == (None, None)  # no existe: hay que calibrar
        assert guardar_calibracion(ruta, perfil=p)  # p: el perfil calibrado más arriba
        perfil_leido, modelo_leido = cargar_calibracion(ruta)
        assert perfil_leido == p and modelo_leido is None  # solo la cara: falta la pantalla
        assert guardar_calibracion(ruta, modelo=modelo)  # añade la mirada y conserva el perfil
        perfil_leido, modelo_leido = cargar_calibracion(ruta)
        assert perfil_leido == p and modelo_leido.predecir(rasgos[0]) == modelo.predecir(rasgos[0])
        assert Calibracion(p).pasos == PASOS_CALIBRACION[:1] and Calibracion(p).perfil() is p  # solo la luz
        with open(ruta, "w") as f:
            f.write("{roto")
        assert cargar_calibracion(ruta) == (None, None)  # dañado: se recalibra, sin lanzar
        with open(ruta, "w") as f:
            json.dump({"version": VERSION_CALIBRACION, "perfil": {"centro_h": "x"}, "mirada": {"media": [1, 2]}}, f)
        assert cargar_calibracion(ruta) == (None, None)
        with open(ruta, "w") as f:
            json.dump({"version": 999, "perfil": p.a_dict()}, f)
        assert cargar_calibracion(ruta) == (None, None)  # otro formato
        borrar_calibracion(ruta)
        borrar_calibracion(ruta)  # borrar dos veces no falla
        assert not os.path.exists(ruta)
    print("calibración guardada: OK")
