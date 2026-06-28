"""
HL7 v2.x MLLP Gateway — EMR AI System / RSJPDHK
=================================================
Protocol layer untuk menerima data real-time dari bedside monitor & ventilator
via HL7 v2.x MLLP (Minimum Lower Layer Protocol) over TCP/IP.

Alur data:
  Bedside Monitor / Ventilator
       │  TCP/IP · MLLP · port 2575
       ▼
  HL7MLLPServer  (listener thread)
       │  raw HL7 string
       ▼
  HL7Parser → HL7Message
       │
       ▼
  HL7VitalExtractor → dict vitals / dict vent
       │
       ▼
  RealDeviceConnector (device_connector.py)
       │
       ▼
  Monitor_Device.py  (Streamlit UI)

Kompatibel dengan:
  • Mindray BeneVision N22 / N17 / N12   (HL7 MLLP Outbound — port 2575)
  • GE CARESCAPE Monitor B850 / B650      (HL7 Outbound Interface)
  • Philips IntelliVue MX700 / MX800      (Data Export Interface)
  • Drager Evita Infinity V500            (HL7 Vent Output)
  • Hamilton G5 / C6                      (HL7 Data Export)
  • Puritan Bennett 980                   (Network Communication Module)

Tidak ada dependensi eksternal — parser ditulis dari scratch supaya
bisa jalan tanpa `python-hl7` / `hl7apy` yang tidak selalu tersedia.
"""

from __future__ import annotations

import logging
import re
import socket
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── MLLP Frame Bytes ──────────────────────────────────────────────────────────
MLLP_START  = b"\x0b"   # VT  — Start-of-Block
MLLP_END    = b"\x1c"   # FS  — End-of-Block
MLLP_CR     = b"\x0d"   # CR  — wajib ikut setelah FS

RECV_BUFFER = 65_536     # 64 KB per recv()
ACCEPT_TIMEOUT = 1.0     # detik, supaya _serve_loop bisa di-stop

# ── LOINC → field VitalSigns ──────────────────────────────────────────────────
LOINC_VITAL: Dict[str, str] = {
    "8867-4":  "heart_rate",
    "8480-6":  "systolic_bp",
    "8462-4":  "diastolic_bp",
    "59408-5": "spo2",
    "2708-6":  "spo2",
    "9279-1":  "respiratory_rate",
    "8310-5":  "body_temp",
    "8331-1":  "body_temp",
    "8478-0":  "map",
    "8591-3":  "cvp",
    "60985-9": "cvp",
}

# ── LOINC → field VentilatorParams ───────────────────────────────────────────
LOINC_VENT: Dict[str, str] = {
    "20112-7": "tidal_volume",
    "76222-9": "tidal_volume",
    "19835-8": "fio2",
    "3150-0":  "fio2",
    "76154-4": "peep",
    "76221-1": "peep",
    "76230-2": "peak_pressure",
    "76005-8": "mean_airway_pressure",
    "76153-6": "mean_airway_pressure",
    "60792-9": "rate_set",
    "33438-3": "rate_set",
}

# ── Vendor proprietary codes ───────────────────────────────────────────────────
VENDOR_VITAL: Dict[str, str] = {
    # Mindray BeneVision
    "MDR-HR":    "heart_rate",
    "MDR-SBP":   "systolic_bp",
    "MDR-DBP":   "diastolic_bp",
    "MDR-SPO2":  "spo2",
    "MDR-RR":    "respiratory_rate",
    "MDR-TEMP":  "body_temp",
    "MDR-MAP":   "map",
    "MDR-CVP":   "cvp",
    # GE CARESCAPE
    "GE-HR":     "heart_rate",
    "GE-NIBP-S": "systolic_bp",
    "GE-NIBP-D": "diastolic_bp",
    "GE-SPO2":   "spo2",
    # Philips IntelliVue
    "PHI-HR":    "heart_rate",
    "PHI-ABPs":  "systolic_bp",
    "PHI-ABPd":  "diastolic_bp",
    "PHI-SpO2":  "spo2",
    # Generic local codes (sering dipakai interface sederhana)
    "HR": "heart_rate",    "PULSE": "heart_rate",
    "SBP": "systolic_bp",  "NI-SBP": "systolic_bp",
    "DBP": "diastolic_bp", "NI-DBP": "diastolic_bp",
    "SPO2": "spo2",        "SAO2": "spo2",
    "RR": "respiratory_rate", "RESP": "respiratory_rate",
    "TEMP": "body_temp",   "TEMPC": "body_temp",
    "MAP": "map",          "NI-MAP": "map",
    "CVP": "cvp",          "RAP": "cvp",
}

