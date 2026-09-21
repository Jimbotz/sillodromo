"""
prueba_botones_mirada.py - Prueba independiente: seleccion de botones con la mirada.

Sustituye OpenFace por MediaPipe FaceLandmarker (el mismo modelo que usa la app)
y prueba la logica de seleccion de botones por mirada:

  1. Calibracion de 4 puntos (arriba, derecha, abajo, izquierda).
  2. Prediccion de la posicion de la mirada en pantalla (Ridge con numpy).
  3. Seleccion de botones por dos vias:
     - Dwell: mantener la mirada sobre un boton ~1.2 s (anillo de progreso).
     - Click por gesto: ALZAR LAS CEJAS activa el boton anclado. Se
       calibra en CADA punto (4 perspectivas de cabeza): por direccion se
       registra tu ratio neutro y alzado de cejas, y el click usa los
       umbrales de la direccion en la que estas mirando.

Uso:
    .\\.venv\\Scripts\\python.exe app\\prueba_botones_mirada.py

Controles: ESC para salir, R para recalibrar, alzar las cejas = click.
"""

import os
import sys
import time
import ctypes

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

MODOLO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelos", "face_landmarker.task")
DELEGADO = BaseOptions.Delegate.GPU if sys.platform == "darwin" else BaseOptions.Delegate.CPU
MAX_CAMARAS = 4

# ---------------------------------------------------------------------------
# Referencias del modelo de 478 puntos (con perillas/iris)
# ---------------------------------------------------------------------------
NARIZ, MEJILLA_A, MEJILLA_B, FRENTE, MENTON = 1, 234, 454, 10, 152
# Ojo izquierdo: comisuras 33 (externa) y 133 (interna), parpados 159 (sup) y 145 (inf)
OJO_IZQ = (33, 133, 159, 145, 468)   # el 5o indice es el centro del iris
# Ojo derecho: comisuras 362 (interna) y 263 (externa), parpados 386 (sup) y 374 (inf)
OJO_DER = (362, 263, 386, 374, 473)

# Cejas: punto medio de cada ceja (105 izquierda, 334 derecha); se compara
# con los centros del iris (468, 473) para detectar el gesto de alzarlas
CEJA_IZQ, CEJA_DER = 105, 334


class RidgeModel:
    """Regresion Ridge con numpy, con estandarizacion interna de features.

    Sin estandarizar, la colinealidad entre las features crudas y sus deltas
    hace que la penalizacion encoja la prediccion hacia la media (error de
    decenas de px). Al escalar cada feature a varianza 1, la penalizacion
    es isótropa y el ajuste queda fiel.
    """

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self.coef = None
        self.mu = None
        self.sd = None

    def _diseno(self, X):
        X = np.asarray(X, dtype=np.float64)
        if self.mu is not None:
            X = (X - self.mu) / self.sd
        return np.hstack([np.ones((X.shape[0], 1)), X])

    def fit(self, X, y) -> None:
        X = np.asarray(X, dtype=np.float64)
        self.mu = X.mean(axis=0)
        self.sd = X.std(axis=0) + 1e-9
        design = self._diseno(X)
        reg = self.alpha * np.eye(design.shape[1])
        reg[0, 0] = 0.0
        self.coef = np.linalg.solve(
            design.T @ design + reg, design.T @ np.asarray(y, dtype=np.float64)
        )

    def predict(self, x):
        x = np.atleast_2d(np.asarray(x, dtype=np.float64))
        design = self._diseno(x)
        return design @ self.coef


class FiltroOneEuro:
    """Filtro One Euro por dimension: se comporta como un paso bajo agresivo
    en reposo (mata el temblor del iris) y abre el corte al moverse rapido
    (no introduce retraso apreciable). Estadar en eye-tracking."""

    def __init__(self, n, freq=30.0, min_cutoff=1.0, beta=0.08, d_cutoff=1.0):
        self.freq, self.min_cutoff, self.beta, self.d_cutoff = freq, min_cutoff, beta, d_cutoff
        self.x_prev = None
        self.dx_prev = np.zeros(n)

    @staticmethod
    def _alpha(cutoff, freq):
        tau = 1.0 / (2.0 * np.pi * cutoff)
        return 1.0 / (1.0 + tau * freq)  # te = 1/freq -> tau/te = tau*freq

    def filtrar(self, x):
        x = np.asarray(x, dtype=np.float64)
        if self.x_prev is None:
            self.x_prev = x.copy()
            return self.x_prev.copy()
        dx = (x - self.x_prev) * self.freq
        a_d = self._alpha(self.d_cutoff, self.freq)
        dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev
        a = self._alpha(self.min_cutoff + self.beta * np.abs(dx_hat), self.freq)
        x_hat = a * x + (1.0 - a) * self.x_prev
        self.x_prev, self.dx_prev = x_hat.copy(), dx_hat
        return x_hat.copy()


