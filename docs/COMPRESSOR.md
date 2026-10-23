# Monitoring sprężarki Atlantic (v0.3.0)

## Warunki
Integracja nie zgaduje startów ani godzin pracy. Tworzy odczyty tylko gdy urządzenie raportuje identyfikatory 24 (liczba startów), 27 (czas pracy w sekundach), 51 (stan on/off), 72 (modulacja %).
Sprawdź **Ustawienia → Urządzenia i usługi → Atlantic CozyTouch Read-Only → Pobierz diagnostykę**: pole `compressor_capability_ids` dla właściwej jednostki.

## Nowe encje analityczne
- Czas pracy sprężarki — godziny: odczyt licznika 27 po przeliczeniu sekund na godziny.
- Średni czas pracy na start: **liczniki całkowite** 27/(60×24), a nie średnia tylko z dzisiejszego dnia.
- Przyrost uruchomień od ostatniego odczytu: różnica kolejnych poprawnych próbek licznika 24.
- Przyrost czasu pracy od ostatniego odczytu: różnica licznika 27 w sekundach.

Przy pierwszej próbce po restarcie Home Assistant, przerwie odczytów >15 min, resecie/zmniejszeniu licznika albo niefizycznej zmianie wartości przyrost jest `unknown` — nie zero.
Interwał 180 sekund nie pozwala precyzyjnie odtworzyć krótkich cykli pracy.

## Statystyki dobowe
Najbezpieczniej skonfigurować w Home Assistant **Pomocnicy → Licznik mediów (Utility Meter)**, wskazując jako źródło oryginalny całkowity licznik sprężarki i ustawiając okres **Dzienny**.
Dla startów wybierz encję z nazwą `Uruchomienia sprężarki`, a dla czasu encję `Czas pracy sprężarki` (jednostka sekundy). Po przeliczeniu w dashboardzie możesz prezentować godziny.
Zweryfikuj prawdziwe `entity_id` w HA — w zależności od urządzenia nazwy mogą się różnić. Nie używaj `starts_delta_last_poll` jako źródła Utility Meter, gdyż nie jest to licznik narastający.

## Kryteria odbioru
1. Potwierdź, że `24` i `27` występują w pobranej diagnostyce dla konkretnego urządzenia.
2. Porównaj całkowite liczby startów i czas pracy ze sterownikiem Atlantic.
3. Po restarcie HA nie pojawiają się sztuczne przyrosty startów.
4. Brak jakichkolwiek komend sterujących po stronie HTTP, HA i panelu.

### Ważne ograniczenie
Zielone testy GitHub Actions dowodzą zgodności składni, testów offline i importu, ale **nie dowodzą**, że Twoja pompa wystawia liczniki przez API.