# Atlantic CozyTouch — Read-Only for Home Assistant

Nieoficjalna, niezależna integracja Home Assistant do **monitorowania** urządzeń Atlantic przez **oficjalne API Atlantic**.

> **Wersja 0.3.0 jest przeznaczona do testów. Nie instaluj jej bez uprzedniego przeglądu kodu oraz wykonania kopii zapasowej Home Assistant.**

## Bezpieczeństwo

- Brak sterowania pompą: **nie ma** encji typu `climate`, `number`, `switch`, `select`, `button` ani usług zapisujących ustawienia.
- Warstwa sieciowa dopuszcza jedynie `POST https://apis.groupe-atlantic.com/users/token` (logowanie) oraz `GET https://apis.groupe-atlantic.com/magellan/cozytouch/setupviewv2` (odczyt).
- Bez serwerów pośredniczących autora integracji, analityki i eksportu danych. **Integracja wymaga chmury producenta**, a nie działa lokalnie/offline.
- Połączenia HTTPS używają standardowej weryfikacji certyfikatów; przekierowania HTTP są blokowane.
- Hasło jest przechowywane przez mechanizm konfiguracji Home Assistant. Chroń `.storage` i kopie zapasowe; nie udostępniaj diagnostycznych logów bez kontroli.
- Brak automatycznych aktualizacji kodu z repozytorium upstream. Sprawdź [model zagrożeń](docs/SECURITY.md).

## v0.1.1 — jakość danych i diagnostyka

- Wartości temperatur poniżej -200°C (np. -273,1°C), typowo oznaczające brak pomiaru, stają się `unknown` zamiast zafałszowywać wykresy. Nie modyfikujemy historii zapisanej wcześniej w Recorder.
- Dwa sensory diagnostyczne: ostatni pomyślny odczyt i bieżący status odczytu z chmury. Status oznacza dostępność telemetrii, nie stan sprężarki ani status samego ogrzewania.
- **Diagnostyka wbudowana w HA:** zanonimizowana lista identyfikatorów capability, również nierozpoznanych. Nie zawiera wartości nieznanych parametrów, tokenów, loginów, nazw ani identyfikatorów urządzeń. Dostępna z menu integracji: **Pobierz diagnostykę**.
- Wszystkie dotychczasowe `unique_id` sensorów pozostają bez zmian.

## v0.2.0 — pełny wykaz parametrów API

- Identyfikujemy **wszystkie numery capability zgłoszone przez Atlantic**, także 6-cyfrowe (>65535).
- Eksport diagnostyczny zawiera rozdział na rozpoznane i nierozpoznane ID dla każdej wykrytej jednostki, bez surowych wartości, loginów, numerów seryjnych ani deviceId.
- Nowe sensory diagnostyczne: liczba rozpoznanych i nierozpoznanych parametrów.
- Gdy późniejsze odświeżenie API ujawni kolejny rozpoznany parametr, HA dodaje jego encję bez ponownej konfiguracji.
- Własne mapowanie bez zgadywania: dostępność danego ID to **nie** dowód, że wartości lub jednostki są poprawne dla konkretnego modelu.
- Dodatkowe odczyty pomp obiegowych (25,26,28,29) tylko tam, gdzie pompa je raportuje.

## v0.3.0 — monitoring sprężarki

- Wspiera odczyty producenta: liczba startów (24), czas pracy (27, sekundy), stan (51, 0/1) i modulacja (72, procent). Powstają tylko tam, gdzie dany model je raportuje.
- Sensory pochodne: licznik godzin pracy, **średni czas pracy na start obliczony z liczników całkowitych** oraz przyrosty startów i sekund od ostatniego poprawnego odczytu.
- Pierwszy odczyt po restarcie HA, długa luka, reset licznika i niewiarygodny przyrost → wartość `unknown`. Żadnych sztucznych startów.
- Nie ma funkcji sterowania pompą ani nowych wywołań API.
- Zobacz instrukcję [monitorowania sprężarki](docs/COMPRESSOR.md), w tym tworzenia statystyk dobowych przez Utility Meter w HA.

