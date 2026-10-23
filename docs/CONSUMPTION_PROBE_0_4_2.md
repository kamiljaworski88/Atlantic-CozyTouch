# v0.4.2 — test historii energii i możliwości COP (tylko odczyt)

## Dlaczego osobny endpoint?

Dotychczasowa integracja odczytywała tylko `GET /magellan/cozytouch/setupviewv2`.
Nowy, opcjonalny odczyt używa udokumentowanej przez społeczność ścieżki
`GET /magellan/setups/{setupId}/consumptions?periodicity=daily`.
`setupId` pochodzi wyłącznie z aktualnego, poprawnie sparsowanego `setupviewv2`
i musi być dodatnią liczbą dziesiętną. Nie udostępniamy go w encjach ani diagnostyce.

Źródło i ograniczenia schematu: [gduteil/cozytouch — consumption.py](https://github.com/gduteil/cozytouch/blob/main/custom_components/cozytouch/consumption.py)
oraz [docs/decisions.md — Consumption](https://github.com/gduteil/cozytouch/blob/main/docs/decisions.md).
Pola `consumedQuantity` i `producedQuantity` mogą istnieć w JSON, ale nie
wiemy, czy Alféa Extensa S Duo XL 10 wysyła produkcję ciepła.

## Co wyświetla Home Assistant?

**Diagnostyka → Historia energii Atlantic · test API** (domyślnie wśród
encjach diagnostycznych):
- `dostepna` — niepusta lista serii;
- `brak_danych` — API zwróciło pustą listę;
- `brak_endpointu` / `odmowa_dostepu` — HTTP 404 / 403;
- `brak_id_instalacji` — brak poprawnego numeru setup;
- `limit_zapytan` — HTTP 429, respektowany Retry-After;
- `brak_autoryzacji`, `blad_http`, `blad_polaczenia`,
  `nieprawidlowa_odpowiedz`.

Atrybuty sensora zawierają jedynie liczbę serii i okresów, rozpoznane
numery typów i jednostek oraz liczbę okresów z liczbowymi polami
`consumedQuantity` i `producedQuantity`. Nie ma tam żadnych dat,
odczytów liczbowych energii, loginów, numerów instalacji ani urządzeń.

Dodatkowy atrybut `deklarowane_pomiary_id164` pokazuje cztery flagi:
`prad_co` (bit 2), `prad_cwu` (16),
`produkcja_ciepla_co` (256) i `produkcja_ciepla_cwu` (1024).
To deklaracja dostępności danego pomiaru, nie dowód jego wartości.
Sam liczbowy ID 164 jest też udostępniony jako sensor diagnostyczny.

Odczyt odbywa się maksymalnie raz na 15 minut, niezależnie od
standardowego odświeżania co 180 s. Po HTTP 403/404 próba jest wyłączona
do ponownego załadowania integracji. Nieudany odczyt historii nie usuwa
danych temperatur ani pozostałych sensorów. Brak POST poza logowaniem,
brak PATCH/PUT, brak sterowania urządzeniem.

## Jak sprawdzić na własnej instalacji

1. Po przeglądzie i zaakceptowaniu PR zrób kopię Home Assistant i zainstaluj
   testową wersję v0.4.2, następnie uruchom ponownie HA.
2. Otwórz encję `Historia energii Atlantic · test API`.
3. Zanotuj **sam status i niesekretne atrybuty** oraz flagi ID 164.
4. Jeśli `okresy_z_energia_wyprodukowana > 0`, to tylko wskazówka:
   trzeba porównać kategorię, jednostkę, okres oraz CO/CWU ze sterownikiem
   przed obliczeniem COP. Nie mnożymy tych wartości przez COP katalogowy.
5. Jeśli endpoint odmawia dostępu lub zwraca pustą listę, pozostawiamy
   dotychczasowe liczniki 57/59 diagnostyczne, bez automatycznych kWh.

Raport z **Pobierz diagnostykę** (format 4) zawiera wyłącznie stan i
zagregowany schemat odpowiedzi, a nie surowy JSON chmury.

**Ważne:** nie przetestowano tego endpointu na koncie użytkownika;
offline testy i zielone GitHub Actions nie są potwierdzeniem COP w danym modelu.
