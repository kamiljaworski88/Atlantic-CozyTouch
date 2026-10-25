# Atlantic CozyTouch — Read-Only for Home Assistant

Nieoficjalna, niezależna integracja Home Assistant do **monitorowania** urządzeń Atlantic przez **oficjalne API Atlantic**.

> **Wersja 0.5.5 jest przeznaczona do testów. Nie instaluj jej bez uprzedniego przeglądu kodu oraz wykonania kopii zapasowej Home Assistant.**

## Bezpieczeństwo

- Brak sterowania pompą: **nie ma** encji typu `climate`, `number`, `switch`, `select`, `button` ani usług zapisujących ustawienia.
- Warstwa sieciowa dopuszcza wyłącznie `POST https://apis.groupe-atlantic.com/users/token` (logowanie) oraz odczyty `GET`: `/magellan/cozytouch/setupviewv2`, `/magellan/setups/{setupId}/consumptions?periodicity=daily`, `/magellan/setups/{setupId}/consumptions?periodicity=monthly` i `/magellan/capabilities/?deviceId=…` (wyłącznie potwierdzone ID pompy przypisane do zalogowanego konta).
- Bez serwerów pośredniczących autora integracji, analityki i eksportu danych. **Integracja wymaga chmury producenta**, a nie działa lokalnie/offline.
- Połączenia HTTPS używają standardowej weryfikacji certyfikatów; przekierowania HTTP są blokowane.
- Hasło jest przechowywane przez mechanizm konfiguracji Home Assistant. Chroń `.storage` i kopie zapasowe; nie udostępniaj diagnostycznych logów bez kontroli.
- Brak automatycznych aktualizacji kodu z repozytorium upstream. Sprawdź [model zagrożeń](docs/SECURITY.md).

## v0.5.5 — weryfikacja miesięcznej produkcji ciepła w API

Po porównaniu ze sterownikiem w październiku 2026 mamy zbliżone
wskazania: ID57 = 26,845 kWh (sterownik: 26 kWh),
ID59 = 10,679 kWh (sterownik: 10 kWh).
Potwierdzają one prawdopodobne przypisanie ID57 do CO, ID59 do CWU,
z konwersją surowych jednostek /1000. Okres i reguły resetu tych
liczników w API nie są jednak jeszcze udowodnione.

- **Nowy bezpieczny GET** `/magellan/setups/{setupId}/consumptions?periodicity=monthly`
  przez oficjalną chmurę Atlantic, maksymalnie **raz na 6 godzin**
  na zalogowaną instalację. Bez pośredników i bez komend zapisu.
- Nowa encja diagnostyczna
  `Historia energii Atlantic · miesięczna kontrola`
  pokazuje tylko anonimowe **liczby** serii i wystąpień
  `consumedQuantity` / `producedQuantity`, ich kody typu,
  kategorii i jednostki. **Nie publikuje samych wartości,
  identyfikatorów, kosztów ani dat.**
- Nawet dodatni `producedQuantity` **nie dowodzi produkcji
  ciepła** (może opisywać produkcję elektryczną).
  Bez jednoznacznego znaczenia, jednostek i wspólnego miesiąca
  nie tworzymy fikcyjnego COP miesięcznego.
- Dotychczasowe sensory obliczania **szacunkowego COP chwilowego**
  pozostają bez zmian. Sensor statusu COP zyskuje informację
  o wyniku testu miesięcznego API.
- Atrybuty sensorów sprężarki pokazują wynik dodatkowego
  odczytu v0.5.4 (także gdy są `unknown`). Nie zmieniamy
  odczytów ID24/27/51/72 ani ich unikalnych identyfikatorów.

**Punkt odniesienia tylko do porównania:** sterownik wyświetla
26/10 kWh energii elektrycznej i 76/36 kWh ciepła CO/CWU,
co daje za dotychczasową część miesiąca COP ~2,92 / 3,60,
łącznie ~3,11 (po zaokrągleniu). Te liczby **nie są wpisane
na stałe do HA**. Automatycznego, wiarygodnego miesięcznego
COP nie można udostępnić, dopóki API nie poda zidentyfikowanej
energii cieplnej.

## v0.5.4 — dodatkowy odczyt diagnostyczny sprężarki

- Jeżeli w zbiorczym odczycie `setupviewv2` brakuje ID 24/27/51/72,
  integracja może wykonać **GET** `/magellan/capabilities/?deviceId=…`
  wyłącznie do maksymalnie dwóch urządzeń pompy zgłoszonych przez
  zalogowane konto Atlantic.
