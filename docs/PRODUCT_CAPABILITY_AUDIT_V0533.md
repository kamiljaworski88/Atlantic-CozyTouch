# Audyt możliwości produktu Magellan (v0.5.33)

## Cel

Rozróżnić trzy niezależne rodzaje informacji:

1. **Definicja globalna** parametru w katalogu producenta;
2. **Deklaracja dla `productId`** urządzenia;
3. **Rzeczywiste zgłoszenie parametru** w odczycie instalacji użytkownika.

Punkt 2 nie dowodzi punktu 3. Brak parametru w odpowiedzi chmurowej
nie dowodzi, że sterownik lokalny nie ma jego licznika.

## Implementacja

Z autoryzowanego `GET /magellan/cozytouch/setupviewv2` pobieramy
bezpieczne identyfikatory katalogowe `productId` i `modelId`.
Nie odczytujemy ich z tekstu od użytkownika, numeru seryjnego
ani konfiguracji. Odrzucamy wartości niepoprawne i wieloznaczne.
Tylko dla jednoznacznego interfejsu pompy (ID91+ID112), ewentualnie
jednoznacznego generatora (ID109+ID116), sprawdzamy katalog.

W **istniejącym, opcjonalnym** mechanizmie `experimental_api_discovery`
dodajemy dla maksymalnie dwóch **różnych** `productId`:

- `GET /magellan/productmodels/capabilities?productid=<id>` — katalog
  definicji produktu, tylko metadane;
- `GET /magellan/productmodels/products/<id>` — próba ustalenia
  `familyId`, tylko metadane.

Każde zapytanie GET jest ograniczone do aktualnego,
uwierzytelnionego produktu. Jeżeli zmieni się powiązanie urządzenia,
badanie kończy się bez kolejnego żądania. **Maksymalnie jeden dodatkowy
GET podczas jednego odświeżenia** i maksymalnie **11 GET na cykl
badania** (w tym wcześniejsze zasoby; jeśli brakuje ID, mniej).
Ta funkcja pozostaje **domyślnie wyłączona**.
Zatrzymanie po HTTP 401 lub 429, brak automatycznych powtórzeń,
limit treści odpowiedzi 1 MB, limit 2048 pozycji katalogu.

Nie ma żadnych wywołań PATCH, PUT lub POST do urządzenia,
ani zmiany w sterowaniu, licznikach energii, COP1/COP2, defrost lub HA Energy.
Uwierzytelnianie użytkownika pozostaje takie jak dotychczas.

## Gdzie zobaczysz wynik?

W Home Assistant, **Narzędzia deweloperskie → Stany**, wyszukaj
encję o nazwie:

**Atlantic · audyt możliwości produktu**

Ma atrybut `wyniki_produktow`, w którym znajdują się wyniki:

- `product_capabilities_interfejs`
- `product_metadata_interfejs`
- `product_capabilities_generator` (jeżeli jest odrębny produkt)
- `product_metadata_generator` (jeżeli jest odrębny produkt)

Wyniki pokazują `product_id`, `model_id`, `family_id` (jeżeli
zwrócony i poprawny) oraz `porownanie`, grupowane według
sprężarki, energii elektrycznej, kandydatów energii cieplnej,
grzałek, hydrauliki, CWU i diagnostyki:

- `w_katalogu` — ID zdefiniowane dla produktu,
- `zgloszone_przez_urzadzenie` — ID zgłoszone w aktualnym odczycie,
- `w_katalogu_ale_brak_w_odczycie` — luka w raportowaniu.

Dodatkowe `nieznane_kandydaty` to tylko **ID + etykieta
kategorii**, bez nazw, opisów i wartości producenta.
`bezposredni_defrost_potwierdzony` i
`wyprodukowana_energia_cieplna_potwierdzona` są zawsze **False**
w tej części badania, ponieważ katalog nie jest pomiarem.

## Uruchomienie

1. Po scaleniu PR zaktualizuj HACS do wersji **0.5.33**
   i przeładuj / uruchom ponownie Home Assistant.
2. Jeśli badanie API jest wyłączone, w opcjach integracji Atlantic-CozyTouch
   świadomie włącz `experimental_api_discovery`.
3. Poczekaj na zakończenie krótkiego cyklu. Przy odświeżeniu
   co 180 s maksymalny plan zajmuje około 33 minuty
   (11 odczytów, po jednym na odświeżenie).
4. W **Narzędzia deweloperskie → Szablony** wklej:

```jinja2
{% for s in states.sensor if 'audyt możliwości produktu' in s.name | lower %}
Stan: {{ s.state }}
{% set wyniki = s.attributes.get('wyniki_produktow', {}) %}
{% for k, v in wyniki.items() %}
Źródło: {{ k }}
Status: {{ v.get('state') }}
Product ID: {{ v.get('product_id') }}
Model ID: {{ v.get('model_id') }}
Family ID: {{ v.get('family_id') }}
Sprężarka: {{ v.get('porownanie', {}).get('sprezarka') }}
Energia elektryczna: {{ v.get('porownanie', {}).get('energia_elektryczna') }}
Grzałki: {{ v.get('porownanie', {}).get('grzalki') }}
Hydraulika: {{ v.get('porownanie', {}).get('hydraulika') }}
Kandydaci defrost / ciepła: {{ v.get('nieznane_kandydaty') }}
{% endfor %}
{% endfor %}
```

Uwaga: encja pojawia się tylko po instalacji nowego kodu.
Jeśli `productId` nie jest dostępny przy module pompy,
raport oznaczy `brak_product_id_w_odczycie_urzadzenia`
zamiast odpytywania losowych produktów.

## Źródła i ograniczenia

- [Groupe Atlantic Developer Portal](https://apis.groupe-atlantic.com/devportal/)
- [Magellan API — wyniki porównawczego badania](https://github.com/gduteil/cozytouch/blob/main/docs/api-surface.md)
- [Poprzedni audyt sprężarki](COMPRESSOR_API_AUDIT_20261102.md)

Testy jednostkowe dodane w `tests/test_readings.py` oraz
`tests/test_api_discovery.py`. Wykorzystują tylko lokalne,
fikcyjne odpowiedzi; nie używają prywatnego konta Atlantic.
