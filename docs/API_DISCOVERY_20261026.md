# Badanie API Atlantic w Home Assistant — 26.10.2026

## Co rzeczywiście ustalono

Pobrano bez logowania listę API z oficjalnego portalu Atlantic i 10 specyfikacji
OpenAPI: Devices, Setups, ProductModels, Capabilities, Monitors, Technilog,
Ecocoaching, BFF_Ecocozy, Setups_v3 i Cozytouch. Nie wykonywano odczytów z konta
użytkownika, prób administracyjnych ani sterowania urządzeniem.

[Wyciąg dowodowy](ATLANTIC_OPENAPI_EVIDENCE_20261026.json) zawiera adresy źródłowe,
wersje, parametry, schematy i hashe lokalnych kopii. Pełne kopie są lokalnie
w `research/atlantic_openapi`; nie zawierają danych konta. Nie instalowano
kodu innych integracji. To analiza protokołu i dokumentacji producenta.

### Nowe ustalenia względem audytu

1. `GET /magellan/devices/{id}/consumptions` deklaruje `periodicity`, `fromDate`,
   `toDate`. `GET /magellan/setups/{id}/consumptions` dodatkowo `deviceId`.
   Bieżące sondy 0.5.22 pomijają zakres dat i filtr urządzenia. To hipoteza
   przyczyny błędów, nie potwierdzenie, że dodanie parametrów usunie HTTP 500.
2. Specyfikacja deklaruje pola query jako string, bez formatu dat i bez enum
   periodicity. Badanie stosuje jeden jawny wariant ISO 8601 UTC oraz znane
   daily/monthly. Brak losowego testowania formatów i ponawiania po błędzie.
3. OpenAPI ma oznaczenia required także przy `setupid` w działającym bez niego
   setupviewv2. Oznaczeń wymaganych pól nie uznajemy za dowód zachowania backendu.
4. Kody kategorii są opisane przez producenta: Heating=1, DHW=2, Cooling=3;
   typ Electricity=1; jednostka KiloWattHour=1. To silniejsze źródło niż wcześniejsza
   analogia do innej pompy. Nadal trzeba sprawdzić zakres instalacji i okres.
5. `producedQuantity` ma ogólny opis produkcji zasobu. Brak jednoznacznej deklaracji
   „ciepło oddane przez tę pompę”. Nie można z samej nazwy utworzyć fabrycznego COP.
6. Capability GET ma filtr `capabilities` w formacie `integer;integer...` i parametr
   `deviceid`. Schemat wartości opisuje modificationDate jako ostatnią modyfikację,
   nie potwierdzony czas pomiaru. Nie odkryto nowego znacznika czasu próbki.
7. Katalog `GET /magellan/productmodels/capabilities` pozwala sprawdzić metadane
   bieżącego producenta, bez zmiany skalowania na podstawie samej resolution.
8. Monitors to stan serwisu, nie historia termodynamiczna. Ecocoaching zwraca porady.
   Technilog opisuje szczegóły urządzeń/sites, nie potwierdzone cieplne kWh.
9. Znaleziono także `/ecocozy/1/v1/setups/{id}/consumption/energy-mix` oraz widok
   consumption i ranking-equipment w BFF. Schemat opisuje **zużycie** według
   źródeł energii. Meta zawiera startDate/endDate, lecz opis i przykłady dat są
   niespójne. Brak dowodu cieplnych liczników. Nie dodano tych endpointów do
   uruchamianego badania: nie poprawiają obecnie dowodu produkcji ciepła.