def extraer_features(puntos) -> np.ndarray:
    """14 descriptores de mirada a partir de los landmarks de MediaPipe.

    Crudos (7):
      [0-1] posicion relativa del iris izquierdo dentro del ojo (x, y)
      [2-3] posicion relativa del iris derecho dentro del ojo (x, y)
      [4-5] orientacion de la cabeza: posicion de la nariz en la cara (h, v)
      [6]   escala: ancho de la cara (distancia aproximada a la camara)
    Deltas (7): respecto a la referencia central de la sesion.
    """
    def iris_en_ojo(ojo):
        ext, inte, sup, inf, iris = (puntos[i] for i in ojo)
        w = max(inte.x - ext.x, 1e-6)
        h = max(inf.y - sup.y, 1e-6)
        return (iris.x - ext.x) / w, (iris.y - sup.y) / h

    izq_x, izq_y = iris_en_ojo(OJO_IZQ)
    der_x, der_y = iris_en_ojo(OJO_DER)

    lado_a, lado_b = sorted((puntos[MEJILLA_A].x, puntos[MEJILLA_B].x))
    escala = max(lado_b - lado_a, 1e-6)
    head_h = (puntos[NARIZ].x - lado_a) / escala - 0.5
    head_v = (puntos[NARIZ].y - puntos[FRENTE].y) / max(
        puntos[MENTON].y - puntos[FRENTE].y, 1e-6
    ) - 0.55

    raw = np.array([izq_x, izq_y, der_x, der_y, head_h, head_v, escala], dtype=np.float64)
    raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
    return raw


def ratio_cejas(puntos) -> float:
    """Altura relativa de las cejas: distancia vertical de cada ceja al
    centro del iris, normalizada por la altura de la cara (frente-menton).
    Al alzar las cejas la distancia crece ~10-20% sobre lo neutral."""
    frente, menton = puntos[FRENTE], puntos[MENTON]
    alto_cara = max(float(np.hypot(frente.x - menton.x, frente.y - menton.y)), 1e-6)
    gaps = []
    for ceja, iris in ((CEJA_IZQ, OJO_IZQ[4]), (CEJA_DER, OJO_DER[4])):
        c, i = puntos[ceja], puntos[iris]
        gaps.append((i.y - c.y) / alto_cara)  # y crece hacia abajo: ceja mas
                                              # arriba -> mayor distancia
    return float(np.mean(gaps))


class LectorMirada:
    """Hilo de fondo: abre la camara y corre MediaPipe fuera del bucle principal."""

    def __init__(self):
        self.cap = None
        self.ultimo_frame = None      # para el PiP
        self.ultimo_raw = None        # features crudos de la ultima cara
        self.lock = __import__("threading").Lock()
        self.activo = False

    def start(self, camera_index=0):
        for i in range(MAX_CAMARAS):
            cap = cv2.VideoCapture(i)
            if cap.isOpened() and cap.read()[0]:
                self.cap = cap
                break
            cap.release()
        if self.cap is None:
            raise RuntimeError("No se pudo abrir ninguna camara.")

        opciones = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODOLO, delegate=DELEGADO),
            running_mode=vision.RunningMode.VIDEO,
        )
        self.activo = True
        self._hilo = __import__("threading").Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    def _bucle(self):
        opciones = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODOLO, delegate=DELEGADO),
            running_mode=vision.RunningMode.VIDEO,
        )
        marca_ms = 0
        with vision.FaceLandmarker.create_from_options(opciones) as detector:
            while self.activo:
                ok, bgr = self.cap.read()
                if not ok:
                    time.sleep(0.01)
                    continue
                espejo = cv2.flip(bgr, 1)  # selfie, como en la app
                rgb = cv2.cvtColor(espejo, cv2.COLOR_BGR2RGB)
                marca_ms = max(marca_ms + 1, int(time.monotonic() * 1000))
                entrada = mp.Image(
                    image_format=mp.ImageFormat.SRGBA,
                    data=cv2.cvtColor(rgb, cv2.COLOR_RGB2RGBA),
                )
                resultado = detector.detect_for_video(entrada, marca_ms)

                with self.lock:
                    self.ultimo_frame = espejo.copy()
                    if resultado.face_landmarks:
                        self.ultimo_raw = extraer_features(resultado.face_landmarks[0])
                        self.ultima_cejas = ratio_cejas(resultado.face_landmarks[0])
                    else:
                        self.ultimo_raw = None
                        self.ultima_cejas = None

    def get_raw(self):
        with self.lock:
            return None if self.ultimo_raw is None else self.ultimo_raw.copy()

    def get_cejas(self):
        with self.lock:
            return self.ultima_cejas

    def get_frame(self):
        with self.lock:
            return None if self.ultimo_frame is None else self.ultimo_frame.copy()

    def stop(self):
        self.activo = False
        if getattr(self, "_hilo", None):
            self._hilo.join(timeout=2)
        if self.cap:
            self.cap.release()


