# Atlantic Extensa S Duo XL 10 — defrost wyłącznie z API (31.10.2026)

## Cel i ograniczenia

Użytkownik nie chce montować dodatkowych czujników. Ma Atlantic CozyTouch (Magellan), HA, Shelly Plug S, zewnętrzny termometr. Docelowo kabel grzejny tacy i odpływu: start przy defroście, 10 min po końcu; roboczy próg ochrony +3°C; limit pojedynczego cyklu 45 min. Analiza dotyczy przede wszystkim **read-only** danych pompy. Brak aktywacji obciążenia 230 V w fazie badań.

Baza repo: main (v0.5.30), commit 8efec1d5c1366b5df632869d4984ded721498120. Audyt wcześniejszy: docs/DEFROST_STAGE1_AUDIT_20261027.md (w osobnej gałęzi), rzeczywista diagnostyka: katalog HTTP 200, capabilities_interfejs HTTP 200, capabilities_generator HTTP 200, 0 kandydatów rozpoznanych nazwą defrost w **ograniczonym** raporcie. Nie oznacza to negatywnego dowodu na wszystkie możliwe dane firmware.

## Istotny nowy trop: capability 65

W repo upstream gduteil/cozytouch plik custom_components/cozytouch/capability_table.py definiuje **ID 65** jako `fan_status` z wartościami `0=off`, `1=on`. Zapis ten jest **ogólnym mapowaniem** społecznościowym Magellan/Cozytouch; nie dowodzi, że ID 65 opisuje wentylator jednostki zewnętrznej WOYA100KLT lub że ten konkretny model emituje ID 65.

Źródło: https://github.com/gduteil/cozytouch/blob/main/custom_components/cozytouch/capability_table.py
Kontekst Extensa S jako *interfejs + generator + sloty*: https://github.com/gduteil/cozytouch/blob/main/docs/decisions.md (rozdział „The Alfea Extensa S is two devices”).

Istniejące identyfikatory w naszym kodzie:
- 51: sprężarka pracuje (binarny)
- 72: modulacja sprężarki (%)
- 24/27: starty i czas pracy sprężarki, **nie** stan defrostu
- 109/116: obieg zasilanie/powrót (powiązanie hydrauliczne wymaga ostrożności)
- 119: temperatura zewnętrzna
- 91: wybrany obieg CO/CWU
- 153/181: tryby ogrzewania/wykonywanego serwisu; żadnego zatwierdzonego `defrost`
- 380: niezweryfikowany kod diagnostyczny CESA; **nie mapować jako defrost** bez semantyki
- 65: obecnie **brak** mapowania w `readings.CAPABILITIES`

## Kluczowy fakt z przeglądu aktualnego kodu

`readings.extract_devices()` przechowuje `reported_capability_ids` dla wszystkich zgłoszonych przez chmurę ID, ale wartości zachowuje tylko dla ID z jawnej listy `CAPABILITIES`. ID 65 jest więc odrzucany jako wartość, **o ile** chmura go w ogóle zwraca. `discovery.redacted_inventory` pokazuje ID znane i niemapowane per urządzenie; `diagnostics.async_get_config_entry_diagnostics` eksportuje tę listę do pobieranej diagnostyki HA, bez wartości surowych i danych logowania. To pozwala już teraz sprawdzić obecność **65** bez żadnych nowych requestów.

`api_discovery.CORE_IDS` **nie** zawiera 65. Dodatkowy filtrowany GET bada wyłącznie CORE_IDS, a wcześniejsza próba dołączenia nazw katalogowych ID zakończyła się 400 — nie poszerzać automatycznie zapytań. Jednocześnie istniejący GET `/magellan/capabilities/?deviceId=...` odczytywany co około 15 min z miejsca `async_probe_compressor_capabilities` zachowuje tylko 24/27/51/72.

`POLL_SECONDS=180` i `modificationDate` oznacza *ostatnią zmianę wartości*, nie moment bieżącego pomiaru. Częstszy polling klienta nie gwarantuje częstszych aktualizacji pompy w chmurze. Publiczny upstream wdrożył 60 s, ale opisuje niezależny rytm wymiany urządzenie-chmura: https://github.com/gduteil/cozytouch

