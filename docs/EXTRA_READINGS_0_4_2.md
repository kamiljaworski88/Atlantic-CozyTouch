# Atlantic CozyTouch v0.4.2 — odczyty dodatkowe (bez sterowania)

## Wynik przeglądu parametrów

Ta gałąź **nie łączy się z pompą użytkownika**. Podstawą są publiczne mapowania capability i aktualna integracja. Integracja tworzy nowe encje **wyłącznie**, gdy właściwe ID występują w rzeczywistej odpowiedzi `setupviewv2`.

| ID Atlantic | Odczyt, jeśli zgłoszony | Status |
|---|---|---|
| 57 / 59 | CO / CWU: roboczo Wh → kWh | **Hipoteza** oparta o zgodność 11629 ↔ 11 kWh i 7126 ↔ 7 kWh na sterowniku |
| 60 | Łączny surowy licznik energii | Obecnie `unknown`; bez zmiany jednostek |
| 22 / 23 / 39 | Zadana CWU, komfort i ECO | Nowe mapowanie tylko do odczytu |
| 40–43 | Temperatura zadana/komfort/ECO stref | Nowe mapowanie tylko do odczytu |
| 65 / 66 | Stan wentylatora / pompy cyrkulacyjnej CWU | Nowe mapowanie; nie utożsamiaj z trybem sprężarki |
| 68 / 70 | Stopień elektrycznego dogrzewania 1 i 2 | Nowe mapowanie, enumeracja producenta |
| 164 | Dostępne rodzaje pomiaru zużycia energii | Surowa maska bitowa, bez domniemanej jednostki |
| 192 / 193 | Punkty krzywej grzewczej dla −10°C i +20°C na zewnątrz | Nowe mapowanie temperatury zasilania |
| 194 / 195 | Punkty krzywej chłodzenia dla +35°C i +25°C | Nowe mapowanie, zależy od wyposażenia |
| 254 | Bazowa nastawa CWU bez wymuszenia | Nowe mapowanie tylko do odczytu |
| 317 | Dostępność drugiego obiegu CO | Nowy odczyt binarny |
| 24 / 27 / 51 / 72 | Starty, czas, stan i modulacja sprężarki | Obsługiwane wcześniej; encje tylko jeśli API raportuje |
| 25 / 26 / 28 / 29 | Starty i czas pomp obiegowych | Obsługiwane wcześniej; **to nie jest sprężarka** |
| 44 / 45 / 46 | Zużycie energii CO/CWU/łączne wg innego mapowania | Obsługiwane wcześniej; tylko jeśli API raportuje |

**COP:** nie potwierdzono identyfikatora faktycznego COP w publicznej tabeli Cozytouch. ID 107079 oznacza `cop_threshold` (próg), nie rzeczywisty COP. Obecność COP w menu fizycznego panelu nie dowodzi dostępności pomiaru w tym endpointzie API. Nie tworzymy fałszywego sensora COP ani nie liczymy COP z samego poboru prądu.

## Robocze sensory energii

Kiedy **ta sama jednostka** zgłasza ID 57 i 59, integracja utworzy:
- `Energia elektryczna CO (robocza)` — ID 57 / 1000, kWh.
- `Energia elektryczna CWU (robocza)` — ID 59 / 1000, kWh.
- `Energia elektryczna CO i CWU (suma robocza)` — suma powyższych, kWh.

Dla wcześniej zaobserwowanych wartości 11629 i 7126 otrzymamy odpowiednio **11,629**, **7,126** i **18,755 kWh**. To wskazania w niepotwierdzonym okresie, a nie na pewno energia za dobę/miesiąc. Odczyty nie mają `state_class`, nie trafiają automatycznie do Energy Dashboard ani do Utility Meter. Nie wolno z nich liczyć COP. Dane surowe i ich historyczne identyfikatory pozostają bez zmian.

Po instalacji w HA odszukaj w **Ustawienia → Urządzenia i usługi → Atlantic CozyTouch Read-Only → Encje** trzy nowe nazwy i **skopiuj faktyczne** `entity_id`; zależą one od rejestru encji Home Assistant.

Przykładowa karta dashboardu (identyfikatory poniżej są wyłącznie **przykładowe** i należy je dopasować do rejestru HA):

```yaml
type: entities
title: "⚡ Atlantic · energia elektryczna (odczyt roboczy)"
show_header_toggle: false
entities:
  - entity: sensor.alfea_extensa_s_energia_elektryczna_co_robocza
    name: Ogrzewanie CO
  - entity: sensor.alfea_extensa_s_energia_elektryczna_cwu_robocza
    name: Ciepła woda CWU
  - entity: sensor.alfea_extensa_s_energia_elektryczna_co_i_cwu_suma_robocza
    name: Suma CO + CWU
```

## Jak sprawdzić rzeczywistą dostępność nowych odczytów i COP

1. Po **przeglądzie i połączeniu PR z main** wykonaj kopię zapasową HA, zaktualizuj integrację i zrestartuj HA.
2. W Atlantic: **Pobierz diagnostykę**. Zanonimizowany `device_capability_inventory` pokaże dla każdej anonimowej jednostki `known_capability_ids` i `unmapped_capability_ids`, także sześciocyfrowe. Raport celowo nie zawiera wartości, tokenów ani numerów seryjnych.
3. Odszukaj nowo zgłoszone ID z tabeli; API może nie pokazywać wszystkich funkcji widocznych na sterowniku. Gdy w danych diagnostycznych pojawią się nieznane ID, weryfikujemy ich znaczenie na podstawie dokumentacji i obserwacji, **nie odgadujemy**.
4. Dla COP szukamy pomiaru rzeczywistej energii oddanej przez pompę albo bezpośredniej wartości sterownika. Nie mylimy parametru `cop_threshold` z COP chwilowym/sezonowym.

## Bezpieczeństwo i kompatybilność

- Jedynie chmura producenta (`apis.groupe-atlantic.com`) — identyczne dotychczasowe logowanie i odczyt `setupviewv2`.
- Nie ma nowych żądań HTTP, sterowania urządzeniem, automatycznej zmiany nastaw, ani udostępniania danych zewnętrznym serwisom.
- Istniejące `unique_id` pozostają bez zmian; nowe sensory dostają nowe identyfikatory.
- Czujniki diagnostyczne są domyślnie odkrywane tylko gdy ID są raportowane; część może wymagać pokazania ukrytych encji diagnostycznych.
