# Atlantic CozyTouch — Read-Only for Home Assistant

Nieoficjalna, niezależna integracja Home Assistant do **monitorowania** urządzeń Atlantic przez **oficjalne API Atlantic**.

> **Wersja 0.5.30 jest eksperymentalna. Przed instalacją wykonaj kopię zapasową Home Assistant. Szacunkowy COP i energia cieplna nie są pomiarem producenta ani statystyką HA Energy.**

## v0.5.30 — próg publikacji energii cieplnej 94%

- Minimalne pokrycie zakończonej doby dla sensorów energii cieplnej obniżono
  z 95% do 94%. Wymóg 100% potwierdzonej topologii pozostaje bez zmian.

## v0.5.29 — osobne sensory szacowanej energii cieplnej

- Dodano zakończonodobowe sensory `Energia cieplna Atlantic · CO (szacunek)`,
  `CWU (szacunek)` i `łącznie (szacunek)` oraz sensor `jakość źródła`.
- Energia jest całkowana wyłącznie z zaakceptowanych odcinków ID112 ×
  (ID109−ID116). Nie uzupełnia braków i nie jest licznikiem producenta.
- Liczba pojawia się dopiero przy co najmniej 94% pokrycia doby i 100%
  segmentów ze zweryfikowaną topologią. Dla osobnych modułów weryfikacja
  wymaga jawnej relacji `masterDeviceId` w odpowiedzi Atlantic; samo włączenie
  opcji cross-device nie wystarcza.
- Sensory są diagnostyczne, bez `device_class` i `state_class`, więc nie trafiają
  do HA Energy ani statystyk długoterminowych.

## Niezależny audyt 26.10.2026 (gałąź audytowa)

[Raport, kontrprzykłady i plan rozwoju](docs/INDEPENDENT_AUDIT_20261026.md)
wykazuje, że dwa skoki licznika nie dowodzą zgodności okresów Q/E.
Ten sam iloraz 0,491/0,052 = 9,44 może nadal zostać przyjęty po 12 minutach.
218 testów offline nie oznacza zweryfikowanego COP. Algorytm i wersja pozostają
bez zmian; nowe testy charakterystyki dokumentują nierozwiązane ograniczenia.

## Opcjonalne badanie API w Home Assistant

[Instrukcja i ustalenia reverse engineeringu](docs/API_DISCOVERY_20261026.md):
bezpośrednio pobrane specyfikacje producenta ujawniły parametry dat historii,
filtr urządzenia oraz filtrowany GET capability. Nowa opcja jest domyślnie
wyłączona, wykonuje do sześciu odczytów i pokazuje wyniki w osobnej encji.
Nie odblokowuje COP ani sterowania pompą.

## Bezpieczeństwo

- Brak sterowania pompą: **nie ma** encji typu `climate`, `number`, `switch`, `select`, `button` ani usług zapisujących ustawienia.
- Warstwa sieciowa dopuszcza wyłącznie `POST https://apis.groupe-atlantic.com/users/token` (logowanie) oraz odczyty `GET`: `/magellan/cozytouch/setupviewv2`, `/magellan/setups/{setupId}/consumptions?periodicity=daily`, `/magellan/setups/{setupId}/consumptions?periodicity=monthly` i `/magellan/capabilities/?deviceId=…` oraz `/magellan/devices/{deviceId}/consumptions?periodicity=daily|monthly` (ostatnia para wyłącznie dla jednej rozpoznanej pompy z konta, maksymalnie co 6 godzin).
- Bez serwerów pośredniczących autora integracji, analityki i eksportu danych. **Integracja wymaga chmury producenta**, a nie działa lokalnie/offline.
- Połączenia HTTPS używają standardowej weryfikacji certyfikatów; przekierowania HTTP są blokowane.
- Hasło jest przechowywane przez mechanizm konfiguracji Home Assistant. Chroń `.storage` i kopie zapasowe; nie udostępniaj diagnostycznych logów bez kontroli.
- Brak automatycznych aktualizacji kodu z repozytorium upstream. Sprawdź [model zagrożeń](docs/SECURITY.md).

## v0.5.26 — naprawa historii CWU w dashboardzie

- Poprawka sensora `Energia elektryczna CWU · dzisiaj (UTC)`: jeśli Atlantic zwrócił poprawną historię, ale nie podał dzisiejszego rekordu CWU, sensor pozostaje dostępny z wartością `unknown` (a **nie** 0 kWh) oraz atrybutem `historia_ostatnich_7_dni_utc` ze starszymi dniami.
- Naprawia znikającą kolumnę CWU z dynamicznego dashboardu, który odczytuje historię z atrybutu dzisiejszego sensora. Analogiczne działanie dla CO. Gdy API jest niedostępne lub zwróciło błąd, sensor nadal pozostaje niedostępny.
- Nie dodaje żadnych żądań do chmury, nie tworzy sztucznych pomiarów, nie zmienia COP1/COP2 ani statystyk HA Energy. Prawdziwe `0 kWh` pozostaje odróżnialne od braku rekordu. Nie ustawia `last_reset` dla brakującego dnia.

## v0.5.25 — COP2: próg obserwacji doby 80% zamiast 95%

- **Nowy próg:** akceptacja eksperymentalnego wskaźnika COP2 zaczyna się przy **≥80% z 86 400 s** poprawnych odcinków hydraulicznych w zakończonej dobie UTC; poprzednio wymagano ≥95%. Test progu korzysta z **niezaokrąglonych sekund**, więc 79,99% nie zostanie zaakceptowane.
- Gdy pokrycie wynosi **80–<95%**, encja diagnostyczna zgłasza `szacunek_niepelna_doba_niska_pewnosc`. Dostępne są nowe atrybuty `minimum_coverage_pct`, `near_complete_coverage_pct`, `missing_seconds`, `partial_day`, `partial_period_bias_warning`, `periods_physically_aligned_confirmed=false` i `thermal_energy_extrapolated=false`.
- **Uwaga o matematyce:** przy niepełnej dobie energia cieplna pochodzi wyłącznie z zapisanych fragmentów, podczas gdy energia elektryczna nadal obejmuje całą dobę. Iloraz NIE jest wtedy COP dla wspólnego przedziału czasu; może być zaniżony, ale nie można gwarantować kierunku błędu. Nie poprawiamy brakujących godzin mnożnikiem 100/pokrycie.
- Powyżej 95% istniejące `szacunek_niska_pewnosc` pozostaje bez zmian. COP2 jest nadal diagnostyczny i niezależny od COP1, bez nowego GET, bez klasy ENERGY lub state_class.

