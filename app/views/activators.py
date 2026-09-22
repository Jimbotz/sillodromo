"""
views/activators.py - Activadores: primero se elige el dispositivo (Focos, Televisiones, Enchufes,
Música o Comandos) y después la acción. Los comandos personalizados son un dispositivo más, con sus
categorías, y se redibujan cada vez que el editor los cambia (ver window.py._reconstruir_comandos).
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from buttons.factory import llenar, volver
from buttons.icons import con_icono
from features import commands as comandos
from tools import scale
from views import common
from views.common import DISPOSITIVOS, ICONOS_DISPOSITIVO, VISTA_EDITOR, boton_volver, crear_vista, primer_bloque, solo_asistente


def crear(ventana) -> QWidget:
    # Por fases: página 0 = elegir dispositivo; página 1 + i = acciones del dispositivo i
    ventana.fases = QStackedWidget()
    ventana.botones_dispositivo = []
    # Los comandos personalizados son un dispositivo más, con sus categorías (ver _crear_fase_comandos)
    ventana.dispositivos = {**DISPOSITIVOS, "Comandos": None}
    ventana.fases.addWidget(_crear_fase_dispositivos(ventana))
    for i, nombre in enumerate(ventana.dispositivos):
        ventana.fases.addWidget(_crear_fase_comandos(ventana, i) if nombre == "Comandos"
                                else _crear_fase_acciones(ventana, i, nombre))
    return ventana.fases


def _boton_navegacion(ventana, parent) -> QPushButton:
    """Arriba a la derecha en Activadores: salto directo a Navegación."""
    boton = con_icono(volver(QPushButton("Volver a la navegación", parent)), "navigation", scale.TAMANO_ICONO_VOLVER)
    boton.clicked.connect(lambda: ventana._ir_a(1))
    return boton


def _crear_fase_dispositivos(ventana) -> QWidget:
    fase = QWidget()
    layout = QVBoxLayout(fase)
    layout.setContentsMargins(20, 12, 20, 20)
    layout.setSpacing(14)

    fila = QHBoxLayout()
    fila.addWidget(boton_volver(ventana, fase))
    fila.addStretch(1)
    fila.addWidget(_boton_navegacion(ventana, fase))

    titulo = QLabel("Elige un dispositivo", fase)
    titulo.setObjectName("tituloVista")

    bloques = QHBoxLayout()
    bloques.setSpacing(14)
    for i, nombre in enumerate(ventana.dispositivos):
        boton = con_icono(llenar(QPushButton(nombre, fase)), ICONOS_DISPOSITIVO[nombre])
        boton.setAccessibleName(f"Elegir dispositivo {i + 1}: {nombre}")
        boton.clicked.connect(lambda _, i=i: _abrir_dispositivo(ventana, i))
        bloques.addWidget(boton)
        ventana.botones_dispositivo.append(boton)

    layout.addLayout(fila)
    layout.addWidget(titulo)
    layout.addLayout(bloques, 1)
    return fase


def _crear_fase_comandos(ventana, i: int) -> QWidget:
    """Comandos personalizados: primero la categoría, después el comando. Se redibuja al editarlos."""
    ventana.i_comandos = i
    fase = QWidget()
    layout = QVBoxLayout(fase)
    layout.setContentsMargins(20, 12, 20, 20)
    ventana.volver_comandos = con_icono(volver(QPushButton("Volver a dispositivos", fase)), "arrow-left",
                                        scale.TAMANO_ICONO_VOLVER)
    ventana.volver_comandos.clicked.connect(lambda: _volver_comandos(ventana))
    # Solo ratón y teclado: la cruceta, la mirada y la boca no lo seleccionan (ver common.SOLO_ASISTENTE)
    editar = solo_asistente(con_icono(volver(QPushButton("Editar comandos (Solo asistente)", fase)), "pencil",
                                      scale.TAMANO_ICONO_VOLVER))
    editar.setAccessibleName("Editar comandos personalizados, solo para quien acompaña, con ratón o teclado")
    editar.clicked.connect(lambda: _abrir_editor(ventana))
    fila = QHBoxLayout()
    fila.addWidget(ventana.volver_comandos)
    fila.addStretch(1)
    fila.addWidget(editar)
    fila.addWidget(_boton_navegacion(ventana, fase))
    ventana.pila_comandos = QStackedWidget(fase)  # 0 = categorías; 1 + k = comandos de la categoría k
    layout.addLayout(fila)
    layout.addWidget(ventana.pila_comandos, 1)
    _reconstruir_comandos(ventana)
    return fase


def _reconstruir_comandos(ventana):
    while ventana.pila_comandos.count():
        pagina = ventana.pila_comandos.widget(0)
        ventana.pila_comandos.removeWidget(pagina)
        pagina.deleteLater()
    categorias, aviso = comandos.cargar()
    filas = lambda bloques: [(None, bloques[k:k + 4]) for k in range(0, len(bloques), 4)]
    nota = " ".join(filter(None, [aviso, "Aún no hay categorías." if not categorias else "",
                                  "Quien acompaña crea las categorías y los comandos con «Editar comandos (Solo asistente)», con ratón o teclado."]))
    ventana.pila_comandos.addWidget(crear_vista("Comandos", filas(
        [(c["nombre"], lambda _, k=k: _abrir_categoria(ventana, k), c["icono"]) for k, c in enumerate(categorias)]), nota))
    for c in categorias:
        vacia = "Aún no hay comandos en esta categoría." if not c["comandos"] else ""
        ventana.pila_comandos.addWidget(crear_vista(c["nombre"], filas(
            [(d["titulo"], d["frase"], d["icono"], d.get("accion", "")) for d in c["comandos"]]), vacia))
    ventana.volver_comandos.setText("Volver a dispositivos")


def _abrir_categoria(ventana, k: int):
    ventana.pila_comandos.setCurrentIndex(1 + k)
    ventana.volver_comandos.setText("Volver a categorías")
    (primer_bloque(ventana.pila_comandos.currentWidget()) or ventana.volver_comandos).setFocus()


def _volver_comandos(ventana):
    k = ventana.pila_comandos.currentIndex() - 1
    if k < 0:
        _volver_a_dispositivos(ventana, ventana.i_comandos)
        return
    ventana.pila_comandos.setCurrentIndex(0)
    ventana.volver_comandos.setText("Volver a dispositivos")
    bloques = common.bloques_visibles(ventana.pila_comandos.currentWidget())
    (bloques[k] if k < len(bloques) else ventana.volver_comandos).setFocus()  # vuelve a la categoría de la que venía


def _abrir_editor(ventana):
    ventana.editor.recargar()
    ventana.vistas.setCurrentIndex(VISTA_EDITOR)


def _cerrar_editor(ventana):
    ventana.vistas.setCurrentIndex(2)
    ventana.fases.setCurrentIndex(1 + ventana.i_comandos)
    ventana.pila_comandos.setCurrentIndex(0)
    ventana.volver_comandos.setText("Volver a dispositivos")
    (primer_bloque(ventana.pila_comandos.currentWidget()) or ventana.volver_comandos).setFocus()


def _crear_fase_acciones(ventana, i: int, nombre: str) -> QWidget:
    fase = QWidget()
    layout = QVBoxLayout(fase)
    layout.setContentsMargins(20, 12, 20, 20)

    volver_btn = con_icono(volver(QPushButton("Volver a dispositivos", fase)), "arrow-left", scale.TAMANO_ICONO_VOLVER)
    volver_btn.setAccessibleName(f"Volver a elegir dispositivo (ahora: {nombre})")
    volver_btn.clicked.connect(lambda: _volver_a_dispositivos(ventana, i))
    fila = QHBoxLayout()
    fila.addWidget(volver_btn)
    fila.addStretch(1)
    fila.addWidget(_boton_navegacion(ventana, fase))

    # Desplazamiento en vez de aplastar los botones si no caben
    desplazable = QScrollArea(fase)
    desplazable.setWidget(crear_vista(nombre, ventana.dispositivos[nombre]))
    desplazable.setWidgetResizable(True)
    desplazable.setFrameShape(QFrame.NoFrame)
    desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    layout.addLayout(fila)
    layout.addWidget(desplazable, 1)
    return fase


def _abrir_dispositivo(ventana, i: int):
    ventana.fases.setCurrentIndex(1 + i)
    if i == ventana.i_comandos:  # empieza siempre por las categorías
        ventana.pila_comandos.setCurrentIndex(0)
        ventana.volver_comandos.setText("Volver a dispositivos")
        (primer_bloque(ventana.pila_comandos.currentWidget()) or ventana.volver_comandos).setFocus()
        return
    # La selección cae en la primera acción, no en "Volver": es lo que se va a usar.
    # Sin acciones (p. ej. aún no hay comandos), en el primer bloque de la página.
    pagina = ventana.fases.currentWidget()
    (primer_bloque(pagina.findChild(QScrollArea)) or primer_bloque(pagina)).setFocus()


def _volver_a_dispositivos(ventana, i: int):
    ventana.fases.setCurrentIndex(0)
    ventana.botones_dispositivo[i].setFocus()  # vuelve al dispositivo del que venía
