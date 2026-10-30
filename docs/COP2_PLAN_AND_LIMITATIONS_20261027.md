# COP2 0.5.25 — alternatywny szacunek sprawności (bez modyfikacji COP1)

## Uzupełnienie 0.5.26 — energia cieplna jako osobne sensory

CO, CWU i suma są publikowane jako diagnostyczne szacunki kWh dopiero po
osiągnięciu 95% pokrycia zakończonej doby i 100% pokrycia segmentami z jawnie
potwierdzoną relacją topologiczną modułów (`masterDeviceId` albo wspólny moduł).
Braków nie ekstrapoluje się. Encje nie mają `device_class` ani `state_class` i
nie są licznikiem producenta ani źródłem dla HA Energy. Osobny sensor jakości
wyjaśnia blokadę: pokrycie, topologia, liczba segmentów i nieznany stan sprężarki.

## Zadanie
Zbudować niezależny od `cop_snapshot.py` rejestr telemetrii i kalkulator COP2. Dotychczasowy COP1 opiera się na przypisaniu przyrostów raw 57/59 do hydrauliki między snapshotami, ale synchronizacja chmurowych skoków z fizyczną energią nie jest dowiedziona. **COP2 celowo korzysta z innego mianownika**: zużycia CO/CWU z historii dziennej Atlantic w `energy_daily.py`.

API Extensa S Duo XL 10 potwierdziło `producedQuantity=null` w historii instalacji i bramki, mimo maski ID164=1298 deklarującej funkcjonalność raportowania energii cieplnej. COP2 **nie udaje brakującego fabrycznego ciepłomierza**.

## Co realizuje ta wersja
- `experimental_cop2` — opcja w HA, domyślnie OFF, niezależna od `experimental_api_discovery` i od COP1.
- Rejestr 14 dni, maks. 10 080 próbek, w oddzielnym pliku HA `.storage`; zero nowych HTTP GET. Debounce 30 s i co około 15 min oraz flush przy unload HA.
- Numer / ID urządzenia, hasło, serial, token, adres, nazwa pokojowa, ścieżki HTTP **nie są zapisywane** w próbkach.
- Wykorzystane pola: HA observation time, nominalny tryb 91, raw CO/CWU 57/59, flow 112 z interfejsu, generator feed/return 109/116, możliwy stan sprężarki 51 i grzałki 64, daty zmian wartości dla wskazanych capability. Wartości ID 8/9/11 **nie są** rzekomą mocą grzałki.
- Powiązanie oddzielnych modułów tylko przy unikatowej parze oraz **dodatkowym włączeniu** istniejącej opcji `experimental_cross_device_cop` (nie jest to dowód wspólnego obiegu).
- Licznik COP2 przelicza zakończoną **dobę UTC** na podstawie przyjętej hipotezy dat `date` w dziennej historii Magellan. Zobacz poniżej ryzyko strefy czasu.

## Formuła
`P[kW] = przepływ[l/min] · (T_zasilania - T_powrotu)[K] · 4.186 / 60`.

Dla pary odczytów 120–480 s o tym samym trybie (CO albo CWU): trapez `Q[kWh] += (P_a+P_b)/2 · dt[h]`. Dla par przecinających północ UTC rozdziela się udział czasu między doby. Zmiana trybu, grzałka aktywna, brak dat zmiany hydrauliki, nieprawidłowe liczby lub luka >480 s: odcinek jest **odrzucony**, a nie szacowany z ostatniej wartości. Stary `modificationDate` >12h na którymkolwiek z ID112/109/116: odrzucony; mniej niż 12h **nie dowodzi** świeżości fizycznej próbki.

Jeżeli sprężarka jest potwierdzona jako OFF na obu końcach, odcinek wnosi 0 ciepła; stan nieznany obniża wiarygodność i jest raportowany. Dopuszczona ujemna moc podczas np. odszraniania może obniżyć Q; nielogicznych bilansów nie zmienia się przez sztuczne ograniczanie COP.

COP2_CO = Q_CO_doba / E_CO_doba; COP2_CWU = Q_CWU_doba / E_CWU_doba; COP2_total = (Q_CO+Q_CWU)/(E_CO+E_CWU), ale tylko gdy oba składniki elektryczne są obecne i >0. Brak rekordu ≠ energia zero.

**Próg publikacji eksperymentalnego wskaźnika od 0.5.25:** pokrycie odcinkami hydrauliki **≥80% z 86 400 s** (mierzonym niezaokrąglonymi sekundami), minimum jeden odcinek; dla **80–<95%** status `szacunek_niepelna_doba_niska_pewnosc` i ostrzeżenie o różnicy okresów. Wynik dzieli *tylko zaobserwowane* Q przez *pełnodobowe* E — **nie jest COP liczonym dla tego samego przedziału**, nie stosować go do oceny sprawności urządzenia. Nie przeszacowujemy Q do 100%. Dane dzienne mogą zostać skorygowane przez chmurę, dlatego wynik jest przeliczany na każdym cyklu. Ratio [0, 12] jako filtr liczbowej nieprawdopodobności, nie „clamp”. Ujemna energia cieplna całej doby => brak COP2.