- Jeden odczyt na urządzenie **nie częściej niż co 15 minut**.
  Tylko cztery znane parametry sprężarki trafiają do sensorów.
  Liczniki mogą pozostać w pamięci maks. 16 minut, stan chwilowy
  jedynie 4 minuty; poza tym odczyty pozostają `unknown`.
- Nowy diagnostyczny sensor `Diagnostyka odczytu sprężarki z API`
  informuje, czy dodatkowe zapytanie uzupełniło pomiary, czy API
  nie zwróciło nowych parametrów. Nie eksponuje numeru urządzenia,
  tokenów ani surowego payloadu.
- Zachowujemy dotychczasowe nazwy i `unique_id` encji. Bez zmian
  sterowania urządzeniem, bez nowych serwerów i metod POST/PATCH/PUT.
- **Nie ma gwarancji**, że osobny endpoint ujawni te liczniki:
  producent może nie udostępniać ich w chmurze dla danego modelu.

## v0.5.3 — brakujące sensory sprężarki w Home Assistant

- Dla urządzenia rozpoznanego na podstawie ID 91 + ID 112 lub
  natywnej telemetrii sprężarki integracja rejestruje sensory:
  **Uruchomienia sprężarki** (ID 24), **Czas pracy sprężarki** (ID 27),
  **Modulacja sprężarki** (ID 72) i **Sprężarka pracuje** (ID 51).
  Rejestruje też istniejące analizy czasu pracy i startów.
- Gdy Atlantic nie zgłasza danych, encja istnieje, ale jej stan jest
  **unknown**. Surowe wartości nie są domyślane z trybu ogrzewania ani
  licznika energii. Atrybuty pokazują, które identyfikatory nie są
  raportowane przez API.
- Stan „Sprężarka pracuje” wykorzystuje najpierw natywny ID 51.
  Tylko gdy ID 51 jest niedostępny, wolno wnioskować o stanie
  ze **świeżego** ID 72 (modulacji). Nie wolno wyprowadzać
  aktualnego stanu z liczników startów i godzin ani aktywnego obiegu.
- Zachowane są dotychczasowe unikalne identyfikatory encji ID 24/27/51/72
  i sensorów pochodnych; bez nowych endpointów, uprawnień i sterowania.
- Nie jest gwarantowane, że chmura producenta udostępnia odczyty licznika
  sprężarki, które widać na lokalnym sterowniku. Wtedy stan pozostaje unknown.

## v0.5.2 (projekt PR) — eksperymentalny COP hydrauliczny

Automatyczny, **wyłącznie diagnostyczny szacunek** COP dla aktywnego
obiegu CO albo CWU. Wykorzystuje źródła Magellan zgłaszane na tej klasie
urządzenia: przepływ ID112 (l/min), zasilanie ID109 (°C), powrót ID116
(°C) oraz krótkookresowy przyrost licznika elektrycznego ID57/59 (hipoteza Wh).
Moc cieplna w kW = (4,186/60) × przepływ [l/min] × (zasilanie−powrót) [K].
Moc elektryczna w kW jest szacowana z przyrostu Wh na spójnej próbce
tego samego obiegu, a COP = moc cieplna / moc elektryczna.

**Ograniczenia:** to nie jest odczyt chwilowego COP producenta ani sezonowy
SCOP. Chmura może aktualizować liczniki rzadko, a temperatura, przepływ i
licznik prądu nie muszą być jednoczesne. Wynik jest pokazywany tylko przy
poprawnej świeżości, spójnym obiegu, dodatnim przyroście elektrycznym
w oknie 2–20 minut oraz wiarygodnych zakresach; w pozostałych wypadkach
COP pozostaje `unknown`. Przybliżenie zakłada wodę zamiast roztworu
glikolu. Skala ID57/59, przypisanie obiegów i jednostka przepływu
pochodzą z publicznego katalogu i porównywalnych urządzeń, lecz
**nie są pomiarowo zatwierdzone na tej konkretnej pompie**.
Szacunek nie trafia do Energy Dashboard ani kosztów. Bez dodatkowych
endpointów, serwerów pośrednich i poleceń sterujących.

## v0.5.1 — dzienne zużycie energii CO/CWU (PR #18)