## v0.5.24 — COP2: oddzielny dobowy szacunek hydrauliczny i rejestr próbek

- **Nowa opcja** `experimental_cop2` (domyślnie wyłączona): niezależny od COP1, lokalny 14-dniowy rejestr snapshotów z existing 180 s polling. Zapisuje jedynie dozwolone wartości numeryczne przepływu, temperatur, trybu, liczników CO/CWU, stanu sprężarki/grzałek oraz znaczniki ostatniej zmiany; **bez** serialu, loginu, tokenu, ID urządzeń czy nowych zapytań do Atlantic.
- Zapis w oddzielnym pliku HA `.storage/atlantic_cozytouch.cop2_telemetry_<entry-id>` (systemowy `Store`), checkpoint maks. co około 15 min i przy prawidłowym unload; retencja 14 dni z limitem 10 080 próbek. Archiwum COP1 jest **nietknięte**.
- Osobne encje diagnostyczne: `COP2 Atlantic · diagnostyka`, `COP2 Atlantic · CO (eksperymentalny)`, `COP2 Atlantic · CWU (eksperymentalny)`, `COP2 Atlantic · łączny (eksperymentalny)`. Żadna **nie ma** state_class ani ENERGY device_class.
- Metoda wyłącznie dla **zakończonej doby UTC**: integracja przepływu ID112 i ΔT z ID109/116 generatora metodą trapezów na krótkich (< 8 min) ciągłych odcinkach. Zmiany trybu, potwierdzona grzałka, brak hydrauliki i przestarzałe znaczniki są odrzucane. Potwierdzona wyłączona sprężarka na obu końcach = 0; brak stanu sprężarki = niska pewność. Negatywnego przepływu ciepła nie usuwamy dla poprawienia wyniku.
- Publikacja **tylko szacunkowego COP2** przy ≥95% pokrycia całej doby oraz dostępnej elektrycznej energii dziennej odpowiedniej kategorii. Brak kategorii CWU nie znaczy 0. Dzienna historia Atlantic może podlegać późniejszej korekcie; wskaźniki są przeliczane na nowo zamiast utrwalania fałszywych statystyk.
- **Ważne ograniczenie:** skojarzenie ID112 między interfejsem a ID109/116 z generatora, czynnik ciepła właściwego wody, znaczenie chmurowych przedziałów UTC i pełna energia grzałek/odszraniania nie zostały fabrycznie zweryfikowane. Dlatego wynik pozostaje niskiej pewności, nie jest pomiarem producenta ani pomiarem do rozliczeń. Dla dwóch modułów potrzebne są **obie** opcje: experimental_cross_device_cop i experimental_cop2. Wyniki będą dostępne dopiero po zebraniu pełnej doby.
- [Opis techniczny, warunki jakości i testy COP2](docs/COP2_PLAN_AND_LIMITATIONS_20261027.md).

## v0.5.23 — pojedynczy odczyt historii energii bramki

- Opcjonalne `experimental_api_discovery` przeprowadza teraz **maksymalnie siedem** kontrolowanych odczytów GET zamiast sześciu. Ostatni bada `/magellan/gateways/{gatewayId}/consumptions?periodicity=daily` — trasę wskazaną w niezależnej analizie aplikacji Atlantic iOS. Schemat i zakres danych dla Extensa S Duo XL wymagają weryfikacji na rzeczywistej instalacji. Nie ma zgadywania parametrów po niepowodzeniu.
- ID bramki musi pochodzić bezpośrednio z `gateways[0].id` własnej, uwierzytelnionej odpowiedzi `setupviewv2`; wymagane jest dokładnie jedno, liczbowe ID. Brak lub wiele bramek: **pomijamy test**. Nie stosujemy ID pompy ani numeru seryjnego jako zamiennika.
- Nowy rezultat `results.gateway_daily_minimal` pokazuje status HTTP i maksymalnie 24 rekordy anonimowej struktury `producedQuantity`/zużycia; nieznany format JSON raportuje tylko bezpieczne nazwy pól. `gateway_target` nie ujawnia ID.
- Wstępne dane CO/CWU z API z 26.10.2026: energia elektryczna za 22–26 października 34,63/9,28 kWh, ale `producedQuantity=null` we wszystkich dziennych i miesięcznych okresach. Nie ma jeszcze dowodu, że GET bramki udostępni energię cieplną.
- Nic nie zmienia obliczeń COP, diagnostyki hydraulicznej, lokalnych danych skumulowanych ani dotychczasowego odczytu 9,44. Brak jakichkolwiek komend do pompy i dodatkowych serwerów.
- [Procedura uruchomienia, bezpieczeństwo i szablon diagnostyczny](docs/GATEWAY_API_DISCOVERY_20261027.md).

## v0.5.22 — poprawna interpretacja ostatniej zmiany czujników hydraulicznych

