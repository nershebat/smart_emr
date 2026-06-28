"""
CLMA Gateway — Persistence Layer & Workflow State Manager
==========================================================
Tanggung jawab:
  • SQLite storage untuk Order, eMAR, Barcode, 5-Rights log
  • CLMAWorkflowManager — satu state machine per sesi Streamlit
  • InfusionBridge — jembatan ke infusion_gateway (pump data → CLMA context)
  • HL7PumpCommander — kirim PCD-03 auto-program command ke BeneFusion nDS ex
  • Audit trail — setiap aksi tersimpan dengan timestamp + user

Database path: app/data/clma.db (SQLite, lokasi sama dengan DB lain)
"""

from __future__ import annotations

import json
import logging
import socket
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import streamlit as st

from .clma_models import (
    AlertSeverity, CLMAWorkflowState, DoseUnit, DrugBarcode,
    DrugInteractionAlert, FiveRightsCheck, FrequencyCode,
    MedicationOrder, OrderStatus, PumpProgramCommand,
    RouteCode, ScanResult, eMAR_Record,
)
from .clma_engine import CLMAEngine, DDIChecker, DoseCalculator

logger = logging.getLogger(__name__)

# ── DB path — sejajar dengan DB lain di app/data/ ────────────────────────────
_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "clma.db"

# session_state key
_SESSION_KEY_WORKFLOWS = "clma_workflows"   # Dict[order_id, CLMAWorkflowState]
_SESSION_KEY_ACTIVE    = "clma_active_order_id"


# =============================================================================
# Database Layer
# =============================================================================

@contextmanager
def _conn():
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_clma_database() -> None:
    """Buat semua tabel CLMA jika belum ada."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS clma_orders (
            order_id            TEXT PRIMARY KEY,
            episode_id          TEXT NOT NULL,
            patient_name        TEXT,
            patient_no_rm       TEXT,
            patient_weight_kg   REAL,
            drug_name           TEXT,
            drug_generic        TEXT,
            drug_class          TEXT,
            dose_value          REAL,
            dose_unit           TEXT,
            route               TEXT,
            frequency           TEXT,
            concentration_mcg_ml REAL,
            concentration_mg_ml  REAL,
            syringe_size_ml     REAL,
            diluent             TEXT,
            rate_ml_h           REAL,
            total_volume_ml     REAL,
            ordered_by          TEXT,
            ordered_by_nip      TEXT,
            ordered_at          TEXT,
            status              TEXT,
            verified_by         TEXT,
            verified_at         TEXT,
            dispensed_by        TEXT,
            dispensed_at        TEXT,
            administered_by     TEXT,
            administered_at     TEXT,
            is_high_alert       INTEGER,
            is_double_check_req INTEGER,
            barcode_id          TEXT,
            scheduled_time      TEXT,
            valid_until         TEXT,
            notes               TEXT,
            created_at          TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS clma_barcodes (
            barcode_id          TEXT PRIMARY KEY,
            order_id            TEXT,
            drug_name           TEXT,
            drug_generic        TEXT,
            concentration_str   TEXT,
            dose_label          TEXT,
            route               TEXT,
            prepared_by         TEXT,
            prepared_at         TEXT,
            expires_at          TEXT,
            lot_number          TEXT,
            ndc_code            TEXT,
            is_dispensed        INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS clma_five_rights (
            check_id            TEXT PRIMARY KEY,
            order_id            TEXT,
            checked_at          TEXT,
            checked_by          TEXT,
            scan_result         TEXT,
            right_patient       INTEGER,
            right_drug          INTEGER,
            right_dose          INTEGER,
            right_route         INTEGER,
            right_time          INTEGER,
            right_doc           INTEGER,
            notes_json          TEXT,
            override_reason     TEXT,
            double_checked_by   TEXT
        );

        CREATE TABLE IF NOT EXISTS clma_emar (
            emar_id             TEXT PRIMARY KEY,
            order_id            TEXT,
            episode_id          TEXT,
            drug_name           TEXT,
            dose_given          REAL,
            dose_unit           TEXT,
            rate_ml_h_actual    REAL,
            route               TEXT,
            administered_by     TEXT,
            administered_by_name TEXT,
            administered_at     TEXT,
            witness_by          TEXT,
            scan_result         TEXT,
            five_rights_score   INTEGER,
            pump_id             TEXT,
            pump_programmed     INTEGER DEFAULT 0,
            site                TEXT,
            notes               TEXT,
            adverse_event       TEXT
        );

        CREATE TABLE IF NOT EXISTS clma_pump_commands (
            cmd_id              TEXT PRIMARY KEY,
            pump_id             TEXT,
            order_id            TEXT,
            drug_name           TEXT,
            rate_ml_h           REAL,
            vtbi_ml             REAL,
            concentration_str   TEXT,
            commanded_by        TEXT,
            commanded_at        TEXT,
            status              TEXT DEFAULT 'PENDING',
            ack_message         TEXT,
            hl7_message         TEXT
        );

        CREATE TABLE IF NOT EXISTS clma_audit_log (
            log_id              TEXT PRIMARY KEY,
            timestamp           TEXT,
            episode_id          TEXT,
            order_id            TEXT,
            action              TEXT,
            performed_by        TEXT,
            detail              TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_orders_episode ON clma_orders(episode_id);
        CREATE INDEX IF NOT EXISTS idx_emar_episode   ON clma_emar(episode_id);
        CREATE INDEX IF NOT EXISTS idx_audit_episode  ON clma_audit_log(episode_id);
        """)


