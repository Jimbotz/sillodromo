"""
prueba_botones_mirada.py - Prueba independiente: seleccion de botones con la mirada.

Sustituye OpenFace por MediaPipe FaceLandmarker (el mismo modelo que usa la app)
y prueba la logica de seleccion de botones por mirada:

  1. Calibracion de 9 puntos (los mismos que seran los botones).
  2. Prediccion de la posicion de la mirada en pantalla (Ridge con numpy).
  3. Seleccion por "dwell": mantener la mirada sobre un boton ~1.2 s para
     activarlo (con anillo de progreso). Por ahora sin interfaz PyQt: es un
     banco de pruebas de la logica.

Uso:
    .\\.venv\\Scripts\\python.exe app\\prueba_botones_mirada.py

Controles: ESC para salir, R para recalibrar.
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
                    else:
                        self.ultimo_raw = None

    def get_raw(self):
        with self.lock:
            return None if self.ultimo_raw is None else self.ultimo_raw.copy()

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
    """Calibracion de 9 puntos + seleccion de botones por dwell."""

    DUR_CENTRO = 1.5      # s capturando la referencia central
    DUR_ESPERA = 0.8      # s volviendo al centro antes de cada punto
    DUR_PREP = 0.8        # s de preparacion sobre el objetivo
    DUR_CAPTURA = 2.0     # s capturando cada punto
    DWELL_SEG = 1.2       # s de mirada sostenida para seleccionar un boton

    def __init__(self):
        self.lector = LectorMirada()
        self.modelo_x = RidgeModel(alpha=10.0)
        self.modelo_y = RidgeModel(alpha=10.0)
        self.referencia_centro = None
        self.centroides = None      # centroide de features por boton (k = 9)
        self._snap_idx = None       # boton anclado actualmente (histéresis)
        self._muestra_datos = []    # muestras engineered por boton durante la calibracion
        self._bloqueados = set()    # botones por re-armar: se activan una vez
                                    # y quedan bloqueados hasta que la mirada
                                    # sale de ellos y vuelve a entrar

        self.screen_w, self.screen_h = screen_resolution()
        self.ventana = "Sillodromo - Prueba botones por mirada"

        # Grilla 3x3 de botones (mismos puntos que la calibracion)
        pad_x, pad_y = int(self.screen_w * 0.18), int(self.screen_h * 0.18)
        xs = [pad_x, self.screen_w // 2, self.screen_w - pad_x]
        ys = [pad_y, self.screen_h // 2, self.screen_h - pad_y]
        self.puntos = [(x, y) for y in ys for x in xs]

        self.botones = []
        self._crear_botones()

    def _crear_botones(self):
        lado = int(min(self.screen_w, self.screen_h) * 0.10)
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
        return np.concatenate([raw, deltas])

    # ------------------------------------------------------------------
    # Snap: el cursor se ancla al boton mas cercano
    # ------------------------------------------------------------------
    def _reset_calibracion(self):
        self.centroides = None
        self._snap_idx = None
        self._muestra_datos = []
        self._bloqueados = set()

    def clasificar(self, raw):
        """Indice del boton al que se esta mirando.

        KMeans con k = 9 y un centroide por boton: durante la calibracion se
        guarda el centroide (media) de las features de cada boton y en vivo se
        elige el mas cercano en el espacio de features. Es mas estable que el
        punto crudo de la regresion porque cuantiza al boton, no a un pixel.
        """
        feats = self.build_features(raw, self.referencia_centro).reshape(1, -1)
        distancias = np.linalg.norm(self.centroides - feats, axis=1)
        return int(np.argmin(distancias)), distancias

    def snap_boton(self, raw):
        """Boton anclado con histéresis: solo cambia de boton si el nuevo es
        claramente mas cercano (evita parpadear entre botones vecinos)."""
        idx, dist = self.clasificar(raw)
        if self._snap_idx is None or dist[idx] < dist[self._snap_idx] * 0.85:
            self._snap_idx = idx
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
    # Calibracion (los 9 puntos futuros son los 9 botones)
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
                muestras.append(raw.copy())
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

        # 9 puntos
        for idx, pt in enumerate(self.puntos):

            def pantalla_espera(estado, n, _pt=pt, _i=idx):
                c = self._pantalla_base(f"Boton {_i + 1}/9 - Vuelve al CENTRO")
                self._circulo_centro(c)
                cv2.putText(c, estado, (40, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                return c

            def pantalla_prep(estado, n, _pt=pt, _i=idx):
                c = self._pantalla_base(f"Boton {_i + 1}/9 - Ahora mira el boton")
                cv2.circle(c, _pt, 25, (255, 0, 0), 2)
                cv2.putText(c, estado, (40, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                return c

            def pantalla_captura(estado, n, _pt=pt, _i=idx, _progreso=[0]):
                c = self._pantalla_base(f"Calibrando boton {_i + 1}/9")
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

            crudos = self._recolectar(pantalla_captura, self.DUR_CAPTURA)
            if crudos is None:
                return False
            if len(crudos) < 10:
                print(f"[Advertencia] Pocas muestras en boton {idx + 1}: {len(crudos)}")
                continue

            for crudo in crudos:
                feats = self.build_features(crudo, self.referencia_centro)
                X_data.append(feats)
                Y_data.append(pt)
            self._muestra_datos.append(np.asarray(X_data[-len(crudos):], dtype=np.float64))
            print(f"Boton {idx + 1} registrado: {len(crudos)} muestras")

        if len({tuple(p) for p in Y_data}) < 5:
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
            print("[Advertencia] No se calibraron los 9 botones; snap por distancia en pantalla.")

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

    def dibujar_botones(self, canvas, mirada, snap_idx=None):
        for i, b in enumerate(self.botones):
            cx, cy = b["centro"]
            l = b["lado"]
            color = (0, 200, 0) if b["activado"] else (90, 90, 90)
            grosor = 4 if b["activado"] else 2
            cv2.rectangle(canvas, (cx - l // 2, cy - l // 2), (cx + l // 2, cy + l // 2), color, grosor)
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

            print("\nMODO PRUEBA: mantén la mirada sobre un boton para seleccionarlo.")
            print("ESC para salir.\n")

            dwell_anterior = None
            anterior = time.time()
            while True:
                ahora = time.time()
                dt = min(ahora - anterior, 0.1)
                anterior = ahora

                raw = self.lector.get_raw()
                canvas = self._pantalla_base("Prueba: seleccion de botones con la mirada")

                if raw is not None:
                    mirada = self.predecir(raw)

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

                    self.actualizar_dwell(idx, dt)
                    self.dibujar_botones(canvas, mirada, idx)

                    # Punto crudo, ancla y linea entre ambos (como el prototipo)
                    cv2.line(canvas, mirada, snap, (0, 255, 255), 2)
                    cv2.circle(canvas, snap, 22, (0, 255, 255), 4)
                    cv2.circle(canvas, mirada, 10, (0, 255, 0), -1)

                    cv2.putText(canvas, f"Mirada: {mirada}", (40, self.screen_h - 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(canvas, f"Snap: {snap} (dist {dist_px}px)",
                                (40, self.screen_h - 100),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                else:
                    for b in self.botones:
                        b["progreso"] = 0.0
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
