"""
editor.py - Pantalla para que quien acompaña cree y edite los comandos personalizados y sus categorías.
Es una pantalla "normal" (teclado y ratón): la mirada y la cruceta no actúan aquí (ver main.py).
Todo se guarda al momento en app/datos/comandos.json.
"""

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import comandos
import icono
import voz

# Mostrado en el selector de color de DialogoComando: (etiqueta, valor guardado en "accion")
OPCIONES_ACCION = [("Sin color", ""), ("Encender (verde)", "on"), ("Apagar (rojo)", "off")]


def _boton(texto: str, nombre_icono: str, parent=None) -> QPushButton:
    """Botón de tamaño normal (no bloque), con icono."""
    boton = icono.con_icono(QPushButton(texto, parent), nombre_icono, 24)
    boton.setObjectName("botonEditor")
    return boton


def _campo(etiqueta: str, widget: QWidget, parent) -> QLabel:
    """Etiqueta visible asociada al campo (los lectores de pantalla la anuncian al entrar en él)."""
    texto = QLabel(etiqueta, parent)
    texto.setObjectName("etiquetaCampo")
    texto.setBuddy(widget)
    widget.setAccessibleName(etiqueta.rstrip(":"))
    return texto


class SelectorIcono(QScrollArea):
    """Todos los iconos disponibles a la vista, para elegir uno con un clic."""

    COLUMNAS = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setMinimumHeight(240)
        contenido = QWidget()
        rejilla = QGridLayout(contenido)
        rejilla.setSpacing(6)
        self.grupo = QButtonGroup(self)  # exclusivo: un solo icono elegido
        for k, nombre in enumerate(icono.catalogo()):
            opcion = QPushButton(contenido)
            opcion.setObjectName("opcionIcono")
            opcion.setCheckable(True)
            opcion.setIcon(icono.icono(nombre, aire=False))
            opcion.setIconSize(QSize(30, 30))
            opcion.setToolTip(nombre)
            opcion.setAccessibleName(f"Icono {nombre}")
            opcion.setProperty("nombre", nombre)
            self.grupo.addButton(opcion)
            rejilla.addWidget(opcion, k // self.COLUMNAS, k % self.COLUMNAS)
        self.setWidget(contenido)

    def seleccionado(self) -> str:
        boton = self.grupo.checkedButton()
        return boton.property("nombre") if boton else icono.POR_DEFECTO

    def seleccionar(self, nombre: str):
        for boton in self.grupo.buttons():
            if boton.property("nombre") == nombre:
                boton.setChecked(True)
                self.ensureWidgetVisible(boton)


class Dialogo(QDialog):
    """Base: campos arriba, selector de icono, mensaje de error y Guardar / Cancelar."""

    def __init__(self, titulo: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(760)
        self.layout_ = QVBoxLayout(self)
        encabezado = QLabel(titulo, self)
        encabezado.setObjectName("tituloTarjeta")
        self.layout_.addWidget(encabezado)
        self.error = QLabel("", self)
        self.error.setObjectName("errorCampo")
        self.error.setWordWrap(True)
        self.icono = SelectorIcono(self)

    def terminar(self, texto_guardar: str = "Guardar"):
        self.layout_.addWidget(_campo("Icono:", self.icono, self))
        self.layout_.addWidget(self.icono, 1)
        self.layout_.addWidget(self.error)
        fila = QHBoxLayout()
        fila.addStretch(1)
        cancelar = _boton("Cancelar", "x", self)
        cancelar.clicked.connect(self.reject)
        guardar = _boton(texto_guardar, "check", self)
        guardar.clicked.connect(self._intentar_guardar)
        fila.addWidget(cancelar)
        fila.addWidget(guardar)
        self.layout_.addLayout(fila)

    def _intentar_guardar(self):
        error = self.validar()
        self.error.setText(error)
        if not error:
            self.accept()

    def validar(self) -> str:
        return ""


class DialogoCategoria(Dialogo):
    def __init__(self, nombres_ocupados: set, categoria: dict = None, parent=None):
        super().__init__("Editar categoría" if categoria else "Nueva categoría", parent)
        self.ocupados = {n.casefold() for n in nombres_ocupados}
        self.nombre = QLineEdit(self)
        self.nombre.setPlaceholderText("Por ejemplo: Solicitar atención")
        self.layout_.addWidget(_campo("Nombre de la categoría:", self.nombre, self))
        self.layout_.addWidget(self.nombre)
        self.terminar()
        self.nombre.setText(categoria["nombre"] if categoria else "")
        self.icono.seleccionar(categoria["icono"] if categoria else icono.POR_DEFECTO)

    def validar(self) -> str:
        nombre = " ".join(self.nombre.text().split())
        if not nombre:
            return "Escribe el nombre de la categoría."
        if nombre.casefold() in self.ocupados:
            return f"Ya existe una categoría llamada «{nombre}»."
        return ""

    def valores(self) -> dict:
        return {"nombre": " ".join(self.nombre.text().split()), "icono": self.icono.seleccionado()}


class DialogoComando(Dialogo):
    def __init__(self, categorias: list, i_categoria: int, comando: dict = None, parent=None):
        super().__init__("Editar comando" if comando else "Nuevo comando", parent)
        self.categorias, self.i_original, self.es_nuevo = categorias, i_categoria, comando is None
        self.titulo = QLineEdit(self)
        self.titulo.setPlaceholderText("Lo que dice el bloque. Por ejemplo: Ir al baño")
        self.frase = QLineEdit(self)
        self.frase.setPlaceholderText("Lo que dirá la voz. Por ejemplo: Por favor, llévenme al baño")
        self.categoria = QComboBox(self)
        for c in categorias:
            self.categoria.addItem(icono.icono(c["icono"], aire=False), c["nombre"])
        self.accion = QComboBox(self)
        for etiqueta, _valor in OPCIONES_ACCION:
            self.accion.addItem(etiqueta)
        probar = _boton("Probar voz", "play", self)
        probar.clicked.connect(lambda: voz.hablar(comandos.normalizar_frase(self.frase.text())))
        fila_frase = QHBoxLayout()
        fila_frase.addWidget(self.frase, 1)
        fila_frase.addWidget(probar)
        self.layout_.addWidget(_campo("Título del comando:", self.titulo, self))
        self.layout_.addWidget(self.titulo)
        self.layout_.addWidget(_campo("Frase que dirá la voz:", self.frase, self))
        self.layout_.addLayout(fila_frase)
        self.layout_.addWidget(_campo("Categoría:", self.categoria, self))
        self.layout_.addWidget(self.categoria)
        self.layout_.addWidget(_campo("Color del bloque:", self.accion, self))
        self.layout_.addWidget(self.accion)
        nota = QLabel("Si la frase empieza por «Alexa», la voz hace una pausa de 1 s tras «Alexa» para que el "
                      "altavoz la escuche. Si es para una persona, escríbela tal cual.", self)
        nota.setObjectName("ayudaCalibracion")
        nota.setWordWrap(True)
        self.layout_.addWidget(nota)
        self.terminar()
        self.categoria.setCurrentIndex(i_categoria)
        valores_accion = [valor for _etiqueta, valor in OPCIONES_ACCION]
        self.accion.setCurrentIndex(valores_accion.index(comando.get("accion", "")) if comando else 0)
        if comando:
            self.titulo.setText(comando["titulo"])
            self.frase.setText(comando["frase"])
        self.icono.seleccionar(comando["icono"] if comando else icono.POR_DEFECTO)

    def validar(self) -> str:
        if not " ".join(self.titulo.text().split()):
            return "Escribe el título del comando (lo que dice el bloque)."
        if comandos.normalizar_frase(self.frase.text()) in ("", "Alexa, "):
            return "Escribe la frase que dirá la voz."
        destino = self.categoria.currentIndex()
        if destino < 0:
            return "Primero crea una categoría."
        llega_nuevo = self.es_nuevo or destino != self.i_original
        if llega_nuevo and len(self.categorias[destino]["comandos"]) >= comandos.MAXIMO:
            return f"La categoría ya tiene {comandos.MAXIMO} comandos, el máximo que cabe en pantalla."
        return ""

    def valores(self) -> tuple:
        comando = {"titulo": " ".join(self.titulo.text().split()),
                   "frase": comandos.normalizar_frase(self.frase.text()), "icono": self.icono.seleccionado(),
                   "accion": OPCIONES_ACCION[self.accion.currentIndex()][1]}
        return self.categoria.currentIndex(), comando


class EditorComandos(QWidget):
    """Categorías a la izquierda, sus comandos a la derecha. Cada cambio se guarda al momento."""

    cambiado = pyqtSignal()  # los comandos cambiaron: hay que redibujar los bloques
    cerrar = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.categorias = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(14)

        cabecera = QHBoxLayout()
        titulo = QLabel("Comandos personalizados", self)
        titulo.setObjectName("tituloVista")
        listo = _boton("Listo", "check", self)
        listo.clicked.connect(self.cerrar.emit)
        cabecera.addWidget(titulo)
        cabecera.addStretch(1)
        cabecera.addWidget(listo)
        layout.addLayout(cabecera)
        ayuda = QLabel("Aquí quien acompaña crea las categorías y sus comandos. Todo se guarda al momento en "
                       "app/datos/comandos.json. Con doble clic se edita.", self)
        ayuda.setObjectName("ayudaCalibracion")
        ayuda.setWordWrap(True)
        layout.addWidget(ayuda)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(24)
        self.lista_categorias, columna_cat = self._columna(
            "Categorías", [("Nueva categoría", "folder-plus", self.nueva_categoria),
                           ("Editar", "pencil", self.editar_categoria_elegida),
                           ("Borrar", "trash-2", self.borrar_categoria_elegida)])
        self.lista_comandos, columna_com = self._columna(
            "Comandos de la categoría", [("Nuevo comando", "plus", self.nuevo_comando),
                                         ("Editar", "pencil", self.editar_comando_elegido),
                                         ("Borrar", "trash-2", self.borrar_comando_elegido)])
        self.titulo_comandos = columna_com.findChild(QLabel)
        self.lista_categorias.currentRowChanged.connect(self._mostrar_comandos)
        self.lista_categorias.itemDoubleClicked.connect(lambda _: self.editar_categoria_elegida())
        self.lista_comandos.itemDoubleClicked.connect(lambda _: self.editar_comando_elegido())
        cuerpo.addWidget(columna_cat, 2)
        cuerpo.addWidget(columna_com, 3)
        layout.addLayout(cuerpo, 1)

    def _columna(self, titulo: str, acciones: list) -> tuple:
        columna = QWidget(self)
        layout = QVBoxLayout(columna)
        layout.setContentsMargins(0, 0, 0, 0)
        encabezado = QLabel(titulo, columna)
        encabezado.setObjectName("tituloTarjeta")
        lista = QListWidget(columna)
        lista.setIconSize(QSize(28, 28))
        lista.setAccessibleName(titulo)
        fila = QHBoxLayout()
        for texto, nombre_icono, accion in acciones:
            boton = _boton(texto, nombre_icono, columna)
            boton.clicked.connect(accion)
            fila.addWidget(boton)
        fila.addStretch(1)
        layout.addWidget(encabezado)
        layout.addWidget(lista, 1)
        layout.addLayout(fila)
        return lista, columna

    # ---- datos ----
    def recargar(self):
        self.categorias, aviso = comandos.cargar()
        if aviso:
            print(aviso, flush=True)
        self._pintar(0)

    def _guardar(self, fila_categoria: int):
        comandos.guardar(self.categorias)
        self._pintar(fila_categoria)
        self.cambiado.emit()

    def _pintar(self, fila_categoria: int):
        self.lista_categorias.blockSignals(True)
        self.lista_categorias.clear()
        for c in self.categorias:
            self.lista_categorias.addItem(QListWidgetItem(icono.icono(c["icono"], aire=False), f'{c["nombre"]} ({len(c["comandos"])})'))
        self.lista_categorias.blockSignals(False)
        self.lista_categorias.setCurrentRow(min(fila_categoria, len(self.categorias) - 1))
        self._mostrar_comandos(self.lista_categorias.currentRow())

    def _mostrar_comandos(self, i: int):
        self.lista_comandos.clear()
        if i < 0:
            self.titulo_comandos.setText("Comandos de la categoría")
            return
        self.titulo_comandos.setText(f"Comandos de «{self.categorias[i]['nombre']}»")
        for c in self.categorias[i]["comandos"]:
            self.lista_comandos.addItem(QListWidgetItem(icono.icono(c["icono"], aire=False), f'{c["titulo"]}  —  «{c["frase"]}»'))

    # ---- operaciones (los diálogos solo piden los datos) ----
    def agregar_categoria(self, valores: dict):
        self.categorias.append({**valores, "comandos": []})
        self._guardar(len(self.categorias) - 1)

    def cambiar_categoria(self, i: int, valores: dict):
        self.categorias[i].update(valores)
        self._guardar(i)

    def quitar_categoria(self, i: int):
        del self.categorias[i]
        self._guardar(max(0, i - 1))

    def poner_comando(self, i_origen: int, j: int, destino: int, comando: dict):
        """j = None: comando nuevo. Si cambia de categoría, se mueve al final de la nueva."""
        if j is not None:
            del self.categorias[i_origen]["comandos"][j]
        if j is not None and destino == i_origen:
            self.categorias[destino]["comandos"].insert(j, comando)
        else:
            self.categorias[destino]["comandos"].append(comando)
        self._guardar(destino)

    def quitar_comando(self, i: int, j: int):
        del self.categorias[i]["comandos"][j]
        self._guardar(i)

    # ---- botones ----
    def nueva_categoria(self):
        dialogo = DialogoCategoria({c["nombre"] for c in self.categorias}, parent=self)
        if dialogo.exec_():
            self.agregar_categoria(dialogo.valores())

    def editar_categoria_elegida(self):
        i = self.lista_categorias.currentRow()
        if i < 0:
            return
        otros = {c["nombre"] for k, c in enumerate(self.categorias) if k != i}
        dialogo = DialogoCategoria(otros, self.categorias[i], parent=self)
        if dialogo.exec_():
            self.cambiar_categoria(i, dialogo.valores())

    def borrar_categoria_elegida(self):
        i = self.lista_categorias.currentRow()
        if i < 0:
            return
        c = self.categorias[i]
        if self._confirmar(f"¿Borrar la categoría «{c['nombre']}» y sus {len(c['comandos'])} comandos?"):
            self.quitar_categoria(i)

    def nuevo_comando(self):
        i = self.lista_categorias.currentRow()
        if i < 0:
            QMessageBox.information(self, "Sin categorías", "Primero crea una categoría.")
            return
        dialogo = DialogoComando(self.categorias, i, parent=self)
        if dialogo.exec_():
            self.poner_comando(i, None, *dialogo.valores())

    def editar_comando_elegido(self):
        i, j = self.lista_categorias.currentRow(), self.lista_comandos.currentRow()
        if i < 0 or j < 0:
            return
        dialogo = DialogoComando(self.categorias, i, self.categorias[i]["comandos"][j], parent=self)
        if dialogo.exec_():
            self.poner_comando(i, j, *dialogo.valores())

    def borrar_comando_elegido(self):
        i, j = self.lista_categorias.currentRow(), self.lista_comandos.currentRow()
        if i < 0 or j < 0:
            return
        if self._confirmar(f"¿Borrar el comando «{self.categorias[i]['comandos'][j]['titulo']}»?"):
            self.quitar_comando(i, j)

    def _confirmar(self, pregunta: str) -> bool:
        caja = QMessageBox(QMessageBox.Question, "Confirmar", pregunta, QMessageBox.Yes | QMessageBox.No, self)
        caja.setDefaultButton(QMessageBox.No)  # la opción segura por defecto
        caja.button(QMessageBox.Yes).setText("Sí, borrar")
        caja.button(QMessageBox.No).setText("No")
        return caja.exec_() == QMessageBox.Yes