VENDOR_VENT: Dict[str, str] = {
    # Drager
    "DRG-VT":    "tidal_volume",
    "DRG-FIO2":  "fio2",
    "DRG-PEEP":  "peep",
    "DRG-PIP":   "peak_pressure",
    "DRG-PMEAN": "mean_airway_pressure",
    "DRG-RR":    "rate_set",
    # Hamilton
    "HAM-VT":    "tidal_volume",
    "HAM-FIO2":  "fio2",
    "HAM-PEEP":  "peep",
    "HAM-PIP":   "peak_pressure",
    # Puritan Bennett
    "PB-VT":     "tidal_volume",
    "PB-FIO2":   "fio2",
    "PB-PEEP":   "peep",
    # Generic
    "TV": "tidal_volume",  "VT": "tidal_volume",  "VTIDAL": "tidal_volume",
    "FIO2": "fio2",        "FI02": "fio2",
    "PEEP": "peep",        "EPAP": "peep",
    "PIP": "peak_pressure", "PPEAK": "peak_pressure",
    "PMEAN": "mean_airway_pressure", "MAWP": "mean_airway_pressure",
    "RR_SET": "rate_set",  "FREQ": "rate_set",
}

# Map raw vent-mode string → VentilatorMode value yang dipakai model
VENT_MODE_MAP: Dict[str, str] = {
    "CMV": "CMV",         "IPPV": "CMV",
    "SIMV": "SIMV",       "VC-SIMV": "SIMV",
    "PSV": "PSV",         "PS": "PSV",         "ASB": "PSV",
    "CPAP": "CPAP",       "SPONT": "CPAP",
    "A/C": "A/C",         "AC": "A/C",         "VC-AC": "A/C",
    "PRVC": "PRVC",       "PC-PRVC": "PRVC",
    "APRV": "APRV",       "BIPAP": "APRV",
    "PC-SIMV": "PC-SIMV",
    "PRESSURE CONTROL": "CMV",
    "VOLUME CONTROL": "CMV",
    "SYNCHRONIZED": "SIMV",
}


# =============================================================================
# Data-classes
# =============================================================================

class HL7MsgType(Enum):
    ORU_R01 = "ORU^R01"   # Observation Result — vital signs utama
    ADT_A01 = "ADT^A01"   # Admit
    ADT_A03 = "ADT^A03"   # Discharge
    ADT_A08 = "ADT^A08"   # Update
    MDM_T02 = "MDM^T02"   # Medical Document — kadang dipakai ventilator
    ACK     = "ACK"
    UNKNOWN = "UNKNOWN"


@dataclass
class HL7Segment:
    """Satu baris / segment HL7 (MSH, PID, OBR, OBX …)."""
    seg_id: str
    fields: List[str]   # index 0 = seg_id itu sendiri

    def f(self, idx: int, default: str = "") -> str:
        """Ambil field ke-idx (1-based). field(1) = kolom pertama setelah |."""
        try:
            return self.fields[idx] or default
        except IndexError:
            return default

    def c(self, fidx: int, cidx: int, default: str = "") -> str:
        """Ambil komponen ke-cidx (0-based) dari field ke-fidx. Separator '^'."""
        try:
            return self.fields[fidx].split("^")[cidx] or default
        except IndexError:
            return default


@dataclass
class HL7Message:
    raw: str
    msg_type: HL7MsgType = HL7MsgType.UNKNOWN
    msg_id: str = ""
    timestamp: str = ""
    sending_app: str = ""
    patient_id: str = ""
    patient_name: str = ""
    segments: List[HL7Segment] = field(default_factory=list)

    def get(self, seg_id: str) -> List[HL7Segment]:
        """Semua segment dengan ID tertentu (banyak OBX, dll.)."""
        return [s for s in self.segments if s.seg_id == seg_id]


@dataclass
class DeviceConnectionStatus:
    connected: bool = False
    host: str = ""
    port: int = 0
    mode: str = ""                        # "server" | "client"
    last_msg_at: Optional[datetime] = None
    total_received: int = 0
    total_errors: int = 0
    last_error: str = ""
    uptime_since: Optional[datetime] = None

    @property
    def uptime_str(self) -> str:
        if not self.uptime_since:
            return "—"
        delta = datetime.now() - self.uptime_since
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s   = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @property
    def last_msg_str(self) -> str:
        if not self.last_msg_at:
            return "Belum ada data"
        delta = datetime.now() - self.last_msg_at
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s yang lalu"
        return self.last_msg_at.strftime("%H:%M:%S")


