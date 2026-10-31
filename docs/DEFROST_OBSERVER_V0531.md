# Atlantic Extensa S Duo XL 10 — obserwator defrostu z samego API (v0.5.31)

## Status

**Zaimplementowane:** diagnostyczny obserwator wyłącznie z istniejących odczytów Magellan/CozyTouch i wizualizacja w panelu `PC Atlantic`, bez dodatkowego termometru na jednostce. **Niezaimplementowane:** żadna aktywacja Shelly lub przewodu grzejnego. Nie ma potwierdzonej flagi defrostu.

Realny eksport HA v0.5.30 z 31.10.2026 potwierdził brak capability 65 (fan), 51 (kompresor) i 72 (modulacja) w 5 modułach `setupviewv2`; są natomiast 91, 109, 116, 119 i 181. Kod 380 to diagnostyka błędu, nie odszranianie.

## Jak działa

- Dotychczasowy odczyt chmurowy co **180 s**, bez zmiany endpointów ani dodatkowych żądań.
- Wybiera urządzenie, które w **tej samej** strukturze ma 109 (temperatura zasilania) i 116 (temperatura powrotu). Przy 0 lub więcej niż 1 takiej parze zwraca `unknown` zamiast łączyć przypadkowe urządzenia.
- `ΔT = T_zasilania − T_powrotu` (°C). Dodatkowo pobiera jednoznaczne 119 (zewnętrzna), 91 (CO/CWU) i 181 (tryb), traktując te wartości wyłącznie jako kontekst, **nie jako próbki zsynchronizowane**.
- W pamięci najwyżej 240 odczytów; w atrybutach sensora do 8 ostatnich anonimowych obserwacji. Home Assistant Recorder może zapisywać zmiany obu encji, jeśli nie są wykluczone z historii.
- **Hipoteza** pojawia się wyłącznie, gdy co najmniej dwa kolejne odczyty w odstępie do 12 minut pokazują `ΔT ≤ −0,8°C`, obieg CO, temperaturę otoczenia ≤7°C oraz przynajmniej jedną zmianę wartości hydraulicznej w ostatnich 15 min. Progi są eksperymentalne, nie z dokumentacji producenta.
- Obecne dane nie pozwalają potwierdzić defrostu: `defrost_potwierdzony: false` i `sygnal_do_sterowania: false` **zawsze**. Samo ujemne ΔT może oznaczać też inny stan pracy.
- `modificationDate` jest czasem ostatniej **zmiany wartości**, a nie fizycznego pomiaru. Obserwator podaje osobno czas odebrania danych przez HA oraz wiek ostatniej zmiany.
- Brak danych, sentinele temperatury, wiele źródeł i problemy łączności nigdy nie stają się sztucznym zerem ani sygnałem sterującym.
- Brak dostępu do identyfikatorów instalacji, nazw urządzeń, tokenów, haseł w atrybutach i w buforze obserwatora.

## Encje i dashboard

1. `Atlantic · obserwator odszraniania` — diagnostyczny sensor tekstowy. Stan `obserwacja`, `brak_jednoznacznej_pary_temperatur`, `brak_waznych_temperatur` lub `hipoteza_odszraniania_niepotwierdzona`.
2. `Atlantic · różnica temperatur zasilanie minus powrót` — liczbowy °C, do wykresów historii i ręcznego przeglądu.
3. Panel boczny `PC Atlantic` pokazuje sekcję „❄️ Odszranianie — obserwacja API” oraz wykres ΔT 24 h. Wyszukuje encje po fragmentach nazw, zamiast narzucać `entity_id`.

Instalacja: backup HA → aktualizacja kodu repo do v0.5.31 → restart lub przeładowanie integracji → panel `PC Atlantic` i nowe encje w Urządzeniach/Stanach. Zmiany NIE ingerują w ręcznie stworzone dashboardy Lovelace; do nich można dodać nowe sensory osobno.

## Protokół walidacji przed sterowaniem

1. Przy pierwszych 5 rzeczywistych defrostach zapisać ręcznie przybliżone momenty początku i końca oraz przebieg wentylatora i wody bez dotykania urządzenia.
2. Porównać historię ΔT z momentami rzeczywistego odszraniania; odnotować również dłuższe postoje i CWU.
3. Policz fałszywe alarmy, przeoczenia i latencję. **Jeżeli nie mamy stabilnej, zweryfikowanej detekcji, nie podpinać tej encji do Shelly.**
4. Ze względu na 180 s polling i asynchroniczną aktualizację chmury włączenie kabla „dokładnie przy defroście, plus 10 minut” może nie być niezawodne nawet po dostrojeniu progów.

## Sterowanie Shelly według temperatury — osobny etap

Użytkownik ma zewnętrzny termometr i Shelly Plug S. Wstępne założenia ochrony skroplin: włączanie przy <+3°C, wyłączanie po bezpiecznej histerezie np. >+5°C; roboczy limit 45 min oraz dogrzewanie po defroście wymagają dodatkowej decyzji. W obecnym pakiecie **nie ma automatyzacji przełączającej gniazdko**: nie znamy zweryfikowanych identyfikatorów encji urządzeń ani sposobu przyłączenia kabla; nie ma też gwarancji działania przy awarii HA/Internetu. Nie wolno przedstawiać chmurowej heurystyki jako ochrony przed zamarznięciem.

Przed automatyzacją: sprawdzić instrukcję kabla, dopuszczalność montażu w mokrej tacy i rurze, zabezpieczenia 230 V, działanie Shelly poza domem, zasady ochrony w dłuższym mrozie, niezależny fallback oraz rzeczywiste `entity_id` termometru i Shelly.

## Offline tests

```
python -m unittest discover -s tests -p "test_defrost_observer.py" -v
```

Testy obejmują brak urządzenia, niejednoznaczność par, uszkodzone pomiary, brak 65/51/72, wymaganie dwóch próbek, ograniczenie wieku zmiany, brak trybu CO, ograniczony bufor, brak danych osobowych i brak potwierdzonej flagi.

Zmiany integracji są read-only, nie zwiększają liczby żądań HTTP, nie zapisują historii do osobnego pliku, nie udostępniają `switch`/sterowania i nie modyfikują innych źródeł COP ani historii energii.