## Istotne granice wiarygodności
- Nie zweryfikowano fizycznie, że 112 i 109/116 obserwują ten sam obieg; przy trybie CWU przepływ/ΔT może mieć inne znaczenie. Numer 91 odzwierciedla tryb raportowany, nie potwierdzony stan hydraulicznego zaworu.
- Woda `4.186` nie koryguje glikolu, temperaturowej zależności ciepła właściwego czy błędu pomiarowego.
- `modificationDate` to **czas ostatniej zmiany**, nie czas pomiaru. Powtarzanie tej samej wartości w kolejnych odpowiedziach setup NIE jest dowodem nowego fizycznego pomiaru. Pokrycie ≥80% oznacza pokrycie *obserwacji API*, nie kalibrowany pomiar.
- Do aktywnej diagnostyki stanów sprężarki i grzałek może nie być pełnych danych. Wyłączenie brakujących okresów może tworzyć systematyczne błędy i nie jest certyfikowaną metodą SCOP.
- Dzienny bucket w historii Atlantic jest mapowany na datę **UTC** z epoch; granica termodynamicznego dnia i lokalnej doby operatora/Atlantica nie została potwierdzona. COP2 może porównywać różne fizyczne okresy (zwłaszcza w Polsce). **Nie publikować jako sprawność rzeczywistą bez walidacji czasowej panel/API.**
- Dane dostępne dopiero po zebraniu pełnej doby od uruchomienia logowania, nie wcześniej; po restarcie pamięć jest przywracana, ale luki w czasie restartu nie są uzupełniane.
- Brak współczynnika korekcji grzałek, granic odszraniania i zgodności bilansu elektrycznego. Wynik oznaczony `szacunek_niska_pewnosc` lub `szacunek_niepelna_doba_niska_pewnosc` **nawet gdy liczbowo wygląda realistycznie**.
- COP1 i poprzedni akumulator (np. 9,44) pozostają rozdzielone. COP2 nie trafia do klasy ENERGY ani statystyk HA, także nie jest wprowadzany do osobnego `total_increasing`.
- Plik .storage z samymi pomiarami może być poufną informacją o nawykach mieszkańców; obowiązują zasady ochrony backupów HA. Wyłączenie opcji zatrzymuje zapisy, ale nie usuwa historycznego pliku lokalnego.

## Widoczne encje i atrybuty
- `COP2 Atlantic · diagnostyka`: status `wylaczone | niewystarczajace_pokrycie | brak_pelnej_energii_elektrycznej | nieprawidlowy_bilans_lub_licznik | szacunek_niepelna_doba_niska_pewnosc | szacunek_niska_pewnosc`, `samples`, `coverage_pct`, `day_utc`, `unknown_compressor_pct`, ilość segmentów, `last_rejection`, ostatni i pierwszy timestamp, Q co/cwu i E co/cwu z tej doby (tylko dla obliczeń o pełnym pokryciu).
- `COP2 Atlantic · CO (eksperymentalny)`, `COP2 Atlantic · CWU (eksperymentalny)`, `COP2 Atlantic · łączny (eksperymentalny)`: liczba lub `unknown`, `method`, data i status. Żadna nie ma deklaracji `state_class` ani klasy ENERGY.

## Testy i dopuszczenie do użytkowania
- Czysty Python, offline: 80% progu akceptacji, 79,79% odrzucenia, odrębny status 80–95% oraz ponad 95% coverage; duża luka; zmiana CO/CWU; niewiarygodne timestampy; grzałka ON, compressor OFF/unknown; missing electricity; korekta historyczna; ujemny bilans; izolacja identyfikatorów; restore; limit retencji; brak splicing po restarcie.
- CI: `python -m unittest discover -s tests -v`, dwa oficjalne kontenery HA 2026.10.2 i 2026.10.4, rzeczywista rejestracja encji w smoke test.
- Po wdrożeniu: 2–7 dni obserwacji, diagnostyczne atrybuty COP2 i porównanie z fabrycznym licznikiem Q_CO/Q_CWU z panelu na wspólnych okresach. Nie ma „zaufanego COP2” bez niezależnej walidacji.

## Uruchomienie HA
1. Wykonaj backup.
2. Zaktualizuj do 0.5.25, restart HA.
3. Ustawienia → Urządzenia i usługi → Atlantic CozyTouch → Konfiguruj / Opcje.
4. Włącz **COP2 i lokalny rejestr telemetrii**.
5. Jeśli generator i interfejs to dwie części jednego urządzenia, włącz także **eksperymentalne powiązanie modułów**.
6. Wyłącz już zakończone badanie API, aby nie powielać sond badawczych.
7. W Narzędziach deweloperskich → Stany obserwuj `COP2 Atlantic · diagnostyka`. `niewystarczajace_pokrycie` pierwszego dnia jest **prawidłowe**.
8. Gdy będzie co najmniej jedna pełna doba, sprawdź COP2, coverage i `unknown_compressor_pct`. Nie porównuj COP1 vs COP2 bez wspólnego przedziału.

Takie wdrożenie nie zmienia sterowania pompą ani ustawień regulatora.
