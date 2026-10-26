# Niezależny audyt Atlantic-CozyTouch — 26.10.2026

Baza: `main`, commit `96702b1`, manifest 0.5.22. Lokalna kopia:
`C:\Users\Dell\Atlantic-CozyTouch`. Gałąź: `codex/independent-audit-20261026`.

Zakres dowodu: przegląd kodu wykonywanego przez integrację, powiązanych testów,
historii ostatnich 35 commitów, README i dokumentów API/COP/bezpieczeństwa.
Brak dostępu do działającej instalacji HA i uwierzytelnionych odpowiedzi użytkownika.
Informacje o odczytach i HTTP 500 pochodzą z jego opisu; nie są nowym pomiarem.
Ten dokument opisuje audyt i projekt kolejnych zmian, nie certyfikat gotowej integracji.

## 1. Executive summary

Warstwa odczytu ma rozsądną podstawę: oficjalny host, allowlista metod i tras,
TLS bez wyłączenia weryfikacji, brak sterowania, ograniczone sondy, redagowana
diagnostyka i brak zewnętrznych zależności w manifeście. Telemetria i diagnostyka
są użyteczne niezależnie od dostępności COP.

**COP 0.5.22 nie ma dowiedzionej zgodności okresów energii.** Dwa skoki opublikowanego
licznika nie są dowodem granic fizycznego zużycia. Nowy test uruchamia rzeczywisty
`cop_snapshot.HydraulicCopEstimator`: 0,491 kWh / 0,052 kWh w 12 minut zostaje
zaakceptowane jako 9,44. Oryginalny sześciominutowy przypadek jest już odrzucany.
To nie dowodzi, że 9,44 jest fizycznie niemożliwe; dowodzi, że wydłużenie okna
nie rozwiązuje nieoznaczoności okresu licznika.

Dodatkowo sumy sprzed zmiany metodologii mogą mieszać się z nowymi, a pokrycie
okna może wynosić 100% także przy próbkach co 8 minut. Nazwa „chwilowy” opisuje
wynik okresowy. Nie wolno traktować tych agregatów jako dobowego ani sezonowego COP.

Nie znaleziono potwierdzonego źródła cieplnych kWh dla tego egzemplarza. Poprawna
odpowiedź przy braku dowodów to brak zweryfikowanego COP, z zachowaniem telemetrii
oraz jawnie oznaczonego archiwum eksperymentów.

## 2. Audyt techniczny i bezpieczeństwa

### Aktualna architektura

`api.py` → `readings.py` → koordynator w `__init__.py` → monitory sprężarki,
energii i `cop_snapshot.py` → `cop_window.py` → `cop_accumulator.py` / `cop_last.py`
→ `sensor.py` / `binary_sensor.py`. Sondy historii mają odrębne parsowanie i
podsumowania. `Store` zapisuje sumy i ostatni wynik w dwóch plikach lokalnych.
`cop_hydraulic.py` jest historycznym, nadal testowanym algorytmem; nie jest
estymatorem importowanym przez koordynator. Testy tego modułu nie dowodzą
poprawności ścieżki produkcyjnej.

### Ustalenia według priorytetu