## Proponowana kolejność, bez dodatkowego sensora

### A. Najpierw diagnostyka istniejącego setup, bez dodatkowego requestu

HA > Ustawienia > Urządzenia i usługi > Atlantic CozyTouch > trzy kropki > Pobierz diagnostykę.
W anonimowej sekcji `device_capability_inventory` sprawdzić per element `known_capability_ids`, `unmapped_capability_ids` i obecność ID 65, 380, 51, 72, 109, 116, 119, 181.

**Interpretacja**:
- 65 nieobecne w każdym urządzeniu: bieżący setup nie dostarcza wentylatora, więc nie można na nim opierać detekcji. Filtrowany GET tylko po ocenie dokumentacji i bez naruszania rate-limit, nie automatyczne skanowanie.
- 65 obecne: można zaprojektować **nowy opt-in** diagnostyczny `ID 65 surowe`, bez dopisywania znaczenia do wentylatora zewnętrznego. Zapisywać 0/1, czasy odczytu i zmiany, mapowanie do konkretnego urządzenia z przyciętymi ID w diagnostyce, bez publikowania account/device ID.
- ID 380 obecne: analizować zmienność tylko po weryfikacji znaczenia; samo `CESA` nie dowodzi stanów defrostu.
- 65 może dotyczyć innego zespołu niż zewnętrzny wentylator.

### B. Obserwator lokalnych korelacji API — read-only, nie sterowanie

Dla wyłącznie odczytywanych próbek (bez nowych żądań) zapisywać czas odebrania, świeżość, ID65, ID51, ID72, ID109, ID116, ID119, ID91, ID181, ID380. Zachować osobne oznaczenie źródłowego logicznego urządzenia i weryfikację `masterDeviceId` przed łączeniem hydrauliki z innym modułem.

Wymagana walidacja na co najmniej 5 rzeczywistych cyklach defrostu oraz okresach niedefrostowych. Poszukiwać np. *sprężarka ON + wentylator OFF + spadek/odwrócenie ΔT wody* — **to tylko hipoteza**, bo zatrzymanie wentylatora, praca CWU, postój, taktowanie, grzałka i przerwy sieci mogą dawać podobne obrazy. Jeśli brak fan 65, być może tylko analiza zmian ΔT: niska swoistość.

Zliczyć wykryte defrosty, defrosty pominięte, fałszywe wykrycia, opóźnienie początku i końca oraz brak danych. Chmura przy 180 sekundach może przeoczyć krótki cykl niezależnie od jakości algorytmu. Nawet 60 sekund nie gwarantuje czasu aktualizacji sprzętu.

### C. Warunki bezpieczeństwa przed przejściem na Shelly

- Domyślnie `defrost_state=unknown` i brak komend do Shelly.
- Nie opierać ochrony odpływu wyłącznie na takiej heurystyce; należy mieć osobny scenariusz przeciwzamarzaniowy, gdy chmura/HA przestanie działać, zaprojektowany odpowiednio do kabla i instalacji.
- 10 min dogrzewania i limit 45 min to robocze parametry automatyzacji, nie fabrycznie potwierdzone czasy defrostu.
- +3°C to roboczy próg ochrony, **nie** przesłanka pozwalająca odrzucić defrost powyżej +3°C.
- Brak pewnego sygnału defrost oznacza brak podstaw do automatycznego włączania grzałki na podstawie zdarzeń.

## Co jest potwierdzone, a co nie

Potwierdzone w kodzie: dostępny read-only snapshot z chmury, identyfikatory i eksport diagnostyki, czas cyklu 180 s, ograniczenie CORE_IDS, brak mapowania ID65.
Potwierdzone w zewnętrznym mapowaniu (nie fabrycznie): ID65 nazwa `fan_status`.
Niepotwierdzone: czy ID65 występuje na tym urządzeniu, czy oznacza wentylator jednostki zewnętrznej, czy wartości docierają na czas, czy ID380 jest stanem odszraniania i czy defrost można wykryć bez fałszywych zdarzeń.

