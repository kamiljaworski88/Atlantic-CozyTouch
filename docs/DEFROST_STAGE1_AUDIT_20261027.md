# Sterowanie grzalka skroplin na podstawie defrostu — etap 1, audyt 27.10.2026

Status: **audyt kodu zakonczony; sygnal defrostu NIEPOTWIERDZONY.**
Zakres: tylko analiza i dokumentacja, bez zmian w kodzie integracji, bez kontaktu z kontem Atlantic, bez komend do pompy i bez zmian elektrycznych.

Baza: main, commit 6450434c3307e5d6e2b5a2f597e4a6b084b6f458; manifest 0.5.25.

## Oczekiwane zachowanie

- Niezaleznie zasilany kabel grzejny: start po **wiarygodnym** poczatku odszraniania; stop 10 minut po jego zakonczeniu.
- Roboczy prog otoczenia: +3 C (nie jest dowodem defrostu i NIE moze bez dodatkowej walidacji blokowac kazdego defrostu).
- Robocze ograniczenie pojedynczego cyklu: 45 min; ostateczny limit i zachowanie przy awarii ustalic po doborze kabla i jego instrukcji.
- Nie dopuszczac do wlaczenia grzalki przez eksperymentalny lub niepewny sygnal. Odmrazanie urzadzenia, zabezpieczenie tacy i droznosc odplywu sa osobnymi zagadnieniami.

## Potwierdzone fakty w kodzie

| Obszar | Zrodlo | Fakt i konsekwencja |
| --- | --- | --- |
| Odpytywanie | custom_components/atlantic_cozytouch/const.py, POLL_SECONDS | 180 s. Nie gwarantuje wykrycia poczatku ani konca kilkuminutowego defrostu. |
| Aktualna telemetria | readings.py, CAPABILITIES | ID 51: binarny stan sprezarki; 72: modulacja; 24/27: liczniki sprezarki; 91: CO/CWU; 109/116: temperatury hydrauliczne; 119: temperatura zewnetrzna; 153/181: tryby pracy; 380: niezweryfikowany kod CESA. Zadnego zweryfikowanego sygnalu defrostu. |
| Stany sprezarki | compressor.py, compressor_operating_state | Tylko ID 51 lub ID 72 ze znacznikiem zmiany wartosci nie starszym niz 450 s. Sama praca sprezarki nie dowodzi defrostu. |
| Odczyt bezposredni | api.py, async_probe_compressor_capabilities | Przewaznie co 15 minut, dopuszcza tylko 24/27/51/72. Nie jest zrodlem zdarzen defrostu. |
| Badanie katalogu | api_discovery.py, catalogue_summary | Istnieje wyszukiwanie nazw zawierajacych defrost/deicing/degivr/degivr z akcentem; zwraca kandydatow z katalogu, NIE ich wartosci ani potwierdzenia wystepowania na danej pompie. |
| Filtrowane GET | api_discovery.py, build_plan | Aktualnie odpytuje wylacznie CORE_IDS. Poszerzanie o obce ID powodowalo HTTP 400 na tym koncie (udokumentowane w docs/API_DISCOVERY_20261026.md). |
| API producenta | api.py, _request | Scisla lista dozwolonych operacji: POST logowania i GET danych. Brak rozkazow do pompy, zewnetrznego serwera autora, zapisu do sterownika. |
| Platformy HA | __init__.py, PLATFORMS | SENSOR i BINARY_SENSOR, bez switch/climate/button. |
| Pochodzenie czasu | readings.py i docs/API_DISCOVERY_20261026.md | modificationDate to ostatnia zmiana wartosci, nie gwarantowana data fizycznego pomiaru. |
| Istniejaca diagnostyka | sensor.py, AtlanticApiDiscoverySensor | Encja „Atlantic · badanie zrodel API” pokazuje ograniczona diagnostyke (wymaga manualnego opt-in). |

## Ustalenia z wczesniejszych prob rzeczywistego API

Wedlug juz zapisanych dokumentow repo, nie nowych testow z ta instalacja:
- katalog parametrow odpowiadal HTTP 200;
- dwa znane filtrowane odczyty capability odpowiadaly HTTP 200;
- pobranie wartosci katalogowych nieznanych ID w powiekszonej liscie powodowalo HTTP 400;
- ostatnie testy historii energii nie dowodza sygnalu defrostu;
- istnienie nazwy defrost w katalogu, jezeli kiedykolwiek wystapi, **nie** oznacza, ze ten egzemplarz pompy wysyla stan odszraniania.

Zrodla: docs/API_DISCOVERY_20261026.md i docs/GATEWAY_API_DISCOVERY_20261027.md.

## Ocena ryzyka dla sterowania fizycznym grzejnikiem