| Priorytet | Dowód w kodzie bazowym | Skutek / decyzja |
|---|---|---|
| P1 | `cop_window.py:170–185`; `cop_snapshot.py:398–420` | Brak rzeczywistych granic okresu energii. Nowy test potwierdza akceptację 9,44 po 12 min. Nie uznawać okna za zweryfikowane. |
| P1 | `cop_accumulator.py:14,113–157`; `__init__.py:40–43` | Schema 1 nie zawiera metodologii, źródła ani kalibracji; odtworzony stary agregat przyjmuje nowe energie. Potrzebne osobne archiwum i nowy magazyn. |
| P1 | `cop_window.py:147,163–174` | Suma wszystkich przyjętych odstępów daje długość okna; próg 95% nie weryfikuje utraconych próbek ani świeżości urządzenia. Rozdzielić ciągłość obserwacji i pokrycie pomiarowe. |
| P2 | `cop_snapshot.py:167–180`; `sensor.py:695,796` | Zastępczy stary agregat oraz nazwa chwilowego COP mogą mylić. Zachować unique_id, zmienić semantykę etykiet i wyeksponować okres/metodę. |
| P2 | `__init__.py`, `update()` | Timestamp był nadawany dopiero po sondach historii (każda może trwać do 15 s). Poprawiono: czas odczytu setup zapisywany przed sondami. Nadal potrzebne metadane czasu dla osobnej sondy sprężarki. |
| P2 | `api.py`, `_note_rate_limited()` | Retry-After 36000 s był skracany do 3600 s. Poprawiono i przetestowano liczby, HTTP-date, niefinitywne i ogromne wartości. |
| P2 | `api.py`, `_request()` | Parametr `params` mógł rozszerzyć dozwolony URL. Brak obecnego wewnętrznego wywołania tej drogi; wzmocniono granicę i test odmowy przed siecią. |
| P2 | `api.py`, `async_probe_consumptions()` | Po 401 innej sondy możliwy był GET z pustym Bearer. Teraz brak tokenu kończy sondę bez sieci; test potwierdza. |
| P2 | `api.py`, wszystkie `response.json()` | Limity urządzeń/rekordów działają po pobraniu i parsowaniu całego JSON. Nie są limitem bajtów odpowiedzi. Pozostaje potrzeba ograniczenia odczytu body i głębokości struktur. |
| P2 | `cop_snapshot.py`, filtr delta T i grzałek | Nie ma niezależnego dowodu odszraniania; odrzucanie ujemnego ciepła i aktywnej grzałki tworzy wybór korzystnych okresów. Takiego wyniku nie nazywać sprawnością całego systemu. |
| P2 | `sensor.py`, `AtlanticDailyElectricitySensor` | Dane są z poziomu instalacji, mapowanie kategorii wymaga lokalnego potwierdzenia, a „dzisiaj” ma klasę TOTAL. Nie utożsamiać z dedykowanym licznikiem tej pompy na koncie wielourządzeniowym. |
| P3 | `config_flow.py` | Brak osobnego przepływu reauth/reconfigure; po zmianie hasła trzeba dopracować bezpieczną wymianę danych wpisu. |
| P3 | `sensor.py`, atrybuty wieku | Wiek ostatniego COP odświeża się z aktualizacją encji, nie ma własnego zegara podczas awarii. Dashboard z `now()` może odświeżać prezentację co minutę. |

Numery linii dotyczą bazy 96702b1; poprawki HTTP przesuwają linie w API.
Reprodukcje: `tests/test_audit_characterization.py`. **To testy charakterystyki
ograniczeń, nie testy akceptacji prawidłowego COP.** Przy naprawie metodologii należy
zastąpić oczekiwanie akceptacji wymaganiem odrzucenia lub osobnego eksperymentu.

### Bezpieczeństwo potwierdzone i granice

- Ruch urządzenia: wyłącznie `https://apis.groupe-atlantic.com`; POST tylko logowanie,
  GET setup, capability i istniejące historie. Bez nowych endpointów w tym PR.
- Przekierowania i nadpisanie TLS/proxy blokowane. 401 setup ma jedną próbę
  odnowienia sesji; 429 wstrzymuje odczyty; błędy sieci i 500 nie są poleceniem pompy.
- Sekrety konta są w config entries HA i pamięci; to nie jest szyfrowany sejf
  integracji. Token nie jest zapisywany przez własny Store.
- Własne magazyny nie zawierają surowych identyfikatorów pompy. Lokalny rejestr
  encji/urządzeń zawiera ID użyte do unique_id; nie należy go eksportować publicznie.
- Redagowany eksport `diagnostics.py` nie zwraca konfiguracji ani surowych wartości.
  Nie jest to gwarancja redakcji dowolnego backupu, logu HA czy innych dodatków.
- Konto/token Atlantic nie mają wymuszonego przez serwer zakresu read-only;
  ograniczenie jest po stronie tego kodu.
- Brak nowych zależności, telemetrii autora i instalowania kodu z innych repozytoriów.
  Obrazy oficjalnego HA w CI służą wyłącznie testom kompatybilności.

## 3. Mapa danych i capability