- Zgłoszenie z HA: `nieaktualne_pomiary_hydrauliczne` przy znacznikach ID109 = 594 s, ID116 = 7759 s, ID112 = 594 s, ID57 = 290 s. Rozbieżność timestampów ID109/116 wynosi **7165 s**, ale Atlantic `modificationDate` jest znacznikiem **ostatniej zmiany wartości**, nie pewnym czasem pomiaru. Porównywanie go z innym czujnikiem z limitem 600 sekund dawało nieuzasadnioną blokadę.
- Usunięto wymóg zbliżonych dat zmiany zasilania i powrotu dla **świadomie włączonego eksperymentalnego powiązania obiegów**. Zamiast tego wymagamy zachowania wartości między kolejnymi zaobserwowanymi snapshotami przez **całe** okno COP (12–60 minut), maksymalnej daty ostatniej zmiany hydrauliki do **12 godzin**, poprawnego przepływu/temperatur i dwóch faktycznych skoków energii elektrycznej.
- Dla `ID112` (przepływ) też nie traktujemy 15 min od ostatniej zmiany jako czasu ostatniego pomiaru. W opcji eksperymentalnej dopuszczamy niezmieniony przepływ do 12 h, ale przy zmianie wcześniej starego wskazania w środku okna następuje jego **odrzucenie**. Bez opt-in przepływ starszy niż 15min nadal blokuje COP.
- Nowe atrybuty `rozbieznosc_znacznikow_temperatur_s` i `semantyka_znacznikow` służą do diagnostyki. Wyniki wykorzystujące stare znaczniki pozostają **niskiej pewności** i nigdy nie są prezentowane jako aktualne, zweryfikowane wartości producenta.
- To **nie gwarantuje**, że czujnik rzeczywiście był na nowo zmierzony przez Atlantic. Brak świeżego zwrotnego potwierdzenia uniemożliwia certyfikowany COP. Nie usuwamy poprzedniego, historycznego i potencjalnie błędnego COP 9,44, ani nie mieszamy dodatkowych okresów po restarcie bez zaobserwowania pełnego okna.
- Brak nowych połączeń, endpointów, zapisów do pompy i serwerów pośredniczących.

## v0.5.21 — naprawa pomiaru przy skokowym liczniku: eliminacja fałszywego COP 9,44

- **Powód poprawki:** realny akceptowany przedział z HA zawierał 0,491 kWh szacowanego ciepła i 0,052 kWh poboru ID57 przez 0,1 h (~6 minut), czyli COP 9,44. Pierwotna metoda dla krótkich przedziałów wiązała skok licznika z energią cieplną za arbitralny okres dwóch odczytów, bez obserwacji **dwóch granic** okresu elektrycznego. Nie jest to dowód prawdziwego COP.
- Od teraz **żaden niezakotwiczony 3–6-minutowy przyrost energii nie zostanie zaakceptowany** do COP lub sum. Usunięto automatyczną ścieżkę krótkich przedziałów. Jedyny zapis energii pochodzi z pełnego, ciągle obserwowanego okresu **12–60 minut między dwoma faktycznie zobaczonymi skokami tego samego licznika**. Wymagane co najmniej cztery odcinki hydrauliczne, nie więcej niż 8 minut między odczytami i co najmniej 95% pokrycia.
- Pierwszy skok tylko wyznacza początek; kolejne odczyty bez zmiany nie dopisują energii do akumulatora. Dla okna, którego elektryczny przyrost jest zbyt mały względem szacowanego ciepła, nadal następuje odrzucenie bez obcinania COP do górnego limitu.
- Przy każdej niepewności przepływu, za długim wieku temperatur, odszranianiu o nieznanym stanie, zgłoszonej grzałce, zmianie obiegu albo luce w odczytach okno zostanie odrzucone. Stale timestamp **nie potwierdza rzeczywistej świeżości** pomiaru.
- **Zgodność wsteczna:** historyczne zaakceptowane sumy z 0.5.20 są zachowane, w tym 9,44 CO. Wynik ten jest **niezweryfikowany**, nadal może służyć jako widoczna historyczna wartość zastępcza, nie zostaje skasowany i nie uzyskuje nowej daty. **Nie wolno uważać go za aktualny COP**. Nowe wartości będą pochodzić z poprawionej metodologii; już zapisane sumy z różnych metod nie są automatycznie kalibrowane.
- W razie niewystarczających danych nadal `unknown` w encji chwilowej, a główna encja utrzymuje poprzedni wynik ze wskazaniem pochodzenia.
- Bez serwerów pośredniczących, nowych zapytań, sterowania pompą lub publikowania wyprodukowanego ciepła jako energii zweryfikowanej.

## v0.5.20 — COP nie znika po aktualizacji z 0.5.18

- Naprawa migracji: w 0.5.19 główny `COP Atlantic · szacunkowy` pokazywał `unknown`, nawet jeśli w magazynie istnieją poprawnie zapisane **zaakceptowane energie skumulowane** z wcześniejszej wersji (np. 1 przedział CO, COP=9,44). Wcześniejsze wersje nie zapisywały oddzielnie daty ostatniego pojedynczego przedziału, dlatego nie dało się wyświetlić `ostatni COP`.
- Teraz główna encja wyświetla **COP skumulowany jako wartość zastępczą** *tylko* gdy brak zarejestrowanego ostatniego indywidualnego wyniku, ale istnieją zapisane zaakceptowane przedziały CO/CWU. Nie zakładamy, że suma wielu przedziałów to ostatnia próbka i **nigdy nie wymyślamy daty pomiaru**.
- Atrybuty `zrodlo_wyswietlanego_cop=zastepczy_cop_skumulowany_bez_daty`, `zastepczy_cop_skumulowany=true`, `obieg_wyswietlanego_cop` i `uwaga_daty` otwarcie wyjaśniają pochodzenie wartości. `ostatni_zaakceptowany_cop_utc` i `wiek_ostatniego_wyniku_h` pozostają puste, gdy data rzeczywiście nie jest znana.
- Po otrzymaniu i zaakceptowaniu nowego COP nastąpi **automatyczna zamiana** na ostatni indywidualny wynik z rzeczywistą datą i obiegiem. Oddzielna encja chwilowa nadal pokazuje `unknown` między próbkami.
- Dotychczasowy magazyn sum pozostaje **bez zmian** (brak destrukcyjnych migracji i nowych statystyk HA Energy). Jeżeli nigdy nie było żadnego zaakceptowanego przedziału, pozostaje `unknown`; nie publikujemy fikcyjnego COP.
- Szacunek 9,44 jest podejrzanie wysoki w porównaniu z panelem Atlantic (ok. 2,92 dla CO). Wartość zastępcza służy wygodzie wyświetlania i nie potwierdza faktycznej sprawności.