## Co odczytuje?

Integracja tworzy sensory **wyłącznie dla identyfikatorów, które pompa faktycznie raportuje**. Obejmuje m.in.:

| Identyfikator Atlantic | Odczyt |
| --- | --- |
| 24 | liczba uruchomień sprężarki |
| 27 | czas pracy sprężarki (wg API: sekundy) |
| 51 | stan sprężarki |
| 72 | modulacja sprężarki (%) |
| 44, 45, 46 | liczniki elektrycznego zużycia CO, CWU i łącznego, automatycznie przeliczone z Wh na kWh |
| 100 | ciśnienie wody |
| 109 | temperatura wody obiegu |
| 111 | temperatura CWU |
| 117, 118 | temperatura pokojowa stref |
| 119 | temperatura zewnętrzna |
| 6, 150, 180 | diagnostyczne kody błędów |

Uwaga: samo istnienie mapowania nie oznacza dostępności danej wielkości dla Alféa Extensa S Duo XL 10. Do potwierdzenia potrzebna jest próba odczytu rzeczywistego urządzenia. **COP i energia cieplna nie są obliczane bez wiarygodnych pomiarów. Wartości zużycia elektrycznego 44–46 mają w API jednostkę Wh i są prezentowane w kWh.**

## Instalacja (dopiero po przeglądzie PR)

1. Zrób kopię zapasową Home Assistant (kontrola importu wykonana na 2026.10.2).
2. **Wymaganie HACS:** standardowy HACS obsługuje tylko publiczne repozytoria GitHub. Dopóki `Atlantic-CozyTouch` jest prywatne, instalacja w HACS jako niestandardowe repozytorium nie będzie dostępna. Nie zmieniaj widoczności bez świadomej decyzji.
3. Po udostępnieniu repozytorium jako publicznego: *HACS → ⋮ → Niestandardowe repozytoria → URL → Integracja → Dodaj*, a następnie zainstaluj **Atlantic CozyTouch Read-Only** z gałęzi `main`. Release nie jest wymagany, gdy HACS wykorzystuje gałąź domyślną.
4. Uruchom ponownie HA, dodaj integrację w *Ustawienia → Urządzenia i usługi* i podaj dane konta Atlantic **tylko w lokalnym formularzu HA**.
5. Zweryfikuj dostępne encje i brak usług sterujących. Kod pozostaje **testową wersją 0.1.0**, dopóki nie zostanie sprawdzony na rzeczywistym urządzeniu.

**Alternatywa zachowująca prywatność repozytorium:** pobierz archiwum ZIP gałęzi `main` ze swojego GitHub i skopiuj folder `custom_components/atlantic_cozytouch` do `/config/custom_components/` na HA, po czym uruchom go ponownie. To instalacja ręczna (nie przez HACS).

## Zakres i ograniczenia v0.1.0

- Odczyt co 180 sekund, z obsługą błędów autoryzacji, HTTP 429 i problemów sieciowych.
- Brak dostępu LAN/Modbus; całkowicie zależna od chmury Atlantic.
- Brak osobnego endpointu historycznego zużycia; podstawowe liczniki energii pochodzą z bieżącego odczytu urządzenia.
- Nie gwarantujemy, że interfejs producenta pozostanie niezmienny ani że każde pole będzie dostępne.
- Brak automatycznych aktualizacji po stronie pompy, wprowadzania zmian czy odkrywania endpointów.

## Niezależna implementacja i licencja

Kod został napisany od podstaw dla projektu Atlantic-CozyTouch, bez kopiowania implementacji `gduteil/cozytouch`. Nazwy identyfikatorów i adresy interfejsu służą do zapewnienia interoperacyjności. Projekt nie jest powiązany z Atlantic. Kod własny na licencji MIT; zobacz [LICENSE](LICENSE).

## Testy

```bash
python -m unittest discover -s tests -v
python -m compileall -q custom_components tests
```
