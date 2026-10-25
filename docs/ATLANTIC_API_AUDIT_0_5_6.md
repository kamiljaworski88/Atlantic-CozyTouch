# Audyt Atlantic Magellan i COP — 25.10.2026 (v0.5.6)

## Źródło dowodów

Katalog publicznych parametrów Atlantic Magellan_ProductModels v1.9:
https://github.com/gduteil/cozytouch/blob/main/scripts/capability_catalogue.jsonl
Znana ścieżka odczytu urządzenia (z parametrem periodicity):
https://github.com/gduteil/cozytouch/blob/main/docs/api-surface.md
Przykład Alféa Extensa S Duo: modelId=2303, productId=54:
https://github.com/gduteil/cozytouch/issues/177

Niniejszy audyt nie dysponuje tokenem użytkownika ani odpowiedzią jego konta
z testowego GET. Dostępność i znaczenie odpowiedzi wymagają testu on-device.

## Potwierdzone znaczenia ID

| ID | Katalog producenta | Jednostka katalogu | Nasze zachowanie |
|---|---|---|---|
| 24 | StartCounterCompressor | szt. | brak wartości -> unknown |
| 27 | HoursRunCompressor | s | brak wartości -> unknown |
| 51 | CompressorState | enum 0/1 | bezpośredni stan gdy zgłoszony |
| 57 | HOME_ElecHeatConsumptionCumulated | kWh (rozdzielczość 0.001) | hipoteza /1000 na surowych wartościach API |
| 59 | HOME_ElecDHWConsumptionCumulated | kWh (rozdzielczość 0.001) | hipoteza /1000 |
| 60 | HOME_ElecTotalConsumptionCumulated | kWh | brak wartości na tym koncie |
| 44 | HOME_GazHeatConsumptionCumulated | kWh | **gaz**, nie prąd; bez statystyk |
| 45 | HOME_GazDHWConsumptionCumulated | kWh | **gaz**, nie prąd; bez statystyk |
| 46 | HOME_GazTotalConsumptionCumulated | kWh | **gaz**, nie prąd; bez statystyk |
| 109 | GENERATOR_WaterOut1 | °C | zasilanie |
| 112 | CirculatorFlowRate | l/min | przepływ obiegu |
| 116 | GENRATOR_WaterReturn | °C | temperatura powrotu, o ile raportowana |
| 164 | HOME_EnergyConsumptionCapabilities | maska | **zużycie**, nie pewna produkcja cieplna |

ID 164 w katalogu definiuje bity 1,2,4,8,16,32,64. Wartość 1298 = 2+16+256+1024
oznacza co najmniej prąd CO/CWU, ale bity 256 i 1024 są **nieopisane** w tym
katalogu. Poprzednie oznaczanie ich „produkcja ciepła CO/CWU” było nieudowodnione.

**Uwaga o skalowaniu 57/59:** katalog podaje kWh z rozdzielczością 0,001.
Telemetria na tym koncie wygląda jak 26845 i 10679, natomiast sterownik
pokazał wcześniej 26 i 10 kWh. Jest to mocna poszlaka, że surowy transfer
reprezentuje tysięczne kWh, ale nie dowód resetów, ram czasu ani
długoterminowej zgodności. Brak klasy HA Energy do czasu walidacji.

## Droga do COP

COP z danych okresowych wymaga wyprodukowanego ciepła i poboru prądu
dla tego samego obiegu i okresu. W sterowniku, dla części października,
26/10 kWh poboru i 76/36 kWh oddanego ciepła daje 2.92 CO / 3.60 CWU,
łącznie 3.11. Te wartości służą do kontroli, nie są wpisywane do HA.

W standardowym katalogu 405 capability nie znaleziono potwierdzonego
licznika wyprodukowanego ciepła CO/CWU. `producedQuantity` w historii
zużycia może dotyczyć produkcji elektrycznej — NIE jest automatycznym
odczytem cieplnym. Dotychczasowa historia instalacji (daily) nie
ujawniła liczbowej produkcji cieplnej. Miesięczny endpoint instalacji
istnieje już w 0.5.5 jako osobny test diagnostyczny.

## Nowy eksperyment — historia konkretnego urządzenia

Znany endpoint Magellan: `GET /magellan/devices/{id}/consumptions`;
publiczny audyt odnotował odpowiedź HTTP 400 przy braku `periodicity`.
W wersji 0.5.6 weryfikujemy **wyłącznie dla jednej rozpoznanej
pompy z własnego konta**:

- `GET /magellan/devices/{deviceId}/consumptions?periodicity=daily`
- `GET /magellan/devices/{deviceId}/consumptions?periodicity=monthly`

Dokładnie dwa warianty, najwyżej raz na 6 godzin; GET po TLS, bez
przekierowań, bez proxy, bez dostępu do obcych ID, bez operacji
sterujących. Brak/odmowa albo nieznany format pozostają statusem
diagnostycznym i nie zakłócają pozostałych sensorów.

Nowa encja `Historia energii Atlantic · odczyt urządzenia` eksportuje
TYLKO anonimowe typy, kategorie, jednostki oraz liczbę rekordów.
Nie przechowuje wartości energetycznych, identyfikatorów, sekretów,
tokenów, adresów, cen ani dat.

## Ograniczenia i dalsze kryterium sukcesu

Udany HTTP 200 nie gwarantuje dodatkowej informacji: oba endpointy mogą
zwracać to samo lub żadnych pomiarów produkcji ciepła. Jeżeli pojawi
się dodatnia `producedQuantity`, najpierw potwierdzamy jej kategorię,
znaczenie i okres oraz zgodność ze sterownikiem. Bez tego automatyczny
COP okresowy pozostaje niedostępny.

Zmiana ID44–46 zachowuje stare `unique_id` encji, ale usuwa wadliwe
jednostki i klasy statystyk. Jeśli wcześniejsze wersje opublikowały
dane tych ID do Recorder, historycznych wpisów/statystyk HA ta
aktualizacja nie usuwa; wymagają osobnej kontroli przy obecnych
użytkownikach liczników gazowych. Wszystkie zmiany read-only.
