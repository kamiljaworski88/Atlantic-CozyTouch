# v0.5.23 — Jednorazowy test historii energii bramki Atlantic

## Dlaczego
Rzeczywiste, autoryzowane odczyty Extensa S Duo XL 10 (26.10.2026):
- `GET /magellan/setups/{setupId}/consumptions?periodicity=daily`: HTTP 200; 5 dni CO + CWU; pole `producedQuantity` zawsze `null`.
- Miesięczny GET setup: HTTP 200; 34,63 kWh CO + 9,28 kWh CWU; `producedQuantity=null`.
- Urządzenie /consumptions: HTTP 500.
- Maska 164 = 1298 (bity 256 i 1024 wskazują deklarowaną obsługę produkcji CO i CWU).
- Publiczna analiza aplikacji Atlantic iOS odnotowała odczyt `/magellan/gateways/{gatewayId}/consumptions`, ale nie potwierdziła jego dostępności ani zakresu danych na tej pompie.

Źródło tropu: https://github.com/gduteil/cozytouch/blob/main/docs/decisions.md

## Co dokładnie wykonuje eksperyment
Dodany jeden wariant GET (tylko z włączoną opcją `experimental_api_discovery`):

```http
GET https://apis.groupe-atlantic.com/magellan/gateways/{gatewayId}/consumptions?periodicity=daily
Authorization: Bearer <lokalna-sesja-integracji>
Accept: application/json
```

**Nie ustalono pełnego kontraktu tego wariantu**: `periodicity=daily` to jeden ostrożny format analogiczny do działającego GET setup. Wynik HTTP 400/403/404/500 to normalny, możliwy rezultat, bez ponawiania i automatycznego wypróbowywania innych parametrów.

`gatewayId` pochodzi wyłącznie z pola `gateways[0].id` w jednej odpowiedzi własnej instalacji na `setupviewv2`, po potwierdzeniu dokładnie jednej bramki i wyłącznie cyfrowego ID (bez GUID/serial/deviceId). Gdy brak bramki, jest ich kilka lub format nieprawidłowy, sondy bramki **nie wykonujemy**. Widoczny w diagnostyce będzie ogólny status `gateway_target`, bez dokładnego ID.

Całe badanie pozostaje do **maks. 7 dodatkowych GET** rozłożonych na kolejne cykle 180 s; po jego zakończeniu nie ma kolejnych zapytań. Tylko jedno nowe żądanie względem 0.5.22. Nadal brak DELETE/PUT/PATCH, aktywnego refresh urządzenia, wyłączenia TLS lub przekierowań, nowych domen/serwerów lub zależności.

## Gdzie sprawdzić wynik
Home Assistant → Narzędzia deweloperskie → Stany → `Atlantic · badanie źródeł API` → atrybuty:

- `gateway_target`: `jedna_bramka_z_konta` albo `brak_lub_wiele_bramek_brak_testu`
- `results.gateway_daily_minimal.http_status`: stan HTTP, jeśli GET wykonano
- `results.gateway_daily_minimal.state`: `historia_odczytana`, `brak_okresow`, `nieznany_format_obiektu` lub błąd
- `results.gateway_daily_minimal.rows`: maksymalnie 24 anonimowe wiersze z kategorią, typem, jednostką, `consumed_quantity_raw`, `produced_quantity_raw` i datą jako Unix epoch
- `produced_non_null`: liczba *widocznych* niepustych wartości producedQuantity, nie licznik cieplnych kWh
- `thermal_energy_confirmed=false`, `cop_ready=false` zawsze przed porównaniem z fizycznym panelem pompy

Odczyt nie zasila `sensor.cop`, liczników skumulowanych ani HA Energy. Stary COP 9,44 nie jest usuwany ani walidowany.

### Szablon HA po aktualizacji

```jinja2
{% for s in states.sensor if 'badanie źródeł API' in s.name %}
Status: {{ s.state }}
Cel bramki: {{ s.attributes.get('gateway_target') }}
Pozostało: {{ s.attributes.get('remaining_requests') }}
{% set g = s.attributes.get('results', {}).get('gateway_daily_minimal', {}) %}
HTTP: {{ g.get('http_status') }}
Stan: {{ g.get('state') }}
Pola schematu: {{ g.get('znane_pola_obecne') }}
Niepuste produkcje (w widocznych rekordach): {{ g.get('produced_non_null') }}
{% for p in g.get('rows', []) %}
{{ p.get('date_epoch') }} | kat={{ p.get('category') }} typ={{ p.get('type') }} jednostka={{ p.get('unit') }}
Prąd={{ p.get('consumed_quantity_raw') }} Produkcja={{ p.get('produced_quantity_raw') }}
{% endfor %}
{% endfor %}
```

## Interpretacja
- **200 + dodatnie `produced_quantity_raw`**: kandydat do porównania z panelowym CO/CWU, najpierw identyfikacja typu, jednostki, daty i okresu, potem dwa niezależne okresy. Bez automatycznego COP.
- **200 + wszystkie `null`**: historia bramki nie rozwiązała problemu energii cieplnej dla obserwowanego okresu.
- **400/403/404/405/500**: nie wykonuj ponowień ani wariantów danych bez analizy wymagań dokumentacji.
- **Brak `gateway_daily_minimal` i cel `brak_lub_wiele_bramek_brak_testu`**: brak jednoznacznego ID bramki; nie wolno zastępować go deviceId ani serialem.

Po zebraniu danych wyłącz `experimental_api_discovery` w Opcjach integracji. Przed aktualizacją wykonaj kopię zapasową HA; włączenie już zaznaczonej opcji utrzyma się przy aktualizacji i uruchomi nową serię. Przetwarzane lokalnie dane nie są wysyłane na dodatkowy serwer.