## v0.5.19 — stała widoczność ostatniego zaakceptowanego COP

- Dotychczasowa encja "COP Atlantic · szacunkowy" zachowuje swój unique_id i wyświetla ostatni zaakceptowany szacunek również w kolejnych odczytach bez wzrostu licznika. Jest to wynik HISTORYCZNY, nie aktualny COP. W atrybutach jest dokładny czas UTC, wiek w godzinach, obieg, metoda, klasa niepewności i informacja o historycznym charakterze.
- Nowa encja "COP Atlantic · aktualna próbka (chwilowy)" wyświetla wynik tylko w momencie nowego zaakceptowanego przedziału i może być unknown podczas postoju.
- Nowe encje "COP Atlantic · ostatni zaakceptowany CO" oraz "COP Atlantic · ostatni zaakceptowany CWU" zachowują oddzielne wartości. Istniejąca encja "ostatni poprawny szacunek (12 h)" zachowuje identyfikator, a etykieta wskazuje teraz wynik historyczny bez 12-godzinnego limitu.
- Ostatnie wartości i znaczniki czasu są zapisywane lokalnie osobno od dotychczasowych sum energii i przywracane po restarcie HA. Brak nowych endpointów sieciowych, zapisów do pompy i statystyk HA Energy.
- Jednorazowa migracja nie rekonstruuje historycznych krótkich wyników z poprzednich wersji: pierwszy utrwalony ostatni COP pojawi się po nowym zaakceptowanym pomiarze w 0.5.19.
- Uwaga: COP 9,44 może być niedokładny; utrwalanie wskazania nie stanowi potwierdzenia poprawności bilansu i nie zmienia diagnostycznego statusu danych.

## v0.5.18 — eksperymentalny COP z obserwowanych okien skokowego licznika

Na podstawie historii HA potwierdzono, że surowy przyrost ID57 występuje **serią skoków rzędu 51/52/74/75 jednostek**, rozdzielonych odczytami 0, często co kilkanaście–kilkadziesiąt minut. Wydłużenie starego limitu 20 minut przez prostą interpolację byłoby niebezpieczne.

- Nowy moduł `cop_window.py` gromadzi **ciągłe krótkie odcinki hydrauliczne** o odstępach 2–8 minut, licząc dla każdego odcinka moc cieplną z rzeczywistych próbek; ani jeden brakujący 3-minutowy odczyt nie jest uzupełniany wstecz.
- Okno zaczyna się **dopiero przy pierwszym faktycznie obserwowanym wzroście** licznika elektrycznego ID57/59 i kończy się **przy kolejnym potwierdzonym wzroście** tego samego licznika oraz obiegu; przed pierwszym skokiem nie liczony jest COP za nieobserwowane zużycie.
- Obsługuje skoki po **20–60 minutach**, pod warunkiem że wszystkie krótkie odcinki łącznie pokrywają co najmniej 95% okresu, nie ma braków odczytów, przełączeń obiegu, resetów licznika ani niezgodności pomiarów.
- Do akumulatora CO/CWU trafia **jedynie kompletny, fizycznie prawdopodobny bilans**. Jeżeli np. skok `51 Wh` nie pasuje do sumy mocy cieplnej z 30 minut (dawałby COP powyżej 10), taki przedział jest **odrzucany**, a nie sztucznie przycinany do 10.
- Bez podwójnego liczenia: dotychczasowa metoda może przyjąć krótkie przedziały do 20 minut; metoda okien obsługuje tylko dłuższe od 20 minut. Dodatkowy atrybut `diagnostyka_okna_energii` pokazuje kompletność i powód odmowy, **bez prywatnych identyfikatorów i wartości energii**.
- Okresowe COP są nadal **diagnostyczne, niecertyfikowane i o niskiej pewności**, a grzałki, stara telemetria, brak pracy pompy lub problem z Wi-Fi mogą uniemożliwić zaakceptowanie okna. Zmiany nie dodają nowego endpointu ani transmisji danych do innych serwerów. Dane starego magazynu HA są zachowane.

## v0.5.17 — naprawa ostatniej zmiany licznika energii

Na rzeczywistej instalacji po 0.5.16 wykryto `nieaktualny_licznik_pradu`, mimo że pozostałe źródła mogą być użyteczne. W Magellan `modificationDate` ID57/59 oznacza **ostatnią zmianę wartości skumulowanego licznika**, nie ostatnie odpytywanie licznika. Licznik w spoczynku może przez długi czas legalnie się nie zmieniać.

