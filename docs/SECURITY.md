# Model bezpieczeństwa i audyt — v0.1.0

## Granica zaufania

Home Assistant komunikuje się **bezpośrednio** z oficjalną usługą `https://apis.groupe-atlantic.com`. Nie ma dodatkowego serwera integracji. Połączenie jest szyfrowane TLS, a weryfikacja certyfikatów pozostaje domyślna.

## Reguły techniczne

| Operacja | Adres | Dozwolona |
| --- | --- | --- |
| Uwierzytelnianie | POST /users/token | Tak, niezbędne do odczytu |
| Stan urządzeń | GET /magellan/cozytouch/setupviewv2 | Tak |
| Parametry sprężarki | GET /magellan/capabilities/?deviceId={accountDevice} | Tak, tylko ID z konta, maks. co 15 min |
| Historia miesięczna | GET /magellan/setups/{accountSetupId}/consumptions?periodicity=monthly | Tak, maks. co 6 godzin |
| Zmiana nastaw / trybów | dowolny endpoint | **Nie** |
| Komendy serwisowe | dowolny endpoint | **Nie** |
| Wysyłka do innych hostów | dowolny | **Nie** |

Kod **nie implementuje** funkcji wysyłającej komendy sterujące. Brak też usług HA i encji sterujących. Aplikacja mobilna Atlantic nadal może sterować urządzeniem poza Home Assistant.

## Ryzyka pozostające

1. API chmurowe nie ma potwierdzonej stabilnej specyfikacji; może się zmienić.
2. Konto i hasło pozostają w pamięci integracji i mechanizmie config entries HA, zgodnie z zasadami Home Assistant. Wyciek backupu lub administrator HA może je ujawnić.
3. API może odrzucić wielokrotne logowania lub odczyty. Polling wynosi 180 s; HTTP 429 nie powoduje aktywnego retry-loop.
4. Odczytowe endpointy producenta nie dają kryptograficznie ograniczonego uprawnienia *read-only*. Ograniczenie jest egzekwowane przez **nasz kod**, nie przez konto Atlantic. Każda późniejsza zmiana kodu wymaga ponownego audytu.
5. Lista encji może zależeć od firmware i udostępnionych danych. Brak możliwości zweryfikowania aktualnych liczników bez bezpiecznego testu na urządzeniu.
6. Każda biblioteka (w tym sam HA, aiohttp) oraz chmura Atlantic podlega własnym ryzykom. Nie ma gwarancji absolutnego bezpieczeństwa.

## Wymagania przed instalacją produkcyjną

- Przegląd zmian PR i logów CI.
- Kopia zapasowa Home Assistant.
- Brak publikacji danych logowania, tokenów, numerów urządzenia w zgłoszeniach.
- Weryfikacja, że encje mają tylko prefiksy `sensor.` i `binary_sensor.`.
- Monitorowanie dziennika HA po pierwszym uruchomieniu oraz pompy przez panel Atlantica.
- Brak automatycznego aktualizowania integracji do nieprzejrzanych wersji.

## Pochodzenie kodu

Projekt bazuje na obserwacji publicznie udokumentowanego zachowania interfejsu, ale nie kopiuje kodu źródłowego nieobjętego jawną licencją z repozytorium gduteil/cozytouch. Rozdział modułów i logika są niezależną implementacją.

## Audyt rozszerzony — 23.10.2026

### Rzeczywista granica HTTP
- Centralny filtr `AtlanticReadOnlyClient._request` zezwala tylko na `POST https://apis.groupe-atlantic.com/users/token` (logowanie) oraz dokładnie dopuszczone `GET` odczytu instalacji, historii energii i parametrów pompy przypisanej do zalogowanego konta.
- Nieprawidłowa metoda lub URL są odrzucane **przed** jakimkolwiek żądaniem.
- Brak przekierowań HTTP, brak możliwości ustawienia `ssl=False` lub parametru proxy przez metodę żądania.
- HTTP 429: wstrzymanie odczytu na 5–60 min zgodnie z `Retry-After`, z domyślną przerwą 15 min.
- Ograniczenie przetwarzania do 128 urządzeń i 1024 parametrów na urządzenie; nieznane identyfikatory nie są publikowane.

### Scenariusze testowe
Testy bez połączenia z producentem obejmują: odmowę wysłania niedozwolonego `POST` do endpointu sterowania, odmowę komunikacji z obcym hostem, wymuszone przekierowanie, błędne logowanie, wygaśnięcie tokenu, HTTP 429, nieprawidłowe dane z chmury, ograniczenia rozmiaru odpowiedzi i poprawne jednostki energii. Dodatkowy workflow importuje komponent na oficjalnym obrazie HA 2026.10.2.

### Ważne ograniczenia
- Konto Atlantic **nie jest kontem read-only**. Token może mieć uprawnienia pozwalające na zapis, lecz ten kod nie wykonuje takich operacji. Każda późniejsza aktualizacja wymaga ponownego audytu.
- Filtr działa na poziomie kodu integracji; nie jest zaporą sieciową i nie audytuje innych dodatków Home Assistant.
- Integracja nie tworzy serwerów pośredniczących autora, ale sieć hosta/ISP może korzystać z własnej infrastruktury pośredniej.
- Nie przeprowadzono jeszcze testów z rzeczywistą pompą ani niezależnego audytu penetracyjnego. Zielony CI nie dowodzi kompatybilności urządzenia.
