# Atlantic-CozyTouch 0.5.9 — anonimowy audyt źródeł COP

## Cel
Główną przeszkodą do automatycznego miesięcznego COP nie jest wzór, lecz
brak potwierdzonej, mierzonej produkcji ciepła w kWh dla tego samego okresu,
co energia pobrana przez pompę. Panel serwisowy może pokazywać dane, które
nie są publikowane przez CozyTouch API.

> **Uwaga o metodzie pomiaru:** Atlantic informuje, że w części rodziny
> Alféa A.I. prezentowane zużycie energii jest szacowane na podstawie
> konfiguracji mocy urządzenia i grzałek, a nie bezpośredniego licznika.
> Źródło: https://www.atlantic.fr/aide/pompe-a-chaleur-air-eau/fonctionnement-utilisation/comment-visualiser-mes-consommations-d-energie-sur-ma-pompe-a-chaleur
> Nie wykazano, że ten sam algorytm i dokładność dotyczą konkretnej
> Extensa S Duo XL 10. Wyświetlacz nie jest wzorcem pomiaru rozliczeniowego.

## Co zostało dodane
Nowa encja diagnostyczna **COP Atlantic · audyt źródeł ciepła** ma
stabilny unique_id kończący się `_thermal_evidence`. Nie dodaje żadnych
zapytania HTTP ani nowych uprawnień. Odczytuje istniejące, zanonimizowane
podsumowania czterech odpowiedzi:
- Historia instalacji / dzienna
- Historia instalacji / miesięczna
- Historia jednej pompy / dzienna
- Historia jednej pompy / miesięczna

Stan encji może być:
- `oczekiwanie_na_dane` — jeszcze nie sprawdzono żadnego źródła
- `zrodla_niedostepne` — znane błędy/odmowy, brak udanego odczytu
- `niekompletne_metadane` — odpowiedź ma niekompletną diagnostykę
- `brak_potwierdzonego_ciepla` — historie dostępne, bez liczbowych kandydatów
- `kandydat_do_weryfikacji` — przynajmniej jeden dostępny odczyt
  zgłosił dodatnie `producedQuantity`; to **nie** pomiar ciepła

Atrybut `zrodla` pokazuje wyłącznie nazwy czterech źródeł, bezpieczne
statusy i liczby rekordów. Pozostałe atrybuty opisują hipotezę flag 256/1024
dla CO/CWU, liczbę miesięcznych par pobór/produkcja (jeśli dostępne),
status braku weryfikacji oraz kod kolejnego kroku diagnostycznego.

**Krytyczne:** Wszystkie stany mają
`energia_cieplna_potwierdzona: false` i `cop_okresowy_gotowy: false`.
Stan kandydat nie potwierdza jednostek, typu energii, obiegu, daty ani
prawdziwej energii oddanej do domu. Odczyt API może opisywać wyprodukowaną
energię elektryczną. Nie należy sumować liczników rekordów pochodzących
z różnych endpointów — mogą dotyczyć tych samych okresów.

## Jak sprawdzić na pompie
1. Wykonaj backup HA. Wersja 0.5.9 jest PR-em zależnym od nierozstrzygniętego
   PR 0.5.8, a **nie** wydaniem na `main`.
2. Po instalacji testowej wejdź w **Narzędzia deweloperskie → Stany**.
   Wyszukaj encję o nazwie `COP Atlantic · audyt źródeł ciepła`.
3. Zapisz jej stan oraz atrybuty `zrodla`, `kolejny_krok` i
   `miesieczne_pary_pobor_produkcja_nieokreslona`.
   Nie podawaj loginów, haseł, tokenów, `deviceId`, ID instalacji,
   numerów seryjnych ani surowych odpowiedzi HTTP.
4. Sprawdź także `COP Atlantic · status obliczeń` i
   `Historia energii Atlantic · miesięczna kontrola`.
   Przy unikalnych urządzeniach logicznych dla ID112 i ID109/116
   oczekiwany brak COP hydraulicznego w v0.5.8.
5. Porównaj z wyświetlaczem Atlantic tylko wartości za **ten sam**
   okres i obieg. Sprawdź, czy dane producenta są pomiarem,
   czy estymacją.

## Warunki dopuszczenia automatycznego COP
- Udokumentowane `kWh` **wyprodukowanego ciepła** dla CO i CWU;
- spójny okres i ten sam obieg oraz wykluczenie podwójnego liczenia;
- zweryfikowany licznik poboru i jego skala; znana metoda
  obliczania wartości producenta, w tym praca grzałek;
- testy na urządzeniu oraz brak sztucznych odczytów.

## Zakres bezpieczeństwa i testów
Warstwa HTTP identyczna jak w 0.5.8; brak serwerów pośredniczących,
zapisu do pompy i statystyk HA Energy. Pure parser przepuszcza jedynie
białą listę statusów, bounded counts i wartości logiczne flag.
Automatyczne testy `python -m unittest discover -s tests -v`,
`compileall` i HA 2026.10.2 smoke; testowanie prawdziwej
pompy wymaga osobnej obserwacji w HA.
