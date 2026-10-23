# Audyt API Atlantic: historia energii — v0.4.3 (read-only)

## Cel i zakres

Ta wersja jest **diagnostyczna**, bez automatycznych liczników CO/CWU w kWh,
bez obliczania COP i bez ingerencji w istniejące encje czy Recorder.
Nie uruchamia nowego endpointu: wykorzystuje już włączone przez v0.4.2
`GET /magellan/setups/{setupId}/consumptions?periodicity=daily` odpytywane
najwyżej raz na 15 minut. Nie dodaje komend zapisu.

## Źródła, status dowodów i ograniczenia

1. **Potwierdzony dostęp na konkretnej instalacji** — raport v0.4.2
   z Atlantic Alféa Extensa S Duo XL 10: stan `dostepna`, **2 serie**,
   1 typ, 1 jednostka, 4 okresy z liczbowym `consumedQuantity`,
   0 okresów z liczbowym `producedQuantity`; ID 164 = 1298.
   Są to liczby rekordów, a nie wartości kWh ani liczby dni.
2. **Zewnętrznie zaobserwowany schemat**:
   [gduteil/cozytouch: consumption.py](https://github.com/gduteil/cozytouch/blob/main/custom_components/cozytouch/consumption.py)
   oraz [opis decyzji i źródeł](https://github.com/gduteil/cozytouch/blob/main/docs/decisions.md).
   Zanonimizowana próbka z *innego* urządzenia (Thermor Duralis ACI HYB)
   potwierdza `type=1` = electricity, `unit=1` = kWh i
   `mode=1`/ `mode=2` = szczyt/poza szczytem. Ten schemat nie dowodzi
   zgodności dla każdego modelu pompy.
3. **Katalog capability** opisany w
   [api-surface.md](https://github.com/gduteil/cozytouch/blob/main/docs/api-surface.md)
   identyfikuje `HOME_EnergyConsumptionCapabilities` (ID 164) jako maskę
   dostępnych funkcji. Dla wartości **1298 = 1024 + 256 + 16 + 2**:
   elektryczność CO, elektryczność CWU, deklarowana produkcja ciepła CO i CWU.
   To **deklaracja możliwości sterownika**, nie dowód na aktywny strumień
   energii cieplnej ani istniejący w chmurze COP.
4. **Niezweryfikowane na pompie**: znaczenie `category` w seriach, sposób
   powiązania serii z CO/CWU, jednostki i okres rozliczeniowy liczników
   capability 57/59, relacja endpointu dziennego do licznika miesięcznego
   z wyświetlacza. Wybór dwóch pierwszych serii jako CO i CWU byłby
   nieuprawnionym zgadywaniem.
5. **Kandydaci do etapu 3**: w opisie upstream
   [decisions.md](https://github.com/gduteil/cozytouch/blob/main/docs/decisions.md)
   wymieniono `GET /magellan/gateways/{id}/consumptions` oraz okresy
   `monthly` i `yearly`. Nie zostały zweryfikowane na tej instalacji,
   zatem w v0.4.3 **nie wykonujemy żadnych dodatkowych requestów**.
   Przed ich implementacją potrzebny jest przegląd schematu i zabezpieczeń.

## Co dokładnie dodaje v0.4.3

Dotychczasowy sensor `Historia energii Atlantic · test API` i jego
`unique_id` pozostają bez zmian. Zostają wszystkie dotychczasowe atrybuty:
`serie`, `typy`, `jednostki`, `okresy_z_energia_pobrana`,
`okresy_z_energia_wyprodukowana`, `mozliwy_pomiar_produkcji`,
`cop_zweryfikowany` oraz `deklarowane_pomiary_id164`.

Nowe atrybuty:

- `serie_szczegoly` — do 12 zanonimizowanych wierszy, każdy zawiera
  `indeks`, `kategoria_kod`, `typ_kod`, `jednostka_kod`,
  `typ_wg_znanego_przykladu`, `jednostka_wg_znanego_przykladu`,
  `przypisanie_co_cwu` (zawsze **niepotwierdzone**),
  `liczba_rekordow`, `liczba_dni_utc`, `data_od_utc`, `data_do_utc`,
  `nieprawidlowe_daty`, `tryby_kody`, `profile_kody`,
  `okresy_z_energia_pobrana`, `okresy_z_energia_wyprodukowana`,
  `okresy_z_dodatnia_produkcja`,
  `okresy_bez_liczbowej_produkcji`; kody trybów i profili są ograniczone
  do 12 na serię, a nadwyżki liczone w `tryby_pominiete` i
  `profile_pominiete`.
- `serie_pominiete_w_szczegolach` — liczba serii wykraczających poza 12;
  podstawowe sumy nadal obejmują wszystkie serie.
- `okresy_z_dodatnia_produkcja` — liczba okresów z produkcją **większą od 0**,
  odmienna od liczby pól zawierających liczbową wartość 0 lub większą.

`mozliwy_pomiar_produkcji` zachowuje starą semantykę: **co najmniej jedno
liczbowe pole** `producedQuantity >= 0`, również jeśli wartość jest 0.
Sam ten atrybut **nie potwierdza dodatniej produkcji ciepła** i nie służy do
wyliczania COP. Nowa metryka dodatnich wartości pomaga to odróżnić.

Data jest interpretowana tylko z poprawnego znacznika Unix (sekundy)
i przedstawiona jako **dzień kalendarzowy UTC**; znacznik nieważny lub
nietypowy nie jest przetwarzany. Jeden dzień z dwiema taryfami może mieć
dwa rekordy — zatem `liczba_rekordow` ≠ `liczba_dni_utc`.

## Ochrona prywatności i bezpieczeństwo

W odpowiedzi diagnostycznej **nie ma** `serialNumber`, `deviceId`,
`deviceUrl`, `zoneId`, nazw instalacji, haseł, tokenów, sum zużycia,
kwot, cen ani surowego JSON. Pokazujemy jednak dni kalendarzowe UTC,
a więc przed opublikowaniem raportu publicznie warto je również usunąć.
Nie publikujemy żadnych wartości pomiarowych CO/CWU ani COP.

Nie modyfikujemy `api.py`, `__init__.py`, częstotliwości zapytań, mechanizmu
autoryzacji ani platform sterujących. Brak konfiguracji nowych encji energii,
`state_class` czy `last_reset` chroni przed błędnymi statystykami HA.
Wykaz kodów jest limitowany (0…10000), struktura jest sprawdzana,
maks. 256 serii i maks. 3660 okresów na serię, a lista szczegółów jest
skracana do 12 wierszy.

## Warunki odbioru przed etapem 3 i wdrożeniem na main

1. GitHub Actions: testy offline, bezpieczeństwa i import oficjalnego
   obrazu HA 2026.10.2 zakończone sukcesem.
2. Na rzeczywistym HA: dwie serie i ich `kategoria_kod`, `typ_kod`,
   `jednostka_kod`, `tryby_kody`, zakresy dat oraz liczniki pól.
3. **Ręczne porównanie** wartości na panelu pompy i w HA w tym samym
   przedziale czasu — zanim jakakolwiek seria dostanie nazwę CO lub CWU.
4. Jeśli brak `producedQuantity`, COP pozostaje **niezweryfikowany**,
   niezależnie od ID 164.

**Status:** kod na gałęzi roboczej / PR. Nie scalać do `main` bez
odrębnego zatwierdzenia użytkownika.
