# Atlantic Magellan API — poszukiwanie energii cieplnej CO/CWU (25.10.2026)

**Cel:** automatycznie odczytać wartości produkcji ciepła, które lokalny
sterownik Atlantic Extensa S Duo XL 10 pokazuje osobno dla CO i CWU, bez
zmyślania kWh i bez serwerów autora integracji.

## Udokumentowane źródła

1. **Magellan `setupviewv2`**: lista capability wartości/znaczników. Według
   publicznego katalogu Atlantic 405 capability, `57` oznacza
   `HOME_ElecHeatConsumptionCumulated` (energia elektryczna CO, rozdzielczość
   0.001 kWh), a `59`: `HOME_ElecDHWConsumptionCumulated` (energia prądu CWU,
   rozdzielczość 0.001 kWh). Rzeczywista skala surowego `value` z tego
   urządzenia wymaga jeszcze porównania 1:1 ze sterownikiem.
2. **ID164**: maska `HOME_EnergyConsumptionCapabilities`.
   Niezależne mapowanie pokazuje bity 256/1024 dla produkcji ciepła CO/CWU;
   katalog OEM w publicznej wersji nie opisuje tych bitów. Bit mówi tylko
   o dostępnej funkcji, **nigdy o liczbie kWh**.
3. **`GET /magellan/setups/<id>/consumptions?periodicity=daily|monthly`**:
   lista rekordów `type`, `unit`, `category`, `consumptionPeriods` i
   `consumedQuantity` / `producedQuantity`. Kody `type=1,unit=1`
   oznaczają energię elektryczną i kWh w publicznie przeanalizowanym przypadku.
   `mode=1/2` to w tym przypadku taryfa prądowa, **nie CO/CWU**.
   `producedQuantity` może dotyczyć produkcji innego rodzaju energii;
   samo pole lub dodatnia liczba nie dowodzą ciepła.
4. **`GET /magellan/devices/<id>/consumptions?periodicity=daily|monthly`**:
   drugi odczyt przez obecny klient, ograniczony do jednej pompy na koncie.
   Nie wolno sumować odpowiedzi urządzenia z odpowiedzią całej instalacji,
   gdyż mogą przedstawiać te same zdarzenia.
5. **`GET /magellan/capabilities/?deviceId=...`**: znany odczyt tylko
   wybranych capability, bez nowych pól kWh ciepła. Publiczny katalog
   urządzeń nie zawiera nazwanych capability `HeatProducedCumulated` CO/CWU.
6. **Overkiz to osobny protokół**. W publicznym zgłoszeniu dla modeli Extensa S
   zgłaszano urządzenie ogłoszone jedynie przez Magellan, a nie Overkiz.
   Nie przełączamy klienta w ciemno na inne serwery.

Źródła publiczne:
- https://github.com/mathieuletyrant/cozytouch-hacs/blob/main/docs/api-surface.md
- https://github.com/mathieuletyrant/cozytouch-hacs/blob/main/docs/decisions.md
- https://github.com/mathieuletyrant/cozytouch-hacs/blob/main/scripts/capability_catalogue.jsonl
- https://community.homey.app/t/app-pro-atlantic-cozytouch-en/159117
- https://www.atlantic.fr/aide/pompe-a-chaleur-air-eau/fonctionnement-utilisation/comment-visualiser-mes-consommations-d-energie-sur-ma-pompe-a-chaleur

## Zmiana diagnostyczna w tym PR

**Nie dodajemy nowego endpointu.** W istniejących dwóch sondach miesięcznych
`Historia energii Atlantic · miesięczna kontrola` i
`Historia energii Atlantic · odczyt urządzenia` pokazujemy atrybut
`audyt_surowych_kandydatow` z najnowszego miesiąca i poprzedniego.

Atrybut zawiera maksymalnie 24 anonimowe rekordy:
- numer serii tylko w obrębie odpowiedzi (bez deviceId/serial/URL),
- `miesiac_utc`,
- `kategoria_kod`, `typ_kod`, `jednostka_kod`, `tryb_kod`,
- `pobor_liczbowy` oraz `produkcja_dodatnia` (wyłącznie wartości logiczne).

**To diagnostyka, nie produkcja ciepła i nie COP.** Prywatne liczby energii
nie trafiają do eksportowanych atrybutów ani do liczników CO/CWU. Producent dla niektórych pomp
opisuje wartości energii jako szacunki, a nie odczyt z miernika.

### Kryterium dopuszczenia automatycznego COP

1. W przyszłej fazie, po weryfikacji odczytu przez samego użytkownika,
   w dwóch różnych okresach miesięcznych wartość produkcji z identycznego
   źródła (`type/unit/category/mode`) musi zgadzać się z osobnym wskazaniem
   energii cieplnej CO/CWU sterownika, po uwzględnieniu formatu/zaokrąglenia.
2. Jednoznaczne przypisanie CO/CWU po katalogu lub wzorcu danych w czasie,
   nie na podstawie niezweryfikowanego `mode`.
3. Potwierdzona jednostka i rozdzielczość, identyczne ramy czasu, brak
   duplikatów oraz weryfikacja czy sterownik pokazuje estymację.
4. Dopiero wtedy rozważyć **osobne sensory zweryfikowanego przez użytkownika
   miesięcznego ciepła i COP**. Zera, `null`, pustych historii nie wypełniać
   wartościami obliczanymi na siłę.

Jeżeli oba endpointy nie przekazują `producedQuantity`, chmura nie
dostarcza nam dotąd ciepła. Wtedy dalsze opcje to potwierdzony lokalny
interfejs sterownika/producenta lub własny ciepłomierz, a nie zgadywanie
COP z nieaktualnych temperatur.
