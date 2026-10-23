# Model bezpieczeństwa i audyt — v0.1.0

## Granica zaufania

Home Assistant komunikuje się **bezpośrednio** z oficjalną usługą \`https://apis.groupe-atlantic.com\`. Nie ma dodatkowego serwera integracji. Połączenie jest szyfrowane TLS, a weryfikacja certyfikatów pozostaje domyślna.

## Reguły techniczne

| Operacja | Adres | Dozwolona |
| --- | --- | --- |
| Uwierzytelnianie | POST /users/token | Tak, niezbędne do odczytu |
| Stan urządzeń | GET /magellan/cozytouch/setupviewv2 | Tak |
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
- Weryfikacja, że encje mają tylko prefiksy \`sensor.\` i \`binary_sensor.\`.
- Monitorowanie dziennika HA po pierwszym uruchomieniu oraz pompy przez panel Atlantica.
- Brak automatycznego aktualizowania integracji do nieprzejrzanych wersji.

## Pochodzenie kodu

Projekt bazuje na obserwacji publicznie udokumentowanego zachowania interfejsu, ale nie kopiuje kodu źródłowego nieobjętego jawną licencją z repozytorium gduteil/cozytouch. Rozdział modułów i logika są niezależną implementacją.