# =============================================================================
# Parser
# =============================================================================

class HL7Parser:
    """
    Parser HL7 v2.x tanpa dependensi eksternal.
    Field separator: | (pipe), komponen: ^, subkomponen: &, repetisi: ~
    """

    @staticmethod
    def parse(raw: str) -> HL7Message:
        msg = HL7Message(raw=raw)
        raw = raw.strip()
        if not raw.startswith("MSH"):
            return msg

        field_sep = raw[3] if len(raw) > 3 else "|"

        for line in re.split(r"[\r\n]+", raw):
            line = line.strip()
            if not line:
                continue
            parts = line.split(field_sep)
            msg.segments.append(HL7Segment(seg_id=parts[0], fields=parts))

        # Metadata dari MSH
        msh_list = msg.get("MSH")
        if msh_list:
            msh = msh_list[0]
            type_raw = msh.f(9)
            for mt in HL7MsgType:
                if mt.value == type_raw:
                    msg.msg_type = mt
                    break
            msg.msg_id      = msh.f(10)
            msg.timestamp   = msh.f(7)
            msg.sending_app = msh.c(3, 0)

        # Data pasien dari PID
        pid_list = msg.get("PID")
        if pid_list:
            pid = pid_list[0]
            msg.patient_id   = pid.c(3, 0)
            msg.patient_name = pid.f(5).replace("^", " ").strip()

        return msg

    @staticmethod
    def generate_ack(msg: HL7Message, code: str = "AA", text: str = "") -> str:
        """Generate MSH + MSA ACK sesuai HL7 v2.5."""
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        return (
            f"MSH|^~\\&|SmartEMR|RSJPDHK|{msg.sending_app}||{now}||ACK|ACK{now}|P|2.5\r"
            f"MSA|{code}|{msg.msg_id}|{text}\r"
        )


# =============================================================================
# Vital / Vent Extractor
# =============================================================================

class HL7VitalExtractor:

    @classmethod
    def extract_vitals(cls, msg: HL7Message) -> Optional[Dict[str, Optional[float]]]:
        """Parse OBX segments → dict vital signs. None jika tidak ada data."""
        vitals: Dict[str, Optional[float]] = {
            k: None for k in
            ("heart_rate", "systolic_bp", "diastolic_bp", "spo2",
             "respiratory_rate", "body_temp", "cvp", "map")
        }
        obxs = msg.get("OBX")
        if not obxs:
            return None

        for obx in obxs:
            obs_id   = obx.c(3, 0).strip()   # OBX-3 identifier
            obs_text = obx.c(3, 1).strip()   # OBX-3 text description
            raw_val  = obx.f(5).strip()       # OBX-5 value

            fname = (
                LOINC_VITAL.get(obs_id)
                or VENDOR_VITAL.get(obs_id.upper())
                or VENDOR_VITAL.get(obs_text.upper())
            )
            if not fname:
                continue

            val = cls._numeric(raw_val)
            if val is None:
                continue

            vitals[fname] = val

        return vitals if any(v is not None for v in vitals.values()) else None

    @classmethod
    def extract_vent(cls, msg: HL7Message) -> Optional[Dict[str, any]]:
        """Parse OBX segments → dict ventilator params. None jika tidak ada."""
        vent: Dict[str, any] = {
            k: None for k in
            ("tidal_volume", "fio2", "peep", "peak_pressure",
             "mean_airway_pressure", "rate_set", "mode", "ie_ratio")
        }
        obxs = msg.get("OBX")
        if not obxs:
            return None

        for obx in obxs:
            obs_id   = obx.c(3, 0).strip()
            obs_text = obx.c(3, 1).strip()
            raw_val  = obx.f(5).strip()

            # Mode ventilator (string, bukan numerik)
            if obs_id.upper() in ("VENT_MODE", "MODE", "MDR-MODE", "DRG-MODE",
                                   "HAM-MODE", "PB-MODE"):
                raw_upper = raw_val.upper().strip()
                vent["mode"] = VENT_MODE_MAP.get(raw_upper, raw_upper or "CMV")
                continue

            fname = (
                LOINC_VENT.get(obs_id)
                or VENDOR_VENT.get(obs_id.upper())
                or VENDOR_VENT.get(obs_text.upper())
            )
            if not fname:
                continue

            val = cls._numeric(raw_val)
            if val is None:
                continue

            # FiO2: normalisasi 0-100 → 0.0-1.0
            if fname == "fio2" and val > 1.0:
                val /= 100.0

            vent[fname] = val

        return vent if any(v is not None for v in vent.values()) else None

    @staticmethod
    def _numeric(s: str) -> Optional[float]:
        """Toleran terhadap trailing unit (mis: '82 bpm' → 82.0)."""
        m = re.match(r"^([+-]?\d+\.?\d*)", s.strip())
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return None