# =============================================================================
# CRUD Helpers
# =============================================================================

class CLMAStore:

    # ── Orders ────────────────────────────────────────────────────────────────

    @staticmethod
    def save_order(order: MedicationOrder) -> None:
        with _conn() as con:
            con.execute("""
            INSERT OR REPLACE INTO clma_orders VALUES (
                :order_id,:episode_id,:patient_name,:patient_no_rm,:patient_weight_kg,
                :drug_name,:drug_generic,:drug_class,:dose_value,:dose_unit,:route,
                :frequency,:concentration_mcg_ml,:concentration_mg_ml,:syringe_size_ml,
                :diluent,:rate_ml_h,:total_volume_ml,:ordered_by,:ordered_by_nip,
                :ordered_at,:status,:verified_by,:verified_at,:dispensed_by,
                :dispensed_at,:administered_by,:administered_at,:is_high_alert,
                :is_double_check_req,:barcode_id,:scheduled_time,:valid_until,:notes,
                datetime('now','localtime')
            )""", {
                "order_id": order.order_id,
                "episode_id": order.episode_id,
                "patient_name": order.patient_name,
                "patient_no_rm": order.patient_no_rm,
                "patient_weight_kg": order.patient_weight_kg,
                "drug_name": order.drug_name,
                "drug_generic": order.drug_generic,
                "drug_class": order.drug_class,
                "dose_value": order.dose_value,
                "dose_unit": order.dose_unit.value,
                "route": order.route.value,
                "frequency": order.frequency.value,
                "concentration_mcg_ml": order.concentration_mcg_ml,
                "concentration_mg_ml": order.concentration_mg_ml,
                "syringe_size_ml": order.syringe_size_ml,
                "diluent": order.diluent,
                "rate_ml_h": order.rate_ml_h,
                "total_volume_ml": order.total_volume_ml,
                "ordered_by": order.ordered_by,
                "ordered_by_nip": order.ordered_by_nip,
                "ordered_at": order.ordered_at,
                "status": order.status.value,
                "verified_by": order.verified_by,
                "verified_at": order.verified_at,
                "dispensed_by": order.dispensed_by,
                "dispensed_at": order.dispensed_at,
                "administered_by": order.administered_by,
                "administered_at": order.administered_at,
                "is_high_alert": int(order.is_high_alert),
                "is_double_check_req": int(order.is_double_check_required),
                "barcode_id": order.barcode_id,
                "scheduled_time": order.scheduled_time,
                "valid_until": order.valid_until,
                "notes": order.notes,
            })

    @staticmethod
    def get_orders(episode_id: str, limit: int = 20) -> List[dict]:
        with _conn() as con:
            rows = con.execute("""
                SELECT * FROM clma_orders
                WHERE episode_id = ?
                ORDER BY ordered_at DESC LIMIT ?
            """, (episode_id, limit)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def update_order_status(
        order_id: str, status: OrderStatus,
        by_field: str = "", by_value: str = "",
        at_field: str = "", at_value: str = "",
    ) -> None:
        sql = f"UPDATE clma_orders SET status=?"
        params: list = [status.value]
        if by_field:
            sql += f", {by_field}=?"
            params.append(by_value)
        if at_field:
            sql += f", {at_field}=?"
            params.append(at_value or datetime.now().isoformat())
        sql += " WHERE order_id=?"
        params.append(order_id)
        with _conn() as con:
            con.execute(sql, params)

    # ── Barcodes ──────────────────────────────────────────────────────────────

    @staticmethod
    def save_barcode(bc: DrugBarcode) -> None:
        with _conn() as con:
            con.execute("""
            INSERT OR REPLACE INTO clma_barcodes VALUES (
                :barcode_id,:order_id,:drug_name,:drug_generic,
                :concentration_str,:dose_label,:route,:prepared_by,
                :prepared_at,:expires_at,:lot_number,:ndc_code,:is_dispensed
            )""", {
                "barcode_id": bc.barcode_id,
                "order_id": bc.order_id,
                "drug_name": bc.drug_name,
                "drug_generic": bc.drug_generic,
                "concentration_str": bc.concentration_str,
                "dose_label": bc.dose_label,
                "route": bc.route.value,
                "prepared_by": bc.prepared_by,
                "prepared_at": bc.prepared_at,
                "expires_at": bc.expires_at,
                "lot_number": bc.lot_number,
                "ndc_code": bc.ndc_code,
                "is_dispensed": int(bc.is_dispensed),
            })

    @staticmethod
    def get_barcode(barcode_id: str) -> Optional[dict]:
        with _conn() as con:
            row = con.execute(
                "SELECT * FROM clma_barcodes WHERE barcode_id=?", (barcode_id,)
            ).fetchone()
        return dict(row) if row else None

    # ── Five Rights ───────────────────────────────────────────────────────────

    @staticmethod
    def save_five_rights(check: FiveRightsCheck) -> None:
        check_id = f"5R-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}"
        notes_json = json.dumps({
            "patient": check.right_patient_note,
            "drug":    check.right_drug_note,
            "dose":    check.right_dose_note,
            "route":   check.right_route_note,
            "time":    check.right_time_note,
            "doc":     check.right_doc_note,
        })
        with _conn() as con:
            con.execute("""
            INSERT OR REPLACE INTO clma_five_rights VALUES (
                :check_id,:order_id,:checked_at,:checked_by,:scan_result,
                :rp,:rd,:rdose,:rr,:rt,:rdoc,:notes,:override,:dc
            )""", {
                "check_id": check_id,
                "order_id": check.order_id,
                "checked_at": check.checked_at,
                "checked_by": check.checked_by,
                "scan_result": check.scan_result.value,
                "rp": int(check.right_patient),
                "rd": int(check.right_drug),
                "rdose": int(check.right_dose),
                "rr": int(check.right_route),
                "rt": int(check.right_time),
                "rdoc": int(check.right_doc),
                "notes": notes_json,
                "override": check.override_reason,
                "dc": check.double_checked_by,
            })

    # ── eMAR ─────────────────────────────────────────────────────────────────

    @staticmethod
    def save_emar(emar: eMAR_Record) -> None:
        with _conn() as con:
            con.execute("""
            INSERT OR REPLACE INTO clma_emar VALUES (
                :emar_id,:order_id,:episode_id,:drug_name,:dose_given,:dose_unit,
                :rate,:route,:by,:by_name,:at,:witness,:scan,:score,
                :pump_id,:pump_prog,:site,:notes,:adverse
            )""", {
                "emar_id": emar.emar_id,
                "order_id": emar.order_id,
                "episode_id": emar.episode_id,
                "drug_name": emar.drug_name,
                "dose_given": emar.dose_given,
                "dose_unit": emar.dose_unit,
                "rate": emar.rate_ml_h_actual,
                "route": emar.route,
                "by": emar.administered_by,
                "by_name": emar.administered_by_name,
                "at": emar.administered_at,
                "witness": emar.witness_by,
                "scan": emar.scan_result,
                "score": emar.five_rights_score,
                "pump_id": emar.pump_id,
                "pump_prog": int(emar.pump_programmed),
                "site": emar.site,
                "notes": emar.notes,
                "adverse": emar.adverse_event,
            })

    @staticmethod
    def get_emar(episode_id: str, hours: int = 24) -> List[dict]:
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        with _conn() as con:
            rows = con.execute("""
                SELECT * FROM clma_emar
                WHERE episode_id=? AND administered_at>=?
                ORDER BY administered_at DESC
            """, (episode_id, since)).fetchall()
        return [dict(r) for r in rows]

    # ── Pump Commands ─────────────────────────────────────────────────────────

    @staticmethod
    def save_pump_command(cmd: PumpProgramCommand) -> str:
        cmd_id = f"CMD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        with _conn() as con:
            con.execute("""
            INSERT INTO clma_pump_commands VALUES (
                :cmd_id,:pump_id,:order_id,:drug_name,:rate,:vtbi,
                :conc,:by,:at,:status,:ack,:hl7
            )""", {
                "cmd_id": cmd_id,
                "pump_id": cmd.pump_id,
                "order_id": cmd.order_id,
                "drug_name": cmd.drug_name,
                "rate": cmd.rate_ml_h,
                "vtbi": cmd.vtbi_ml,
                "conc": cmd.concentration_str,
                "by": cmd.commanded_by,
                "at": cmd.commanded_at,
                "status": cmd.status,
                "ack": cmd.ack_message,
                "hl7": cmd.to_hl7_pcd03(),
            })
        return cmd_id

    # ── Audit Log ─────────────────────────────────────────────────────────────

    @staticmethod
    def audit(episode_id: str, order_id: str, action: str,
              performed_by: str, detail: str = "") -> None:
        log_id = f"LOG-{uuid.uuid4().hex[:8].upper()}"
        with _conn() as con:
            con.execute("""
            INSERT INTO clma_audit_log VALUES (?,?,?,?,?,?,?)
            """, (log_id, datetime.now().isoformat(), episode_id,
                  order_id, action, performed_by, detail))

    @staticmethod
    def get_audit(episode_id: str, limit: int = 50) -> List[dict]:
        with _conn() as con:
            rows = con.execute("""
                SELECT * FROM clma_audit_log
                WHERE episode_id=? ORDER BY timestamp DESC LIMIT ?
            """, (episode_id, limit)).fetchall()
        return [dict(r) for r in rows]


# =============================================================================
# Barcode Factory
# =============================================================================

class BarcodeFactory:
    """Generate barcode label untuk satu unit obat yang disiapkan farmasi."""

    @staticmethod
    def create(order: MedicationOrder, pharmacist_nip: str) -> DrugBarcode:
        barcode_id = f"BC-{uuid.uuid4().hex[:8].upper()}"
        now        = datetime.now()
        expires    = now + timedelta(hours=24)   # IV max 24 jam

        dose_label = (
            f"{order.dose_value} {order.dose_unit.value} — "
            f"Rate {order.rate_ml_h:.2f} ml/h"
        )

        return DrugBarcode(
            barcode_id        = barcode_id,
            order_id          = order.order_id,
            drug_name         = order.drug_name,
            drug_generic      = order.drug_generic,
            concentration_str = order.concentration_display,
            dose_label        = dose_label,
            route             = order.route,
            prepared_by       = pharmacist_nip,
            prepared_at       = now.isoformat(),
            expires_at        = expires.isoformat(),
            lot_number        = f"LOT{now.strftime('%Y%m%d')}",
            ndc_code          = "",
        )


# =============================================================================
# HL7 Pump Commander — kirim PCD-03 ke BeneFusion nDS ex
# =============================================================================

class HL7PumpCommander:
    """
    Kirim HL7 PCD-03 programming command ke Mindray BeneFusion nDS ex.
    nDS ex kemudian mem-forward perintah ke eSP ex yang sesuai.

    Koneksi: MLLP TCP ke nDS ex (default port 2576 — programming port,
    berbeda dari port 2575 yang dipakai untuk upload data ke SmartEMR).
    """

    def __init__(self, host: str = "192.168.1.200", port: int = 2576, timeout: float = 5.0):
        self.host    = host
        self.port    = port
        self.timeout = timeout

    def send_command(self, cmd: PumpProgramCommand) -> Tuple[bool, str]:
        """Return (success, message)."""
        hl7_msg = cmd.to_hl7_pcd03()
        frame = b"\x0b" + hl7_msg.encode("latin-1") + b"\x1c\x0d"
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.sendall(frame)
                resp = b""
                while b"\x1c" not in resp:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    resp += chunk
            ack_str = resp.decode("latin-1", errors="replace")
            if "AA" in ack_str:
                return True, f"✓ Pump {cmd.pump_id} diprogram: {cmd.drug_name} @ {cmd.rate_ml_h:.2f} ml/h"
            return False, f"nDS ex rejected: {ack_str[:100]}"
        except ConnectionRefusedError:
            return False, f"Koneksi ke nDS ex {self.host}:{self.port} ditolak"
        except socket.timeout:
            return False, f"Timeout koneksi ke nDS ex ({self.timeout}s)"
        except Exception as exc:
            return False, f"Error: {exc}"

    def ping(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=2.0):
                return True
        except Exception:
            return False


# =============================================================================
# Workflow Manager — satu per sesi Streamlit
# =============================================================================

class CLMAWorkflowManager:
    """
    Manages semua CLMAWorkflowState di st.session_state.
    Satu order_id → satu CLMAWorkflowState.
    """

    @staticmethod
    def _workflows() -> Dict[str, CLMAWorkflowState]:
        if _SESSION_KEY_WORKFLOWS not in st.session_state:
            st.session_state[_SESSION_KEY_WORKFLOWS] = {}
        return st.session_state[_SESSION_KEY_WORKFLOWS]

    @classmethod
    def get_all(cls) -> Dict[str, CLMAWorkflowState]:
        return cls._workflows()

    @classmethod
    def get(cls, order_id: str) -> Optional[CLMAWorkflowState]:
        return cls._workflows().get(order_id)

    @classmethod
    def get_active(cls) -> Optional[CLMAWorkflowState]:
        oid = st.session_state.get(_SESSION_KEY_ACTIVE)
        return cls.get(oid) if oid else None

    @classmethod
    def set_active(cls, order_id: str) -> None:
        st.session_state[_SESSION_KEY_ACTIVE] = order_id

    @classmethod
    def create_order(
        cls,
        episode_id: str,
        patient_name: str,
        patient_no_rm: str,
        weight_kg: float,
        drug_name: str,
        drug_generic: str,
        drug_class: str,
        dose_value: float,
        dose_unit: DoseUnit,
        route: RouteCode,
        frequency: FrequencyCode,
        conc_mcg_ml: float,
        conc_mg_ml: float,
        syringe_ml: float,
        diluent: str,
        ordered_by: str,
        ordered_by_nip: str,
        notes: str = "",
    ) -> Tuple[CLMAWorkflowState, "DoseCalculationResult"]:
        from .clma_engine import DoseCalculationResult
        order, calc = CLMAEngine.create_order(
            episode_id=episode_id, patient_name=patient_name,
            patient_no_rm=patient_no_rm, patient_weight_kg=weight_kg,
            drug_name=drug_name, drug_generic=drug_generic, drug_class=drug_class,
            dose_value=dose_value, dose_unit=dose_unit, route=route,
            frequency=frequency, concentration_mcg_ml=conc_mcg_ml,
            concentration_mg_ml=conc_mg_ml, syringe_size_ml=syringe_ml,
            diluent=diluent, ordered_by=ordered_by, ordered_by_nip=ordered_by_nip,
            notes=notes,
        )
        CLMAStore.save_order(order)
        CLMAStore.audit(episode_id, order.order_id, "ORDER_CREATED",
                        ordered_by_nip, f"{drug_name} {dose_value} {dose_unit.value}")

        wf = CLMAWorkflowState(order=order)
        cls._workflows()[order.order_id] = wf
        cls.set_active(order.order_id)
        return wf, calc

    @classmethod
    def pharmacy_verify(
        cls, order_id: str, pharmacist_nip: str, pharmacist_name: str
    ) -> DrugBarcode:
        wf = cls._workflows()[order_id]
        wf.order.status      = OrderStatus.VERIFIED
        wf.order.verified_by = pharmacist_nip
        wf.order.verified_at = datetime.now().isoformat()
        CLMAStore.update_order_status(
            order_id, OrderStatus.VERIFIED,
            "verified_by", pharmacist_nip,
            "verified_at", wf.order.verified_at,
        )

        barcode = BarcodeFactory.create(wf.order, pharmacist_nip)
        wf.barcode             = barcode
        wf.order.barcode_id    = barcode.barcode_id
        wf.order.status        = OrderStatus.DISPENSED
        wf.order.dispensed_by  = pharmacist_nip
        wf.order.dispensed_at  = datetime.now().isoformat()

        CLMAStore.save_barcode(barcode)
        CLMAStore.update_order_status(
            order_id, OrderStatus.DISPENSED,
            "dispensed_by", pharmacist_nip,
            "dispensed_at", wf.order.dispensed_at,
        )
        CLMAStore.audit(wf.order.episode_id, order_id, "PHARMACY_VERIFIED",
                        pharmacist_nip, f"Barcode: {barcode.barcode_id}")
        return barcode

    @classmethod
    def scan_and_verify(
        cls, order_id: str, scanned_patient_id: str,
        nurse_nip: str, active_drugs: Optional[List[str]] = None,
        allergies: Optional[List[str]] = None,
    ) -> FiveRightsCheck:
        wf = cls._workflows()[order_id]
        if not wf.barcode:
            raise ValueError("Belum ada barcode — farmasi harus dispense dulu.")

        check = CLMAEngine.verify_five_rights(
            order=wf.order, barcode=wf.barcode,
            scanned_patient_id=scanned_patient_id,
            nurse_nip=nurse_nip,
            current_active_drugs=active_drugs,
            patient_allergies=allergies,
        )

        # DDI check
        if active_drugs:
            wf.ddi_alerts = DDIChecker.check(wf.order.drug_name, active_drugs, order_id)

        wf.five_rights = check
        CLMAStore.save_five_rights(check)
        CLMAStore.audit(wf.order.episode_id, order_id, "SCAN_VERIFY",
                        nurse_nip, f"Result: {check.scan_result.value} | Score: {check.score}/6")
        return check

    @classmethod
    def administer(
        cls, order_id: str, nurse_nip: str, nurse_name: str,
        rate_actual: float, pump_id: str = "",
        pump_commander: Optional[HL7PumpCommander] = None,
        site: str = "", witness_nip: str = "", notes: str = "",
    ) -> eMAR_Record:
        wf = cls._workflows()[order_id]
        if not wf.can_administer:
            raise ValueError("5-Rights belum lulus atau belum dilakukan scan.")

        # Auto-program pump jika ada commander
        pump_programmed = False
        if pump_id and pump_commander:
            cmd = CLMAEngine.create_pump_command(wf.order, pump_id, nurse_nip)
            wf.pump_command = cmd
            CLMAStore.save_pump_command(cmd)
            ok, msg = pump_commander.send_command(cmd)
            pump_programmed = ok
            cmd.status      = "SENT" if ok else "REJECTED"
            cmd.ack_message = msg
            logger.info("Pump command: %s", msg)

        emar = CLMAEngine.create_emar(
            order=wf.order, five_rights=wf.five_rights,
            nurse_nip=nurse_nip, nurse_name=nurse_name,
            rate_actual=rate_actual, pump_id=pump_id,
            pump_programmed=pump_programmed,
            site=site, witness_nip=witness_nip, notes=notes,
        )
        wf.emar = emar

        wf.order.status          = OrderStatus.ADMINISTERED
        wf.order.administered_by = nurse_nip
        wf.order.administered_at = emar.administered_at

        CLMAStore.save_emar(emar)
        CLMAStore.update_order_status(
            order_id, OrderStatus.ADMINISTERED,
            "administered_by", nurse_nip,
            "administered_at", emar.administered_at,
        )
        CLMAStore.audit(
            wf.order.episode_id, order_id, "ADMINISTERED",
            nurse_nip,
            f"{wf.order.drug_name} {rate_actual:.2f} ml/h | "
            f"Pump: {pump_id or '-'} | 5R: {wf.five_rights.score}/6",
        )
        return emar

    @classmethod
    def load_from_db(cls, episode_id: str) -> None:
        """Reload active orders dari DB ke session_state (setelah page refresh)."""
        rows = CLMAStore.get_orders(episode_id, limit=10)
        for row in rows:
            if row["order_id"] in cls._workflows():
                continue   # sudah ada di memory
            # Rebuild order object
            try:
                order = MedicationOrder(
                    order_id=row["order_id"], episode_id=row["episode_id"],
                    patient_name=row["patient_name"] or "",
                    patient_no_rm=row["patient_no_rm"] or "",
                    patient_weight_kg=row["patient_weight_kg"] or 0,
                    drug_name=row["drug_name"] or "",
                    drug_generic=row["drug_generic"] or "",
                    drug_class=row["drug_class"] or "",
                    dose_value=row["dose_value"] or 0,
                    dose_unit=next((du for du in DoseUnit if du.value == row["dose_unit"]),
                                   DoseUnit.ML_H),
                    route=next((r for r in RouteCode if r.value == row["route"]),
                                RouteCode.IV_CONTINUOUS),
                    frequency=next((f for f in FrequencyCode if f.value == row["frequency"]),
                                    FrequencyCode.CONTINUOUS),
                    concentration_mcg_ml=row["concentration_mcg_ml"] or 0,
                    concentration_mg_ml=row["concentration_mg_ml"] or 0,
                    syringe_size_ml=row["syringe_size_ml"] or 50,
                    diluent=row["diluent"] or "",
                    rate_ml_h=row["rate_ml_h"] or 0,
                    total_volume_ml=row["total_volume_ml"] or 0,
                    ordered_by=row["ordered_by"] or "",
                    ordered_by_nip=row["ordered_by_nip"] or "",
                    ordered_at=row["ordered_at"] or "",
                    status=next((s for s in OrderStatus if s.value == row["status"]),
                                 OrderStatus.PENDING),
                    is_high_alert=bool(row["is_high_alert"]),
                    is_double_check_required=bool(row["is_double_check_req"]),
                    barcode_id=row["barcode_id"] or "",
                    notes=row["notes"] or "",
                )
                cls._workflows()[order.order_id] = CLMAWorkflowState(order=order)
            except Exception as exc:
                logger.warning("Gagal load order %s: %s", row.get("order_id"), exc)