- Cztery nowe sensory: energia elektryczna **CO i CWU dzisiaj** oraz **CO i CWU wczoraj**, liczone według dni UTC. Korzystają z istniejącego endpointu historii Magellan.
- Kody `category=1` (CO) i `category=2` (CWU), `type=1` i `unit=1` (kWh) potwierdzono na zbliżonej pompie Atlantic; przed użyciem w rozliczeniach konieczne jest porównanie z ekranem Twojej Extensa S Duo XL 10.
- Sensor „dzisiaj” ma `device_class=energy`, `state_class=total` i reset przy północy UTC. „Wczoraj” to historyczny odczyt bez klasy statystyk; atrybut ostatnich 7 dni nie odtwarza dawnych danych w Recorder.
- Parser sprawdza jednostki, taryfy i duplikaty. Brak pomiaru nie staje się zerem. Nie zmieniamy istniejących encji, diagnostycznego panelu COP ani funkcji read-only.
- COP **nadal nie jest obliczany** — nie ma wiarygodnego pomiaru energii cieplnej w odpowiedzi API.
- [Instrukcja i granice walidacji](docs/DAILY_ENERGY_0_5_0.md).

## v0.5.0 — końcowy audyt energii (bez fikcyjnego COP)

- Nowe **diagnostyczne** odczyty `Hipoteza energii CO · ID 57` i `Hipoteza energii CWU · ID 59`: wstępna konwersja Wh / 1000, niezweryfikowane przypisanie i okres.
- Nowy sensor `COP Atlantic · gotowość danych` — status, a nie wymyślona wartość sprawności.
- Sensory hipotezy **nie mają** `state_class` ani `device_class=energy` i nie wchodzą do statystyk Energy Dashboard.
- [Dashboard Mushroom](dashboards/atlantic_energy_diagnostic_0_5_0.yaml) oraz [raport pięciu etapów i warunki odbioru](docs/ENERGY_COP_FINALIZATION_0_5_0.md).
- Dotychczasowe odczyty historii: 2 serie, 4 rekordy energii elektrycznej, **0 rekordów wyprodukowanego ciepła**; ID164=1298 deklaruje funkcje, nie pomiary. COP liczymy dopiero po potwierdzeniu ciepła i prądu w tym samym okresie.
- Integracja pozostaje tylko do odczytu.

## v0.1.1 — jakość danych i diagnostyka

- Wartości temperatur poniżej -200°C (np. -273,1°C), typowo oznaczające brak pomiaru, stają się `unknown` zamiast zafałszowywać wykresy. Nie modyfikujemy historii zapisanej wcześniej w Recorder.
- Dwa sensory diagnostyczne: ostatni pomyślny odczyt i bieżący status odczytu z chmury. Status oznacza dostępność telemetrii, nie stan sprężarki ani status samego ogrzewania.
- **Diagnostyka wbudowana w HA:** zanonimizowana lista identyfikatorów capability, również nierozpoznanych. Nie zawiera wartości nieznanych parametrów, tokenów, loginów, nazw ani identyfikatorów urządzeń. Dostępna z menu integracji: **Pobierz diagnostykę**.
- Wszystkie dotychczasowe `unique_id` sensorów pozostają bez zmian.

## v0.2.0 — pełny wykaz parametrów API

- Identyfikujemy **wszystkie numery capability zgłoszone przez Atlantic**, także 6-cyfrowe (>65535).
- Eksport diagnostyczny zawiera rozdział na rozpoznane i nierozpoznane ID dla każdej wykrytej jednostki, bez surowych wartości, loginów, numerów seryjnych ani deviceId.
- Nowe sensory diagnostyczne: liczba rozpoznanych i nierozpoznanych parametrów.
- Gdy późniejsze odświeżenie API ujawni kolejny rozpoznany parametr, HA dodaje jego encję bez ponownej konfiguracji.
- Własne mapowanie bez zgadywania: dostępność danego ID to **nie** dowód, że wartości lub jednostki są poprawne dla konkretnego modelu.
- Dodatkowe odczyty pomp obiegowych (25,26,28,29) tylko tam, gdzie pompa je raportuje.

## v0.3.0 — monitoring sprężarki

- Wspiera odczyty producenta: liczba startów (24), czas pracy (27, sekundy), stan (51, 0/1) i modulacja (72, procent). Powstają tylko tam, gdzie dany model je raportuje.
- Sensory pochodne: licznik godzin pracy, **średni czas pracy na start obliczony z liczników całkowitych** oraz przyrosty startów i sekund od ostatniego poprawnego odczytu.
- Pierwszy odczyt po restarcie HA, długa luka, reset licznika i niewiarygodny przyrost → wartość `unknown`. Żadnych sztucznych startów.
- Nie ma funkcji sterowania pompą ani nowych wywołań API.
- Zobacz instrukcję [monitorowania sprężarki](docs/COMPRESSOR.md), w tym tworzenia statystyk dobowych przez Utility Meter w HA.

