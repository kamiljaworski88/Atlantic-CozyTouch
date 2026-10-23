# Atlantic CozyTouch — plan rozwoju produktu

Projekt jest **wyłącznie do odczytu**. Oficjalna chmura Atlantic jest jedynym punktem komunikacji z producentem. Nie instalujemy żadnego serwera pośredniczącego.

Każdy etap ma osobne issue; funkcje powstają na gałęziach i wymagają testów oraz PR przed połączeniem z `main`. Kolejne wydania nie muszą mieć ustalonych dat, ponieważ dostępność danych zależy od API producenta.

| Wersja | Cel | Zgłoszenie |
|---|---|---|
| 0.1.1 | Poprawność temperatur, stabilne encje, monitoring łączności | [#2](https://github.com/kamiljaworski88/Atlantic-CozyTouch/issues/2) |
| 0.2.0 | Identyfikacja urządzeń, odkrywanie parametrów, anonimowa diagnostyka | [#3](https://github.com/kamiljaworski88/Atlantic-CozyTouch/issues/3) |
| 0.3.0 | Starty i czas pracy sprężarki, analiza taktowania | [#4](https://github.com/kamiljaworski88/Atlantic-CozyTouch/issues/4) |
| 0.4.0 | Energia i koszty CO/CWU, Energy Dashboard | [#5](https://github.com/kamiljaworski88/Atlantic-CozyTouch/issues/5) |
| 0.5.0 | Smart Adapt i analiza temperatur | [#6](https://github.com/kamiljaworski88/Atlantic-CozyTouch/issues/6) |
| 0.6.0 | Dashboardy, alerty i raporty | [#7](https://github.com/kamiljaworski88/Atlantic-CozyTouch/issues/7) |
| 0.7.0 | Hardening, CI i migracje | [#8](https://github.com/kamiljaworski88/Atlantic-CozyTouch/issues/8) |
| 1.0.0 | Stabilna wersja HACS po weryfikacji rzeczywistych urządzeń | [#9](https://github.com/kamiljaworski88/Atlantic-CozyTouch/issues/9) |

## Bramy jakości

- Brak komend sterowania pompą we wszystkich wersjach i test blokady wywołań HTTP.
- Weryfikacja nowych identyfikatorów i jednostek przed publikacją nowych sensorów.
- Żaden nieznany parametr nie może być fałszywie opisany jako COP, praca sprężarki lub temperatura.
- Zmiany w `unique_id` wymagają migracji i jawnej decyzji.
- Diagnostyka nie wysyła danych poza HA i nie pokazuje sekretów.
- Przed stabilnym wydaniem test z Alféa Extensa S Duo XL 10 oraz potwierdzenie dokładności odczytów.

## Bieżąca walidacja produktu

v0.3.0: integracja dynamicznie wykrywa możliwości urządzeń. Raport Extensa S Duo XL 10 potwierdził **brak** standardowych ID sprężarki 24/27/51/72 przy tym odczycie. Nie wolno tworzyć sztucznych liczników sprężarki z pomp obiegowych.

v0.4.0: diagnostyczne sondy wartości 57/59/60/112 i mapowanie trybów 91/153/181. Dopiero po porównaniu surowych danych z pomiarami i stabilności liczników można stworzyć narastające sensory kWh i włączyć je do Energy Dashboard. Bez kalibracji i wskazania jednostek nie uznajemy tej części roadmapy za zamkniętą.
