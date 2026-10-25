# COP Atlantic 0.5.10 — praktyczny odbiór na Extensa S Duo XL 10 WiFi

## Dlaczego 0.5.9 nie wyświetlała COP?
API Magellan pokazuje co najmniej dwa logiczne moduły pompy: interfejs z
ID57,59,91,112 oraz generator z ID109,116. W 0.5.8 wprowadzono blokadę
przed automatycznym, niezweryfikowanym połączeniem źródeł. Bez połączenia
brak dostępnej pary przepływ–temperatura i brak COP hydraulicznego.

Drugi problem: pole `modificationDate` przy ID91 oznacza czas ostatniej
**zmiany obiegu** CO/CWU, a nie czas ostatniego pomiaru. Starszy znacznik
sam w sobie nie jest problemem. 0.5.10 zachowuje porównanie znacznika
zmiany obiegu między pomiarami, nie wymaga odświeżania trybu co 15 min.

## Co pozwala wykonać 0.5.10?
Przy świadomym włączeniu opcji `experimental_cross_device_cop` integracja
może obliczać **eksperymentalny COP hydrauliczny** z jednej jedynej pary
modułów. To **nie** dowodzi fizycznego powiązania tych modułów w instalacji
ani prawdziwego COP odczytanego z urządzenia. Przy dodatkowym obiegu lub
kilku pompach nadal nie da się nic obliczyć.

1. Zrób pełną kopię zapasową HA i zainstaluj tylko po kontroli kodu.
2. Po aktualizacji integracji i restarcie HA wejdź w Ustawienia →
   Urządzenia i usługi → Atlantic CozyTouch → Konfiguruj/Opcje.
3. Włącz checkbox **„Włącz eksperymentalny COP między jedyną parą
   modułów”**, jeżeli wiesz, że interfejs i generator dotyczą jednej
   fizycznej pompy. Zapisz. HA przeładuje integrację.
4. W Narzędziach deweloperskich → Stany znajdź sensor
   `COP Atlantic · status obliczeń` (rzeczywista nazwa encji może być
   prefiksowana nazwą urządzenia). Sprawdź `topologia_zrodel`
   oraz `wiek_probek_s`.
5. Gdy pompa **aktywnie grzeje** i zmienia się licznik prądu, po co
   najmniej dwóch zsynchronizowanych odczytach zobacz
   `COP Atlantic · szacunkowy`. Gdy pompa jest wyłączona/bez ΔT,
   zobacz `brak_aktywnego_grzania` i stan `unknown`.
6. W sensorze `COP Atlantic · ostatni poprawny szacunek (12 h)`
   znajdziesz ostatni poprawny wynik, jeśli taki powstał wcześniej
   w tej sesji integracji. Wynik wygasa po 12h i nie jest COP bieżącym.

## Kiedy COP jest odrzucany?
- Wyłączona opcja, ale różne moduły:
  `niepotwierdzone_powiazanie_obiegu`.
- Odczytów jest więcej niż jedna pasująca para:
  `brak_jednoznacznych_zrodel`.
- Brak przepływu 2–80 l/min: `brak_przeplywu_lub_wartosc_poza_zakresem`.
- Zasilanie – powrót około 0°C: `brak_aktywnego_grzania`;
  zbyt mała lub odwrócona ΔT: `delta_t_niewiarygodna`.
- Opóźniona telemetria: `nieaktualne_pomiary_hydrauliczne` albo
  `niespojne_czasy_probek`; atrybut `wiek_probek_s` mówi, które pole.
- Licznik ID57/59 nie wzrósł:
  `oczekiwanie_na_przyrost_energii`. To nie COP = 0.
- CO/CWU przełączono podczas okna:
  `zmiana_trybu_pracy`; trzeba zebrać nowe próbki.
- Wypada bezpieczny przedział pomiaru 2–20 minut lub reset:
  nie ma liczbowego COP do czasu zebrania kolejnych próbek.

## Jak liczony jest szacunek?
```
Moc cieplna [kW] = (4.186 / 60) × przepływ [l/min] × (T_zasilania - T_powrotu) [K]
Pobór [kW] ~ wzrost rawWh ID57 lub ID59 × 3.6 / odstęp_s
COP szacunkowy = średnia mocy cieplnej na końcach okresu / pobór [kW]
```

**Ograniczenia**: jednostka Wh i reset ID57/59 nie są pomiarem
rozliczeniowo potwierdzonym. Woda z glikolem zmienia pojemność cieplną.
Brak bezpośredniego pomiaru zasilania elektrycznego sprężarki, grzałek,
odszraniania. Wyprodukowane ciepło w kWh dla miesiąca nadal nie jest
jednoznacznie dostępne z chmury. Dodatni wynik to tylko eksperymentalny
szacunek w okresie aktywnego grzania. Żadnego `state_class` ani integracji
z HA Energy dla COP.

## Co bezpiecznie przesłać do analizy?
Wyłącznie stan `COP Atlantic · status obliczeń` oraz jego atrybuty
`topologia_zrodel` i `wiek_probek_s`; dodatkowo odczyty
temperatur obiegu (ID109/116) i przepływu (ID112) podczas grzania.
Nie wysyłaj loginów, tokenów, numeru seryjnego ani deviceId.

Nie wolno zakładać, że w danej chwili jest wytwarzane ciepło tylko
dlatego, że aktywny obieg pokazuje „CO”. Na przedstawionym ekranie
25,8°C – 25,7°C = 0,1 K, a więc brak warunków do wiarygodnego COP.