## v0.4.3 — audyt kategorii i okresów energii (historia zmian)

- Rozszerza **istniejący sensor** `Historia energii Atlantic · test API` o `serie_szczegoly`: anonimowe indeksy, kody `category/type/unit`, tryby i profile, liczbę dni, zakres dat UTC oraz informację o brakujących i dodatnich wartościach produkcji.
- `type=1` / `unit=1` interpretujemy w diagnostyce jako energię elektryczną w kWh **tylko według schematu potwierdzonego na innym urządzeniu Atlantic**. **Nie przypisujemy automatycznie dwóch serii do CO i CWU**.
- Wszystkie stare nazwy encji i atrybuty zostają, nie tworzymy nowych liczników w panelu Energia i nie liczymy COP; bez nowego ruchu HTTP ani sterowania pompą.
- Raport JSON z diagnostyki ma format 5. Szczegóły są ograniczone do 12 serii, bez surowego zużycia, kwot, identyfikatorów konta/urządzenia ani tokenów.
- [Audyt API, ograniczenia i procedura odbioru](docs/ENERGY_API_AUDIT_0_4_3.md). Zachowane mapowanie diagnostyczne, bez automatycznej klasyfikacji CO/CWU.

## v0.4.2 — ostrożny test endpointu historii energii

- Opcjonalny odczyt wyłącznie GET `/magellan/setups/{setupId}/consumptions?periodicity=daily`, nie częściej niż co 15 minut. Identyfikator instalacji jest walidowany i nigdy nie trafia do diagnostyki.
- Nowy sensor diagnostyczny **Historia energii Atlantic · test API** pokazuje status, liczby okresów z `consumedQuantity` / `producedQuantity` oraz kody typów i jednostek — **bez surowych danych zużycia**.
- Surowy ID **164** jest dostępny do weryfikacji wraz z flagami: elektryczność CO/CWU i deklarowane wytwarzanie ciepła CO/CWU.
- Żaden licznik nie dostaje nowych jednostek kWh, nie powstaje COP, nie zmienia się Energy Dashboard. COP będzie możliwy dopiero po potwierdzeniu semantyki i okresów na Twojej pompie.
- Endpoint 403/404 jest wyłączany do ponownego wczytania integracji; 429 uruchamia istniejący mechanizm odczekania. Niepowodzenie dodatkowego odczytu nie psuje podstawowych sensorów.
- Zobacz [test i interpretację odczytu](docs/CONSUMPTION_PROBE_0_4_2.md). To wersja **do przeglądu i testów**, nie potwierdzenie dostępności energii cieplnej w Extensa.

## v0.4.1 — walidacja odczytów energii i świeżości danych

- Nowy status ID `60`: rozróżnia brak wartości, pustą odpowiedź, niepoprawny format, wartość ujemną lub poza zakresem. Nie eksportuje surowego tekstu API.
- Dwa pomocnicze sensory **przyrostu surowego wskazania** `57` i `59`; nie mają jednostek energii ani HA `state_class`. Po pierwszym odczycie, nieudanym polling, luce, zmianie urządzenia lub spadku wartości zwracają `unknown` zamiast fałszywej statystyki.
- Sensor **Aktualność telemetrii Atlantic** analizuje czas ostatniego sukcesu i status ostatniego polling; lokalne odświeżenie co 60 sekund nie generuje dodatkowego ruchu do Atlantic.
- Pobierana diagnostyka HA ma format `3` i zawiera wyłącznie anonimowe kody stanu walidacji, nie liczby energii ani dane urządzeń.
- [Szablon raportu walidacyjnego](docs/ENERGY_VALIDATION_REPORT.md) i [propozycja bloku dashboardu](docs/DASHBOARD_0_4_1.md).
- Nadal **nie ma** potwierdzonego skalowania ID `57/59/60`, sensorów kWh, automatycznych kosztów ani COP.

## v0.4.0 — telemetria energii i trybów (walidacja na urządzeniu)

Po analizie diagnostyki Extensa S Duo XL 10 integracja rozpoznaje dodatkowo:
- **91**: aktywny obieg CO / CWU (kody 1 / 3).
- **153**: stan ogrzewania (wył. / ogrzewanie / chłodzenie).
- **181**: wykonywany tryb usługi (nie jest to stan sprężarki).
- **99**: binarny stan funkcji CWU (znaczenie zależy od modelu).
- **380**: kod diagnostyczny jednostki zewnętrznej CESA (liczbowy, bez automatycznej interpretacji alarmu).
- **57, 59, 60**: **surowe wskazania liczników energii** bez jednostek, klas energii i statystyk (do weryfikacji skalowania/znaczenia).
- **112**: **surowy odczyt przepływu**, bez przypisywania L/min przed porównaniem z urządzeniem.