## Następny nieinwazyjny test

Pobrać *diagnostics* z własnej integracji i odczytać same listy ID per urządzenie. Nie trzeba ponownie uruchamiać `experimental_api_discovery`, zmieniać częstotliwości odczytu, montować czujnika ani przesyłać poświadczeń. Dalsze wdrożenie obserwatora wyłącznie po potwierdzeniu dostępności sygnału oraz osobnej akceptacji zmian kodu.

## Uzupełnienie: wyniki diagnostyki rzeczywistej pompy, 31.10.2026, HA v0.5.30

Użytkownik przekazał standardowy eksport Home Assistant `diagnostics_format=5` z `last_poll_ok=true`. Zredagowana analiza **samych identyfikatorów** (bez metadanych konta, wartości ani seriali):

| Moduł (kolejność w anonimowym eksporcie) | Liczba ID | Parametry przydatne do weryfikacji |
| --- | ---: | --- |
| 1 | 52 | 91, 109, 112, 119, 180, **380**, 370, 381 |
| 2 | 4 | 109 |
| 3 | 78 | 153, 181, 350 |
| 4 | 44 | brak istotnej telemetrii defrostu |
| 5 | 13 | 49, 50, 100, 109, 116 |

**Wniosek stanowczy dla tego eksportu:** ID **65**, **51**, **72** nie występują w żadnym z pięciu zestawów `known_capability_ids + unmapped_capability_ids`; `compressor_capability_ids=[]` dla każdego. Tym samym nie da się oprzeć aktualnego detektora na wentylatorze/sprężarce z danych widocznych w tym eksporcie. Nie przesądza to o odpowiedzi *innych, dozwolonych* endpointów lub stanach niewidocznych w bieżącym snapshot.

Porównanie z publiczną tabelą `gduteil/cozytouch/custom_components/cozytouch/capability_table.py`:
- **380 = `outdoor_unit_error_code_cesa`** — kod **usterki** jednostki zewnętrznej, nie znacznik odszraniania. Nie używać go do startu kabla; jego obecność nie zwiększa wiarygodności detektora.
- **370 = `hub_movable_subproducts`** — niezwiązany z defrostem.
- **381 = `ble_pairing_compatibility`** — niezwiązany z defrostem.
- **49 = `generator_flame_status`, 50 = `generator_modulation_level`** — ogólne mapowanie generatora, **nie** udowodniony fizyczny stan sprężarki tej pompy. Nie zastępować nimi 51/72.
- **90 = `generator_dhw_burner_starts`, 299 = `heat_cool_switch_type`, 350 = `air_circulation_supported_speeds`** — nie opisują bieżącego defrostu.
- ID 180 to błąd jednostki zewnętrznej; 91 wybór CO/CWU; 109/116 temperatury wody (nie wymiennika zewnętrznego).

**Ważne ograniczenie diagnostyki:** standardowy eksport nie zawiera wartości capability ani pełnej historii, więc nie da się w nim zweryfikować spadków temperatur, czasu defrostu ani semantyki dynamicznych kodów.

**Zmieniony plan:** Nie dodawać `binary_sensor.defrost` pod pozorem pomiaru. Jeżeli użytkownik chce nadal badać API, dodać *tylko* lokalny, diagnostyczny rejestr zmian już dostępnych 91/109/116/119/181 z czasem faktycznego otrzymania przez HA, a następnie ręcznie skorelować je z min. 5 obserwowanymi rzeczywistymi defrostami. Bez ID 65/51/72 jego czułość i swoistość mogą być niewystarczające do sterowania Shelly. Równolegle projekt zabezpieczenia antyzamarzaniowego opartego na istniejącym zewnętrznym termometrze (niezależne od zdarzeń defrostu) i na zasadach instalacyjnych, pamiętając o ryzyku awarii HA/chmury.

Nie zmieniono uruchomionej integracji, częstotliwości API, panelu HA ani sterowania Shelly.
