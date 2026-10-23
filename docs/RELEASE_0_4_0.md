# v0.4.0 — raport wydania testowego (telemetria energii)

**Status:** wersja do testów domowych, bez zatwierdzonych statystyk energii.

## Nowe odczyty

- **ID 91** — aktywny obieg `CO` / `CWU` (wartości inne niż 1 i 3 pozostają nieznane).
- **ID 153** — stan ogrzewania/chłodzenia/wyłączony.
- **ID 181** — tryb działania systemu; nie jest stanem sprężarki.
- **ID 99** — neutralnie nazwany binarny stan funkcji CWU.
- **ID 380** — surowy kod diagnostyczny jednostki CESA, bez interpretacji alarmu.
- **ID 57, 59, 60** — **surowe wartości liczników energii**, bez jednostki, klasy energii i wsparcia Energy Dashboard.
- **ID 112** — **surowe wskazanie przepływu**, bez przypisywania jednostki przed kalibracją.

Pozostałe parametry nie tworzą encji sterujących. Istniejące identyfikatory `unique_id` pozostają bez zmian.

## Instrukcja odbioru

1. W Home Assistant zrób pełną kopię zapasową.
2. Sprawdź dostępność aktualizacji w **HACS → Atlantic CozyTouch Read-Only**. Jeśli HACS nie pokazuje nowej wersji, sprawdź, czy repozytorium ma wydany tag/release — nie zakładaj, że zmiana `manifest.json` automatycznie utworzyła wydanie GitHub.
3. Po zainstalowaniu sprawdź `manifest.json` i uruchom ponownie Home Assistant.
4. Otwórz **Ustawienia → Urządzenia i usługi → Atlantic CozyTouch Read-Only → Urządzenia → Encje** i pokaż również wyłączone diagnostyczne.
5. Dla **ID 57/59/60/91/112/153/181** zapisz: nazwę urządzenia/strefy (bez numerów seryjnych), godzinę i wartości z dwóch chwil. Obserwuj naturalny cykl CO/CWU, niczego w pompie nie wymuszaj.
6. Porównaj zużycie energii z dedykowanym pomiarem pompy lub z wiarygodnym odczytem sterownika. Licznik energii całego domu (PGE) ani falownik PV (FoxESS) **nie są** automatycznie miarą zużycia pompy.
7. Zgłoś rozbieżności w issue #5; nie kopiuj danych konta, tokenów, numerów seryjnych ani pełnego payloadu API.

## Kryteria dopuszczenia Energy Dashboard

- Potwierdzone znaczenie poszczególnych ID i jednostki (Wh/kWh).
- Potwierdzona monotoniczność, rozpoznanie resetów i odczytów błędnych.
- Kontrola, czy licznik obejmuje CO, CWU czy całe urządzenie.
- Jawna migracja historii, jeśli kiedykolwiek zmienimy jednostkę istniejących sensorów.
- Brak statystyk COP bez energii cieplnej i elektrycznej.

## Bezpieczeństwo

Nadal tylko **POST** logowania i **GET** odczytu do oficjalnej chmury Atlantic. Żadnych nowych endpointów ani komend sterowania.