1. **Krytyczne dla automatyki**: brak zweryfikowanego bitu defrost; nie uruchamiac grzalki na bazie stan sprezarki/tryb CO/samego COP.
2. **Wysokie**: 180-sekundowy cloud polling, mozliwe opoznienie i niedostepnosc chmury; nie uznawac go za deterministyczne sterowanie.
3. **Wysokie**: same temperatury hydrauliczne nie wyznaczaja chwili przelaczenia zaworu czterodrogowego; potrzebna korelacja z prawdziwymi zdarzeniami.
4. **Wysokie**: niezaleznie od Home Assistant, odplyw wymaga fizycznej ochrony przed zamarzaniem i doboru kabla zgodnego z instrukcja.
5. **Srednie**: ID 72 i czasy modificationDate moga opisywac dawna zmiane, a nie aktualny pomiar.
6. **Srednie**: dogrzewanie „10 min po koncu” wymaga znajomosci rzeczywistego momentu konca; przy zaniku sygnalu nie wolno utozsamiac braku danych z zakonczeniem.

## Rekomendacja architektoniczna

**Wariant preferowany:** osobny, lokalny detektor lub niezawodny sygnal defrost z oficjalnie dopuszczonego wyjscia instalacyjnego (jesli serwis potwierdzi jego istnienie), nastepnie przekazanie zdarzenia do HA. Nie ingerowac w sterownik pompy bez zatwierdzonego schematu producenta.

**Wariant badawczy:** jesli API Atlantic rzeczywiscie wystawia stan defrostu, mozna udostepnic go tylko do obserwacji w read-only. Dopiero po dowodzie latencji i zarejestrowaniu wielu cykli zdecydowac, czy nadaje sie do sterowania. Biezacej chmury 180 s nie traktowac jako rozwiazania podstawowego.

**Wariant awaryjny:** niezalezna ochrona odplywu termostatem/odpowiednio dobranym obwodem, niepolegajaca tylko na HA. Prog +3 C jest parametrem roboczym ochrony, a nie detektorem zdarzenia.

## Zadanie weryfikacyjne przed etapem 2

W HA, przy zachowaniu kopii zapasowej i zwyklych zasad ochrony konta:
1. W opcjach Atlantic CozyTouch uruchomic istniejace experimental_api_discovery tylko jesli uzytkownik chce przeprowadzic kolejna ograniczona serie GET; po zebraniu wynikow wylaczyc. Mechanizm wykonuje maks. 7 dodatkowych GET na serie, do oficjalnego hosta Atlantic.
2. W Narzedziach deweloperskich / Szablony wykonac wyłącznie nastepujacy zanonimizowany podglad (nie wysylac surowych payloadow z chmury, hasel ani tokenow):

~~~jinja2
{% for s in states.sensor if 'badanie źródeł API' in s.name %}
status: {{ s.state }}
pozostalo: {{ s.attributes.get('remaining_requests') }}
{% set results = s.attributes.get('results', {}) %}
{% set catalog = results.get('catalogue', {}) %}
catalog_http: {{ catalog.get('http_status') }}
kandydaci_defrost_ID: {{ catalog.get('rows', []) | selectattr('defrost_name_candidate', 'equalto', true) | map(attribute='capability_id') | list }}
interfejs_http: {{ results.get('capabilities_interfejs', {}).get('http_status') }}
generator_http: {{ results.get('capabilities_generator', {}).get('http_status') }}
{% endfor %}
~~~

3. Jezeli sa kandydaci, odczytac w raporcie jedynie jawne liczbowe ID i sprawdzic lokalnie znana dokumentacje ich znaczenia, NIE sondowac losowych tras ani nie przyjmowac skali/semantyki bez sprawdzenia.
4. Przeprowadzic rejestr obserwacji min. 5 rzeczywistych defrostow: recznie odnotowana chwila poczatku i konca; rownoczesnie historia encji Atlantic, stan wentylatora i temperatury, jesli sa dostepne. Zakres i metode wyznaczania tzw. ground truth ustalic z serwisem/obserwacja zachowania urzadzenia. Sprawdzic opoznienia, przeoczenia i falszywe alarmy rowniez poza defrostem.
5. Jezeli brak pewnej flagi lub opoznienie zbyt duze, przejsc do projektu lokalnego detektora (bez ingerecji w elektronike i bez dotykania elementow ruchomych/goracych), z osobna analiza bezpieczenstwa.

## Kryterium zakonczenia etapu 1

- [x] Przeglad aktualnego kodu integracji na main.
- [x] Mapa istniejacych stanow i ograniczen czasowych.
- [x] Potwierdzony brak **zweryfikowanego** sygnalu defrostu w obecnym mapowaniu.
- [x] Zidentyfikowana bezpieczna sciezka ograniczonej diagnostyki.
- [ ] Potwierdzenie mozliwosci bezposredniego odczytu na rzeczywistym urzadzeniu — wymaga danych HA, nie da sie tego uczciwie stwierdzic na podstawie samego repo.
- [ ] Ocena opoznien i skutecznosci detekcji — wymaga obserwacji rzeczywistych cykli.

Nie modyfikowano kodu ani manifestu; brak nowych wersji, encji, komend, zmian elektrycznych i aktywacji grzalki. Brak uruchomienia testow w dzialajacym HA.
