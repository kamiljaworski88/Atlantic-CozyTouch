# Atlantic-CozyTouch v0.5.0 — dzienne zużycie energii CO / CWU

## Po co i co wiadomo

Potwierdzony na **tej konkretnej instalacji** endpoint
`GET /magellan/setups/{setupId}/consumptions?periodicity=daily`
zwrócił dwie serie, `category=1` i `category=2`, obie `type=1`
(energia elektryczna), `unit=1` (kWh), `mode=0` (bez podziału taryf),
z dni 22 i 23 października 2026 r. Wszystkie 4 okresy zawierały
`consumedQuantity`; `producedQuantity` nie miało żadnej liczbowej wartości.

Przypisanie `category=1` **CO** i `category=2` **CWU** zostało
niezależnie potwierdzone na innej pompie Magellan (Atlantic Alféa Excellia S)
po porównaniu profili z wyświetlaczem:
[phase0-findings, pkt 4](https://github.com/nekonyuu/home-dashboard/blob/main/docs/phase0-findings.md).
Podział `type=1` / `unit=1` i semantykę podziału taryf
potwierdza także [gduteil/cozytouch](https://github.com/gduteil/cozytouch/blob/main/custom_components/cozytouch/consumption.py).
**Pozostaje do sprawdzenia zgodność liczb z wyświetlaczem Twojej Extensa S Duo XL 10.**

## Encje tworzone w v0.5.0

Nazwy wyświetlane w Home Assistant (rzeczywiste `entity_id` ustala HA):

| Sensor | Źródło | Stan |
| --- | --- | --- |
| Energia elektryczna CO · dzisiaj (UTC) | `category=1, type=1, unit=1` | suma danego dnia [kWh] |
| Energia elektryczna CWU · dzisiaj (UTC) | `category=2, type=1, unit=1` | suma danego dnia [kWh] |
| Energia elektryczna CO · wczoraj (UTC) | `category=1` | całkowite zużycie poprzedniego dnia [kWh] |
| Energia elektryczna CWU · wczoraj (UTC) | `category=2` | całkowite zużycie poprzedniego dnia [kWh] |

- Dla bieżących sensorów zastosowano `device_class=energy`,
  `state_class=total` oraz `last_reset` ustawiany na początek dnia **UTC**.
  To ważne, bo dzienne wartości w chmurze mogą być później skorygowane
  zarówno w górę, jak i w dół. Po północy nowy `last_reset` oznacza nowy
  licznik; brak jeszcze bieżącego dnia daje `unknown`, nie zero.
- Sensory **wczoraj** nie otrzymują `state_class` (historyczny punkt nie jest
  żywym licznikiem i nie powinien trafiać jako taki do statystyk energii).
- Na sensorach **dzisiaj** atrybut `historia_ostatnich_7_dni_utc` przedstawia
  ostatnie maksymalnie 7 dostępnych dni. To podgląd w HA, **nie** backfill
  do bazy Recorder. Recorder i statystyki HA zbierają historię od instalacji.
- Nie ma automatycznego przesuwania historycznych dat do bieżącego dnia;
  nieobecny/nieprawidłowy pomiar ma stan `unavailable`.
- Wykres w HA można zbudować ze wskazań sensorów **dzisiaj** (Historia lub
  wykres statystyk po wdrożeniu). Wsteczna historia sprzed wdrożenia nie
  pojawi się automatycznie w statystykach Recorder.

**Uwaga o strefie czasowej:** API definiuje dzień przez północ UTC.
W Polsce doba UTC zaczyna się o 01:00 (zimą) albo o 02:00 (latem) czasu
lokalnego. Nie jest to dokładnie doba kalendarzowa Europe/Warsaw;
dla porównania wykorzystuj te same okresy z ekranu Atlantic.

## Integralność danych

Parser `energy_daily.py` przechowuje w pamięci wyłącznie kategorię,
dzień UTC i liczbę kWh, nigdy całych odpowiedzi HTTP.
Dane tworzą się tylko dla:
- `category=1` albo `2`,
- dokładnie `type=1`, `unit=1`,
- poprawnej daty UTC, dodatniego lub zerowego wyniku (z zakresu
  zabezpieczającego przed ekstremalnymi wartościami),
- poprawnego kodu taryfy: `mode=0` lub `1` lub `2`.

Jeżeli dla jednego dnia są dwa okresy taryfowe (1/2), dodajemy je do siebie.
Jeśli dla dnia powtarza się ten sam tryb, współwystępuje `mode=0` z
`1/2`, brakuje odczytu, podano inną jednostkę lub wykryto dwie serie tej
samej kategorii, dane nie są publikowane. Nie twórz fałszywego zera.
Każda kategoria przechowuje maksymalnie 40 dat w pamięci; do atrybutu HA
trafia maksymalnie 7 ostatnich dni.

**Nie ma nowych endpointów, poleceń sterujących, serwerów pośrednich czy
rozszerzenia danych diagnostycznych.** Diagnostyka pobierana z HA nadal nie
zawiera odczytów energii, haseł, ID instalacji, numerów seryjnych ani tokenów.
Wersja zachowuje identyfikatory i semantykę istniejących sensorów 57/59/60.

## COP — bez zmian

ID164=1298 deklaruje obsługę energii cieplnej CO/CWU, ale endpoint
historii zwrócił 0 liczbowych pomiarów `producedQuantity`. Nie tworzymy
wymyślonych wartości energii wyprodukowanej, COP, SCOP ani kosztów.

## Procedura odbioru przed wdrożeniem produkcyjnym

1. Sprawdź PR i wyniki CI: kompilacja, testy offline (również bezpieczeństwo
   i brak zapisu), import w oficjalnym HA 2026.10.2.
2. Zrób kopię zapasową HA, po zaakceptowanym merge zaktualizuj integrację,
   uruchom HA ponownie i sprawdź cztery nowe sensory.
3. Porównaj **CO/CWU w kWh za ten sam dzień UTC** ze sterownikiem Atlantic,
   uwzględniając granicę doby i ewentualne późniejsze korekty chmury.
4. Sprawdź przyrost w trakcie ładowania CWU i ogrzewania CO oraz stan po
   północy UTC. W razie rozbieżności nie dodawaj ich do panelu Energia.
5. Dopiero po pozytywnej walidacji zdecyduj o dodaniu do panelu Energia
   Home Assistant; nie dodawaj sensora „wczoraj” jako licznika energii.

**Stan projektu:** PR v0.5.0 do przeglądu; żaden plik na `main` nie jest
automatycznie zastępowany, dopóki właściciel nie wyrazi osobnej zgody.