Źródła pierwotne:
- [Devices 1.92](https://apis.groupe-atlantic.com/api/am/devportal/v3/apis/158f3299-b2cc-474e-a3e2-17de3efec2f3/swagger)
- [Setups 1.9](https://apis.groupe-atlantic.com/api/am/devportal/v3/apis/04ec0d9c-fc56-4566-ab28-b76d44ec42d1/swagger)
- [Capabilities 1.9](https://apis.groupe-atlantic.com/api/am/devportal/v3/apis/940512d4-587e-4935-b741-f216f1b189be/swagger)
- [ProductModels 1.9](https://apis.groupe-atlantic.com/api/am/devportal/v3/apis/cf6d6569-5d4c-4524-9dcf-73137ce42564/swagger)
- [BFF Ecocozy](https://apis.groupe-atlantic.com/api/am/devportal/v3/apis/e298764e-0a07-4cfa-ab77-771cd344a045/swagger)

## Wdrożone zmiany

Nowa opcja HA `experimental_api_discovery` jest domyślnie wyłączona i niezależna
od eksperymentalnego COP. Po włączeniu zbiera dowody w maksymalnie sześciu GET:

| Etap | Odczyt | Cel |
|---|---|---|
| 1 | `/magellan/productmodels/capabilities` | jednostki i resolution znanych ID; kandydatury nazw produkcji/defrost |
| 2 | `/magellan/capabilities/?deviceid=...&capabilities=...` | znane pola interfejsu; porównanie obecności z setup |
| 3 | ten sam odczyt jedynego generatora, jeśli rozpoznany | 109/116, sprężarka/grzałki i pozostałe żądane ID |
| 4 | `/magellan/devices/{id}/consumptions?periodicity=monthly&fromDate=...&toDate=...` | miesięczne liczby do porównania z panelem |
| 5 | ta sama ścieżka z daily | sprawdzenie dziennej dostępności i formatu |
| 6 | `/magellan/setups/{id}/consumptions?periodicity=monthly&fromDate=...&toDate=...&deviceId=...` | odczyt instalacji ograniczony do tej pompy |

Wszystkie adresy są na `https://apis.groupe-atlantic.com`. Zachowano istniejące,
zaobserwowane aliasy ścieżek Magellan bez numeru wersji; OpenAPI podaje także
wersjonowane basePath. Badanie nie próbuje automatycznie kolejnych aliasów.

Zakres dat: od początku poprzedniego miesiąca UTC do chwili utworzenia planu;
identyczny w trzech sondach historii. Daty odpowiedzi są traktowane jako hipoteza
epoch seconds i pokazywane surowo. Brak jawnego końca okresu w starej odpowiedzi
pozostaje `period_end_confirmed: false` — query nie dowodzi granic rekordów.

Żądane ID: 8,9,11,24,27,51,57,58,59,60,64,72,91,109,112,116,164. Dodatkowo do 16
niewrażliwych capability z katalogu, których nazwy wskazują możliwą produkcję
ciepła lub defrost. Dla tych nowych, nieprzejrzanych ID eksportowana jest tylko
obecność/metadane, nigdy surowa wartość. Wyszukiwanie nazw nie dowodzi kompletności
katalogu ani właściwego znaczenia capability.

Pola są zebrane w **osobnej encji diagnostycznej**, nie podmieniane w telemetrii.
Nie łączymy próbek pobranych w różnych cyklach jako zsynchronizowanych pomiarów.
Wartości numeric_value_raw nie mają domyślnych jednostek ani przelicznika.
Historie pokazują maksymalnie 24 najnowsze rekordy na odpowiedź: category/type/unit,
mode/profil, consumed_quantity_raw i produced_quantity_raw. Są to dane do porównania,
nie statystyki Energy ani wyprodukowane ciepło. Brak podwójnego sumowania źródeł.

## Bezpieczeństwo i obciążenie

- Najwyżej jeden dodatkowy GET w cyklu 180 s, maksymalnie sześć na czas życia
  klienta przy niezmienionej instalacji. Około 15–18 minut przy sprawnej chmurze.
- Normalne sondy integracji nadal działają; limit sześciu dotyczy dodatku badawczego.
- Reload/restart z włączoną opcją uruchamia nową serię. Po zebraniu danych wyłączyć
  opcję. Zmiana instalacji czyści kontekst badania; zmiana docelowego urządzenia
  przerywa kolejkę. Więcej niż jeden możliwy interfejs pompy blokuje badanie.
- 401/429 kończy serię bez następnych żądań; 429 ustawia wspólny cooldown.
  Błędy 400/403/404/500 są zapisywane bez body i bez ponawiania tej sondy.
- Brak PATCH/refreshcapability/writecapability, operacji parowania i endpointów admin.
- Dokładny URL dopuszczany wyłącznie na czas wewnętrznej sondy; ID tylko z
  bieżącej odpowiedzi własnego konta. Brak argumentu umożliwiającego dowolny URL.
- Limit body 1 MB przed parsowaniem JSON, timeout 15 s, wyłączone przekierowania,
  domyślna weryfikacja TLS i brak nowych zależności.
- Raport nie zawiera konta, tokenu, numerów seryjnych, deviceId/setupId ani nazw
  urządzeń. Zawiera lokalne liczby energii/temperatur i daty obserwacji, które
  Recorder HA może utrwalić jako atrybuty. Nie eksportuje surowej odpowiedzi API.
- Diagnostyka pobierana przez standardowy diagnostics.py nie zostaje rozszerzona
  o te wartości. Nowa encja służy lokalnej inspekcji.

## Jak uruchomić w Home Assistant

1. Zainstalować przeglądnięty commit gałęzi PR z zielonym CI. Nie ma nowego tagu
   ani deklaracji wydania HACS. Nie zmieniono manifestu ani schematu magazynu.
   Do testu można zastąpić katalog `custom_components/atlantic_cozytouch` jego
   wersją z tej gałęzi, po backupie; następnie zrestartować HA.
2. Ustawienia → Urządzenia i usługi → Atlantic CozyTouch → Konfiguruj/Opcje.
3. Zaznaczyć **Uruchom ograniczone badanie API tylko do odczytu**. Nie trzeba
   włączać eksperymentalnego COP. Zapis przeładuje integrację.
4. W Narzędzia deweloperskie → Stany znaleźć **Atlantic · badanie źródeł API**.
   `w_trakcie` oznacza kolejkę; `remaining_requests` jej pozostałą długość.
   `zakonczono_sprawdz_wyniki` oznacza zakończenie prób, a nie sukces wszystkich GET.
5. Po zakończeniu skorzystać z `API_DISCOVERY_TEMPLATE.jinja`. Zachować raport
   lokalnie przed wyłączeniem opcji. Nie przekazywać haseł ani surowych dumpów.
6. Wyłączyć opcję. Encja wróci do wylaczone; nie trzeba usuwać integracji.

Brak endpointu/formatu oznacza jawny status błędu. Nie obniżamy przez to kryteriów COP.
Jeżeli nowy endpoint zwróci dodatnie produced_quantity_raw, porównać z panelem
CO i CWU za dokładnie ten sam okres. 76/26 i 36/10 z opisu są historycznym
przykładem, a nie wartościami, których parser ma poszukiwać lub wymuszać.

## Kolejne decyzje po wyniku

- 200 z datami zamiast 500 bez dat: mocna przesłanka wady starego żądania;
  powtórzyć kontrolę zakresu i semantyki, zanim zastąpi się sondy produkcyjne.
- Dodatnie Q z właściwym obiegiem: wymagana zgodność panel/API w dwóch okresach,
  jednostki i zakres grzałek. Dopiero potem osobny sensor cieplnych kWh/COP.
- Parametr w direct GET, nieobecny w setup: można dodać jego niezależne źródło
  obserwacji i encję po walidacji jednostki/stanu; nie używać starego cache jako
  świeżej próbki hydraulicznej.
- Nadal 500/brak produkcji: nie można deklarować, że chmura udostępnia wymagane
  ciepło. Następny krok to analiza konkretnej, zredagowanej odpowiedzi lub
  dokumentacji tej generacji regulatora, nie skanowanie przypadkowych URL.

## Testy

Testy offline obejmują sześć odczytów rozłożonych na cykle, ponowne wywołanie bez
nowych zapytań, brak zmian danych wejściowych/COP, ograniczenie URL do konta,
401/429, zbyt duży JSON, zły format, zmianę urządzenia, niejednoznaczną pompę,
prywatność i ograniczenie raportu. Pełny zestaw po dodaniu badania: 228 testów OK.
Dostępność parametrów na konkretnej pompie pozostaje do potwierdzenia w HA.
