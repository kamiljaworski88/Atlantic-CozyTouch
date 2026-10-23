# Procedura bezpiecznego testu na Home Assistant

**Nie przeprowadzaj testu bez uprzedniej kopii zapasowej HA i ukończonej kontroli PR/CI.**
Integracja nie wysyła poleceń sterujących, ale korzysta z konta Atlantic (przez chmurę producenta), więc test wymaga świadomego zalogowania.

## Faza A — test bez podłączania pompy

1. Sprawdź diff w PR oraz wynik testów offline i importu Home Assistant.
2. Potwierdź, że w źródle jedyne operacje HTTP to:
   - `POST https://apis.groupe-atlantic.com/users/token` (autoryzacja),
   - `GET https://apis.groupe-atlantic.com/magellan/cozytouch/setupviewv2` (odczyt).
3. Sprawdź, że nie ma platform `climate`, `switch`, `number`, `select`, `button` ani usług.
4. Sprawdź możliwość odinstalowania komponentu oraz zawartość backupu.

## Faza B — instalacja kontrolowana na HA 2026.10.x

Przed wykonaniem: najlepiej osobna instancja testowa. Jeśli używasz głównego HA, wybierz moment, gdy można go zrestartować bez zakłócenia automatyzacji.

1. Wykonaj **pełny backup** Home Assistant.
2. W GitHub otwórz gałąź `feat/read-only-v0.1.0`, pobierz ZIP przez **Code → Download ZIP**. Nie pobieraj gałęzi `main`, która na tym etapie nie ma integracji.
3. Ze ZIP skopiuj wyłącznie folder `custom_components/atlantic_cozytouch/` do `/config/custom_components/atlantic_cozytouch/`.
4. Zweryfikuj, że ścieżka zawiera `manifest.json`, `__init__.py`, `config_flow.py`, `sensor.py`, `binary_sensor.py`.
5. Uruchom ponownie Home Assistant. Sprawdź dziennik — nie powinno być błędów importowania `atlantic_cozytouch`.
6. W *Ustawienia → Urządzenia i usługi → Dodaj integrację* znajdź **Atlantic CozyTouch Read-Only**.
7. Zaloguj się kontem Atlantic, ale **nie podawaj hasła w wiadomościach, zrzutach ekranowych ani na GitHubie**.
8. Otwórz urządzenia/encje integracji. Oczekiwane domeny: wyłącznie `sensor` i `binary_sensor`; sensory diagnostyczne mogą być domyślnie niewidoczne w głównym widoku, sprawdź listę wszystkich encji.
9. Odczekaj 3–6 minut (1–2 cykle odczytu), sprawdź czy wartości się aktualizują. Nie zmieniaj w międzyczasie żadnych ustawień pompy.
10. Zweryfikuj ręcznie dostępne wartości: 24 (starty), 27 (sekundy pracy), 51 (stan sprężarki), 72 (modulacja), 44–46 (energia elektryczna w kWh), 119 (temperatura zewnętrzna).
11. Upewnij się, że integracja nie zarejestrowała żadnych encji sterujących i nie wpłynęła na krzywą grzewczą oraz temperatury nastaw.

## Faza C — akceptacja po pierwszym odczycie

Zgłoś wyłącznie:
- działanie integracji: OK / błąd;
- widoczne nazwy encji (bez identyfikatorów konta, numerów seryjnych, tokenów);
- porównanie 2–3 wartości z wyświetlaczem pompy, w szczególności licznika sprężarki i energii;
- zanonimizowane logi w przypadku błędu.

Brak sensora 24/27/51/72 oznacza, że **tego identyfikatora pompa nie raportuje w bieżącym API**; nie będziemy go zgadywać lub zastępować nieudokumentowanym zapisem.

## Wycofanie instalacji

1. W Home Assistant usuń integrację Atlantic CozyTouch Read-Only (nie aplikację Atlantic).
2. Usuń katalog `/config/custom_components/atlantic_cozytouch/`.
3. Uruchom ponownie Home Assistant.
4. Gdyby HA zachowywał się nieprawidłowo — przywróć wykonany backup.

Operacje te nie zmieniają ustawień samej pompy. Reset fabryczny pompy nie jest potrzebny.

## Granice gwarancji

Nie ma niezależnego konta Atlantic z uprawnieniami wyłącznie do odczytu; integracja ogranicza operacje **w kodzie**, nie na poziomie uprawnień chmury. Jeśli ktoś w przyszłości podmieni kod integracji, może zmienić tę właściwość. Instaluj wyłącznie przejrzane wersje.
