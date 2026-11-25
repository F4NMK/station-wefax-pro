"""Dépendances optionnelles (CAT série, audio).

Dépendances : pip install numpy opencv-python pillow scipy pyserial sounddevice
L'absence de pyserial ou de sounddevice (ou de la bibliothèque PortAudio) ne bloque pas le
démarrage : les fonctions correspondantes sont simplement désactivées.
"""

try:
    import serial
    import serial.tools.list_ports

    HAS_SERIAL = True
except ImportError:
    serial = None
    HAS_SERIAL = False

try:
    import sounddevice as sd

    HAS_AUDIO = True
except (ImportError, OSError):  # OSError : PortAudio absent
    sd = None
    HAS_AUDIO = False
