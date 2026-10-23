# Atlantic CozyTouch v0.5.0 — raport prac 1–5

## Audyt danych i źródeł

Na fizycznej pompie Alféa Extensa S Duo XL 10 capability 164 = 1298 = 2+16+256+1024 deklaruje: elektryczność CO, elektryczność CWU, możliwość pomiaru produkcji ciepła CO i CWU. Jest to deklaracja funkcji, a nie gwarancja transmisji liczbowych pomiarów do chmury.

Dotychczasowy raport historii energii z tej instalacji: stan dostępna, **2 serie, 4 rekordy zużycia elektrycznego oraz zero liczbowych rekordów producedQuantity**. Trzeba ponowić odczyt i zbadać kategorie serii; są to liczby *rekordów*, nie kilowatogodziny.

ID 57 = 11629 i ID 59 = 7522 na wcześniejszym zrzucie przy ID91 = CWU. Przypuszczenie: ID57 to prąd CO, ID59 to prąd CWU, a wartość w Wh. Daje ono odpowiednio 11.629 i 7.522 kWh. Nie potwierdzono okresu, resetu i jednoznacznego znaczenia.

Zewnętrzny projekt [gduteil/cozytouch](https://github.com/gduteil/cozytouch) mapuje ID57/59 jako energię, a ID164 jako maskę możliwości pomiaru. W [decisions.md](https://github.com/gduteil/cozytouch/blob/main/docs/decisions.md) przykład z *innego* urządzenia pokazuje type=1/unit=1 jako energię elektryczną kWh. Nie jest to dowód mapowania serii CO i CWU tej pompy.

W upstream występuje nazwa COP przy ID107078, ale jest to typ przełączania kotła, **nie pomiar sprawności pompy ciepła**. Nie znaleziono potwierdzonego chwilowego COP dla tego modelu w standardowych capability. Bez wyprodukowanej energii cieplnej na tym samym przedziale co energia elektryczna nie wyliczamy COP.

## Zmiany programistyczne

- Nowe diagnostyczne sensory: **Hipoteza energii CO · ID 57** i **Hipoteza energii CWU · ID 59**. Warunkowo przeliczają Wh / 1000, bez statystyk Home Assistant. Brak wartości daje unknown, nie zero.
- Nowy status **COP Atlantic · gotowość danych**. Gdy brak produkcji cieplnej: brak danych. Gdy pojawi się dodatnia produkcja: do weryfikacji, nadal nie liczbowy COP.
- Dashboard Mushroom: [dashboards/atlantic_energy_diagnostic_0_5_0.yaml](../dashboards/atlantic_energy_diagnostic_0_5_0.yaml).
- Nie zmieniono oryginalnych unikalnych identyfikatorów, odczytów sprężarki, 57/59, ani historii energii.
- Testy walidują fałszywe zera, skrajne wartości, zakresy, maski i zabezpieczenie przed statystykami HA.

## Bezpieczeństwo

**Tylko odczyt**: poza autoryzacją POST /users/token wykorzystywane są GET /magellan/cozytouch/setupviewv2 i GET /magellan/setups/{setupId}/consumptions?periodicity=daily. Brak poleceń zmieniających stan pompy, usług i platform aktuatorów. Nie ma serwerów pośredniczących autora; integracja łączy się z chmurą producenta. Nie ma eksportu loginów, tokenów, numerów urządzeń, ani surowych danych energetycznych do diagnostyki.

Eksperymentalne sensory **nie mają** ani device_class=energy, ani state_class, więc nie stanowią legalnych danych dla Energy Dashboard / utility_meter / kosztów. W HA dostępne są w grupie diagnostycznej.

## Kontrola odbioru na prawdziwej pompie

1. Po bezpiecznej aktualizacji HA odczytaj stan i atrybuty encji **Historia energii Atlantic · test API** oraz **COP Atlantic · gotowość danych**.
2. Porównaj wartości z fizycznym sterownikiem dla **tego samego okresu**, najlepiej odczyt narastający w tym samym dniu oraz osobno za rok.
3. Sprawdź, czy ID57 i ID59 reagują na odpowiednio CO i CWU, gdzie następuje reset, i czy skala 1000 pasuje bez przesunięć.
4. Jeśli API udostępni producedQuantity, ustal: urządzenie, obieg, jednostkę, datę, poziom rozliczenia. Dopiero po tej walidacji wolno dodać sensory realnej produkcji ciepła i COP.
5. Zrób odbiór bezpieczeństwa w HA (brak usług sterujących) oraz sprawdź logi po 2–3 cyklach i po restarcie.

Bez rzeczywistych danych cieplnych COP pozostaje dostępny na wyświetlaczu sterownika lub w dzienniku odczytów; nie jest po prostu do pobrania przez obecną trasę API.

## Testy końcowe

GitHub Actions uruchamiają compileall, testy unittest, import do obrazu Home Assistant 2026.10.2 oraz kontrolę parsowania YAML. Zaliczony CI nie jest odpowiednikiem testu na pompie: finalny COP jest **nieweryfikowalny zdalnie bez nowych rekordów produkcji cieplnej**.
