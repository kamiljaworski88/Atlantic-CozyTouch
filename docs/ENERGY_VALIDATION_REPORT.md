# Sprint v0.4.1 — protokół walidacji energii (szablon)

**Status:** weryfikacja surowych liczników, a nie raport kosztów i nie pomiar COP.

## Dane referencyjne do zebrana

Podaj osobno okres prezentowany przez aplikację Atlantic (dzień, miesiąc, okres niestandardowy) i czas pierwszego/ostatniego zrzutu. Aplikacja może pokazywać licznik zużycia dla **innego okresu** niż surowy licznik API — nie utożsamiaj ich na podstawie podobnej liczby.

| Moment | ID 57 (surowy) | ID 59 (surowy) | ID 60 (surowy) | ID 91 (CO/CWU) | Aplikacja CO (kWh) | Aplikacja CWU (kWh) |
|---|---:|---:|---:|---|---:|---:|
| T0 (godzina …) | … | … | … / unknown | … | … | … |
| T1 (godzina …) | … | … | … / unknown | … | … | … |

## Z automatycznej diagnostyki v0.4.1

1. W HA: **Ustawienia → Urządzenia i usługi → Atlantic CozyTouch Read-Only → Pobierz diagnostykę**.
2. Raport `diagnostics_format: 3` zawiera `energy_validation` — dla każdego anonimowego indeksu urządzenia: `value_status` oraz `comparison` dla ID 57/59/60. **Nie zawiera żadnej wartości energii, nazwy ani deviceId.**
3. Sensor **Diagnostyka wskazania ID 60** pokazuje jeden z powodów: `valid`, `missing`, `empty`, `invalid_format`, `negative`, `out_of_range`. To diagnoza struktury odpowiedzi, nie diagnoza uszkodzenia pompy.
4. Sensory **Przyrost surowego wskazania ID 57/59** porównują tylko kolejne udane odczyty tej samej jednostki. Po restarcie, błędzie lub luce >15 minut zwracają `unknown`. Atrybut `comparison_status` wyjaśnia dlaczego.
5. Sensor **Aktualność telemetrii Atlantic**: `aktualny` (ostatni dobry odczyt nie starszy niż 7,5 min), `opozniony`, `blad_ostatniego_odczytu` lub `brak_udanego_odczytu`. Odświeżanie jego stanu co minutę działa lokalnie i **nie wysyła żadnego dodatkowego zapytania API**.

## Interpretacja wyników

- **Nie przypisuj** ani ID 57, ani ID 59 do CO lub CWU przed potwierdzeniem zmian w tym samym okresie w aplikacji producenta.
- Status `increased` oznacza dodatni przyrost **surowych jednostek**; nie oznacza Wh/kWh ani chwilowej mocy.
- Status `decreased_or_reset` może oznaczać reset, zmianę horyzontu licznika lub błąd API — sam fakt spadku tego nie rozstrzyga.
- ID 60 może być zgłaszane przez urządzenie, lecz zawierać pustą lub niepoprawną wartość. Nowa diagnostyka pozwala te przypadki rozdzielić.
- Liczniki PGE i FoxESS dla całego domu nie są pomiarem dedykowanym Atlantic. Nie obliczaj z nich bezpośrednio COP.
- Nie wklejaj całych zrzutów z tokenami, loginami i numerami seryjnymi. Udostępnij wyłącznie wybrane wartości sensorów i anonimową sekcję raportu.

## Kryteria zamknięcia sprintu pomiarowego

- Potwierdzone odczyty w T0 i T1 z tego samego okresu aplikacji.
- Znaczenie i jednostka ID 57/59 ustalone na podstawie przyrostów oraz niezależnego punktu odniesienia.
- Przyczyna `unknown` dla ID 60 wyjaśniona strukturalnie.
- Przetestowane przerwy, restarty, błędy API i ujemne przyrosty.
- Dopiero w kolejnym PR sensory kWh, Energy Dashboard, koszty lub statystyki dobowe.
