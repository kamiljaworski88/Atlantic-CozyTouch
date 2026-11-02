# Audyt odczytów sprężarki Atlantic — 2026-11-02 (read-only)

## Cel i wynik wstępny

Dla instalacji Atlantic Extensa S Duo XL 10 odczyt `setupviewv2`
i dodatkowy GET parametrów urządzenia nie udostępniły:
- ID 24 — licznik uruchomień sprężarki,
- ID 27 — czas pracy sprężarki (katalogowe sekundy),
- ID 51 — stan sprężarki,
- ID 72 — modulacja sprężarki.

Stan HA `brak_nowych_parametrow` z czterema wartościami `False` jest
**wynikiem obserwacji API na tym koncie**, nie dowodem, że urządzenie
nie ma tych danych na lokalnym sterowniku.

## Przeanalizowane zasoby GET

| Zasób | Cel | Stan dowodów |
|---|---|---|
| `/magellan/cozytouch/setupviewv2` | Stan urządzeń | Działa; nie zwrócił 24/27/51/72 |
| `/magellan/capabilities/?deviceId=...` | Dodatkowy odczyt znanego urządzenia z konta | Wykonany; `brak_nowych_parametrow` |
| `/magellan/productmodels/capabilities` | Globalny katalog definicji | Opisuje pola; nie dowodzi wartości na konkretnej pompie |
| `/magellan/capabilities/?deviceid=...&capabilities=...` | Eksperymentalny odczyt tylko istniejącego urządzenia | Kod już obsługuje; zapytania o dowolne nowe ID nie są automatycznie generowane |
| `/magellan/setups/.../consumptions?periodicity=...` | Historia energii | Nie jest źródłem liczników startów ani godzin sprężarki |
| `/magellan/devices/.../consumptions?periodicity=...` | Historia energii urządzenia | Testowane oddzielnie; nie utożsamiać z telemetrią sprężarki |
| `/magellan/gateways/.../consumptions?periodicity=daily` | Historia energii bramki, jeśli znana | Eksperymentalne; nie potwierdza pracy sprężarki |

## Co zmienia ten PR

Wykorzystuje **już istniejący, opcjonalny odczyt globalnego katalogu**;
nie dodaje nowych tras ani żądań HTTP, nie zmienia domyślnej częstotliwości,
nie wprowadza sterowania urządzeniem.

Katalog może zawierać:
- ID24, 27, 51, 72 — definicje bezpośrednich sygnałów sprężarki,
- ID50 — `GENERATOR_ModulationLevel`, czyli **modulacja generatora**;
  jest sygnałem pośrednim, **nie zastępuje** ID72,
- inne niesklasyfikowane pola z `Compressor` / `Compresseur` /
  `Verdichter` w nazwie, z pominięciem oczywistych błędów i temperatur.

Każda pozycja ma `tylko_metadane: true` oraz
`potwierdzony_odczyt_z_pompy: false`. Katalog nie zwraca wartości
użytkownika, numerów seryjnych ani tokenów. Maksymalnie 24 pozycje.
Kandydaci **nie są automatycznie dodawani do zapytań urządzenia**.

Dostępność ID50 w bieżącym zestawie danych pokazuje osobny atrybut
`generator_modulacja_id_50_obecna`, ale nie służy do określania
`sprężarka pracuje` i nie zwiększa liczników startów/czasu.

## Weryfikacja w Home Assistant

1. Zaktualizuj integrację po merge i przeładuj ją.
2. Jeśli badanie źródeł API jest wyłączone, wejdź w
   **Ustawienia → Urządzenia i usługi → Atlantic CozyTouch → Konfiguruj**
   i świadomie włącz opcję `experimental_api_discovery`.
   Ta opcja jest eksperymentalna i może wysyłać do 6 dodatkowych GET
   na cykl badawczy (nie więcej niż 1 na odświeżenie).
3. W **Narzędzia deweloperskie → Szablony** wpisz:

```jinja2
{% set s = states.sensor.diagnostyka_odczytu_sprezarki_z_api %}
Status: {{ s.state }}
Katalog: {{ s.attributes.get('katalog_api_sprezarki') | tojson }}
Modulacja generatora ID50 obecna: {{ s.attributes.get('generator_modulacja_id_50_obecna') }}
Brakujące ID: {{ s.attributes.get('brakujace_id_w_standardowym_odczycie') }}
```

Jeśli katalog zwraca definicje 24/27/51/72, a odczyty nadal pokazują
`False`, to nadal **nie ma potwierdzonych danych sprężarki**.
Następne badanie powinno dotyczyć tylko udokumentowanych alternatywnych
zasobów GET, przy zachowaniu limitów, whitelisty i anonimizacji.

## Źródło definicji i ograniczenia

Porównawczo: publiczny
[katalog parametrów Magellan](https://github.com/gduteil/cozytouch/blob/1cdec93f858d8b206a48c5c25d342f36340f6649/scripts/capability_catalogue.jsonl)
potwierdza znaczenia ID24, 27, 50, 51, 72, ale **nie ich obecność na Extensa S**.
Zasoby te są nieoficjalnie zbadanym protokołem chmurowym Atlantic.
Nie weryfikowano w tym PR żadnych odpowiedzi z prywatnego konta; testy są
offline. W żadnym wypadku nie wolno generować czasu pracy, startów ani stanu
sprężarki z samego trybu CO/CWU.
