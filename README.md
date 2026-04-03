# FPP KSeF Export (Legacy)

Eksporter faktur z systemu FPP (Clarion DOS 3.x) do formatu KSeF FA(3) XML,
kompatybilny z **Aplikacją Podatnika 2.0** (Ministerstwo Finansów).

## Przeznaczenie

Narzędzie legacy do obsługi **Centrum Dystrybucji Naukowej (CDN)** w roku
obrachunkowym 2025/2026. Odczytuje bazy danych Clarion DOS (TRANHEAD.DAT,
TRANELEM.DAT) i generuje faktury XML zgodne ze schematem FA(3) KSeF.

## Wymagania

- Python 3.8+
- tkinter (wbudowany w standardową instalację Python)
- Brak zewnętrznych zależności

## Konfiguracja

1. Skopiuj `config.json.example` do `config.json`
2. Uzupełnij dane sprzedawcy (NIP, adres), konto bankowe i ścieżki do plików DAT
3. Uruchom:

```bash
python fpp_ksef_export.py
```

## Format bazy danych

Aplikacja odczytuje pliki binarne Clarion DOS 3.x:

- **TRANHEAD.DAT** — nagłówki faktur (dane kontrahenta, daty, sumy)
- **TRANELEM.DAT** — pozycje faktur (produkty, ilości, ceny)
- **MATERIA.DAT** — katalog produktów (opcjonalnie, do PKWiU)

Kodowanie tekstu: Mazovia (DOS Polish).

## Uwagi

- Na Windows można zmienić rozszerzenie na `.pyw` aby ukryć okno konsoli
- Reguły GTU w kodzie (sekcja `GTU_RULES`) wymagają dostosowania
  do asortymentu firmy — domyślne reguły są przykładowe
- Plik `exported.json` tworzony jest automatycznie jako rejestr
  wyeksportowanych faktur
- Schemat KSeF FA(3) obowiązuje od 1 lutego 2026

## Licencja

Kod udostępniony do użytku edukacyjnego i osobistego.
