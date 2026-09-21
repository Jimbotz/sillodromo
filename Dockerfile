FROM debian:trixie-slim

# Evitar prompts interactivos durante la instalación
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Deshabilitar MIT-SHM para prevenir errores de memoria compartida en X11 forwarding
    QT_X11_NO_MITSHM=1

# PyQt5 desde apt y no desde pip: pip no publica wheels de PyQt5 para Linux arm64
# (Apple Silicon, Raspberry Pi). El paquete de Debian existe para amd64 y arm64
# e instala por sí mismo las librerías X11/xcb que necesita Qt.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pyqt5 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no-root para seguridad y compatibilidad de permisos con el servidor X11
ARG USER_ID=1000
ARG GROUP_ID=1000

RUN groupadd -g ${GROUP_ID} appuser && \
    useradd -u ${USER_ID} -g appuser -m -s /bin/bash appuser

WORKDIR /app

# Copiar el código de la aplicación
COPY app/ /app/

# Ajustar permisos para el usuario no-root
RUN chown -R appuser:appuser /app

# Cambiar a usuario no-root
USER appuser

# Comando predeterminado para iniciar la aplicación
CMD ["python3", "main.py"]
