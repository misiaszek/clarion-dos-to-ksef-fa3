# 🚀 Clarion DOS to KSeF FA(3) Exporter

**"Legacy Meets Modernity"** – Reanimacja systemów DOS dla Krajowego Systemu e-Faktur (A.D. 2026)

Ten program to lekki, napisany w Pythonie most (connector), który wyciąga dane
z archiwalnych baz danych Clarion 3.x (pliki `.DAT`) – używanych m.in.
w legendarnym systemie **CDN FPP** – i konwertuje je do nowoczesnego formatu XML
zgodnego ze strukturą KSeF FA(3).

## 🛠️ Dlaczego to powstało?

W 2026 roku wiele firm wciąż korzysta z systemów DOS-owych ze względu na ich
niesamowitą szybkość obsługi klienta ("klawiatura-only"). Zamiast wydawać
dziesiątki tysięcy na nowe systemy ERP, ten skrypt pozwala zostać przy
sprawdzonych rozwiązaniach, spełniając jednocześnie wymogi Ministerstwa Finansów.

## ✨ Kluczowe funkcje

- **Bezpośredni odczyt plików .DAT** — Obsługa niskopoziomowa formatów Clarion
  (BCD, DECIMAL, specyficzne daty od 1800 r.).
- **Kodowanie Mazovia** — Pełna tablica mapowania polskich znaków z DOS na UTF-8.
- **Inteligentne GTU** — Automatyczna klasyfikacja kodów towarowych
  (np. elektronika GTU_06) na podstawie Twoich reguł w Pythonie.
- **Zgodność z FA(3)** — Generuje gotowe pliki XML do wczytania
  w Aplikacji Podatnika 2.0.
- **AI-Powered** — Kod opracowany przy wsparciu LLM w rekordowe 4 dni.

## 🚀 Jak wyeksportować fakturę z FPP do KSeF?

### Przygotowanie (jednorazowe)

1. Zainstaluj Python 3.8+ (jeśli nie masz — [python.org](https://www.python.org/downloads/))
2. Skopiuj `config.json.example` do `config.json`
3. Uzupełnij w `config.json`:
   - dane sprzedawcy (NIP, nazwa, adres)
   - numer konta bankowego (pojawi się na fakturach z odroczonym terminem)
   - ścieżki do plików `TRANHEAD.DAT` i `TRANELEM.DAT` z katalogu FPP

### Codzienna praca

1. Wystaw fakturę w FPP jak zwykle
2. Uruchom eksporter:

```bash
python fpp_ksef_export.py
```

3. W oknie programu wybierz fakturę z listy (najnowsze na górze)
4. Sprawdź podgląd — dane nabywcy, pozycje, kwoty
5. Kliknij **Export to KSeF XML** i zapisz plik `.xml`
6. Otwórz [Aplikację Podatnika 2.0](https://www.podatki.gov.pl/ksef/) i wczytaj wygenerowany XML
7. Zweryfikuj i wyślij fakturę do KSeF

Wyeksportowane faktury oznaczane są ✓ na liście, a rejestr zapisywany jest
w `exported.json` (tworzony automatycznie).

## Wymagania

- Python 3.8+
- tkinter (wbudowany w standardową instalację Python)
- Brak zewnętrznych zależności

## Format bazy danych

Aplikacja odczytuje pliki binarne Clarion DOS 3.x:

- **TRANHEAD.DAT** — nagłówki faktur (dane kontrahenta, daty, sumy)
- **TRANELEM.DAT** — pozycje faktur (produkty, ilości, ceny)
- **MATERIA.DAT** — katalog produktów (opcjonalnie, do odczytu PKWiU)

Kodowanie tekstu: Mazovia (DOS Polish).

## Uwagi

- Na Windows można zmienić rozszerzenie na `.pyw` aby ukryć okno konsoli
- Reguły GTU w kodzie (sekcja `GTU_RULES`) wymagają dostosowania
  do asortymentu firmy — domyślne reguły są przykładowe
- Schemat KSeF FA(3) obowiązuje od 1 lutego 2026

## Licencja

Kod udostępniony do użytku edukacyjnego i osobistego.
