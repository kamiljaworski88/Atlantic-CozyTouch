# Atlantic CozyTouch v0.5.8 — walidacja COP (25.10.2026)

## Co zmieniamy
Integracja nadal wyłącznie **monitoruje** pompę Atlantic przez oficjalną
chmurę producenta. COP hydrauliczny jest **eksperymentalną hipotezą**, nie
odczytem gwarantowanym przez Atlantic i nie miernikiem sprawności sezonowej.
Nie dodano endpointów, komend sterowania, eksportu prywatnych danych ani
liczników energii cieplnej.

### Krytyczne zabezpieczenie topologii
W dostępnym wcześniej snapshotcie pompy przepływ ID112 i temperatury
zasilania/powrotu ID109/116 mogą pochodzić z różnych logicznych urządzeń
Magellan. Samo istnienie po jednym takim urządzeniu nie dowodzi wspólnej
pętli hydraulicznej. Od v0.5.8 kalkulator zwraca
`niepotwierdzone_powiazanie_obiegu` i **nie** liczy COP dla takich danych.

Nie należy obchodzić tej kontroli przez kopiowanie `deviceId` lub łączenie
wartości według nazwy urządzenia. W przyszłości dopuszczalne jest jawne
mapowanie *tylko po udokumentowanej walidacji instalacji i po testach*.

### Walidacja czasów
Sprawdzamy pochodzące z API `modificationDate` dla ID91 (wybrany obieg),
112 (przepływ), 109/116 (temperatury), oraz 57 lub 59 (elektryczność).
Każdy znacznik musi być świeży (do 900 s względem aktualnego czasu), a
różnica najstarszego i najnowszego w jednym snapshotcie nie przekracza
180 s. Nie zastępujemy czasu producenta zegarem lokalnego pollingu.

Moc elektryczna to `3.6 * delta_raw_Wh / delta_vendor_seconds`, tylko dla
ciągłego przyrostu na jednym obiegu w przedziale 120–1200 sekund.
W tym wzorze jednostka Wh oraz przypisanie 57/59 są nadal hipotezą
transportową opartą na porównaniu ze sterownikiem. Odczyty mogą być
opóźnione i zgrupowane przez chmurę.

Moc cieplna według wzoru dla **wody** to
`(4.186 / 60) * przeplyw_l_na_min * (zasilanie_C - powrot_C)`.
Przy obliczaniu ilorazu za okres stosujemy średnią z wartości cieplnej na
obu końcach przedziału, a nie tylko ostatni snapshot. Nie jest to dokładna
całka w okresie; w przypadku defrostu lub grzałek wynik może być mylący.

## Dlaczego jeszcze nie ma miesięcznego COP?
Sterownik pokazał pobór 26/10 kWh i wyprodukowane ciepło 76/36 kWh dla
CO/CWU. ID57 i ID59 odpowiadają prawdopodobnie poborowi energii, jednak
publiczne Magellan API nadal nie udostępniło potwierdzonych wartości
**wytworzonego ciepła** i przypisanego okresu.

W danych historii pole `producedQuantity` może opisywać inne rodzaje
produkcji, w tym energię elektryczną. W v0.5.8 podajemy tylko liczbę
rekordów, w których współwystępują dodatnie liczby `consumedQuantity` i
`producedQuantity`. Taka para **nie dowodzi** tej samej kategorii fizycznej,
jednostek, daty ani pochodzenia z tej samej pompy; pomiar ciepła jest
nadal **niezweryfikowany**.

## Warunki uruchomienia wiarygodnego COP okresowego
1. Jednoznaczny licznik wyprodukowanych kWh ciepła CO i/lub CWU,
   oznaczony jako energia cieplna przez producenta lub niezależnie
   zweryfikowany na instalacji.
2. Jednoznaczny pobór energii elektrycznej przypisany do tego samego
   obiegu oraz tego samego **dokładnego** okresu rozliczeniowego.
3. Testy skali i resetów liczników (miesiąc/dzień/cykl/całe życie),
   taryf, brakujących okresów, ponowionych próbek, odszraniania i grzałek.
4. Porównanie z ekranem sterownika z uwzględnieniem zaokrągleń i
   synchronizacji czasu.
5. Dopiero wtedy można dodać liczbowy COP CO/CWU/suma. Bez potwierdzonych
   pomiarów należy prezentować `unknown`, a nie wartość z ekranu
   przepisana na stałe.

## Test odbiorczy w HA
- Wykonaj pełną kopię zapasową; do testów użyj gałęzi PR, nie instaluj
  niezweryfikowanej wersji jako stabilnej.
- Sprawdź `COP Atlantic · status obliczeń`. Gdy czujniki należą do
  różnych urządzeń, oczekuj `niepotwierdzone_powiazanie_obiegu`
  i `COP Atlantic · szacunkowy = unknown`.
- Dla niezsynchronizowanych `modificationDate` spodziewany status to
  `niespojne_czasy_probek`.
- W sensorze `Historia energii Atlantic · miesięczna kontrola`
  można zobaczyć anonimowe liczby par poboru/produkcji; wartości kWh
  nie są publikowane.
- `COP Atlantic · gotowość danych` powinien wykazywać
  `rekordy_produkcji_ciepla: null` i
  `produkcja_ciepla_zidentyfikowana: false`.
- Sprawdź, czy ID, sekrety i surowe payloady nie pojawiają się w
  diagnostyce oraz czy istniejące encje zachowały swoje `unique_id`.

## Testy automatyczne
`python -m unittest discover -s tests -v`; CI wykonuje także
`compileall` i import modułów na obrazie HA 2026.10.2.
Zielony CI weryfikuje kod, **nie dostępność producenta ani hydraulikę**.