def screen_resolution() -> tuple:
    """Resolucion real de la pantalla principal (DPI-aware)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    return (
        ctypes.windll.user32.GetSystemMetrics(0),
        ctypes.windll.user32.GetSystemMetrics(1),
    )


class PruebaBotones:
    """Calibracion de 4 puntos + seleccion de botones por dwell."""

    DUR_CENTRO = 1.5      # s capturando la referencia central
    DUR_ESPERA = 0.8      # s volviendo al centro antes de cada punto
    DUR_PREP = 0.8        # s de preparacion sobre el objetivo
    DUR_CAPTURA = 2.0     # s capturando cada punto
    DWELL_SEG = 1.2       # s de mirada sostenida para seleccionar un boton
    ESTABILIDAD_FRAMES = 6  # frames seguidos para cambiar el boton anclado
    VENTANA_MEDIANA = 5     # frames de mediana para la prediccion
    # Click por gesto: ALZAR LAS CEJAS. Se calibra en CADA punto de la
    # calibracion (4 perspectivas de cabeza): en cada punto se registra el
    # ratio neutro (mientras se mira el boton) y el ratio con las cejas
    # alzadas. El click dispara al superar el punto medio entre ambos.
    CEJA_ALZADO_SEG = 1.0    # s capturando el gesto alzado en cada punto
    CEJA_MIN_GAP = 0.015     # gap minimo neutro->alzado para confiar en el punto
    # Fallback si el gesto no se calibro: umbrales sobre el neutral central
    CEJA_SUBE_ABS = 0.19
    CEJA_BAJA_ABS = 0.16

    def __init__(self):
        self.lector = LectorMirada()
        self.modelo_x = RidgeModel(alpha=1.0)
        self.modelo_y = RidgeModel(alpha=1.0)
        self.referencia_centro = None
        self.cejas_neutro = None    # neutral de cejas capturada por sesion
        self._cejas_datos = []      # ratios de cejas durante la referencia central
        self.centroides = None      # centroide de features por boton (k = 4)
        self.segmentos = None       # nivel 1: 3 segmentos horizontales
        self._snap_idx = None       # boton anclado actualmente (histéresis)
        self._muestra_datos = []    # muestras engineered por boton durante la calibracion
        self._bloqueados = set()    # botones por re-armar: se activan una vez
                                    # y quedan bloqueados hasta que la mirada
                                    # sale de ellos y vuelve a entrar
        self._filtro = FiltroOneEuro(7)
        self._ventana = []          # ultimas features filtradas (mediana)
        self._candidato = None      # snap: boton que compite por el ancla
        self._cand_cont = 0         # frames consecutivos del candidato
        self._cejas_alzadas = False  # estado del gesto de click (HUD)
        self._flash_click = 0.0     # segundos restantes de destello al hacer click
        # Umbral del click POR PERSPECTIVA (calibrado en cada punto):
        # neutro y alzado del ratio de cejas mirando cada boton
        self.neutro_por = None      # [4] ratio neutro por boton
        self.alzado_por = None      # [4] ratio con cejas alzadas por boton

        self.screen_w, self.screen_h = screen_resolution()
        self.ventana = "Sillodromo - Prueba botones por mirada"

        # 4 botones en cruz: el centro es solo referencia de calibracion,
        # no es boton seleccionable.
        cx, cy = self.screen_w // 2, self.screen_h // 2
        off_x = int(self.screen_w * 0.28)
        off_y = int(self.screen_h * 0.28)
        self.puntos = [
            (cx, cy - off_y),   # arriba
            (cx + off_x, cy),   # derecha
            (cx, cy + off_y),   # abajo
            (cx - off_x, cy),   # izquierda
        ]
        self.etiquetas = ["ARRIBA", "DERECHA", "ABAJO", "IZQUIERDA"]
        self.centro_ref = (cx, cy)

        self.botones = []
        self._crear_botones()

    def _crear_botones(self):
        lado = int(min(self.screen_w, self.screen_h) * 0.12)
        self.botones = [
            {"centro": (x, y), "lado": lado, "activado": False, "progreso": 0.0}
            for (x, y) in self.puntos
        ]

    # ------------------------------------------------------------------
    # Features extendidas: crudos (7) + deltas vs centro (7) = 14
    # ------------------------------------------------------------------
    @staticmethod
    def build_features(raw, centro=None):
        raw = np.asarray(raw, dtype=np.float64).reshape(-1)
        if centro is None:
            deltas = np.zeros(7, dtype=np.float64)
        else:
            centro = np.asarray(centro, dtype=np.float64).reshape(-1)
            deltas = raw - centro
            deltas[6] = 0.0  # la escala no debe restarse: normaliza la distancia
        extras = PruebaBotones._cuadraticos(raw)
        return np.concatenate([raw, deltas, extras])

    @staticmethod
    def _cuadraticos(raw):
        """Terminos cuadraticos y de interaccion: la relacion mirada->pantalla
        no es lineal (el ojo rota en esferico), estos terminos capturan la
        curvatura y reducen el error en las esquinas de la pantalla."""
        gx = (raw[0] + raw[2]) / 2.0   # gaze horizontal conjunto
        gy = (raw[1] + raw[3]) / 2.0   # gaze vertical conjunto
        hx, hy = raw[4], raw[5]        # rotacion de cabeza
        return np.array([gx * gx, gy * gy, gx * gy, hx * hx, hy * hy, gx * hx])

    # ------------------------------------------------------------------
    # Snap: el cursor se ancla al boton mas cercano
    # ------------------------------------------------------------------
    def _reset_calibracion(self):
        self.centroides = None
        self.segmentos = None
        self._seg_de = np.zeros(4, dtype=int)
        self._snap_idx = None
        self.cejas_neutro = None
        self._cejas_datos = []
        self._cejas_alzadas = False
        self._flash_click = 0.0
        self.neutro_por = None
        self.alzado_por = None
        self._muestra_datos = []
        self._bloqueados = set()
        self._filtro = FiltroOneEuro(7)   # estado limpio por sesion
        self._ventana = []
        self._candidato = None
        self._cand_cont = 0

    def _observar(self, raw):
        """Pipeline de estabilizacion: One Euro + mediana de ventana.
        Se usa igual en calibracion y en vivo para que los datos
        compartan la misma distribucion."""
        if raw is None:
            return None
        filtrado = self._filtro.filtrar(raw)
        self._ventana.append(filtrado)
        if len(self._ventana) > self.VENTANA_MEDIANA:
            self._ventana.pop(0)
        return np.median(np.asarray(self._ventana), axis=0)

    def clasificar(self, raw):
        """Indice del boton al que se esta mirando, en dos niveles.

        Nivel 1 (grueso): 3 segmentos horizontales de la pantalla
        (IZQUIERDA / CENTRO / DERECHA), cada uno con su centroide de features.
        Nivel 2 (fino): dentro del segmento ganador, el boton con el centroide
        mas cercano. Decidir de a dos niveles (3 opciones y despues 1-2)
        es mas estable que elegir entre todos los botones de golpe.

        La decision jerarquica se expresa como puntaje por boton:
            score(i) = dist_a_segmento(seg(i)) + dist_a_boton(i)
        asi el ancla con su sosten sigue operando sobre los 4 indices.
        """
        feats = self.build_features(raw, self.referencia_centro).reshape(1, -1)
        dist_boton = np.linalg.norm(self.centroides - feats, axis=1)

        if self.segmentos is None:
            # fallback: centroide mas cercano entre todos los botones
            return int(np.argmin(dist_boton)), dist_boton

        dist_seg = np.linalg.norm(
            np.vstack([s["centroide"] for s in self.segmentos]) - feats, axis=1
        )
        scores = dist_seg[self._seg_de] + dist_boton
        return int(np.argmin(scores)), scores

    @staticmethod
    def _segmento_de(pt, screen_w):
        """Segmento horizontal de un punto de pantalla: 0 izquierda,
        1 centro, 2 derecha (con zona muerta alrededor del centro)."""
        cx = screen_w // 2
        margen = int(screen_w * 0.08)
        if pt[0] < cx - margen:
            return 0
        if pt[0] > cx + margen:
            return 2
        return 1

    def snap_boton(self, raw):
        """Boton anclado con doble estabilizacion:
        1. Histéresis: el retador debe ser claramente mas cercano (x0.6).
        2. Sosten: ademas debe ganar ESTABILIDAD_FRAMES frames seguidos.
        El ancla solo se mueve cuando la mirada realmente cambio de boton."""
        idx, dist = self.clasificar(raw)
        if self._snap_idx is None:
            self._snap_idx = idx
            return self._snap_idx, dist[self._snap_idx]

        if idx != self._snap_idx:
            if idx == self._candidato:
                self._cand_cont += 1
            else:
                self._candidato, self._cand_cont = idx, 1
            if (self._cand_cont >= self.ESTABILIDAD_FRAMES
                    or dist[idx] < dist[self._snap_idx] * 0.6):
                self._snap_idx = idx
                self._candidato = None
                self._cand_cont = 0
        else:
            self._candidato = None
            self._cand_cont = 0
        return self._snap_idx, dist[self._snap_idx]

    # ------------------------------------------------------------------
    # Dibujo
    # ------------------------------------------------------------------
    def _pip(self, canvas):
        frame = self.lector.get_frame()
        ph = 240
        if frame is None:
            cv2.putText(canvas, "camara: sin imagen", (40, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            return
        pw = int(frame.shape[1] * ph / frame.shape[0])
        pip = cv2.resize(frame, (pw, ph))
        x0, y0 = self.screen_w - pw - 20, 20
        canvas[y0:y0 + ph, x0:x0 + pw] = pip

    def _pantalla_base(self, titulo):
        canvas = np.zeros((self.screen_h, self.screen_w, 3), dtype=np.uint8)
        cv2.putText(canvas, titulo, (40, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        self._pip(canvas)
        return canvas

    def _circulo_centro(self, canvas):
        cv2.circle(canvas, (self.screen_w // 2, self.screen_h // 2), 25, (255, 180, 0), 2)

    # ------------------------------------------------------------------
    # Calibracion (los 4 puntos futuros son los 4 botones)
    # ------------------------------------------------------------------
    def _recolectar(self, canvas_fn, duracion):
        muestras = []
        inicio = time.time()
        while time.time() - inicio < duracion:
            raw = self.lector.get_raw()
            estado = "rostro: OK" if raw is not None else "rostro: SIN DETECTAR"
            canvas = canvas_fn(estado, len(muestras))
            cv2.imshow(self.ventana, canvas)
            if cv2.waitKey(1) & 0xFF == 27:
                return None
            if raw is not None:
                suave = self._observar(raw)
                muestras.append(suave.copy())
                # ratio de cejas del frame (para el neutral del click)
                ratio_c = self.lector.get_cejas()
                if ratio_c is not None:
                    self._cejas_datos.append(float(ratio_c))
        return muestras

    def calibrar(self):
        X_data, Y_data = [], []
        self._reset_calibracion()

        cv2.namedWindow(self.ventana, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(self.ventana, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.resizeWindow(self.ventana, self.screen_w, self.screen_h)

        print("\n--- CALIBRACION: mira el centro y luego cada punto ---")

        # Referencia central de la sesion
        def pantalla_centro(estado, n):
            c = self._pantalla_base("Mira el CENTRO de la pantalla")
            self._circulo_centro(c)
            cv2.putText(c, estado, (40, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(c, f"muestras: {n}", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            return c

        muestras = self._recolectar(pantalla_centro, self.DUR_CENTRO)
        if not muestras or len(muestras) < 10:
            print("[Error] No se obtuvo la referencia central.")
            return False
        self.referencia_centro = np.median(muestras, axis=0)

        # Altura neutral de cejas en el centro: mediana de lo capturado.
        # Sirve de base si el gesto por perspectiva no alcanza a calibrarse.
        if self._cejas_datos:
            self.cejas_neutro = float(np.median(self._cejas_datos))
            print(f"Cejas neutras (centro): ratio {self.cejas_neutro:.3f}")
        else:
            print("[Advertencia] Sin neutral de cejas en el centro; umbral fijo.")
        self._cejas_datos = []

        # 4 puntos (reintento automatico si un punto sale con pocas muestras)
        neutros, alzados = [], []
        for idx, pt in enumerate(self.puntos):
            neutr_ultimo = None
            crudos = None
            for intento in range(2):
                def pantalla_espera(estado, n, _pt=pt, _i=idx):
                    c = self._pantalla_base(f"Boton {_i + 1}/4 - Vuelve al CENTRO")
                    self._circulo_centro(c)
                    cv2.putText(c, estado, (40, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    return c

                def pantalla_prep(estado, n, _pt=pt, _i=idx):
                    c = self._pantalla_base(f"Boton {_i + 1}/4 - Ahora mira el boton")
                    cv2.circle(c, _pt, 25, (255, 0, 0), 2)
                    cv2.putText(c, estado, (40, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    return c

                def pantalla_captura(estado, n, _pt=pt, _i=idx):
                    c = self._pantalla_base(f"Calibrando boton {_i + 1}/4")
                    cv2.circle(c, _pt, 20, (0, 0, 255), -1)
                    progreso = int(min(1.0, n / 120.0) * 50)
                    cv2.circle(c, _pt, 35 + progreso, (0, 255, 0), 2)
                    cv2.putText(c, estado, (40, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    cv2.putText(c, f"muestras: {n}", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    return c

                if self._recolectar(pantalla_espera, self.DUR_ESPERA) is None:
                    return False
                if self._recolectar(pantalla_prep, self.DUR_PREP) is None:
                    return False

                n_prev = len(self._cejas_datos)   # para el neutro de este punto
                crudos = self._recolectar(pantalla_captura, self.DUR_CAPTURA)
                if crudos is None:
                    return False
                # Neutro de cejas EN ESTA PERSPECTIVA (mirando el boton)
                neutr_i = self._cejas_datos[n_prev:]
                neutr_ultimo = (float(np.median(neutr_i)) if len(neutr_i) >= 10
                                else None)
                if len(crudos) >= 10:
                    break
                print(f"[Advertencia] Reintento {intento + 1}: boton {idx + 1} con {len(crudos)} muestras.")
            else:
                print(f"[Advertencia] Boton {idx + 1} omitido por pocas muestras.")
                continue

            for crudo in crudos:
                feats = self.build_features(crudo, self.referencia_centro)
                X_data.append(feats)
                Y_data.append(pt)
            self._muestra_datos.append(np.asarray(X_data[-len(crudos):], dtype=np.float64))
            print(f"Boton {idx + 1} registrado: {len(crudos)} muestras")
            neutros.append(neutr_ultimo if neutr_ultimo is not None
                           else (self.cejas_neutro if self.cejas_neutro is not None else 0.15))

            # ------------------------------------------------------------
            # Gesto del click en esta perspectiva: alzar las cejas mirando
            # el mismo boton. asi cada direccion tiene sus propios umbrales.
            # ------------------------------------------------------------
            def pantalla_alzado(estado, n, _pt=pt, _i=idx):
                c = self._pantalla_base(f"Click {_i + 1}/4 - Mira el boton y ALZA LAS CEJAS")
                cv2.circle(c, _pt, 25, (0, 200, 0), 2)
                cv2.putText(c, estado, (40, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(c, f"muestras: {n}", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                return c

            self._cejas_datos = []
            alzado_muestras = self._recolectar(pantalla_alzado, self.CEJA_ALZADO_SEG)
            if alzado_muestras is None:
                return False
            if self._cejas_datos:
                alzados.append(float(np.median(self._cejas_datos)))
            else:
                alzados.append(0.0)  # sin datos: este punto usara el fallback
            self._cejas_datos = []

        if len({tuple(p) for p in Y_data}) < 3:
            print("[Error] Muy pocos puntos calibrados. Repite.")
            return False

        X_arr = np.asarray(X_data, dtype=np.float64)
        Y_arr = np.asarray(Y_data, dtype=np.float64)
        self.modelo_x.fit(X_arr, Y_arr[:, 0])
        self.modelo_y.fit(X_arr, Y_arr[:, 1])

        # Centroide de features por boton (solo botones con datos suficientes)
        self.centroides = np.vstack([
            muestras.mean(axis=0) for muestras in self._muestra_datos
        ])
        # Si un boton no se calibro, sus muestras faltan: realinear centros
        if len(self._muestra_datos) != len(self.puntos):
            self.centroides = None  # sin centroides: cae al snap por pantalla
            self.segmentos = None
            print("[Advertencia] No se calibraron los 4 botones; snap por distancia en pantalla.")
        else:
            # Nivel 1: agrupar botones en 3 segmentos horizontales
            nombres = ["IZQUIERDA", "CENTRO", "DERECHA"]
            grupos = {}
            for i, pt in enumerate(self.puntos):
                grupos.setdefault(self._segmento_de(pt, self.screen_w), []).append(i)
            self._seg_de = np.zeros(len(self.puntos), dtype=int)
            for s, idxs in grupos.items():
                self._seg_de[idxs] = s
            self.segmentos = [
                {"nombre": nombres[s], "indices": np.asarray(idxs),
                 "centroide": self.centroides[idxs].mean(axis=0)}
                for s, idxs in sorted(grupos.items())
            ]
            for s in self.segmentos:
                print(f"Segmento {s['nombre']}: botones "
                      f"{[self.etiquetas[i] for i in s['indices']]}")

        # Umbrales del click por perspectiva: solo puntos con gap suficiente
        if len(neutros) == len(self.puntos) and len(alzados) == len(self.puntos):
            self.neutro_por, self.alzado_por = [], []
            for i, (n, a) in enumerate(zip(neutros, alzados)):
                if a - n >= self.CEJA_MIN_GAP:
                    self.neutro_por.append(n)
                    self.alzado_por.append(a)
                    print(f"Click boton {i + 1}: neutro {n:.3f} -> alzado {a:.3f}")
                else:
                    self.neutro_por.append(self.cejas_neutro or 0.15)
                    self.alzado_por.append(0.0)  # usa fallback en este boton
                    print(f"[Advertencia] Click boton {i + 1}: gap corto "
                          f"({(a - n):.3f}); se usa el umbral fijo.")
            self.neutro_por = np.asarray(self.neutro_por)
            self.alzado_por = np.asarray(self.alzado_por)

        print(f"\nCalibracion OK: {X_arr.shape[0]} muestras x {X_arr.shape[1]} features.")
        return True

    # ------------------------------------------------------------------
    # Logica de seleccion de botones (lo que se quiere validar aqui)
    # ------------------------------------------------------------------
    def predecir(self, raw):
        feats = self.build_features(raw, self.referencia_centro).reshape(1, -1)
        x = int(self.modelo_x.predict(feats)[0])
        y = int(self.modelo_y.predict(feats)[0])
        return max(0, min(self.screen_w - 1, x)), max(0, min(self.screen_h - 1, y))

    @staticmethod
    def boton_en(boton, punto):
        cx, cy = boton["centro"]
        l = boton["lado"] // 2
        return abs(punto[0] - cx) <= l and abs(punto[1] - cy) <= l

    def actualizar_dwell(self, idx, dt):
        """Mirada sostenida sobre el boton anclado: acumula progreso y
        activa al completar.

        Re-armado: al activar, el boton queda bloqueado; solo puede
        volver a activarse si la mirada ancla en otro boton y regresa.
        Asi no se disparan ON/OFF en cadena por seguir mirando el boton.
        """
        for i, b in enumerate(self.botones):
            if i == idx:
                if i in self._bloqueados:
                    continue
                b["progreso"] = min(1.0, b["progreso"] + dt / self.DWELL_SEG)
                if b["progreso"] >= 1.0:
                    b["activado"] = not b["activado"]   # toggle: validar con el usuario
                    b["progreso"] = 0.0
                    self._bloqueados.add(i)
                    print(f"Boton seleccionado: {b['centro']} -> {'ON' if b['activado'] else 'OFF'}")
            else:
                b["progreso"] = 0.0
                # al mirar otro boton, se re-arma este
                self._bloqueados.discard(i)

    def click_cejas(self, ratio, idx):
        """Click por gesto: ALZAR LAS CEJAS activa el boton ancado (toggle).

        Umbrales POR PERSPECTIVA: en la calibracion se registro, para cada
        boton, el ratio neutro (mirando el boton) y el ratio con las cejas
        alzadas. Al estar anclado en un boton se usan SOLO sus umbrales, asi
        el gesto funciona igual con la cabeza en cualquiera de las 4 poses.

        Histéresis: dispara al superar el punto medio neutro->alzado y
        re-arma al volver a la mitad inferior; un solo alzo genera un solo
        click. No respeta el bloqueo de re-armado: es un gesto deliberado
        (la histéresis ya evita dobles clicks) y limpia el bloqueo."""
        if (self.neutro_por is not None and self.alzado_por is not None
                and self.alzado_por[idx] > self.neutro_por[idx]):
            neutro, alzado = self.neutro_por[idx], self.alzado_por[idx]
            sube = neutro + 0.5 * (alzado - neutro)
            baja = neutro + 0.25 * (alzado - neutro)
        else:
            # fallback: umbral fijo sobre el neutral central capturado
            base = self.cejas_neutro if self.cejas_neutro is not None else 0.15
            sube, baja = base + 0.04, base + 0.02

        if ratio >= sube:
            if not self._cejas_alzadas:
                self._cejas_alzadas = True
                b = self.botones[idx]
                b["activado"] = not b["activado"]
                b["progreso"] = 0.0
                self._bloqueados.discard(idx)
                self._flash_click = 0.5
                print(f"Click (cejas): {b['centro']} -> {'ON' if b['activado'] else 'OFF'}")
        elif ratio <= baja:
            self._cejas_alzadas = False

    def dibujar_botones(self, canvas, mirada, snap_idx=None):
        for i, b in enumerate(self.botones):
            cx, cy = b["centro"]
            l = b["lado"]
            color = (0, 200, 0) if b["activado"] else (90, 90, 90)
            grosor = 4 if b["activado"] else 2
            cv2.rectangle(canvas, (cx - l // 2, cy - l // 2), (cx + l // 2, cy + l // 2), color, grosor)
            cv2.putText(canvas, self.etiquetas[i], (cx - l // 2, cy + l // 2 + 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            if b["progreso"] > 0:
                # anillo de progreso del dwell alrededor del boton
                ang = int(b["progreso"] * 360)
                cv2.ellipse(canvas, (cx, cy), (l // 2 + 14, l // 2 + 14),
                            0, 0, ang, (0, 255, 255), 3)
            if i == snap_idx:
                # boton anclado por el snap (cursor cuantizado)
                cv2.rectangle(canvas, (cx - l // 2 - 6, cy - l // 2 - 6),
                              (cx + l // 2 + 6, cy + l // 2 + 6), (255, 180, 0), 2)

    # ------------------------------------------------------------------
    # Bucle principal de prueba
    # ------------------------------------------------------------------
    def run(self):
        self.lector.start()
        try:
            if not self.calibrar():
                return

            print("\nMODO PRUEBA: mantén la mirada sobre un boton para seleccionarlo,")
            print("o alza las CEJAS para hacer click en el boton anclado.")
            print("ESC para salir.\n")

            dwell_anterior = None
            anterior = time.time()
            while True:
                ahora = time.time()
                dt = min(ahora - anterior, 0.1)
                anterior = ahora

                raw = self._observar(self.lector.get_raw())
                canvas = self._pantalla_base("Prueba: seleccion de botones con la mirada")

                if raw is not None:
                    mirada = self.predecir(raw)

                    # Centro: referencia visual (no es boton)
                    self._circulo_centro(canvas)

                    # Snap: anclar el cursor al boton mas cercano.
                    # Primario: centroide de features (kmeans k=9). Fallback:
                    # distancia euclidea del punto predicho a los centros.
                    if self.centroides is not None:
                        idx, dist_feat = self.snap_boton(raw)
                    else:
                        idx = min(
                            range(len(self.botones)),
                            key=lambda i: (self.botones[i]["centro"][0] - mirada[0]) ** 2
                            + (self.botones[i]["centro"][1] - mirada[1]) ** 2,
                        )
                    snap = self.botones[idx]["centro"]
                    dist_px = int(
                        ((snap[0] - mirada[0]) ** 2 + (snap[1] - mirada[1]) ** 2) ** 0.5
                    )

                    # Puerta del dwell: solo acumula si la mirada cruda esta
                    # realmente sobre el boton anclado; entre botones decae,
                    # asi miradas "a medias" no terminan activando nada.
                    radio = self.botones[idx]["lado"] * 0.75
                    if dist_px <= radio:
                        self.actualizar_dwell(idx, dt)
                    else:
                        for b in self.botones:
                            b["progreso"] = max(0.0, b["progreso"] - 2.0 * dt)

                    # Click por gesto: alzar las cejas activa el boton anclado
                    ratio_cejas_vivo = self.lector.get_cejas()
                    if ratio_cejas_vivo is not None:
                        self.click_cejas(ratio_cejas_vivo, idx)
                        estado_cejas = ("ALZAR CEJAS = click"
                                        if not self._cejas_alzadas else "cejas: ALZADAS")
                        color_cejas = (200, 200, 200) if not self._cejas_alzadas else (0, 165, 255)
                        cv2.putText(canvas, estado_cejas, (40, self.screen_h - 170),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_cejas, 2)
                    self._flash_click = max(0.0, self._flash_click - dt)

                    self.dibujar_botones(canvas, mirada, idx)
                    if self._flash_click > 0:
                        # destello blanco del boton recien clickeado
                        cx, cy = self.botones[idx]["centro"]
                        l = self.botones[idx]["lado"]
                        cv2.rectangle(canvas, (cx - l // 2, cy - l // 2),
                                      (cx + l // 2, cy + l // 2), (255, 255, 255), 6)

                    # Punto crudo, ancla y linea entre ambos (como el prototipo)
                    cv2.line(canvas, mirada, snap, (0, 255, 255), 2)
                    cv2.circle(canvas, snap, 22, (0, 255, 255), 4)
                    cv2.circle(canvas, mirada, 10, (0, 255, 0), -1)

                    cv2.putText(canvas, f"Mirada: {mirada}", (40, self.screen_h - 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(canvas, f"Snap: {snap} (dist {dist_px}px)",
                                (40, self.screen_h - 100),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    if self.segmentos is not None:
                        seg = next((s for s in self.segmentos if idx in s["indices"]), None)
                        if seg:
                            cv2.putText(canvas,
                                        f"Segmento: {seg['nombre']}  |  Boton: {self.etiquetas[idx]}",
                                        (40, self.screen_h - 140),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                else:
                    for b in self.botones:
                        b["progreso"] = 0.0
                    self._ventana = []      # descarta features viejas
                    self._candidato = None  # el ancla no salta con datos rancios
                    self._cand_cont = 0
                    self._cejas_alzadas = False  # sin rostro no hay gesto activo
                    self.dibujar_botones(canvas, (0, 0))
                    cv2.putText(canvas, "Buscando rostro...", (40, self.screen_h - 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                cv2.putText(canvas, "ESC: salir", (40, self.screen_h - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                cv2.imshow(self.ventana, canvas)

                tecla = cv2.waitKey(1) & 0xFF
                if tecla == 27:
                    break
                if tecla in (ord("r"), ord("R")):
                    if self.calibrar():
                        for b in self.botones:
                            b["activado"] = False
        finally:
            self.lector.stop()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    PruebaBotones().run()
