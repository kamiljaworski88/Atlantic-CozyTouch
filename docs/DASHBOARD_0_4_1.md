# Dashboard Atlantic — proponowany blok „Walidacja telemetrii v0.4.1”

W istniejącym widoku `PC Atlantic` dodaj pod sekcją energii poniższe trzy **istniejące** sensory. Nie ma nowych zdefiniowanych jednostek energii.

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: >
      **Walidacja energii Atlantic:** liczby są surowymi odczytami.
      Nie są potwierdzonymi Wh/kWh i nie należy ich dodawać
      do panelu Energia ani sumować.
  - type: entities
    title: Surowe wartości API Atlantic
    show_header_toggle: false
    entities:
      - entity: sensor.alfea_extensa_s_wskazanie_energii_id_57_surowe
        name: ID 57
      - entity: sensor.alfea_extensa_s_wskazanie_energii_id_59_surowe
        name: ID 59
      - entity: sensor.alfea_extensa_s_wskazanie_energii_id_60_surowe
        name: ID 60 (może być unknown)
  - type: history-graph
    title: Wskazania surowe — 24 godziny
    hours_to_show: 24
    entities:
      - entity: sensor.alfea_extensa_s_wskazanie_energii_id_57_surowe
      - entity: sensor.alfea_extensa_s_wskazanie_energii_id_59_surowe
```

### Dodanie nowych encji diagnostycznych

Po zainstalowaniu gałęzi v0.4.1 i restarcie HA wejdź w **Ustawienia → Urządzenia i usługi → Atlantic CozyTouch Read-Only → Encje**. Wyszukaj:
- `Przyrost surowego wskazania ID 57`
- `Przyrost surowego wskazania ID 59`
- `Diagnostyka wskazania ID 60`
- `Aktualność telemetrii Atlantic`

Wybierz nazwy i skopiuj **rzeczywiste** `entity_id` z rejestru HA. Identyfikator generowany przez HA zależy od nazwy urządzenia i istniejącego rejestru — nie zgadujemy go w dashboardzie.

Do sekcji diagnostyki dodaj kartę `entities` z czterema skopiowanymi `entity_id`. Diagnostyczne encje mogą domyślnie być ukryte na karcie urządzenia. Użyj przełącznika wyświetlania encji diagnostycznych.

**Brak nowych platform sterowania, brak dodatkowego polling oraz brak wykresów kWh/COP/kosztów.**