- Zamiast blokady przed wstępnym porównaniem, integracja tworzy **baseline z dwóch udanych obserwacji** nawet przy niezmienionym liczniku (ostatnia zmiana do 366 dni wstecz). Stan `punkt_startowy_starego_licznika_czekamy_na_przyrost` i `licznik_bez_przyrostu_ponad_15_minut` **nie podają COP**.
- Po rzeczywistym przyroście ID57/59 wymagany jest **nowy, aktualny (do 15 min) vendor modificationDate**, późniejszy niż ostatnia zmiana z wcześniejszego punktu i nie wcześniejszy niż rozpoczęcie obserwowanego przedziału (tolerancja 60s). Jeżeli metadane nie potwierdzają nowego przyrostu, interwał jest odrzucany: `przyrost_pradu_z_nieaktualnym_znacznikiem` lub `zmiana_pradu_bez_nowego_znacznika`.
- Stary znacznik nie jest używany przy wstępnym porównaniu świeżych temperatur i przepływu. Po zwiększeniu licznika wszystkie cztery kanały znowu podlegają weryfikacji czasowej. Nic nie jest ekstrapolowane na brakujące okresy.
- W `COP Atlantic · status obliczeń` dostępny jest atrybut `diagnostyka_licznika_pradu` (ID57 albo ID59, czas od **ostatniej zmiany** i czy faktycznie był przyrost), bez wartości energii, ID urządzeń, adresów i tokenów.
- **Brak zmiany wartości licznika nie jest błędem ani potwierdzeniem awarii**: może oznaczać brak poboru, wolne aktualizacje chmurowe lub postój pompy. Algorytm nadal wymaga pomiarów hydraulicznych, pewnego obiegu, prawidłowego przyrostu energii i zgodności zabezpieczeń.
- Bez nowych endpointów, zapisów do pompy lub nowych serwerów. COP nadal jest eksperymentalny, nie weryfikowany ze sterownikiem.

## v0.5.16 — naprawa fałszywej blokady COP przez ID8 = 3000

- Na faktycznej pompie Extensa S Duo XL 10 otrzymaliśmy `ID8=3000`, co w poprzedniej wersji wyświetlało błędne **3000 kW** i blokowało COP. Katalog Atlantic dla ID8/9/11 podaje `kW` i maksimum `20`, więc dla takiego surowego odczytu skala/jednostka są **sprzeczne z deklaracją katalogową**; prawdopodobnym, ale NIEpotwierdzonym wyjaśnieniem jest 3000 W (3 kW).
- Sensory ID8/9/11 zachowują swoje `unique_id` i od teraz wyświetlają **wartości surowe bez jednostki**, bez publikowania statystyk. Nowe atrybuty sensorów objaśniają konflikt skali i brak potwierdzenia aktywności grzałki.
- Nowa diagnostyka `heater_evidence.py` w atrybucie `diagnostyka_grzalek` czujnika `COP Atlantic · status obliczeń`: stan odczytu ID8/9/11 i stan binarny ID64, bez numerów urządzeń lub tajnych danych.
- ID64 jawnie raportujący aktywną grzałkę CWU **nadal blokuje COP**. Dodatni odczyt ID8/9/11 w udokumentowanym zakresie do 20 (w jednostkach katalogowych) **nadal blokuje eksperymentalny COP**. Wartości wyraźnie sprzeczne ze skalą katalogową, takie jak `3000`, są oznaczane jako **niezweryfikowane**, zamiast fałszywie potwierdzać pracę grzałki. Taki szacunek otrzymuje **niską pewność** i nie jest fabrycznym COP.
- Poprawiono kolejność diagnostyki: `Delta T` i `Moc cieplna szacunkowa` będą obliczane przed sprawdzeniem grzałek, o ile spełniają pozostałe wymogi.
- Bez nowych HTTP, bez zapisów do pompy i bez serwerów pośredniczących. Weryfikacja poboru grzałki po stronie pompy/elektryki pozostaje zalecana; 3000 samo w sobie nie dowodzi ani włączenia, ani wyłączenia.

## v0.5.15 — przebudowa eksperymentalnego COP na bazie obserwowanych snapshotów

- Obliczenia COP w uruchamianej integracji przełączono na `cop_snapshot.py`. Stary `cop_hydraulic.py` pozostaje wyłącznie jako moduł historyczny i nie jest używany przez koordynator.
- Energia cieplna jest całkowana z `ID112 [l/min]` × (`ID109−ID116 [K]`) w krótkich przedziałach kolejnych udanych odczytów HA; energia elektryczna pochodzi z przyrostu `ID57` albo `ID59`, z zastosowaniem katalogowego kroku **0.001 kWh** na jednostkę surową. Mapa skali konkretnej pompy wymaga porównania z panelem.
- `modificationDate` jest datą **ostatniej zmiany wartości**, dlatego przy świadomie włączonej opcji `experimental_cross_device_cop` można eksperymentalnie użyć niezmienionych temperatur z ostatnią zmianą starszą niż 15 minut (maks. **12 h**), tylko jeśli mamy aktualny przepływ, rosnący licznik energii oraz zgodną parę odczytów. Snapshot nie dowodzi świeżości temperatury u źródła.
- Stare znaczniki temperatur, małe `ΔT 0.75–1.5K` lub nieznany stan sprężarki oznaczają **niski poziom pewności**. Brak przyrostu energii nie tworzy COP. Odrzucane są: reset licznika, stary przepływ/prąd, niejasne źródła, zmiana obiegu, grzałka CWU lub wykryta moc grzałek pomocniczych ID8/9/11, sprężarka jawnie wyłączona, fizycznie niespójna moc/COP i długie przerwy.
- Nie ma nowych endpointów ani serwerów pośredniczących, zapisów do pompy i statystyk HA Energy. Sumy dotyczą **tylko zaakceptowanych przedziałów**, nie całej doby/miesiąca. Wcześniejsze sumy lokalne zostają zachowane.
- Nowe atrybuty statusu: `pewnosc_szacunku`, `roznica_temperatur_k`, `metoda_probkowania` i `skala_pradu_nadal_do_weryfikacji`.
- Szczegóły: [algorytm COP snapshot v0.5.15](docs/COP_SNAPSHOT_V0_5_15.md).

## v0.5.14 — naprawa badania historii miesięcznej urządzenia

