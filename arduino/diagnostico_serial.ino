/*
 * diagnostico_serial.ino - Sillódromo: prueba de la conexión interfaz <-> placa
 *
 * NO mueve nada. Solo recibe los 2 bytes que envía app/silla.py
 * ([vertical, horizontal], 128 = neutro) y los imprime al Monitor Serial.
 *
 * Sirve para comprobar, SIN riesgo de que la silla se mueva, que el puerto,
 * el baudrate (9600) y los valores que envía la interfaz son correctos.
 *
 * Prueba recomendada:
 *   a) Carga este sketch en la placa (COM3) con Arduino IDE.
 *   b) Abre el Monitor Serial a 9600 baudios.
 *   c) En una terminal de tu PC manda un pulso de prueba:
 *        .venv\Scripts\python.exe -c "import serial; s=serial.Serial('COM3',9600); s.write(bytes([248,128])); s.close()"
 *   d) El Monitor Serial debe mostrar: VERTICAL=248 HORIZONTAL=128 -> ADELANTE
 *
 * Cuando la interfaz (app/silla.py) esté corriendo, cierra el Monitor Serial:
 * el puerto COM3 solo lo puede usar un programa a la vez.
 */

const byte NEUTRO = 128;

void setup() {
  Serial.begin(9600);
}

void loop() {
  if (Serial.available() >= 2) {
    byte vertical = Serial.read();
    byte horizontal = Serial.read();

    Serial.print("VERTICAL=");
    Serial.print(vertical);
    Serial.print("  HORIZONTAL=");
    Serial.print(horizontal);

    if (vertical == NEUTRO && horizontal == NEUTRO) {
      Serial.println("  -> NEUTRO (parada)");
    } else if (vertical > NEUTRO) {
      Serial.println("  -> ADELANTE");
    } else if (vertical < NEUTRO) {
      Serial.println("  -> ATRAS");
    } else if (horizontal > NEUTRO) {
      Serial.println("  -> GIRO DERECHA");
    } else {
      Serial.println("  -> GIRO IZQUIERDA");
    }
  }
}
