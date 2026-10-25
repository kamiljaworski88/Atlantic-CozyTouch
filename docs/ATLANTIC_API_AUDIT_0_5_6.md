# Audyt oficjalnego API Atlantic Magellan — 25.10.2026

## Metoda i ograniczenia
Analiza jest **statyczna**: publiczny katalog 405 definicji capability
Atlantic oraz kod interfejsów Magellan w projekcie Cozytouch; porównano
także ekran lokalnego sterownika właściciela z odczytami Home Assistant.
Nie logowano się do konta użytkownika i nie wysyłano zapytań do jego pompy.
Zielone testy GitHub nie potwierdzają obsługi tych parametrów przez firmware.

Źródła:
- [Kopia publicznego katalogu definicji Magellan](https://github.com/gduteil/cozytouch/blob/main/scripts/capability_catalogue.jsonl)
  (pochodzi z GET /magellan/productmodels/capabilities, według autorów projektu).
- [Mapa endpointów i odkrycie katalogu](https://github.com/gduteil/cozytouch/blob/main/docs/api-surface.md).
- [Podobna integracja HA — interfejs zapytań o energię](https://github.com/gduteil/cozytouch/blob/main/custom_components/cozytouch/consumption.py).
- [Badania obsługi Alfea Extensa S w Magellan i Overkiz](https://community.homey.app/t/app-pro-atlantic-cozytouch-en/159117/15).

## Potwierdzone numery capability

| ID | Nazwa w katalogu | Jednostka opisana w katalogu | Uwagi |
|---|---|---|---|
| 24 | StartCounterCompressor | brak | Licznik startów (opis wspomina dzień) |
| 27 | HoursRunCompressor | s | Czas pracy sprężarki |
| 44/45/46 | HOME_Gaz…ConsumptionCumulated | kWh | **Gaz, nie elektryczność!** |
| 51 | CompressorState | On/Off | Stan sprężarki, gdy raportowany |
| 57 | HOME_ElecHeatConsumptionCumulated | kWh | Energia elektryczna CO |
| 58 | HOME_ElecCoolConsumptionCumulated | kWh | Energia elektryczna chłodzenia |
| 59 | HOME_ElecDHWConsumptionCumulated | kWh | Energia elektryczna CWU |
| 60 | HOME_ElecTotalConsumptionCumulated | kWh | Energia elektryczna łącznie (użytkownik widzi missing) |
| 72 | CompressorModulation | % | Modulacja sprężarki |
| 109 | GENERATOR_WaterOut1 | °C | Zasilanie |
| 112 | CirculatorFlowRate | l/min | Przepływ obiegu |
| 116 | GENRATOR_WaterReturn | °C | Powrót, ale nie wiadomo czy ten sam obieg co 112 |
| 164 | HOME_EnergyConsumptionCapabilities | maska | Flagi **zużycia**, nie licznik ciepła |

Uwaga: deklaracja metadanych ID 57/59 mówi „kWh”, ale na badanej
pompie wartości surowe 26845 i 10679 są bliskie wskazaniom ekranu
26 i 10 kWh dopiero **po podzieleniu przez 1000**. Oznacza to
możliwe inne skalowanie transportowe, nie potwierdzony, uniwersalny
kontrakt dla każdego urządzenia. Integracja utrzymuje wyłącznie
diagnostyczną hipotezę kWh, bez rozliczeniowych statystyk.

## ID 164 — korekta ważnego błędu interpretacji

W katalogu `HomeNRJConsCapabilities` ma **wyłącznie** zdefiniowane:
gaz CO=1, prąd CO=2, prąd chłodzenia=4, gaz CWU=8, prąd CWU=16,
paliwo CO=32, paliwo CWU=64.

ID 164 = **1298** u tego użytkownika zawiera bity
2 + 16 + 256 + 1024.
- 2 i 16 mówią o dostępności danych zużycia elektrycznego CO/CWU.
- Znaczenie 256 i 1024 **nie jest zdefiniowane w opublikowanej masce**.
- Nie wolno przypisywać 256/1024 do „wytworzone ciepło CO/CWU”.
  Nie można z tej maski stworzyć sensora produkcji ciepła lub COP.

## Źródła danych COP — co jest realnie możliwe

1. Sterownik pokazuje miesięczne CO/CWU: prąd 26/10 kWh i ciepło 76/36 kWh.
   Pozwala to policzyć tylko orientacyjny COP za ten sam okres, po uwzględnieniu
   zaokrągleń i dat odczytu.
2. `GET /magellan/cozytouch/setupviewv2`: raportuje ID57/59,
   ale w dotychczasowym wykazie capability nie ma natywnych
   liczników **wytworzonej energii cieplnej**.
3. `GET /magellan/capabilities/?deviceId=…`: osobny odczyt
   listy capability urządzenia, przetestowany przez integrację 0.5.4.
   Może być świeższy, lecz **nie gwarantuje** nowych parametrów.
4. `GET /magellan/setups/{id}/consumptions?periodicity=daily`
   i `monthly` (drugi od v0.5.5): schemat ma `producedQuantity`,
   ale w znanych odpowiedziach to pole było **null**. Nawet gdy
   pojawi się liczba, trzeba ustalić jej znaczenie, jednostkę,
   obieg i datę; nie zakładać, że oznacza energię cieplną.
5. Fizyka `P[kW] = 4.186/60 × przepływ[l/min] × (zasilanie−powrót)[K]`:
   teoretycznie poprawna dla wody, ale **ID 112** i **ID 116**
   występowały na różnych urządzeniach logicznych w
   spisie tej instalacji. Bez potwierdzenia wspólnego obiegu
   nie należy ich łączyć na wykresie COP.

## Zmiany zabezpieczające v0.5.6
- Prawidłowe opisy i jednostki **gazowych** ID44–46;
  brak historycznych statystyk energii dla tych pól.
- Dekodowanie maski ID164 według rzeczywistych opisów,
  z pozostawieniem nierozpoznanych bitów jako nieznanych.
- Szacunek hydraulicznego COP wymaga jednoznacznego
  pochodzenia przepływu, zasilania i powrotu z jednego urządzenia
  logicznego; w przeciwnym razie `unknown`.
- Diagnostyka dodatkowego GET sprężarki jest umieszczona
  pod urządzeniem pompy, jeśli można wskazać dokładnie jedno.

## Rozstrzygnięcie

**Brak obecnie dowodu, że Magellan API oddaje produkcję
ciepła, którą wyświetla lokalny panel Alféa Extensa S Duo XL 10.**
Serwer może udostępniać inny protokół niż ekran serwisowy.
Nie tworzyć fikcyjnego COP, nie wysyłać zapisów, nie
zbierać hasła ani prywatnych zrzutów protokołu poza HA.