- W sondzie `Historia energii Atlantic · odczyt urządzenia` zmieniono kolejność na **monthly przed daily**: błąd HTTP 400/500 w historii dziennej nie pomija już historii miesięcznej, czyli jedynego możliwego kandydata dla COP miesięcznego.
- Atrybuty `monthly.http_status` i `daily.http_status` pokazują wyłącznie numeryczne kody HTTP (np. 200, 400, 500), bez URL, seriali, tokenów, surowych odpowiedzi lub prywatnych wartości energii.
- Autoryzacja 401 i limit 429 nadal natychmiast przerywają sondę bez następnych żądań; 403/404/405 są raportowane dla obu metod, bez błędnego pominięcia próbki monthly.
- To **poprawka diagnostyczna**, jeszcze nie odblokowanie COP. Historia całej instalacji w październiku 2026 nie zgłasza dodatniej `producedQuantity`; bez potwierdzonego źródła wytworzonego ciepła nowy licznik COP nie może zostać podany jako wiarygodny.

## v0.5.13 — badanie źródła wyprodukowanego ciepła w API

- Diagnostyczny test `producedQuantity` dla miesięcznych historii pobieranych już z oficjalnej chmury, **bez dodatkowych żądań API**. W istniejących dwóch sensorach `Historia energii Atlantic · miesięczna kontrola` oraz `Historia energii Atlantic · odczyt urządzenia` atrybut `audyt_surowych_kandydatow` pokazuje **tylko anonimowe i ograniczone liczbowo kandydatury** produkcji z ostatnich dwóch miesięcy wraz z kodami `type/unit/category/mode`, **bez prywatnych liczb energii**. Przy braku produkcji stan `brak_dodatnich_producedquantity`.
- `producedQuantity` **nie jest automatycznie uznawane za ciepło**: liczby pozostają surowe, nie trafiają do COP, nie są zapisywane historycznie i nie są sumowane między endpointami. Brak identyfikatorów urządzeń, numerów seryjnych, tokenów, kosztów i dokładnych dat w diagnostyce.
- Cel: porównać wykryte kandydatury z ekranem sterownika Atlantic, w którym energia wyprodukowana dla CO i CWU jest pokazana osobno. Wewnętrzne ID57/59 według publicznego katalogu to **energia elektryczna** odpowiednio CO i CWU, a `ID164` to **flagi wsparcia funkcji**, nie liczniki ciepła.
- Kryteria walidacji i źródła: [audyt API Magellan 25.10.2026](docs/ATLANTIC_THERMAL_API_RESEARCH_20261025.md).
- Ta aktualizacja **nie odblokowuje samoczynnie COP** i nie zmienia istniejącego szacunkowego algorytmu. Jeśli historia nie zawiera wartości `producedQuantity`, należy poszukiwać ciepła w innym źródle.

## v0.5.12 — skumulowany COP z poprawnych przedziałów CO/CWU

- Nowe **trzy encje diagnostyczne**: `COP Atlantic · skumulowany (zaakceptowane próbki)`, `COP Atlantic · skumulowany CO (zaakceptowane próbki)`, `COP Atlantic · skumulowany CWU (zaakceptowane próbki)`. Nie usuwamy ani nie zmieniamy istniejących `unique_id`.
- **Wzór: Σ(ciepło szacowane, kWh) / Σ(prąd szacowany, kWh)**. Nie sumujemy średnich lub chwilowych COP. Sumujemy tylko poprawne odcinki 2–20 minut z nowym przyrostem ID57/59, dodatnim ΔT, zsynchronizowaną hydrauliką i prawidłowym stosunkiem energii. Osobne sumy dla CO i CWU nie dublują tych samych interwałów.
- Wynik nie znika podczas postoju ani chwilowego błędu chmury. Zlicza tylko **zaakceptowane interwały**, a nie pełen okres kalendarzowy: atrybuty pokazują liczby próbek, łączny pokryty czas oraz szacowane kWh ciepła i prądu.
- Sumy zapisywane są **lokalnie w HA** poprzez `homeassistant.helpers.storage.Store`, odseparowane na każdą konfigurację konta; bez loginów, identyfikatorów urządzeń, tokenów, timestampów, zewnętrznych serwerów czy wysyłania danych. Zapis z opóźnieniem 60s plus flush przy normalnym przeładowaniu/wyłączeniu integracji.
- Po instalacji zaczynamy od **braku wartości (unknown)**, bo nie da się wiarygodnie odtworzyć ciepła wytworzonego przed aktualizacją. COP pojawi się dopiero po **pierwszym zaakceptowanym przedziale grzania** i będzie stopniowo bardziej reprezentatywny w miarę poprawnych próbek.
- Ważne: prąd i moc hydrauliczna są estymacjami na bazie surowych pól Atlantic; to **nie jest SCOP**, sezonowy COP ani pomiar certyfikowany. Nie publikujemy długoterminowych statystyk HA Energy, bo pokrycie i skala źródeł nie są potwierdzone.
- Poprawiono także ukryty błąd struktury danych bazowych występujący po zmianie trybu CO/CWU albo resecie licznika.

## v0.5.11 — COP eksperymentalny przy stabilnych temperaturach w Atlantic

- Dane terenowe pompy: przepływ ostatnio zmieniony ~179 s temu, temperatura zasilania 4360 s, powrotu 4658 s, energia elektryczna 1075 s. W v0.5.10 **każdy** znacznik `modificationDate` musiał mieć mniej niż 900 s, co zawsze blokowało próbę COP dla stabilnych temperatur.
- W **świadomie włączonym trybie eksperymentalnym** oraz wyłącznie dla jedynej pary modułów dopuszczamy temperatury ze znacznikiem zmiany do **2 h**. To nie jest potwierdzenie ich aktualności; wynik ma specjalny status `szacunek_eksperymentalny_stare_temperatury` oraz atrybut `wiarygodnosc_temperatur: stare_znaczniki_zmian_niska_pewnosc`.
- Dodatkowe zabezpieczenia: dwa kolejne skuteczne odczyty ze **stałymi wartościami temperatur**, znaczniki obu temperatur oddalone maksymalnie o 600 s; **przepływ i licznik energii nadal muszą być świeże (≤ 15 min)** i między sobą zsynchronizowane (≤ 600 s), a licznik musi wykazać realny przyrost w przedziale 2–20 min. Tylko dodatnia różnica temperatur ≥ 1°C może wywołać COP. Dalsze warunki i limity jak wcześniej.
- Przy nieaktualnym liczniku, braku wzrostu energii albo niegrzejącej pompie wynik nadal będzie **unknown**. Nie fałszujemy czasu producenta i nie prezentujemy starego COP jako bieżącego.
- Bez nowych endpointów, danych osobowych, sterowania pompą ani pośredników. Nie jest to certyfikowany pomiar COP, miesięczny COP, ani wielkość do rozliczeń energii.
- To **eksperyment oparty na założeniu**, że wielokrotnie odczytana ta sama temperatura mimo starego `modificationDate` może oznaczać stabilny stan pracy, a nie zerwaną telemetrię. Testy na sprzęcie nadal konieczne.

