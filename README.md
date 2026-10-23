# Atlantic CozyTouch — Read-Only for Home Assistant

Nieoficjalna, niezależna integracja Home Assistant do **monitorowania** urządzeń Atlantic przez **oficjalne API Atlantic**.

> **Wersja 0.1.0 jest przeznaczona do testów. Nie instaluj jej bez uprzedniego przeglądu kodu oraz wykonania kopii zapasowej Home Assistant.**

## Bezpieczeństwo

- Brak sterowania pompą: **nie ma** encji typu `climate`, `number`, `switch`, `select`, `button` ani usług zapisujących ustawienia.
- Warstwa sieciowa dopuszcza jedynie `POST https://apis.groupe-atlantic.com/users/token` (logowanie) oraz `GET https://apis.groupe-atlantic.com/magellan/cozytouch/setupviewv2` (odczyt).
- Bez serwerów pośredniczących autora integracji, analityki i eksportu danych. **Integracja wymaga chmury producenta**, a nie działa lokalnie/offline.
- Połączenia HTTPS używają standardowej weryfikacji certyfikatów; przekierowania HTTP są blokowane.
- Hasło jest przechowywane przez mechanizm konfiguracji Home Assistant. Chroń `.storage` i kopie zapasowe; nie udostępniaj diagnostycznych logów bez kontroli.
- Brak automatycznych aktualizacji kodu z repozytorium upstream. Sprawdź [model zagrożeń](docs/SECURITY.md).

## Co odczytuje?

Integracja tworzy sensory **wyłącznie dla identyfikatorów, które pompa faktycznie raportuje**. Obejmuje m.in.:

| Identyfikator Atlantic | Odczyt |
| --- | --- |
| 24 | liczba uruchomień sprężarki |
| 27 | czas pracy sprężarki (wg API: sekundy) |
| 51 | stan sprężarki |
| 72 | modulacja sprężarki (%) |
| 44, 45, 46 | energia/zużycie CO, CWU i łączne (jeśli raportowane) |
| 100 | ciśnienie wody |
| 109 | temperatura wody obiegu |
| 111 | temperatura CWU |
| 117, 118 | temperatura pokojowa stref |
| 119 | temperatura zewnętrzna |
| 6, 150, 180 | diagnostyczne kody błędów |

Uwaga: samo istnienie mapowania nie oznacza dostępności danej wielkości dla Alféa Extensa S Duo XL 10. Do potwierdzenia potrzebna jest próba odczytu rzeczywistego urządzenia. **COP i energia cieplna nie są obliczane bez wiarygodnych pomiarów.**

## Instalacja (dopiero po przeglądzie PR)

1. Zrób kopię zapasową Home Assistant (testowana docelowa wersja: 2026.10.x).
2. Zainstaluj jako **niestandardowe repozytorium integracji HACS**: `https://github.com/kamiljaworski88/Atlantic-CozyTouch` (prywatne repo może wymagać dodatkowego dostępu HACS).
3. Po udostępnieniu wydania na `main`, dodaj integrację **Atlantic CozyTouch Read-Only** przez *Ustawienia → Urządzenia i usługi*.
4. Podaj dane do konta Atlantic Cozytouch (nie podawaj ich w issues, PR-ach ani czacie).
5. Sprawdź encje oraz brak usług sterujących.

Alternatywnie po zatwierdzeniu kodu skopiuj `custom_components/atlantic_cozytouch` do katalogu `config/custom_components/` i uruchom ponownie HA.

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
