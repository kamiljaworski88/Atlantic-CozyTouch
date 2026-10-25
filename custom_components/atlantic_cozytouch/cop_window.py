"""Experimental metered-electricity update windows; observe, never backfill.

Atlantic ID57/59 moves in batches. A valid *counter-to-counter* window needs
continuous short HA hydraulic observations AND two witnessed vendor counter
advances on the same circuit. Initial startup readings cannot close a window:
the preceding electricity bucket may contain energy from before HA started.

This helper does not contact the cloud, publish heat statistics or retain any
private identifiers in its diagnostics. It is deliberately NOT a daily COP.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

MAX_STEP_SECONDS = 480    # 3-min regular polling, allow modest scheduling jitter
MIN_STEP_SECONDS = 120
MAX_WINDOW_SECONDS = 3600
MIN_WINDOW_SECONDS = 720  # >=12m of continuous snapshots for trustworthy thermal coverage
MIN_COVERAGE = 0.95
MAX_METER_CHANGE_AGE = 900

@dataclass(frozen=True)
class WindowResult:
    heat_kwh: float
    electric_kwh: float
    seconds: int
    covered_seconds: int
    segment_count: int

class ObservedElectricWindow:
    """In-memory only, fail closed across gaps, mode/heater/flow anomalies."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._last = None
        self._anchor = None
        self._heat_kwh = 0.0
        self._covered_seconds = 0
        self._segments = 0
        self.last_reason = "oczekiwanie_na_obserwacje"
        self.last_coverage_percent = None
        self.last_window_seconds = None
        self.last_segment_count = 0
        self.last_counter_increment_seen = False

    def _clear_anchor(self, reason: str) -> None:
        self._anchor = None
        self._heat_kwh = 0.0
        self._covered_seconds = 0
        self._segments = 0
        self.last_reason = reason

    def diagnostics(self) -> dict:
        """No raw electricity quantities, device IDs, tokens or timestamps."""
        return {
            "status": self.last_reason,
            "okno_sekundy": self.last_window_seconds,
            "pokrycie_procent": self.last_coverage_percent,
            "liczba_krotkich_odcinkow": self.last_segment_count,
            "maks_przerwa_miedzy_probkami_s": MAX_STEP_SECONDS,
            "maks_czas_okna_s": MAX_WINDOW_SECONDS,
            "liczymy_od_dwoch_widzianych_skokow_licznika": True,
            "przyrost_licznika_w_biezacym_odczycie": self.last_counter_increment_seen,
        }

    @staticmethod
    def _compatible(a, b) -> bool:
        if a.source_key != b.source_key or a.circuit != b.circuit:
            return False
        if a.mode_stamp != b.mode_stamp:
            return False
        if b.flow_stamp < a.flow_stamp:
            return False
        if b.electric_stamp < a.electric_stamp:
            return False
        # An old/cloud-stale temperature series is only usable if it is
        # unchanged, never if it shifts without recent corresponding metadata.
        if (
            (a.stale_temperature or b.stale_temperature)
            and (a.supply != b.supply or a.ret != b.ret)
        ):
            return False
        return True

    @staticmethod
    def _new_meter_event(a, b) -> bool:
        delta = b.electric_raw - a.electric_raw
        age = (b.seen.timestamp() - b.electric_stamp)
        return (
            isfinite(delta) and delta > 0
            and b.electric_stamp > a.electric_stamp
            and -60 <= age <= MAX_METER_CHANGE_AGE
            and b.electric_stamp >= a.seen.timestamp() - 60
        )

    def ingest(self, current) -> WindowResult | None:
        """Call only after whole hydraulic snapshot passed all upstream gates.

        The current sample is a dataclass with seen/source_key/circuit/stamps,
        hydraulic thermal_kw and raw counter. Returns a validated candidate
        only for a fully observed 12-60 minute interval anchored by TWO
        witnessed counter changes. No unanchored short COP is trustworthy.
        """
        self.last_counter_increment_seen = False
        previous = self._last
        self._last = current
        if previous is None:
            self.last_reason = "czekamy_na_pierwszy_zaobserwowany_skok_licznika"
            return None
        seconds = round((current.seen - previous.seen).total_seconds())
        if not MIN_STEP_SECONDS <= seconds <= MAX_STEP_SECONDS:
            self._clear_anchor("przerwa_miedzy_snapshotami")
            return None
        if not self._compatible(previous, current):
            self._clear_anchor("zmiana_trybu_lub_niespojne_czujniki")
            return None

        delta = current.electric_raw - previous.electric_raw
        if delta < 0:
            self._clear_anchor("reset_licznika")
            return None
        if delta > 0 and not self._new_meter_event(previous, current):
            self._clear_anchor("niespojny_czas_skoku_licznika")
            return None
        if delta > 0:
            self.last_counter_increment_seen = True
        if delta == 0 and current.electric_stamp != previous.electric_stamp:
            self._clear_anchor("zmiana_stempla_bez_przyrostu")
            return None

        if self._anchor is not None:
            # Consecutive successful samples with no missing 3-minute slots.
            segment = (previous.thermal_kw + current.thermal_kw) / 2 * seconds / 3600
            if not isfinite(segment) or segment <= 0 or segment > 10:
                self._clear_anchor("nieprawidlowa_moc_odcinka")
                return None
            self._heat_kwh += segment
            self._covered_seconds += seconds
            self._segments += 1
            window_seconds = round((current.seen - self._anchor.seen).total_seconds())
            if window_seconds > MAX_WINDOW_SECONDS:
                self._clear_anchor("okno_przekroczylo_godzine")
                return None

        if delta == 0:
            self.last_reason = (
                "obserwowanie_pelnego_okna" if self._anchor is not None
                else "czekamy_na_pierwszy_zaobserwowany_skok_licznika"
            )
            return None

        result = None
        if self._anchor is not None:
            duration = round((current.seen - self._anchor.seen).total_seconds())
            self.last_window_seconds = duration
            self.last_segment_count = self._segments
            self.last_coverage_percent = (
                round(self._covered_seconds / duration * 100, 1)
                if duration > 0 else 0.0
            )
            energy_kwh = (current.electric_raw - self._anchor.electric_raw) / 1000
            if duration < MIN_WINDOW_SECONDS:
                self.last_reason = "za_krotkie_okno_licznika_mniej_niz_12_minut"
            elif self._covered_seconds / duration < MIN_COVERAGE or self._segments < 4:
                self.last_reason = "niepelne_pokrycie_pomiarami"
            elif not 0 < energy_kwh < 10:
                self.last_reason = "nieprawidlowy_przyrost_energii"
            elif not 0.5 <= self._heat_kwh / energy_kwh <= 10:
                # This catches e.g. 51 Wh / 25 min of nominal 4 kW heat.
                # Do not transform it into plausible COP by clipping.
                self.last_reason = "energia_cieplna_i_prad_fizycznie_niespojne"
            else:
                result = WindowResult(
                    self._heat_kwh, energy_kwh, duration,
                    self._covered_seconds, self._segments,
                )
                self.last_reason = "zaakceptowane_okno_eksperymentalne"
        else:
            self.last_reason = "punkt_odniesienia_po_pierwszym_skoku_licznika"

        # The next electric energy window can ONLY start from a witnessed
        # counter transition. Resets prevent double counting at boundaries.
        self._anchor = current
        self._heat_kwh = 0.0
        self._covered_seconds = 0
        self._segments = 0
        return result