## v0.5.10 — szacunkowy COP po zgodzie na połączenie dwóch modułów

- Rozwiązanie problemu `niepotwierdzone_powiazanie_obiegu` z pompą **Alféa Extensa S Duo XL 10 WiFi**: chmura Atlantic potrafi umieścić `57/59/91/112` (energia, obieg, przepływ) na logicznym interfejsie, a `109/116` (temperatury) na module generatora.
- **Ustawienie użytkownika — domyślnie WYŁĄCZONE.** Po przeglądzie konfiguracji instalacji w Home Assistant otwórz **Ustawienia → Urządzenia i usługi → Atlantic CozyTouch → Konfiguruj/Opcje**, zaznacz **„Włącz eksperymentalny COP między jedyną parą modułów”**, zapisz. Integracja przeładuje się automatycznie. Jeżeli nie ma takiej opcji, sprawdź, czy zainstalowana jest wersja 0.5.10 i ponownie uruchom HA.
- Łączenie następuje tylko, gdy istnieje **dokładnie jeden** moduł interfejsu `57/59/91/112` oraz **dokładnie jeden** generator `109/116`. Jest to założenie użytkownika, **nie dowód** fizycznego połączenia obiegów. Pozostałe zabezpieczenia danych pozostają aktywne; brak wyprodukowanej energii cieplnej w API wciąż uniemożliwia prawdziwy COP miesięczny.
- Poprawiono drugą blokadę: `modificationDate` **ID91 oznacza zmianę trybu**, więc nawet stary znacznik czasu jest dopuszczalny, gdy tryb pozostaje niezmienny. Zmiana znacznika w trakcie liczenia resetuje podstawę porównania.
- Wymagany jest **aktywny przepływ i różnica temperatur zasilanie–powrót ≥1°C**, dopuszczalne znaczniki czasu hydrauliki i przyrost energii CO/CWU w okresie 2–20 min. Wynik `COP Atlantic · szacunkowy` to wyłącznie eksperyment na danych z chmury — nie wynik producenta i nie licznik do rozliczeń.
- Jeśli pompa aktualnie nie grzeje (np. widoczne ~25,8°C i ~25,7°C, ΔT=0,1 K), wynik bieżącego COP jest **nieznany**, a status pokazuje `brak_aktywnego_grzania`. Nie podstawiamy wartości `0`.
- Nowy sensor **„COP Atlantic · ostatni poprawny szacunek (12 h)”** zatrzymuje tylko wynik wyliczony wcześniej w ciągu ostatnich 12h; nie jest chwilowym COP ani zapisem długoterminowym i może być nieznany po restarcie.
- Atrybuty statusu COP zawierają rodzaj topologii i bezpieczny wiek próbek `wiek_probek_s` bez surowych dat ani ID urządzeń. Pozwalają rozpoznać blokady `niespojne_czasy_probek`, `brak_przeplywu...`, `oczekiwanie_na_przyrost_energii`.
- Bez nowych endpointów, serwerów pośredniczących, komend pompy, statystyk energetycznych i naruszenia istniejących unique_id. [Instrukcja odbioru COP 0.5.10](docs/COP_ESTIMATOR_0_5_10.md).

## v0.5.9 — zbiorczy audyt źródeł produkcji energii dla COP

- Nowy sensor diagnostyczny `COP Atlantic · audyt źródeł ciepła`, automatycznie analizujący cztery już odczytywane ścieżki `setup/day`, `setup/month`, `device/day`, `device/month`.
- Stan rozróżnia: brak danych, niedostępne API, niekompletne metadane, brak potwierdzonego ciepła oraz **niezweryfikowanego kandydata**, gdy dostępna seria zawiera dodatnie `producedQuantity`.
- Zanonimizowane, ograniczone liczby rekordów na źródło, hipoteza flag 256/1024 (nie są kWh), kod kolejnego kroku. Brak tokenów, identyfikatorów urządzeń, surowych wartości energii oraz informacji o użytkowniku.
- `energia_cieplna_potwierdzona: false` i `cop_okresowy_gotowy: false` do czasu potwierdzenia rodzaju energii, okresu i skali na prawdziwej pompie. **Nie tworzymy niezweryfikowanego COP miesięcznego.**
- Bez nowych endpointów, usług zapisu ani serwerów pośredniczących. Zachowane stare encje i `unique_id`.
- W instrukcji uwzględniono uwagę Atlantic, że na części Alféa A.I. wyświetlane zużycie może być **oszacowaniem**, a nie bezpośrednim pomiarem.
- [Odbiór testowy 0.5.9](docs/COP_SOURCE_AUDIT_0_5_9.md). Prace oparto na 0.5.8, które nadal wymaga przeglądu i testu na urządzeniu.

## v0.5.8 — bezpieczny COP i zgodność czasowa pomiarów

