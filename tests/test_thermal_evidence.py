"""Pure, offline tests of anonymized COP source inventory."""
import importlib.util
from pathlib import Path
import sys
import unittest

FILE = Path(__file__).resolve().parents[1] / "custom_components/atlantic_cozytouch/thermal_evidence.py"
spec = importlib.util.spec_from_file_location("thermal_evidence_pure_test", FILE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class TestThermalEvidence(unittest.TestCase):
    def test_initial_state_never_makes_up_energy(self):
        got = module.thermal_evidence({}, {}, {}, {})
        self.assertEqual(got["status"], "oczekiwanie_na_dane")
        self.assertFalse(got["energia_cieplna_potwierdzona"])
        self.assertFalse(got["cop_okresowy_gotowy"])
        self.assertEqual(len(got["zrodla"]), 4)

    def test_empty_histories_do_not_look_like_heat(self):
        got = module.thermal_evidence(
            {"state": "dostepna", "okresy_z_dodatnia_produkcja": 0},
            {"state": "brak_serii"},
            {"daily": {"state": "brak_danych"}, "monthly": {"state": "brak_serii"}},
            {"produkcja_ciepla_co_bit_256": True,
             "produkcja_ciepla_cwu_bit_1024": True},
        )
        self.assertEqual(got["status"], "brak_potwierdzonego_ciepla")
        self.assertTrue(got["hipoteza_obslugi_produkcji_co"])
        self.assertFalse(got["energia_cieplna_potwierdzona"])

    def test_candidate_must_remain_unverified(self):
        got = module.thermal_evidence(
            {"state": "dostepna", "okresy_z_dodatnia_produkcja": 1},
            {"state": "dostepna", "okresy_z_dodatnia_produkcja": 3,
             "rekordy_z_para_poboru_i_produkcji_nieokreslonej": 2},
            {"daily": {"state": "dostepna",
                       "dodatnia_produkcja_niezweryfikowana": 4},
             "monthly": {"state": "dostepna",
                         "dodatnia_produkcja_niezweryfikowana": 7}},
            {"produkcja_ciepla_co_bit_256": True},
        )
        self.assertEqual(got["status"], "kandydat_do_weryfikacji")
        self.assertEqual(got["miesieczne_pary_pobor_produkcja_nieokreslona"], 2)
        self.assertEqual([x["rekordy_z_dodatnia_produkcja_nieokreslona"]
                          for x in got["zrodla"]], [1, 3, 4, 7])
        self.assertFalse(got["cop_okresowy_gotowy"])
        self.assertFalse(got["energia_cieplna_potwierdzona"])

    def test_bad_statuses_and_counts_fail_closed_without_raw_values(self):
        secret = "LEAK_MY_PASSWORD_1234"
        got = module.thermal_evidence(
            {"state": secret, "okresy_z_dodatnia_produkcja": 200},
            {"state": "dostepna", "okresy_z_dodatnia_produkcja": True,
             "rekordy_z_para_poboru_i_produkcji_nieokreslonej": secret},
            {"daily": {"state": "dostepna",
                       "dodatnia_produkcja_niezweryfikowana": -4},
             "monthly": {"state": "nie_sprawdzono",
                         "dodatnia_produkcja_niezweryfikowana": 20},
             "token": secret, "deviceId": secret},
            {"produkcja_ciepla_co_bit_256": secret, "id": secret},
        )
        self.assertEqual(got["status"], "niekompletne_metadane")
        self.assertNotIn(secret, str(got))
        self.assertIsNone(got["miesieczne_pary_pobor_produkcja_nieokreslona"])
        self.assertIsNone(got["hipoteza_obslugi_produkcji_co"])
        self.assertFalse(got["cop_okresowy_gotowy"])

    def test_unavailable_network_sources_and_no_double_sum(self):
        got = module.thermal_evidence(
            {"state": "blad_polaczenia", "okresy_z_dodatnia_produkcja": 9999},
            {"state": "endpoint_niedostepny"},
            {"daily": {"state": "brak_autoryzacji"},
             "monthly": {"state": "nie_sprawdzono"}},
            {},
        )
        self.assertEqual(got["status"], "zrodla_niedostepne")
        self.assertTrue(all(
            x["rekordy_z_dodatnia_produkcja_nieokreslona"] is None
            for x in got["zrodla"]
        ))

    def test_object_payload_and_giant_integer_remain_bounded(self):
        got = module.thermal_evidence(
            {"state": "dostepna",
             "okresy_z_dodatnia_produkcja": 10**80},
            object(), ["private"], {"produkcja_ciepla_cwu_bit_1024": 1}
        )
        self.assertEqual(got["status"], "niekompletne_metadane")
        self.assertIsNone(got["hipoteza_obslugi_produkcji_cwu"])
        self.assertLess(len(str(got)), 1700)


if __name__ == "__main__":
    unittest.main()
