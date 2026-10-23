# v0.4.0 — bezpieczna walidacja energii i trybów Atlantic

## Co pokazują nowe sensory?

| Capability | Opis źródłowego mapowania | Publikacja w tej wersji |
| --- | --- | --- |
| 57 | energy / power_consumption | surowa liczba, BEZ jednostki |
| 59 | energy / power_consumption | surowa liczba, BEZ jednostki |
| 60 | total_electricity_consumption | surowa liczba, BEZ jednostki |
| 91 | active_circuit | CO dla `1`, CWU dla `3`; inne -> unknown |
| 99 | dhw_pump / resistance zależnie od produktu | tylko stan on/off; nazwa neutralna |
| 112 | circulator_flow_rate | surowa liczba BEZ L/min |
| 153 | heating_status | wyłączone, ogrzewanie, chłodzenie |
| 181 | service_in_progress | enum usługi; nie jest to stan sprężarki |
| 380 | outdoor_unit_error_code_cesa | surowy kod; bez automatycznego alarmu |

**Uwaga:** urządzenia zgłaszają ID niezależnie od jego przydatności. Kody są mapowane według publicznej tabeli Cozytouch i nie zostały jeszcze zweryfikowane dla wszystkich modeli Atlantic.

## Instrukcja walidacji

1. Zrób kopię HA i zainstaluj v0.4.0 przez HACS po publikacji/merge.
2. W urządzeniu Atlantic w HA odszukaj sensory diagnostyczne **Wskazanie energii · ID 57**, **ID 59**, **ID 60**, **Odczyt przepływu · ID 112**. Obserwuj je również w historii, np. przez 24 godziny.
3. Zapisz parę odczytów (początek i koniec, lokalna data/godzina) oraz stan ID 91 podczas CO i naturalnego podgrzewania CWU.
4. Porównaj surowe liczniki z wiarygodnym zewnętrznym pomiarem energii pompy. Liczniki PGE/FoxESS obejmują inne obciążenia domu i nie są automatycznie pomiarem pompy.
5. Zweryfikuj, czy wartości są narastające, czy resetują się, oraz czy są w Wh / kWh. Nie zgaduj z podobieństwa cyfr.
6. Nie wysyłaj pliku `.storage`, loginów, tokenów ani surowej odpowiedzi API. Wystarczą same, lokalnie skopiowane wartości wyżej wymienionych sensorów.

## Bramka v0.4 energia i koszty

Dopiero po pozytywnej walidacji:
- nadajemy jednostkę i `SensorDeviceClass.ENERGY` sensownemu licznikowi;
- wybieramy `TOTAL_INCREASING` wyłącznie dla potwierdzonych liczników;
- uwzględniamy reset, brak danych i korektę historii przy zmianie jednostek;
- ustalamy zakres CO/CWU i liczymy koszt dopiero przy poprawnej taryfie;
- nie wyliczamy COP bez pomiaru energii cieplnej.

## Bezpieczeństwo

Raport **Pobierz diagnostykę** nadal ujawnia wyłącznie numery capability, nigdy wartości nowych sensorów. Nowe mapowania nie wprowadzają HTTP POST poza autoryzacją ani żadnych operacji zapisu w HA.