- **Korekta topologii:** COP hydrauliczny nie łączy ID112 (przepływ) z ID109/116 (zasilanie/powrót) z różnych urządzeń logicznych bez potwierdzonego mapowania. Zwraca `niepotwierdzone_powiazanie_obiegu` i `unknown`, zamiast pozornie dokładnego wyniku. Na tej Extensa czujniki mogą występować na różnych logicznych urządzeniach; do odblokowania pomiaru niezbędna będzie niezależna walidacja powiązania obiegów.
- Weryfikacja świeżości **ID91,112,109,116 oraz ID57/59** używa znaczników `modificationDate` producenta. Maksymalna różnica czasów w jednej próbce: **180 s**; luka w przyrostach energii musi mieścić się w przedziale 2–20 min.
- Szacunkowy COP hydrauliczny wykorzystuje średnią z mocy cieplnej na początku i na końcu przedziału (metoda trapezów), zamiast tylko ostatniej próbki. To nadal **eksperymentalny szacunek**, nie pomiar ciepła i nie SCOP.
- Na błędzie odczytu chmury resetujemy podstawę porównawczą COP; przerwa sieciowa nie może stworzyć fałszywego przyrostu.
- Diagnostyka miesięczna rozpoznaje liczbę rekordów, w których **pobrana energia** i **nieokreślona produkcja** występują w tej samej odpowiedzi. **Nie oznacza to potwierdzenia energii cieplnej ani zgodności czasu/jednostek**; nie eksportujemy wartości kWh, kosztów, tokenów ani ID.
- W statusie gotowości COP atrybut `rekordy_produkcji_ciepla` ma teraz wartość `null` (brak dowodu), a liczby potencjalnych rekordów otrzymały jednoznaczną nazwę `rekordy_produkcji_nieokreslonej`. Dotychczasowe `unique_id` encji pozostają bez zmian.
- Brak nowych endpointów, pośredników, komend sterowania, klas HA Energy i syntetycznego miesięcznego COP.
- [Plan weryfikacji 0.5.8](docs/COP_VALIDATION_0_5_8.md).

## v0.5.7 — ostrożne użycie bitów 256/1024 z ID 164

- **ID 164 = 1298** rozkłada się na 2 (pobór prądu CO),
  16 (pobór prądu CWU), **256 (hipoteza obsługi produkcji ciepła CO)** i
  **1024 (hipoteza obsługi produkcji ciepła CWU)**. Dwa ostatnie znaczenia
  pochodzą z [niezależnego mapowania CozyTouch](https://github.com/gduteil/cozytouch/blob/main/custom_components/cozytouch/capability_table.py),
  a nie z oficjalnego katalogu Atlantic Magellan v1.9.
- Nowy sensor diagnostyczny **Możliwości produkcji ciepła · ID 164 (hipoteza)**:
  `hipoteza_co_i_cwu`, `hipoteza_co`, `hipoteza_cwu`, `brak_flag_produkcji`
  lub przy niejednoznacznych danych status błędu, z czytelnymi atrybutami.
- Odczyt jest ograniczony do **jednej** pompy rozpoznanej po ID 91 i 112;
  nie łączymy masek pochodzących z innych urządzeń konta.
- Dotychczasowe diagnostyczne odczyty historii energii i gotowości COP
  zyskują te same informacje o flagach. **Nie powstają żadne zmyślone kWh
  wyprodukowanego ciepła ani liczbowy COP z samej maski.**
- Bez nowych tras HTTP, przechowywania danych prywatnych, zmian pompy
  ani ingerencji w HA Energy Dashboard.

## v0.5.6 — audyt katalogu producenta i bezpieczny test historii urządzenia

- **Krytyczna korekta:** ID **44, 45, 46** oznaczają *zużycie gazu*
  według katalogu Atlantic, a nie energię elektryczną. Zachowujemy
  `unique_id`, ale wyłączamy błędną konwersję /1000, jednostki i
  statystyki HA Energy; historyczny Recorder nie jest modyfikowany.
- ID **57/59** to w katalogu elektryczność CO/CWU, co wspierają zdjęcia
  sterownika. Skalowanie surowego odczytu /1000 pozostaje hipotezą
  diagnostyczną aż do potwierdzenia okresu i resetu licznika.
- ID **164** to maska możliwości pomiaru **zużycia**. Jej bity 256 i
  1024 są nieudokumentowane w katalogu, więc nie oznaczamy ich
  dłużej automatycznie jako „pomiar produkcji ciepła”.
- Nowy tylko-GET, bezpiecznie ograniczony do jednej pompy z konta:
  `/magellan/devices/{deviceId}/consumptions?periodicity=daily|monthly`
  (najwyżej co 6 godzin). Sprawdza wyłącznie anonimową strukturę
  odpowiedzi w encji **Historia energii Atlantic · odczyt urządzenia**.
  Nie pobiera ani nie publikuje kont, tokenów, kosztów ani wartości
  energetycznych do diagnostyki; brak serwerów pośredniczących i
  komend sterujących.
- Dane wyprodukowanego **ciepła** nadal nie są potwierdzone w
  publicznym katalogu ani dotychczasowej historii chmury. Żadnego
  sztucznie wyliczanego miesięcznego COP.
- [Raport źródeł, testu i ograniczeń](docs/ATLANTIC_API_AUDIT_0_5_6.md).

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
| 44, 45, 46 | surowe wskazania zużycia **gazu** CO, CWU i łącznego; bez statystyk i konwersji |
| 100 | ciśnienie wody |
| 109 | temperatura wody obiegu |
| 111 | temperatura CWU |
| 117, 118 | temperatura pokojowa stref |
| 119 | temperatura zewnętrzna |
| 6, 150, 180 | diagnostyczne kody błędów |

Uwaga: samo istnienie mapowania nie oznacza dostępności danej wielkości dla Alféa Extensa S Duo XL 10. Do potwierdzenia potrzebna jest próba odczytu rzeczywistego urządzenia. **Rzeczywisty COP okresowy wymaga wiarygodnego odczytu wytworzonego ciepła i pobranej energii elektrycznej z tego samego okresu. ID 44–46 oznaczają gaz, a nie prąd.**

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
