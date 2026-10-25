# Atlantic CozyTouch v0.5.15 — eksperymentalny COP ze snapshotów HA

## Co zmieniono
Dotychczasowa implementacja `cop_hydraulic.py` bazowała na `modificationDate`
temperatur i odrzucała dane po dwóch godzinach od **ostatniej zmiany wartości**.
Znacznik nie informuje, czy czujnik był ponownie zmierzony. Nowa implementacja
`cop_snapshot.py` zbiera kolejne udane obserwacje `setupviewv2`
i wyznacza moc cieplną z wartości odczytanych w konkretnym snapshocie,
jednocześnie **oddzielając obserwację wartości przez HA od dowodu jej świeżości
po stronie pompy**.

Kod nie wykona żadnego dodatkowego HTTP i nie zmienia uprawnień integracji.

## Znane jednostki z katalogu Atlantic
- `112 / CirculatorFlowRate` — l/min, rozdzielczość 0.01.
- `109 / GENERATOR_WaterOut1` — °C, rozdzielczość 0.01.
- `116 / GENERATOR_WaterReturn` — °C, rozdzielczość 0.01.
- `57 / HOME_ElecHeatConsumptionCumulated` — kWh, katalogowa rozdzielczość 0.001.
- `59 / HOME_ElecDHWConsumptionCumulated` — kWh, katalogowa rozdzielczość 0.001.
- `91 / GENERATORStatus` — rozróżnia tryb pracy generatora CO/CWU.
- `64 / DHWExtraElecStatus` — wskazanie grzałki elektrycznej CWU.

Źródło: publiczny katalog ProductModels wydobyty przez niezależną integrację:
https://github.com/mathieuletyrant/cozytouch-hacs/blob/main/scripts/capability_catalogue.jsonl

Katalogowa rozdzielczość **nie wystarcza do udowodnienia**, że u konkretnego
użytkownika w payloadzie każda surowa jednostka licznika 57/59 = 1 Wh.
Algorytm traktuje to jako hipotezę wymagającą porównania z panelem pompy.
To samo dotyczy przypisania przepływu do obiegu CWU.

## Matematyka
`P_thermal[kW] = flow[L/min] * (T_out-T_return)[K] * 4.186 / 60`.
Dla dwóch zaakceptowanych obserwacji:
`E_thermal[kWh] = (P_previous + P_current)/2 * seconds/3600`.
`E_electric[kWh] = (raw_now-raw_previous) / 1000` (hipoteza).
`COP_interval = E_thermal / E_electric`.
`COP_accumulated = sum(E_thermal) / sum(E_electric)`, oddzielnie CO/CWU.

## Filtrowanie
- Obowiązkowa jednoznaczność źródeł (`57+59+91+112` oraz `109+116`).
- Różne urządzenia logiczne oraz fallback starych temperatur wymagają opcji
  `experimental_cross_device_cop=true` ustawionej wcześniej przez użytkownika.
- Temperatury, które nie zmieniały się od 15min–12h, są **wyłącznie
  szacunkiem o niskiej pewności**. Wymagamy zgodnych znaczników pary (600 s),
  przepływu i licznika prądu zmienionych maks. 15 min temu, stałych wartości
  starej pary między zaakceptowanymi obserwacjami, dodatniego przyrostu prądu.
- Przy małym `DeltaT` (0.75–1.5 K) oraz nieznanym stanie sprężarki wynik ma
  niską pewność. `DeltaT < 0.75 K` nie generuje COP.
- Przedział obejmuje 2–20 minut pomiędzy obserwacjami; każda przerwa ponad
  20 minut, reset licznika, zmiana trybu lub niezgodność znaczników odrzuca go.
- Nie sumujemy okresów bez przyrostu licznika; nie dopisujemy ciepła po
  wznowieniu pracy podczas defrostu, postoju lub awarii.
- Wykryty aktywny status grzałki CWU (64), dodatni pobór grzałek pomocniczych (8/9/11) i jawne wyłączenie sprężarki (51)
  blokują obliczenia; niewidoczny status sprężarki zostawia niską pewność.
  Inne grzałki, odszranianie i obieg CWU mogą nadal nie być w pełni widoczne
  w tym protokole — **to istotne ograniczenie**.

## Użytkowanie i test
Po aktualizacji w HA:
1. Sprawdź, czy opcja eksperymentalnej analizy między modułami jest włączona.
2. W czasie faktycznego grzania z dodatnim przyrostem ID57/59 obserwuj
   `COP Atlantic · status obliczeń` i atrybuty `pewnosc_szacunku`,
   `roznica_temperatur_k`, `wiek_probek_s`.
3. Po co najmniej dwóch obserwacjach o odstępie 2–20 min możliwy jest
   szacunkowy COP. Przy braku ruchu licznika ma pozostać `unknown`.
4. Wartości `COP Atlantic · skumulowany ...` obejmują tylko zaakceptowane
   przedziały, **nie** pełen dzień / miesiąc. Historię sum zapisaną przez starszą
   implementację zachowano; w razie zmiany metodologii można ją wyzerować
   ręcznie, ale integracja nie wykonuje destrukcyjnej migracji.

**Nigdy nie traktuj wyniku jako fabryczny COP/S COP producenta,
fakturowany pomiar energii ani podstawę rachunku za prąd.** Tylko
niezależny certyfikowany licznik ciepła i dedykowany licznik elektryczny
dają możliwość niezależnej weryfikacji takiego ilorazu.
