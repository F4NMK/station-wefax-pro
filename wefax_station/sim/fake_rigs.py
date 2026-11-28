"""Postes simulés au niveau du port série (tests sans matériel) : Yaesu CAT ASCII et Yaesu CAT 5 octets."""

from wefax_station.radio.yaesu import YAESU_MODELS


class FakeYaesuAscii:
    """Répond comme un FT-991A (ou autre modèle ASCII) : FA, MD0, GT0, NR0, BC0, PA0, RA0, SM0, ID."""

    def __init__(self, model_id="0670", baud=38400):
        self.model_id = model_id
        self.baud = baud
        self.freq = 14070000
        self.state = {"MD0": "2", "GT0": "3", "NR0": "1", "BC0": "1", "PA0": "0", "RA0": "0"}
        self.out = bytearray()
        self.log = []
        self.tx_seen = False

    def handle(self, data, baud):
        if baud != self.baud:
            return  # mauvais débit : le poste ne comprend rien
        for cmd in data.decode("ascii", errors="ignore").split(";"):
            cmd = cmd.strip()
            if not cmd:
                continue
            self.log.append(cmd)
            if cmd.startswith("TX") or cmd.startswith("MX"):
                self.tx_seen = True
            if cmd == "FA":
                self.out += f"FA{self.freq:09d};".encode()
            elif cmd.startswith("FA") and len(cmd) > 2:
                self.freq = int(cmd[2:])
            elif cmd == "ID":
                self.out += f"ID{self.model_id};".encode()
            elif cmd == "SM0":
                self.out += b"SM0120;"
            elif cmd[:3] in self.state:
                if len(cmd) == 3:
                    self.out += f"{cmd}{self.state[cmd]};".encode()
                else:
                    self.state[cmd[:3]] = cmd[3:]


class FakeYaesuLegacy:
    """Répond comme un FT-817 : lecture fréquence/mode (0x03), réglage fréquence (0x01), mode (0x07), RX (0xE7)."""

    def __init__(self, baud=9600):
        self.baud = baud
        self.freq_10hz = 1407000
        self.mode = 0x01
        self.out = bytearray()
        self.frames = []

    def handle(self, data, baud):
        if baud != self.baud:
            return
        for i in range(0, len(data) - 4, 5):
            f = bytes(data[i : i + 5])
            self.frames.append(f)
            op = f[4]
            if op == 0x03:
                s = f"{self.freq_10hz:08d}"
                self.out += bytes([int(s[k : k + 2], 16) for k in (0, 2, 4, 6)] + [self.mode])
            elif op == 0x01:
                self.freq_10hz = int("".join(f"{b:02x}" for b in f[:4]))
            elif op == 0x07:
                self.mode = f[0]
            elif op == 0xE7:
                self.out += bytes([0x07])


class FakeSerial:
    """Remplace serial.Serial : relie un port nommé à un poste simulé."""

    RIGS = {}

    def __init__(self, port=None, baudrate=9600, timeout=0.25, write_timeout=0.25, **kw):
        if port not in self.RIGS:
            raise OSError(f"port {port} introuvable")
        self.rig = self.RIGS[port]
        self.baudrate = baudrate
        self.is_open = True
        self.dtr = self.rts = False

    @property
    def in_waiting(self):
        return len(self.rig.out)

    def reset_input_buffer(self):
        self.rig.out.clear()

    def write(self, data):
        self.rig.handle(bytes(data), self.baudrate)
        return len(data)

    def flush(self):
        pass

    def read(self, n=1):
        d = bytes(self.rig.out[:n])
        del self.rig.out[:n]
        return d

    def read_until(self, term=b";"):
        i = self.rig.out.find(term)
        if i < 0:
            return self.read(len(self.rig.out))
        return self.read(i + len(term))

    def close(self):
        self.is_open = False


class FakePortInfo:
    def __init__(self, device, description, vid=None):
        self.device = device
        self.description = description
        self.manufacturer = "Silicon Labs"
        self.vid = vid


def model_name(model_id):
    return YAESU_MODELS.get(model_id, model_id)