Katalog źródłowy: [zapis odpowiedzi ProductModels](https://github.com/gduteil/cozytouch/blob/main/scripts/capability_catalogue.jsonl).
Jest to publiczna kopia odpowiedzi producenta, a nie nowe pobranie z konta tej pompy.
Próba odczytu portalu producenta przez narzędzie WWW nie powiodła się.
Rozdzielczość katalogowa nie jest dowodem mnożnika surowej reprezentacji.

| ID | Znaczenie katalogowe / robocze | Jednostka / rozdzielczość | Status dla instalacji |
|---|---|---|---|
| 57 | energia elektryczna CO | kWh / 0,001 | /1000 jest hipotezą transferu |
| 59 | energia elektryczna CWU | kWh / 0,001 | jw. |
| 60 | energia elektryczna całkowita | kWh / 0,001 | brak poprawnej wartości zgłoszony wcześniej |
| 91 | aktywny obieg | enum | 1→CO, 3→CWU; potwierdzić naturalną zmianą |
| 109 | temperatura zasilania | °C | potrzebny wybór właściwego modułu |
| 116 | temperatura powrotu | °C / 0,01 | katalog przeczy starej nazwie exhaust_temperature |
| 112 | przepływ | l/min | skala i wspólny obieg wymagają potwierdzenia |
| 51 | stan sprężarki | enum/bool | nieobecność nie oznacza OFF |
| 64 | stan grzałki CWU | enum/bool | potrzebny czas i wiarygodność stanu |
| 8,9,11 | moce grzałek | katalog: kW; odczyt 3000 niezgodny | brak potwierdzenia skali i nominalna/chwilowa |
| 24,27,72 | starty, czas, modulacja sprężarki | liczba, s, % | tylko jeżeli urządzenie raportuje |
| 111,117–119 | CWU, pokój, zewnętrzna | °C | odrębne punkty pomiarowe |
| 164 | możliwości energetyczne | maska bitowa | nie jest energią |
| 6,150,180,380 | diagnostyka błędów | kod/tekst | interpretować dla modelu |

Dla każdego pola trzeba przechowywać niezależnie `last_value_change_at`,
`api_observed_at`, `measurement_at` (zwykle nieznane), źródło, skalę i stan jakości.
Polling integracji 180 s nie jest częstotliwością pomiaru pompy. Odczyt bez zmiany
przez 7759 s nie dowodzi ani awarii czujnika, ani jego świeżości. Wartości 594/7759 s
i rozbieżność 7165 s opisują wiek zmian, nie synchronizację pomiarów.

### Gdzie szukać energii wyprodukowanej

Istnieją cztery sondy: setup daily/monthly oraz device daily/monthly. `producedQuantity`
i bity capability są kandydaturami, nie dowodem cieplnych kWh. HTTP 500 nie dowodzi,
że licznik nie istnieje; nie uprawnia też do zgadywania kolejnych tras lub obejścia
uprawnień. Publiczny [opis API autora badań](https://github.com/gduteil/cozytouch/blob/main/docs/api-surface.md)
opisuje katalog ProductModels i format capability, ale nie ustanawia fizycznych
przedziałów energii. Nie dodano tych tras do klienta integracji.

[Instrukcja Atlantic Extensa S Duo XL](https://atlantic.be/belgique/download/showpad/ab564799921fdbe569e8a1897b3ec959)
wiąże T24 z wyświetlaczem w diagnostyce komunikacji. W przeszukanym dokumencie
nie znaleziono Modbus. To nie jest dowód braku wszystkich interfejsów, ale nie daje
mapy rejestrów, protokołu ani parametrów elektrycznych do samodzielnego podłączenia.
Nie ustalono, w którym układzie pamięci znajduje się licznik widoczny na panelu.
[Dokumentacja BSB-LAN](https://docs.bsb-lan.de/supported_heating_systems.html)
wymaga zgodnej magistrali BSB/LPB/PPS i właściwego regulatora. Nie potwierdza tego
konkretnego Extensa S. RS-485 określa warstwę fizyczną, nie semantykę rejestrów.
Nie zaleca się adaptera na podstawie nazwy Alféa ani złącza T24.

Atlantic [opisuje estymowany charakter zużycia dla Alféa A.I.](https://www.atlantic.fr/aide/pompe-a-chaleur-air-eau/fonctionnement-utilisation/comment-visualiser-mes-consommations-d-energie-sur-ma-pompe-a-chaleur).
Nie przenosimy tej informacji automatycznie na generację S. Panel jest odniesieniem
zgodności prezentacji, nie automatycznie wzorcem metrologicznym.

## 4. Matematyka i metodologia docelowa

Dla wody: `P = przepływ_l_min × ΔT × 4,186 / 60 [kW]`, przy przybliżeniu gęstości
1 kg/l. Dla glikolu, temperatury i lokalizacji czujników współczynnik wymaga korekty.
Całka trapezowa `Q = Σ((P_i+P_(i+1))/2 × Δt_h)` zakłada zachowanie między punktami;
nie odzyskuje odszraniania lub przełączenia, którego nie zarejestrowano.

Niech `C_pub(t)=C_fiz(t-d(t))`. Kod dzieli `Q(t1,t2)` przez
`C_fiz(t2-d2)-C_fiz(t1-d1)`. Bez znanych opóźnień lub granic okresu to inne przedziały.
Nawet stałe opóźnienie nie gwarantuje zgodności przy zmiennej mocy. Dwa różne
przebiegi zużycia mogą dać identyczne odczyty chmury. Tego nie naprawia test zakresu
0,5–10 ani minimum 12 minut. Wartości 2,92 i 9,44 z innych okresów również nie są
same w sobie porównaniem walidacyjnym.

Jeśli niezależnie ustalono maksymalne opóźnienie D i moc Pmax, można ograniczyć
błąd energii brzegowej przez `Pmax × (d1+d2) + 2r` (czas w godzinach, r jako
konserwatywny błąd pojedynczego odczytu). Gdy D nie jest znane, nie ma liczbowego
przedziału ufności. Samo wydłużenie okna zmniejsza wpływ błędu dopiero po wykazaniu
jego ograniczenia. Nie przyznajemy arbitralnie „95% pewności”.

Docelowe poziomy:

1. **Zgodne dane okresowe producenta:** potwierdzony rodzaj ciepła i prądu, obieg,
   jednostki, ten sam początek/koniec, zakres grzałek i rewizje. Wynik nazywać COP
   według danych producenta; zachować informację pomiar/estymacja.
2. **Pomiar zewnętrzny:** dedykowany licznik całej pompy i ciepłomierz o zgodnych
   granicach układu i czasu. Bez wykluczania elektrycznej energii odszraniania,
   grzałek i postoju z COP systemowego. Podział CO/CWU tylko z wiarygodnym trybem.
3. **Estymacja hydrauliczna zwalidowana:** potwierdzone jednostki, topologia,
   ciągłość, ograniczone opóźnienie i niepewność czujników. Rejestrować niepewność,
   signed heat podczas defrost i braki; nie uzupełniać luk fikcyjną energią.
4. **Eksperyment chmurowy:** obecny stan danych. Wynik diagnostyczny, nie pomiar
   sprawności. Brak podstaw do agregacji dobowej/miesięcznej/sezonowej.

COP sumaryczny to `(Q_CO+Q_CWU)/(E_CO+E_CWU)` dla zgodnych okresów i zakresów,
nie średnia arytmetyczna COP. Nie dodawać ID60 do 57+59. Przy braku rozdziału
obiegów można mieć poprawny bilans całkowity, ale nie wolno wymyślać podziału.

## 5. Docelowe encje, dane i dashboard

| Grupa | Encje i jednostki | Zachowanie |
|---|---|---|
| Komfort | CWU, pokój, zewnętrzna °C | niezależne od COP |
| Hydraulika | zasilanie/powrót °C, ΔT K, przepływ l/min | przepływ dopiero po potwierdzeniu skali; raw oddzielnie |
| Praca | tryb, sprężarka, grzałki, defrost, błędy | brak dowodu = unknown, nie OFF |
| Prąd | CO/CWU/całość kWh; moc W lub kW | verified licznik osobno od hipotezy i średniej okresowej |
| Ciepło | CO/CWU/całość kWh; estymowana moc kW | źródło producent/miernik/estymator w nazwie i metadanych |
| COP | ostatni okres CO/CWU/całość; archiwum eksperymentalne | bez słowa chwilowy dla ilorazu energii |
| Jakość | ostatni odczyt, wiek, metoda, status, pokrycie, odrzucenia | niezależne od wartości historycznej |

Minimalny rekord pomiaru: źródło, obieg, wartość, jednostka, skala, ostatnia zmiana,
czas odbioru, potwierdzony czas pomiaru lub null, status jakości. Minimalny rekord
bilansu: metoda/wersja kalibracji, granice okresu, Q/E, zakres grzałek, pokrycie
obserwacji i pomiarów, powody odrzucenia, liczba segmentów, status opóźnienia.
Idempotencja przez klucz źródło+obieg+metoda+okres; rewizja zastępuje rekord,
nie dopisuje drugi raz tej samej energii. Resety liczników rozpoczynają nową epokę.

Nie potrzeba wielu nowych modułów: zachować klienta, parser i coordinator,
wydzielić wspólny model jakości, źródło okresów energii i kalkulator bilansu.
Stary `cop_hydraulic.py` przenieść do jawnego archiwum testowego po migracji.
Nowy Store schema 2 musi oddzielać metodologie. Schema 1 zachować bez zmian jako
legacy/unverified; nie dopisywać do niego nowych potwierdzonych bilansów.
Otwarte okna nie przechodzą restartu; zatwierdzone rekordy zapisują się atomowo.
Dwa obecne pliki mogą być niespójne po awarii między zapisami; przyszły rekord
powinien łączyć wynik i energie w jednej transakcji Store.

Przykład widoku: `dashboards/atlantic_audit_read_only.yaml`. Korzysta z wbudowanych
sekcji i kart Markdown, wyszukuje istniejące encje integracji, nie wymaga Mushroom.
Nie dopisuje danych ani sterowania. Liczby historyczne mają jawne opisy; brakujące
encje nie są zastępowane zerami. Wykresy należy podłączyć do faktycznych entity_id
z lokalnego rejestru; nie do unique_id ani nazw zgadniętych z API. Krótką historię
COP może przechowywać Recorder, lecz obecne encje COP nie mają state_class dla
statystyk długoterminowych. Nie deklarować, że istnieje już historia miesięczna COP.

## 6. Plan implementacji i priorytety

| Etap | Wartość | Warunek odbioru |
|---|---|---|
| P0: dowody | ustalenie realnych źródeł bez zmiany pompy | anonimowy raport i dwa wspólne okresy panel/API |
| P1: izolacja danych | brak mieszania 9,44 ze zwalidowanym COP | migration schema 1→archiwum; nowe okresy oddzielnie |
| P1: bilans | zgodne Q/E, ograniczona niepewność | okresy źródłowe lub niezależnie potwierdzony lag; brak dowodu blokuje verified |
| P2: jakość | osobny czas zmiany/odczytu/pomiaru | awaria/reset/zmiana trybu nie zamyka poprawnego okna |
| P2: HA | przyjazny dashboard i właściwe statystyki | stare unique_id zachowane, brak fałszywego current COP |
| P2: bezpieczeństwo | ograniczony JSON, reauth, dokładne czasy sond | testy błędów i realny lifecycle HA |
| P3: analiza domu | pogoda/koszty/PV i alarmy | wyłącznie porównywalne okresy z jakością danych |

PGE GAMA 350 jest kontekstem zużycia domu: korelacja może wskazać zdarzenia, ale
nie wydziela automatycznie energii pompy. FoxESS daje bilans PV/sieci/magazynu,
nie ciepło. Przy magazynie uwzględnić ładowanie/rozładowanie i straty. Koszt pompy
można liczyć jako sumę jej energii w przedziałach taryfowych × właściwa cena;
bez licznika/rozbicia to estymacja, nie faktura. Udział PV w pompie wymaga jawnego
modelu alokacji, nie utożsamienia całej autokonsumpcji z ogrzewaniem.

Analiza COP względem pogody wymaga dopasowania temperatury zewnętrznej, temperatury
zasilania, trybu CO/CWU, pracy grzałek, defrost i pokrycia. Porównywać podobne
warunki; nie wnioskować przyczynowo z samej korelacji. Prognozy rozpocząć od modeli
stopniogodzin i bazowego CWU, trenować po zebraniu danych, oceniać na późniejszym
okresie. Nie generować prognozy sprawności z obecnych niezsynchronizowanych COP.

Zewnętrzne źródła przyszłe: użytkownik wybiera encje dedykowanego licznika i
ciepłomierza HA; integracja sprawdza jednostkę, obieg, zakres, reset, czas i dostępność.
Bez automatycznego wybierania GAMA/FoxESS. Brak dodatkowego sprzętu nie blokuje
telemetrii, diagnostyki ani odczytów energii producenta.

## 7. Kod, testy i dokumentacja

W tej gałęzi wdrożono ograniczone poprawki HTTP i czasu obserwacji opisane wyżej,
4 nowe testy HTTP i 5 testów charakterystyki COP. Wzmocniono istniejący test
allowlisty o params. **Nie zmieniono algorytmu COP, nie podniesiono wersji i nie
poluzowano limitów.** Brak dowodu źródłowego nie uzasadnia kolejnego algorytmu,
który jedynie częściej pokazuje liczbę.

Lokalnie Python 3.14.4: 209 testów bazowych OK; po zmianach 218 testów OK.
Polecenie: `python -m unittest discover -s tests -q`.
CI używa Python 3.13 i oficjalnych obrazów HA. Dodano macierz 2026.10.2 i
[2026.10.4](https://github.com/home-assistant/core/releases/tag/2026.10.4), najnowszej
stabilnej wersji wskazanej przez API GitHub w dniu audytu. Smoke import i rejestracja
encji nie zastępują pełnych testów lifecycle/config flow/Recorder na prawdziwym HA.
Status CI konkretnego commitu należy sprawdzić w PR; lokalny OK go nie zastępuje.

### Instalacja, migracja i powrót

To gałąź audytowa / draft PR, a nie nowe wydanie HACS. Do zwykłej aktualizacji
poczekać na sprawdzony tag i CI. HACS: repozytorium typu Integration, pobranie
zatwierdzonego wydania, restart HA, kontrola diagnostyki. Nie kopiować danych
logowania ani `.storage` do GitHub. Przed przyszłą migracją zrobić backup HA,
zachować schema 1 oraz rejestry encji; nie usuwać integracji dla samej aktualizacji.
Powrót: przywrócić poprzednie wydanie oraz zgodny backup magazynu, jeśli zmienił
się schema; restart, weryfikacja odczytu i brak łączenia otwartego okna sprzed restartu.
Ten PR nie zmienia schematu magazynów, unique_id ani wymagań HACS.

## 8. Kryteria potwierdzenia na instalacji

1. Wkleić `docs/AUDIT_CHECK_TEMPLATE.jinja` do Narzędzia deweloperskie → Szablon.
   Raport ma określone pola i nie wymaga tokenu, ID urządzeń ani surowego JSON API.
2. W dwóch oddzielnych, jednoznacznie opisanych okresach odnotować na panelu Q/E
   CO/CWU i porównać wybrane odczyty lokalnie. Daty, obieg, reset i strefa czasowa
   muszą być wspólne. Tolerancję wyprowadzić z rozdzielczości/zaokrąglenia panelu,
   nie z arbitralnej granicy COP. Podane 26/76 i 10/36 są punktem odniesienia,
   nie konfiguracją algorytmu.
3. Potwierdzić `producedQuantity` jako ciepło dla tych samych okresów, albo jawnie
   zapisać brak źródła. Raport 500 nie może odblokować COP; nie zwiększać sondowania.
4. Automatyczny replay: skoki 3/15/30/60 min, zero, reset, opóźnienie publikacji
   stałe i zmienne, stara stała temperatura, zmiana starej temperatury, defrost,
   grzałki, zmiana obiegu, restart i awaria. Obecne testy obejmują wiele tych
   zachowań, lecz brak pełnego replay rzeczywistych okresów i lagów pozostaje luką.
5. Każdy przyszły zaakceptowany bilans daje się odtworzyć z Q/E, granic i wersji
   metody; duplicate replay nie zmienia sum, a awaria nie daje fikcyjnego zera.
6. Legacy 9,44 pozostaje archiwum, nie nowym wynikiem ani składnikiem zweryfikowanej
   sumy. Historyczny COP zachowuje oryginalną datę, a bieżący bez danych jest unknown.
7. Brak nowych tras sieciowych bez opisu, brak sterowania, sekrety nie wychodzą
   w diagnostyce. CI musi przejść dla obu wersji HA; następnie test na instalacji.

### Decyzje: potwierdzenie / hipoteza / ryzyko / weryfikacja / brak danych

| Decyzja | Potwierdzone | Hipoteza i ryzyko | Weryfikacja | Brak danych |
|---|---|---|---|---|
| Jednostki prądu | katalog kWh 0,001 | raw/1000; błędny mnożnik | zgodne przyrosty panel/API | raw bez Energy |
| Ciepło producenta | panel pokazuje według użytkownika | dostępność cloud nieznana | dwa okresy i semantyka serii | brak verified Q/COP |
| Synchronizacja | czasy publikacji/odczytu | granice fizyczne nieznane | okres źródłowy albo zmierzony lag | eksperyment, nie bilans |
| Hydraulika | wzór dla wody | wspólny obieg i świeżość | topologia, medium, rejestracja | nie całkować do verified |
| Grzałki/defrost | dostępność części pól | zakres liczników nieznany | dokumentacja i obserwacja | brak pełnego COP systemu |
| Interfejs lokalny | T24 łączy wyświetlacz | protokół/elektryka nieznane | producent/regulator/rejestry | żadnego adaptera |
| Migracja | schema 1 nie ma metody | sum nie da się rozdzielić | test archiwizacji/restartu | zachować jako legacy |