# =============================================================================
# MLLP Server — device PUSH ke sistem kita (paling umum: Mindray, GE, Philips)
# =============================================================================

class HL7MLLPServer:
    """
    TCP server MLLP yang mendengarkan incoming HL7 dari bedside monitor.

    Setiap koneksi device ditangani di thread daemon terpisah.
    Callback dipanggil di thread tersebut — pastikan penggunaannya thread-safe
    (gunakan threading.Lock di RealDeviceConnector).
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 2575,
        on_vitals: Optional[Callable[[Dict, HL7Message], None]] = None,
        on_vent:   Optional[Callable[[Dict, HL7Message], None]] = None,
        on_raw:    Optional[Callable[[str], None]] = None,
    ):
        self.host = host
        self.port = port
        self._on_vitals = on_vitals
        self._on_vent   = on_vent
        self._on_raw    = on_raw

        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self.status = DeviceConnectionStatus(mode="server", host=host, port=port)

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> Tuple[bool, str]:
        """Bind port dan mulai listen. Return (sukses, pesan)."""
        if self._running.is_set():
            return True, "Server sudah berjalan."
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((self.host, self.port))
            self._sock.listen(5)
            self._sock.settimeout(ACCEPT_TIMEOUT)
            self._running.set()
            self._thread = threading.Thread(
                target=self._serve, name="HL7-MLLP-Server", daemon=True
            )
            self._thread.start()
            self.status.connected    = True
            self.status.uptime_since = datetime.now()
            logger.info("HL7 MLLP Server listening %s:%d", self.host, self.port)
            return True, f"Server aktif di port {self.port} — menunggu koneksi device."
        except OSError as exc:
            msg = f"Gagal bind port {self.port}: {exc}"
            self.status.last_error = msg
            logger.error(msg)
            return False, msg

    def stop(self) -> None:
        self._running.clear()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self.status.connected    = False
        self.status.uptime_since = None
        logger.info("HL7 MLLP Server dihentikan.")

    def is_running(self) -> bool:
        return self._running.is_set()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _serve(self) -> None:
        while self._running.is_set():
            try:
                conn, addr = self._sock.accept()
                logger.info("Koneksi HL7 dari %s:%d", *addr)
                t = threading.Thread(
                    target=self._handle, args=(conn, addr), daemon=True
                )
                t.start()
            except socket.timeout:
                continue
            except Exception as exc:
                if self._running.is_set():
                    self.status.total_errors += 1
                    self.status.last_error = str(exc)
                    logger.error("MLLP accept error: %s", exc)
                break

    def _handle(self, conn: socket.socket, addr: tuple) -> None:
        buf = b""
        with conn:
            conn.settimeout(30.0)
            try:
                while self._running.is_set():
                    try:
                        chunk = conn.recv(RECV_BUFFER)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buf += chunk

                    # Ekstrak semua frame MLLP lengkap dari buffer
                    while MLLP_START in buf and MLLP_END in buf:
                        s = buf.index(MLLP_START)
                        e = buf.index(MLLP_END, s)
                        frame = buf[s + 1: e]
                        buf   = buf[e + 2:]          # skip FS + CR

                        try:
                            raw_hl7 = frame.decode("latin-1").strip()
                        except Exception:
                            continue

                        self.status.total_received  += 1
                        self.status.last_msg_at      = datetime.now()

                        if self._on_raw:
                            self._on_raw(raw_hl7)

                        msg = HL7Parser.parse(raw_hl7)
                        self._dispatch(msg)

                        # Kirim ACK
                        ack = HL7Parser.generate_ack(msg)
                        conn.sendall(
                            MLLP_START + ack.encode("latin-1") + MLLP_END + MLLP_CR
                        )

            except Exception as exc:
                self.status.total_errors += 1
                self.status.last_error = str(exc)
                logger.error("HL7 handler error (%s): %s", addr, exc)

    def _dispatch(self, msg: HL7Message) -> None:
        vitals = HL7VitalExtractor.extract_vitals(msg)
        if vitals and self._on_vitals:
            self._on_vitals(vitals, msg)

        vent = HL7VitalExtractor.extract_vent(msg)
        if vent and self._on_vent:
            self._on_vent(vent, msg)


# =============================================================================
# MLLP Client — kita PULL dari device (mode jarang, Philips versi lama)
# =============================================================================

class HL7MLLPClient:
    """
    Kirim pesan HL7 ke device dan tunggu response/ACK.
    Dipakai ketika device berperan sebagai server (bukan yang lazim).
    """

    def __init__(self, host: str, port: int = 2575, timeout: float = 5.0):
        self.host    = host
        self.port    = port
        self.timeout = timeout
        self.status  = DeviceConnectionStatus(mode="client", host=host, port=port)

    def ping(self) -> bool:
        """Test koneksi TCP tanpa kirim HL7."""
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout):
                self.status.connected  = True
                return True
        except Exception as exc:
            self.status.connected  = False
            self.status.last_error = str(exc)
            return False

    def send(self, hl7_str: str) -> Optional[str]:
        """Kirim pesan dan kembalikan response string (ACK/ORU)."""
        frame = MLLP_START + hl7_str.encode("latin-1") + MLLP_END + MLLP_CR
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.sendall(frame)
                resp = b""
                while True:
                    chunk = sock.recv(RECV_BUFFER)
                    if not chunk or MLLP_END in resp:
                        break
                    resp += chunk

            self.status.connected      = True
            self.status.total_received += 1
            self.status.last_msg_at    = datetime.now()

            if MLLP_START in resp and MLLP_END in resp:
                s = resp.index(MLLP_START) + 1
                e = resp.index(MLLP_END, s)
                return resp[s:e].decode("latin-1")
            return resp.decode("latin-1")

        except Exception as exc:
            self.status.connected  = False
            self.status.total_errors += 1
            self.status.last_error = str(exc)
            logger.error("HL7 client error (%s:%d): %s", self.host, self.port, exc)
            return None


# =============================================================================
# Demo / Test helper
# =============================================================================

def make_demo_oru(patient_id: str = "EP-DEMO-001") -> HL7Message:
    """
    Buat dan parse ORU^R01 dummy — untuk testing tanpa device nyata.
    Mensimulasikan output Mindray BeneVision N22 ICCU.
    """
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    raw = (
        f"MSH|^~\\&|MINDRAY_N22|RSJPDHK_ICCU||SMARTEMR|{now}||ORU^R01|MSG{now}|P|2.5\r"
        f"PID|1||{patient_id}^^^RSJPDHK||DEMO^PASIEN||19700101|M\r"
        f"OBR|1||{patient_id}|VITALS^Vital Signs|||{now}\r"
        "OBX|1|NM|8867-4^Heart rate^LN||82|/min|60-100|N|||F\r"
        "OBX|2|NM|8480-6^Systolic BP^LN||125|mmHg|90-140|N|||F\r"
        "OBX|3|NM|8462-4^Diastolic BP^LN||80|mmHg|60-90|N|||F\r"
        "OBX|4|NM|59408-5^SpO2^LN||97|%|95-100|N|||F\r"
        "OBX|5|NM|9279-1^Respiratory rate^LN||16|/min|12-20|N|||F\r"
        "OBX|6|NM|8310-5^Body temperature^LN||36.8|Cel|36.5-37.5|N|||F\r"
        "OBX|7|NM|8478-0^Mean arterial pressure^LN||95|mmHg|70-105|N|||F\r"
        "OBX|8|NM|8591-3^CVP^LN||8.5|cmH2O|5-12|N|||F\r"
        "OBX|9|TX|VENT_MODE^Ventilator mode||SIMV||||||F\r"
        "OBX|10|NM|20112-7^Tidal volume^LN||480|mL|||N|||F\r"
        "OBX|11|NM|19835-8^FiO2^LN||55|%|||N|||F\r"
        "OBX|12|NM|76154-4^PEEP^LN||6.0|cmH2O|||N|||F\r"
        "OBX|13|NM|76230-2^Peak pressure^LN||22.0|cmH2O|||N|||F\r"
        "OBX|14|NM|76005-8^Mean airway pressure^LN||14.0|cmH2O|||N|||F\r"
        "OBX|15|NM|60792-9^Vent rate set^LN||14|/min|||N|||F\r"
    )
    return HL7Parser.parse(raw)