Te sensory istnieją **tylko gdy Atlantic je raportuje** i pozostają diagnostyczne. Żadna surowa wartość energii nie jest kierowana do Energy Dashboard ani używana do obliczania COP. Nie dodaliśmy nowych żądań HTTP, komend sterujących ani ujawniania surowych wartości w pobieranym raporcie diagnostycznym. Zobacz [plan walidacji v0.4.0](docs/ENERGY_VALIDATION.md).

## Co odczytuje?

Integracja tworzy sensory **wyłącznie dla identyfikatorów, które pompa faktycznie raportuje**. Obejmuje m.in.:

| Identyfikator Atlantic | Odczyt |
| --- | --- |
| 24 | liczba uruchomień sprężarki |
| 27 | czas pracy sprężarki (wg API: sekundy) |
| 51 | stan sprężarki |
| 72 | modulacja sprężarki (%) |
| 44, 45, 46 | liczniki elektrycznego zużycia CO, CWU i łącznego, automatycznie przeliczone z Wh na kWh |
| 100 | ciśnienie wody |
| 109 | temperatura wody obiegu |
| 111 | temperatura CWU |
| 117, 118 | temperatura pokojowa stref |
| 119 | temperatura zewnętrzna |
| 6, 150, 180 | diagnostyczne kody błędów |

Uwaga: samo istnienie mapowania nie oznacza dostępności danej wielkości dla Alféa Extensa S Duo XL 10. Do potwierdzenia potrzebna jest próba odczytu rzeczywistego urządzenia. **COP i energia cieplna nie są obliczane bez wiarygodnych pomiarów. Wartości zużycia elektrycznego 44–46 mają w API jednostkę Wh i są prezentowane w kWh.**

## Instalacja (dopiero po przeglądzie PR)

1. Zrób kopię zapasową Home Assistant (kontrola importu wykonana na 2026.10.2).
2. **HACS:** niestandardowe repozytorium musi być publicznie dostępne. Sprawdź aktualną widoczność repozytorium w GitHub przed dodaniem go w HACS; nie trzeba jej zmieniać dla wersji ręcznej.
3. W HACS: *⋮ → Niestandardowe repozytoria → URL repozytorium → Integracja → Dodaj*, a następnie zainstaluj **Atlantic CozyTouch Read-Only** z `main` i ponownie uruchom Home Assistant.
4. Uruchom ponownie HA, dodaj integrację w *Ustawienia → Urządzenia i usługi* i podaj dane konta Atlantic **tylko w lokalnym formularzu HA**.
5. Zweryfikuj dostępne encje i brak usług sterujących. Kod pozostaje **testową wersją 0.5.0**, dopóki nie zostanie sprawdzony na rzeczywistym urządzeniu.

**Alternatywa zachowująca prywatność repozytorium:** pobierz archiwum ZIP gałęzi `main` ze swojego GitHub i skopiuj folder `custom_components/atlantic_cozytouch` do `/config/custom_components/` na HA, po czym uruchom go ponownie. To instalacja ręczna (nie przez HACS).

## Zakres i ograniczenia (aktualny stan)

- Odczyt co 180 sekund, z obsługą błędów autoryzacji, HTTP 429 i problemów sieciowych.
- Brak dostępu LAN/Modbus; całkowicie zależna od chmury Atlantic.
- Istnieje dodatkowy endpoint historii energii, lecz dotychczas nie zwrócił pomiarów produkcji ciepła. ID 57/59 w kWh pozostają diagnostycznymi hipotezami.
- Nie gwarantujemy, że interfejs producenta pozostanie niezmienny ani że każde pole będzie dostępne.
- Brak automatycznych aktualizacji po stronie pompy, wprowadzania zmian czy odkrywania endpointów.

## Niezależna implementacja i licencja

Kod został napisany od podstaw dla projektu Atlantic-CozyTouch, bez kopiowania implementacji `gduteil/cozytouch`. Nazwy identyfikatorów i adresy interfejsu służą do zapewnienia interoperacyjności. Projekt nie jest powiązany z Atlantic. Kod własny na licencji MIT; zobacz [LICENSE](LICENSE).

## Testy

```bash
python -m unittest discover -s tests -v
python -m compileall -q custom_components tests
```
