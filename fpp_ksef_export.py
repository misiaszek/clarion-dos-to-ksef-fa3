"""
Clarion Invoice Database Exporter

A GUI application to browse and export invoices from Clarion DOS 3.x database files
(TRANHEAD.DAT and TRANELEM.DAT) to KSeF FA(3) XML format.

Requirements:
- Python 3.8+
- tkinter (included with Python)
"""

__version__ = "1.0"
__date__ = "2026-03-30"

import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal
import xml.etree.ElementTree as ET
from xml.dom import minidom
import struct
import os
import json


# ============================================================================
# GTU Rules  (edit here to add/change GTU classifications)
#   kod_prefix     : beginning of product code (case-insensitive)
#   nazwa_contains : substring in product name (case-insensitive)
#   min_price      : optional minimum unit price (cenaf PLN) to qualify
#   Rules are checked top-to-bottom, first match wins.
# ============================================================================

GTU_RULES = [
    # === PRZYKŁADOWE REGUŁY — dostosuj do asortymentu swojej firmy ===
    # {'gtu': 'GTU_06', 'kod_prefix': 'ELEK', 'min_price': Decimal('400')},
    # {'gtu': 'GTU_06', 'nazwa_contains': 'KAMERA', 'min_price': Decimal('200')},
    # {'gtu': 'GTU_12', 'kod_prefix': 'USL'},
]


# ============================================================================
# Clarion Database Reading Functions
# ============================================================================

CLARION_BASE_DATE = date(1800, 12, 28)


def decode_clarion_date(days: int) -> Optional[date]:
    """Convert Clarion date (days since 1800-12-28) to Python date."""
    if days > 0 and days < 200000:
        return CLARION_BASE_DATE + timedelta(days=days)
    return None


def decode_string(data: bytes, encoding: str = 'cp1250') -> str:
    """
    Decode string from bytes using Mazovia encoding table.
    Clarion DOS uses Mazovia encoding for Polish characters.
    """
    # Complete Mazovia decoding table (256 characters)
    MAZOVIA_TABLE = [
        '\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',  # 0x00-0x07
        '\x08', '\t',   '\n',   '\x0b', '\x0c', '\r',   '\x0e', '\x0f',  # 0x08-0x0F
        '\x10', '\x11', '\x12', '\x13', '\x14', '\x15', '\x16', '\x17',  # 0x10-0x17
        '\x18', '\x19', '\x1a', '\x1b', '\x1c', '\x1d', '\x1e', '\x1f',  # 0x18-0x1F
        ' ', '!', '"', '#', '$', '%', '&', "'", '(', ')', '*', '+', ',', '-', '.', '/',  # 0x20-0x2F
        '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', ':', ';', '<', '=', '>', '?',  # 0x30-0x3F
        '@', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O',  # 0x40-0x4F
        'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', '[', '\\', ']', '^', '_', # 0x50-0x5F
        '`', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o',  # 0x60-0x6F
        'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', '{', '|', '}', '~', '\x7f',  # 0x70-0x7F
        # Extended characters (0x80-0xFF) - Mazovia Polish encoding
        '\u20ac', '\ufffe', '\u201a', '\ufffe', '\u201e', '\u2026', '\u0105', '\u2021',  # 0x80-0x87: €, ?, ‚, ?, „, …, ą, ‡
        '\ufffe', '\u2030', '\u0160', '\u2039', '\ufffe', '\u0107', '\u017d', '\u0104',  # 0x88-0x8F: ?, ‰, Š, ‹, ?, ć, Ž, Ą
        '\u0118', '\u0119', '\u0142', '\u201c', '\u201d', '\u0106', '\u2013', '\u2014',  # 0x90-0x97: Ę, ę, ł, ", ", Ć, –, —
        '\u015a', '\u2122', '\u0161', '\u203a', '\u0141', '\u0165', '\u015b', '\ufffe',  # 0x98-0x9F: Ś, ™, š, ›, Ł, ť, ś, ?
        '\u0179', '\u017b', '\xf3',   '\xd3',   '\u0144', '\u0143', '\u017a', '\u017c',  # 0xA0-0xA7: Ź, Ż, ó, Ó, ń, Ń, ź, ż
        '\xa8',   '\xa9',   '\u015e', '\xab',   '\xac',   '\xad',   '\xae',   '\ufffe',  # 0xA8-0xAF: ¨, ©, Ş, «, ¬, ­, ®, ?
        '\xb0',   '\xb1',   '\u02db', '\ufffe', '\xb4',   '\xb5',   '\xb6',   '\xb7',    # 0xB0-0xB7: °, ±, ˛, ?, ´, µ, ¶, ·
        '\xb8',   '\ufffe', '\u015f', '\xbb',   '\u013d', '\u02dd', '\u013e', '\ufffe',  # 0xB8-0xBF: ¸, ?, ş, », Ľ, ˝, ľ, ?
        '\u0154', '\xc1',   '\xc2',   '\u0102', '\xc4',   '\u0139', '\ufffe', '\xc7',    # 0xC0-0xC7: Ŕ, Á, Â, Ă, Ä, Ĺ, ?, Ç
        '\u010c', '\xc9',   '\ufffe', '\xcb',   '\u011a', '\xcd',   '\xce',   '\u010e',  # 0xC8-0xCF: Č, É, ?, Ë, Ě, Í, Î, Ď
        '\u0110', '\ufffe', '\u0147', '\ufffe', '\xd4',   '\u0150', '\xd6',   '\xd7',    # 0xD0-0xD7: Đ, ?, Ň, ?, Ô, Ő, Ö, ×
        '\u0158', '\u016e', '\xda',   '\u0170', '\xdc',   '\xdd',   '\u0162', '\xdf',    # 0xD8-0xDF: Ř, Ů, Ú, Ű, Ü, Ý, Ţ, ß
        '\u0155', '\xe1',   '\xe2',   '\u0103', '\xe4',   '\u013a', '\ufffe', '\xe7',    # 0xE0-0xE7: ŕ, á, â, ă, ä, ĺ, ?, ç
        '\u010d', '\xe9',   '\ufffe', '\xeb',   '\u011b', '\xed',   '\xee',   '\u010f',  # 0xE8-0xEF: č, é, ?, ë, ě, í, î, ď
        '\u0111', '\ufffe', '\u0148', '\ufffe', '\xf4',   '\u0151', '\xf6',   '\xf7',    # 0xF0-0xF7: đ, ?, ň, ?, ô, ő, ö, ÷
        '\u0159', '\u016f', '\xfa',   '\u0171', '\xfc',   '\xfd',   '\u0163', '\u02d9',  # 0xF8-0xFF: ř, ů, ú, ű, ü, ý, ţ, ˙
    ]
    
    stripped = data.rstrip(b'\x00 ')
    if not stripped:
        return ''
    
    # Decode using Mazovia table
    try:
        result = []
        for byte in stripped:
            char = MAZOVIA_TABLE[byte]
            # Skip undefined characters (0xFFFE)
            if char != '\ufffe':
                result.append(char)
        return ''.join(result).strip()
    except:
        # Fallback to standard encodings
        for enc in [encoding, 'cp852', 'latin-1']:
            try:
                return stripped.decode(enc).strip()
            except:
                continue
        return stripped.decode('latin-1', errors='replace').strip()


def decode_bcd_decimal(data: bytes, decimal_places: int = 2) -> Decimal:
    """Decode packed decimal number."""
    if not data:
        return Decimal(0)
    try:
        value = int.from_bytes(data, byteorder='little', signed=True)
        if decimal_places > 0:
            return Decimal(value) / Decimal(10 ** decimal_places)
        return Decimal(value)
    except:
        return Decimal(0)


def decode_clarion_decimal(data: bytes, decimal_places: int = 2) -> Decimal:
    """
    Decode Clarion DECIMAL(n,d) packed BCD format.
    Each byte contains 2 BCD digits (0-9).
    Sign nibble: 0xF or 0xD = negative, 0xC = positive, 0x0 = positive.
    Example: bytes 00 00 00 00 31 71 = BCD 000000003171 = 3171 -> 31.71
    Example: bytes F0 00 00 00 31 71 = negative -> -31.71
    """
    if not data or len(data) == 0:
        return Decimal(0)
    try:
        is_negative = False
        value = 0
        for byte in data:
            high_nibble = (byte >> 4) & 0x0F
            low_nibble = byte & 0x0F

            if high_nibble > 9:
                is_negative = (high_nibble in (0x0D, 0x0F))
                value = value * 10 + low_nibble
            elif low_nibble > 9:
                is_negative = (low_nibble in (0x0D, 0x0F))
                value = value * 10 + high_nibble
            else:
                value = value * 100 + high_nibble * 10 + low_nibble

        if is_negative:
            value = -value

        if decimal_places > 0:
            return Decimal(value) / Decimal(10 ** decimal_places)
        return Decimal(value)
    except Exception as e:
        return Decimal(0)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class InvoiceHeader:
    """Invoice header record."""
    record_num: int
    id: int
    typ: int
    rok: str
    numer: int
    seria: str
    dokument: str
    data: Optional[date]
    kon: str
    k_nazwa1: str
    k_nazwa2: str
    k_adres1: str
    k_kodp: str
    k_miasto: str
    nip: str
    odb: str
    o_nazwa1: str
    o_nazwa2: str
    o_adres1: str
    o_kodp: str
    o_miasto: str
    o_adres2: str
    total: Decimal
    vat: Decimal
    termin: Optional[date]
    platnosc: int
    opis: str
    
    @property
    def full_number(self) -> str:
        if self.seria:
            return f"{self.numer}/{self.rok}/{self.seria}"
        return f"{self.numer}/{self.rok}"
    
    @property 
    def customer_name(self) -> str:
        name = f"{self.k_nazwa1} {self.k_nazwa2}".strip()
        return name if name else self.kon

    @property
    def receiver_name(self) -> str:
        name = f"{self.o_nazwa1} {self.o_nazwa2}".strip()
        return name if name else self.odb


@dataclass
class InvoiceElement:
    """Invoice line item."""
    record_num: int
    id: int
    lp: int
    data: Optional[date]
    typ: int
    kon: str
    kod: str
    nazwa: str
    cecha: str
    ile: Decimal
    jm: str
    cena0: Decimal
    cenaw: Decimal
    cenat: Decimal
    cenaf: Decimal
    wal: str
    podatek: str
    pokwota: Decimal


PLATNOSC_LABELS = {
    1: 'gotówka',
    2: 'czek',
    3: 'przelew',
    4: 'kredyt',
    5: 'inne',
    6: 'karta płatnicza',
}

PLATNOSC_TO_KSEF = {
    1: '1',   # gotówka → KSeF 1 (gotówka)
    2: '4',   # czek → KSeF 4 (czek)
    3: '6',   # przelew → KSeF 6 (przelew)
    4: '5',   # kredyt → KSeF 5 (kredyt kupiecki)
    5: '6',   # inne → KSeF 6 (przelew)
    6: '2',   # karta płatnicza → KSeF 2 (karta)
}


# ============================================================================
# Database Readers
# ============================================================================

class TranHeadReader:
    """Reader for TRANHEAD.DAT - Invoice Headers."""
    
    DATA_START = 1619
    RECORD_LENGTH = 643
    
    def __init__(self, filepath: str, encoding: str = 'cp1250'):
        self.filepath = Path(filepath)
        self.encoding = encoding
        self._data: bytes = b''
        
    def open(self):
        with open(self.filepath, 'rb') as f:
            self._data = f.read()
            
    @property
    def record_count(self) -> int:
        if len(self._data) <= self.DATA_START:
            return 0
        usable = len(self._data) - self.DATA_START
        full = usable // self.RECORD_LENGTH
        remainder = usable % self.RECORD_LENGTH
        # Some files are a few bytes short for the final record; still count it.
        return full + (1 if remainder > 0 else 0)
    
    def read_record(self, record_num: int) -> Optional[InvoiceHeader]:
        if record_num < 0 or record_num >= self.record_count:
            return None
            
        offset = self.DATA_START + (record_num * self.RECORD_LENGTH)
        rec = self._data[offset:offset + self.RECORD_LENGTH]
        
        if len(rec) < self.RECORD_LENGTH:
            if len(rec) == 0:
                return None
            # Pad incomplete last record with zeros
            rec = rec.ljust(self.RECORD_LENGTH, b'\x00')
        
        # Parse based on Clarion Scanner structure (643 byte records)
        # ID: LONG (4 bytes) at offset 0 - little-endian
        id_val = struct.unpack('<i', rec[0:4])[0]
        
        # TYP: BYTE at offset 4
        typ = rec[4]
        
        # ROK: STRING(2) at offset 5
        rok = decode_string(rec[5:7])
        
        # NUMER: DECIMAL(5,0) at offset 7 (3 bytes packed BCD)
        numer = int(decode_clarion_decimal(rec[7:10], 0))
        
        # SERIA: STRING(4) at offset 10
        seria = decode_string(rec[10:14])
        
        # X: STRING(1) at offset 14
        x = decode_string(rec[14:15])
        
        # DOKUMENT: STRING(15) at offset 15
        dokument = decode_string(rec[15:30])
        
        # DATA: LONG at offset 30 (Clarion date, little-endian)
        data_days = struct.unpack('<i', rec[30:34])[0]
        invoice_date = decode_clarion_date(data_days)
        
        # KON: STRING(8) at offset 34
        kon = decode_string(rec[34:42])
        
        # K_NAZWA1: STRING(40) at offset 42
        k_nazwa1 = decode_string(rec[42:82])
        
        # K_NAZWA2: STRING(40) at offset 82
        k_nazwa2 = decode_string(rec[82:122])
        
        # K_ADRES1: STRING(40) at offset 122
        k_adres1 = decode_string(rec[122:162])
        
        # K_KODP: STRING(6) at offset 162
        k_kodp = decode_string(rec[162:168])
        
        # K_MIASTO: STRING(30) at offset 168
        k_miasto = decode_string(rec[168:198])
        
        # ZEZW_OLD: STRING(40) at offset 198 (skip)
        
        # NIP: STRING(15) at offset 238
        nip = decode_string(rec[238:253])
        
        # ODB: STRING(8) at offset 253
        odb = decode_string(rec[253:261])
        
        # O_NAZWA1: STRING(40) at offset 261
        o_nazwa1 = decode_string(rec[261:301])
        
        # O_NAZWA2: STRING(40) at offset 301
        o_nazwa2 = decode_string(rec[301:341])
        
        # O_ADRES1: STRING(40) at offset 341
        o_adres1 = decode_string(rec[341:381])
        
        # O_KODP: STRING(6) at offset 381
        o_kodp = decode_string(rec[381:387])
        
        # O_MIASTO: STRING(30) at offset 387
        o_miasto = decode_string(rec[387:417])
        
        # O_ADRES2: STRING(40) at offset 417
        o_adres2 = decode_string(rec[417:457])
        
        # OPIS: STRING(40) at offset 457
        opis = decode_string(rec[457:497])
        
        # TOTAL: DECIMAL(13,2) at offset 497 - 7 bytes packed BCD
        total = decode_clarion_decimal(rec[497:504], 2)
        
        # VAT: DECIMAL(13,2) at offset 570 - 7 bytes packed BCD
        vat = decode_clarion_decimal(rec[570:577], 2)
        
        # TERMIN: LONG at offset 581
        termin_days = struct.unpack('<i', rec[581:585])[0]
        termin = decode_clarion_date(termin_days)
        
        # ROZLICZONO: BYTE at offset 585 (skip)
        # PLATNOSC: BYTE at offset 586 (1=gotówka, 3=przelew, etc.)
        platnosc = rec[586] if len(rec) > 586 else 0
        
        return InvoiceHeader(
            record_num=record_num,
            id=id_val,
            typ=typ,
            rok=rok,
            numer=numer,
            seria=seria,
            dokument=dokument,
            data=invoice_date,
            kon=kon,
            k_nazwa1=k_nazwa1,
            k_nazwa2=k_nazwa2,
            k_adres1=k_adres1,
            k_kodp=k_kodp,
            k_miasto=k_miasto,
            nip=nip,
            odb=odb,
            o_nazwa1=o_nazwa1,
            o_nazwa2=o_nazwa2,
            o_adres1=o_adres1,
            o_kodp=o_kodp,
            o_miasto=o_miasto,
            o_adres2=o_adres2,
            total=total,
            vat=vat,
            termin=termin,
            platnosc=platnosc,
            opis=opis
        )
    
    def read_all_records(self, typ_filter: Optional[int] = None) -> List[InvoiceHeader]:
        """
        Read all invoice headers.
        
        Args:
            typ_filter: If specified, only return invoices with this typ value
        """
        records = []
        for i in range(self.record_count):
            rec = self.read_record(i)
            if rec and rec.rok:
                # Apply type filter if specified
                if typ_filter is not None and rec.typ != typ_filter:
                    continue
                records.append(rec)
        return records
    
    def get_filtered_indices(self, typ_filter: Optional[int] = None,
                             seria_prefix: Optional[str] = None) -> List[int]:
        """
        Get list of record indices that match the filter, in reverse order (newest first).
        Fast scan - only checks typ byte and seria prefix, no full record parsing.
        """
        prefix_bytes = seria_prefix.encode('ascii') if seria_prefix else None
        prefix_len = len(prefix_bytes) if prefix_bytes else 0
        indices = []
        for i in range(self.record_count - 1, -1, -1):  # Reverse order
            offset = self.DATA_START + (i * self.RECORD_LENGTH)
            if offset + 14 > len(self._data):
                continue
            # Quick check: only read typ byte (offset 4 in record)
            typ = self._data[offset + 4]
            if typ_filter is not None and typ != typ_filter:
                continue
            # Quick check: rok should not be empty (offset 5-6 in record)
            rok = self._data[offset + 5:offset + 7]
            if rok == b'\x00\x00' or rok == b'  ':
                continue
            # Quick check: seria prefix (offset 10 in record, STRING(4))
            if prefix_bytes and self._data[offset + 10:offset + 10 + prefix_len] != prefix_bytes:
                continue
            indices.append(i)
        return indices
    
    def read_records_by_indices(self, indices: List[int]) -> List[InvoiceHeader]:
        """Read specific records by their indices."""
        records = []
        for i in indices:
            rec = self.read_record(i)
            if rec:
                records.append(rec)
        return records


class TranElemReader:
    """Reader for TRANELEM.DAT - Invoice Line Items."""
    
    DATA_START = 882  # Empirically determined
    RECORD_LENGTH = 171  # Empirically determined
    
    def __init__(self, filepath: str, encoding: str = 'cp1250'):
        self.filepath = Path(filepath)
        self.encoding = encoding
        self._data: bytes = b''
        self._index: Dict[int, List[int]] = {}  # invoice_id -> [record_nums]
        
    def open(self):
        with open(self.filepath, 'rb') as f:
            self._data = f.read()
        self._build_index()
    
    def _build_index(self):
        """Build index: invoice_id -> list of record numbers (fast scan of ID field only)."""
        self._index = {}
        for i in range(self.record_count):
            offset = self.DATA_START + (i * self.RECORD_LENGTH)
            # Only read ID (4 bytes at offset 0 of record)
            id_val = struct.unpack('<i', self._data[offset:offset+4])[0]
            if id_val > 0:
                if id_val not in self._index:
                    self._index[id_val] = []
                self._index[id_val].append(i)
            
    @property
    def record_count(self) -> int:
        if len(self._data) <= self.DATA_START:
            return 0
        usable = len(self._data) - self.DATA_START
        full = usable // self.RECORD_LENGTH
        remainder = usable % self.RECORD_LENGTH
        # Count a partial final record if present
        return full + (1 if remainder > 0 else 0)
    
    def read_record(self, record_num: int) -> Optional[InvoiceElement]:
        if record_num < 0 or record_num >= self.record_count:
            return None
            
        offset = self.DATA_START + (record_num * self.RECORD_LENGTH)
        rec = self._data[offset:offset + self.RECORD_LENGTH]
        
        if len(rec) < self.RECORD_LENGTH:
            if len(rec) == 0:
                return None
            rec = rec.ljust(self.RECORD_LENGTH, b'\x00')
        
        # Parse based on Clarion Scanner exact structure:
        # ID: LONG (4 bytes) at offset 0
        id_val = struct.unpack('<i', rec[0:4])[0]
        
        # LP: SHORT (2 bytes) at offset 4
        lp = struct.unpack('<h', rec[4:6])[0]
        
        # DATA: LONG (4 bytes) at offset 6 - Clarion date
        data_days = struct.unpack('<i', rec[6:10])[0]
        elem_date = decode_clarion_date(data_days)
        
        # TYP: BYTE at offset 10
        typ = rec[10]
        
        # KON: STRING(8) at offset 11
        kon = decode_string(rec[11:19])
        
        # KOD: STRING(20) at offset 19
        kod = decode_string(rec[19:39])
        
        # NAZWA: STRING(40) at offset 39
        nazwa = decode_string(rec[39:79])
        
        # CECHA: STRING(20) at offset 79
        cecha = decode_string(rec[79:99])
        
        # ILE: DECIMAL(11,4) at offset 99 - 6 bytes packed BCD
        ile = decode_clarion_decimal(rec[99:105], 4)
        
        # JM: STRING(4) at offset 105
        jm = decode_string(rec[105:109])
        
        # OP: DECIMAL(9,2) at offset 109 - 5 bytes (skip for now)
        
        # JM2: STRING(4) at offset 114
        jm2 = decode_string(rec[114:118])
        
        # CENAZ: DECIMAL(15,6) at offset 118 - 8 bytes
        cenaz = decode_clarion_decimal(rec[118:126], 6)
        
        # CENA0: DECIMAL(11,2) at offset 126 - 6 bytes
        cena0 = decode_clarion_decimal(rec[126:132], 2)
        
        # CENAW: DECIMAL(11,2) at offset 132 - 6 bytes
        cenaw = decode_clarion_decimal(rec[132:138], 2)
        
        # CENAT: DECIMAL(11,2) at offset 138 - 6 bytes
        cenat = decode_clarion_decimal(rec[138:144], 2)
        
        # CENAF: DECIMAL(11,2) at offset 144 - 6 bytes
        cenaf = decode_clarion_decimal(rec[144:150], 2)
        
        # WAL: STRING(3) at offset 150
        wal = decode_string(rec[150:153])
        
        # GR: STRING(3) at offset 153
        gr = decode_string(rec[153:156])
        
        # POKWOTA: DECIMAL(11,2) at offset 156 - 6 bytes
        pokwota = decode_clarion_decimal(rec[156:162], 2)
        
        # PODATEK: DECIMAL(5,2) at offset 162 - 3 bytes
        podatek_val = decode_clarion_decimal(rec[162:165], 2)
        
        # RECEPTURA: BYTE at offset 165
        receptura = rec[165] if len(rec) > 165 else 0
        
        return InvoiceElement(
            record_num=record_num,
            id=id_val,
            lp=lp,
            data=elem_date,
            typ=typ,
            kon=kon,
            kod=kod,
            nazwa=nazwa,
            cecha=cecha,
            ile=ile,
            jm=jm,
            cena0=cena0,
            cenaw=cenaw,
            cenat=cenat,
            cenaf=cenaf,
            wal=wal,
            podatek=str(podatek_val),
            pokwota=pokwota
        )
    
    def read_all_records(self) -> List[InvoiceElement]:
        records = []
        for i in range(self.record_count):
            rec = self.read_record(i)
            if rec and rec.nazwa:
                records.append(rec)
        return records
    
    def get_elements_for_invoice(self, invoice_id: int) -> List[InvoiceElement]:
        """Get regular line items for a specific invoice ID (lp >= 0). Uses index for O(1) lookup."""
        result = []
        record_nums = self._index.get(invoice_id, [])
        for rec_num in record_nums:
            elem = self.read_record(rec_num)
            if elem and elem.lp >= 0:
                result.append(elem)
        return result

    def get_payment_info_for_invoice(self, invoice_id: int) -> str:
        """Get payment info stored as lp < 0 records (e.g., LP=-100). Uses index for O(1) lookup.
        Only returns meaningful info (starting with ZAPL), ignores 'Brak zapłaty' etc."""
        record_nums = self._index.get(invoice_id, [])
        for rec_num in record_nums:
            elem = self.read_record(rec_num)
            if elem and elem.lp < 0 and elem.nazwa:
                text = elem.nazwa.strip()
                if text.upper().startswith('ZAPL'):
                    return text
        return ""


# ============================================================================
# XML Export
# ============================================================================

def sanitize_text(text: str) -> str:
    """Remove or replace invalid XML characters."""
    if not text:
        return ''
    # Remove control characters and invalid XML chars
    result = []
    for char in text:
        code = ord(char)
        # Valid XML 1.0 characters
        if code == 0x9 or code == 0xA or code == 0xD or \
           (0x20 <= code <= 0xD7FF) or \
           (0xE000 <= code <= 0xFFFD):
            result.append(char)
        else:
            result.append(' ')  # Replace with space
    return ''.join(result)


def prettify_xml(elem: ET.Element) -> str:
    """Return a pretty-printed XML string with proper UTF-8 encoding."""
    # Sanitize all text content
    for node in elem.iter():
        if node.text:
            node.text = sanitize_text(node.text)
        if node.tail:
            node.tail = sanitize_text(node.tail)
    
    # Use bytes with explicit UTF-8 encoding for minidom
    rough_bytes = ET.tostring(elem, encoding='utf-8', xml_declaration=False)
    reparsed = minidom.parseString(rough_bytes)
    # Get pretty XML as string (decode from UTF-8)
    pretty_bytes = reparsed.toprettyxml(indent="  ", encoding='utf-8')
    return pretty_bytes.decode('utf-8')


class MateriaReader:
    """Reader for MATERIA.DAT - Product catalog (PKWiU lookup)."""
    
    DATA_START = 1798
    RECORD_LENGTH = 367
    REC_HEADER = 5  # status byte + 4 bytes memo pointer
    KOD_OFFSET = REC_HEADER + 0
    KOD_LEN = 20
    SWW_OFFSET = REC_HEADER + 330
    SWW_LEN = 20
    
    def __init__(self, filepath: str, encoding: str = 'cp1250'):
        self.filepath = Path(filepath)
        self.encoding = encoding
        self._data: bytes = b''
        self._pkwiu: Dict[str, str] = {}
        
    def open(self):
        with open(self.filepath, 'rb') as f:
            self._data = f.read()
        self._build_index()
    
    def _build_index(self):
        """Build dict: product code -> PKWiU (only for non-empty SWW)."""
        self._pkwiu = {}
        for i in range(self.record_count):
            offset = self.DATA_START + (i * self.RECORD_LENGTH)
            rec = self._data[offset:offset + self.RECORD_LENGTH]
            if rec[0] == 0:
                continue
            kod = decode_string(rec[self.KOD_OFFSET:self.KOD_OFFSET + self.KOD_LEN])
            sww = decode_string(rec[self.SWW_OFFSET:self.SWW_OFFSET + self.SWW_LEN])
            if kod and sww:
                self._pkwiu[kod] = sww
    
    @property
    def record_count(self) -> int:
        if len(self._data) <= self.DATA_START:
            return 0
        usable = len(self._data) - self.DATA_START
        return usable // self.RECORD_LENGTH
    
    @property
    def pkwiu_map(self) -> Dict[str, str]:
        return self._pkwiu


def export_invoice_to_xml(header: InvoiceHeader, elements: List[InvoiceElement], payment_info: str = "") -> ET.Element:
    """Convert invoice to XML element."""
    invoice = ET.Element('Faktura')
    
    # Header info
    naglowek = ET.SubElement(invoice, 'Naglowek')
    ET.SubElement(naglowek, 'ID').text = str(header.id)
    ET.SubElement(naglowek, 'Numer').text = header.full_number
    ET.SubElement(naglowek, 'Data').text = str(header.data) if header.data else ''
    ET.SubElement(naglowek, 'Typ').text = str(header.typ)
    ET.SubElement(naglowek, 'Rok').text = header.rok
    ET.SubElement(naglowek, 'NumerFaktury').text = str(header.numer)
    ET.SubElement(naglowek, 'Seria').text = header.seria
    ET.SubElement(naglowek, 'Dokument').text = header.dokument
    if payment_info:
        ET.SubElement(naglowek, 'PlatnoscInfo').text = payment_info
    
    # Customer info
    kontrahent = ET.SubElement(invoice, 'Kontrahent')
    ET.SubElement(kontrahent, 'Kod').text = header.kon
    ET.SubElement(kontrahent, 'Nazwa1').text = header.k_nazwa1
    ET.SubElement(kontrahent, 'Nazwa2').text = header.k_nazwa2
    ET.SubElement(kontrahent, 'Adres').text = header.k_adres1
    ET.SubElement(kontrahent, 'KodPocztowy').text = header.k_kodp
    ET.SubElement(kontrahent, 'Miasto').text = header.k_miasto
    ET.SubElement(kontrahent, 'NIP').text = header.nip
    
    # Line items
    pozycje = ET.SubElement(invoice, 'Pozycje')
    for elem in sorted(elements, key=lambda x: x.lp):
        pozycja = ET.SubElement(pozycje, 'Pozycja')
        ET.SubElement(pozycja, 'LP').text = str(elem.lp)
        ET.SubElement(pozycja, 'KodProduktu').text = elem.kod
        ET.SubElement(pozycja, 'Nazwa').text = elem.nazwa
        ET.SubElement(pozycja, 'Cecha').text = elem.cecha
        ET.SubElement(pozycja, 'Ilosc').text = str(elem.ile)
        ET.SubElement(pozycja, 'JednostkaMiary').text = elem.jm
        ET.SubElement(pozycja, 'CenaNetto').text = str(elem.cena0)
        ET.SubElement(pozycja, 'CenaBrutto').text = str(elem.cenaf)
        ET.SubElement(pozycja, 'Waluta').text = elem.wal
        ET.SubElement(pozycja, 'StawkaPodatku').text = elem.podatek
    
    # Totals
    podsumowanie = ET.SubElement(invoice, 'Podsumowanie')
    ET.SubElement(podsumowanie, 'LiczbaPozycji').text = str(len(elements))
    ET.SubElement(podsumowanie, 'WartoscNetto').text = str(header.total)
    ET.SubElement(podsumowanie, 'VAT').text = str(header.vat)
    ET.SubElement(podsumowanie, 'Opis').text = header.opis
    
    return invoice


# ============================================================================
# KSeF FA(2) XML Export
# ============================================================================

KSEF_NAMESPACE = "http://crd.gov.pl/wzor/2025/06/25/13775/"  # FA(3) from Feb 1, 2026
KSEF_ETD_NAMESPACE = "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/01/05/eD/DefinicjeTypy/"


def _ksef_currency_code(wal: str) -> str:
    wal = (wal or "").strip().upper()
    if wal in ("ZŁ", "ZL", "PLN"):
        return "PLN"
    return wal if wal else "PLN"


def _ksef_rate_key(rate: str, zero_vat_type: str = 'KR') -> str:
    rate = (rate or "").strip().lower()
    if rate in ("23", "23.0"):
        return "P_13_1", "P_14_1"
    if rate in ("8", "8.0", "7", "7.0"):
        return "P_13_2", "P_14_2"
    if rate in ("5", "5.0"):
        return "P_13_3", "P_14_3"
    if rate in ("0", "0.0"):
        zero_map = {'KR': 'P_13_6_1', 'WDT': 'P_13_6_2', 'EX': 'P_13_6_3'}
        return zero_map.get(zero_vat_type, 'P_13_6_1'), None
    if rate in ("zw", "np"):
        return "P_13_7", None
    return "P_13_1", "P_14_1"


def _ksef_price_pln(elem: InvoiceElement) -> Decimal:
    """Return unit invoice price in PLN (cenaf = cena fakturowa)."""
    return elem.cenaf if elem.cenaf else elem.cena0


def _match_gtu(elem: InvoiceElement) -> Optional[str]:
    """Match element against GTU_RULES. Returns e.g. 'GTU_06' or None."""
    kod = (elem.kod or '').strip().upper()
    nazwa = (elem.nazwa or '').strip().upper()
    price = _ksef_price_pln(elem)
    for rule in GTU_RULES:
        prefix = rule.get('kod_prefix')
        contains = rule.get('nazwa_contains')
        if prefix and not kod.startswith(prefix):
            continue
        if contains and contains.upper() not in nazwa:
            continue
        if not prefix and not contains:
            continue
        min_price = rule.get('min_price')
        if min_price is not None and price < min_price:
            continue
        return rule['gtu']
    return None


def _ksef_sum_by_vat(elements: List[InvoiceElement], zero_vat_type: str = 'KR') -> Dict[str, Decimal]:
    sums: Dict[str, Decimal] = {}
    vat_sums: Dict[str, Decimal] = {}
    for elem in elements:
        price = _ksef_price_pln(elem)
        net = (elem.ile * price) if price is not None else Decimal(0)
        rate_key, vat_key = _ksef_rate_key(elem.podatek, zero_vat_type)
        sums[rate_key] = sums.get(rate_key, Decimal(0)) + net
        if vat_key:
            try:
                rate = Decimal(str(elem.podatek))
                vat_val = (net * rate) / Decimal(100)
            except Exception:
                vat_val = Decimal(0)
            vat_sums[vat_key] = vat_sums.get(vat_key, Decimal(0)) + vat_val
    sums.update(vat_sums)
    return sums


def export_invoice_to_ksef_xml(
    header: InvoiceHeader,
    elements: List[InvoiceElement],
    payment_info: str,
    seller: Dict[str, str],
    ksef_options: Optional[Dict[str, Any]] = None,
    pkwiu_map: Optional[Dict[str, str]] = None,
) -> ET.Element:
    """Build KSeF FA(3) XML invoice for goods sales (mandatory from Feb 1, 2026)."""
    if ksef_options is None:
        ksef_options = {}
    ET.register_namespace('', KSEF_NAMESPACE)
    ET.register_namespace('etd', KSEF_ETD_NAMESPACE)

    faktura = ET.Element(
        'Faktura',
        {
            'xmlns': KSEF_NAMESPACE,
            'xmlns:etd': KSEF_ETD_NAMESPACE,
            'xmlns:xsi': "http://www.w3.org/2001/XMLSchema-instance",
        },
    )

    # ========== Naglowek ==========
    naglowek = ET.SubElement(faktura, 'Naglowek')
    kod_form = ET.SubElement(naglowek, 'KodFormularza', {
        'kodSystemowy': 'FA (3)',
        'wersjaSchemy': '1-0E',
    })
    kod_form.text = 'FA'
    ET.SubElement(naglowek, 'WariantFormularza').text = '3'
    ET.SubElement(naglowek, 'DataWytworzeniaFa').text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    ET.SubElement(naglowek, 'SystemInfo').text = 'Clarion Invoice Exporter'

    # ========== Podmiot1 (Sprzedawca) ==========
    podmiot1 = ET.SubElement(faktura, 'Podmiot1')
    p1_id = ET.SubElement(podmiot1, 'DaneIdentyfikacyjne')
    seller_nip = seller.get('nip', '').replace('-', '').strip()
    seller_name = seller.get('name', '').strip()
    seller_addr1 = seller.get('addr1', '').strip()
    seller_addr2 = seller.get('addr2', '').strip()
    
    ET.SubElement(p1_id, 'NIP').text = seller_nip
    ET.SubElement(p1_id, 'Nazwa').text = seller_name
    p1_addr = ET.SubElement(podmiot1, 'Adres')
    ET.SubElement(p1_addr, 'KodKraju').text = seller.get('country', 'PL') or 'PL'
    ET.SubElement(p1_addr, 'AdresL1').text = seller_addr1
    # AdresL2 is optional - only add if not empty
    if seller_addr2:
        ET.SubElement(p1_addr, 'AdresL2').text = seller_addr2

    # ========== Podmiot2 (Nabywca) ==========
    podmiot2 = ET.SubElement(faktura, 'Podmiot2')
    p2_id = ET.SubElement(podmiot2, 'DaneIdentyfikacyjne')
    raw_nip = header.nip.replace('-', '').strip() if header.nip else ''
    buyer_name = header.customer_name.strip() if header.customer_name else ''
    buyer_addr1 = header.k_adres1.strip() if header.k_adres1 else ''
    buyer_addr2 = f"{header.k_kodp} {header.k_miasto}".strip()

    EU_PREFIXES = {
        'AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'EL', 'ES',
        'FI', 'FR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT',
        'NL', 'PT', 'RO', 'SE', 'SI', 'SK', 'XI',
    }
    nip_prefix = raw_nip[:2].upper() if len(raw_nip) > 2 else ''
    buyer_country = 'PL'

    if nip_prefix == 'PL':
        ET.SubElement(p2_id, 'NIP').text = raw_nip[2:]
    elif nip_prefix in EU_PREFIXES:
        ET.SubElement(p2_id, 'KodUE').text = nip_prefix
        ET.SubElement(p2_id, 'NrVatUE').text = raw_nip[2:]
        buyer_country = nip_prefix
    elif raw_nip and raw_nip[0].isdigit():
        ET.SubElement(p2_id, 'NIP').text = raw_nip
    elif raw_nip:
        prefix = nip_prefix
        ET.SubElement(p2_id, 'KodKraju').text = prefix
        ET.SubElement(p2_id, 'NrID').text = raw_nip[2:]
        buyer_country = prefix
    else:
        ET.SubElement(p2_id, 'BrakID').text = '1'

    ET.SubElement(p2_id, 'Nazwa').text = buyer_name

    if buyer_addr1:
        p2_addr = ET.SubElement(podmiot2, 'Adres')
        ET.SubElement(p2_addr, 'KodKraju').text = buyer_country
        ET.SubElement(p2_addr, 'AdresL1').text = buyer_addr1
        if buyer_addr2:
            ET.SubElement(p2_addr, 'AdresL2').text = buyer_addr2
    # FA(3) required: JST (jednostka samorządu terytorialnego) i GV (grupa VAT)
    jst_value = '1' if ksef_options.get('jst', False) else '2'
    gv_value = '1' if ksef_options.get('gv', False) else '2'
    ET.SubElement(podmiot2, 'JST').text = jst_value
    ET.SubElement(podmiot2, 'GV').text = gv_value

    # ========== Podmiot3 (Odbiorca) - from GUI or Clarion data ==========
    # Priority: GUI Podmiot3 > Clarion receiver data
    podmiot3_enabled = ksef_options.get('podmiot3_enabled', False)
    podmiot3_name = ksef_options.get('podmiot3_name', '')
    
    if podmiot3_enabled and podmiot3_name:
        # Use GUI Podmiot3 data
        p3_addr1 = ksef_options.get('podmiot3_addr1', '').strip()
        p3_addr2 = ksef_options.get('podmiot3_addr2', '').strip()
        p3_email = ksef_options.get('podmiot3_email', '').strip()
        
        podmiot3 = ET.SubElement(faktura, 'Podmiot3')
        p3_id = ET.SubElement(podmiot3, 'DaneIdentyfikacyjne')
        p3_nip_raw = ksef_options.get('podmiot3_nip', '').strip()
        if re.match(r'^\d{10}-\d{5}$', p3_nip_raw):
            ET.SubElement(p3_id, 'IDWew').text = p3_nip_raw
        elif p3_nip_raw:
            p3_nip_clean = p3_nip_raw.replace('-', '')
            ET.SubElement(p3_id, 'NIP').text = p3_nip_clean
        else:
            ET.SubElement(p3_id, 'BrakID').text = '1'
        ET.SubElement(p3_id, 'Nazwa').text = podmiot3_name
        
        if p3_addr1:
            p3_addr = ET.SubElement(podmiot3, 'Adres')
            ET.SubElement(p3_addr, 'KodKraju').text = 'PL'
            ET.SubElement(p3_addr, 'AdresL1').text = p3_addr1
            if p3_addr2:
                ET.SubElement(p3_addr, 'AdresL2').text = p3_addr2
        
        if p3_email:
            p3_kontakt = ET.SubElement(podmiot3, 'DaneKontaktowe')
            ET.SubElement(p3_kontakt, 'Email').text = p3_email
        
        ET.SubElement(podmiot3, 'Rola').text = ksef_options.get('podmiot3_rola', '2')
    elif header.o_adres1 and header.o_adres1.strip() and header.o_adres1 != header.k_adres1:
        # Fallback: Use Clarion receiver data if available
        p3_name = (header.receiver_name or header.odb or header.o_nazwa1 or '').strip()
        p3_addr1 = header.o_adres1.strip()
        p3_addr2 = f"{header.o_kodp} {header.o_miasto}".strip()
        
        if p3_name and p3_addr1:  # Only add if we have valid data
            podmiot3 = ET.SubElement(faktura, 'Podmiot3')
            p3_id = ET.SubElement(podmiot3, 'DaneIdentyfikacyjne')
            ET.SubElement(p3_id, 'BrakID').text = '1'  # Usually no NIP for receiver
            ET.SubElement(p3_id, 'Nazwa').text = p3_name
            p3_addr = ET.SubElement(podmiot3, 'Adres')
            ET.SubElement(p3_addr, 'KodKraju').text = 'PL'
            ET.SubElement(p3_addr, 'AdresL1').text = p3_addr1
            if p3_addr2:
                ET.SubElement(p3_addr, 'AdresL2').text = p3_addr2
            ET.SubElement(podmiot3, 'Rola').text = '2'  # 2 = Odbiorca

    # ========== Fa (Faktura) ==========
    fa = ET.SubElement(faktura, 'Fa')
    ET.SubElement(fa, 'KodWaluty').text = 'PLN'
    
    # P_1 (data wystawienia) = data eksportu do KSeF (wymagane przez system)
    export_date = datetime.now().strftime('%Y-%m-%d')
    ET.SubElement(fa, 'P_1').text = export_date
    
    # P_1M (miejsce wystawienia) is optional - only add if city provided
    seller_city = seller.get('city', '').strip()
    if seller_city:
        ET.SubElement(fa, 'P_1M').text = seller_city
    
    ET.SubElement(fa, 'P_2').text = header.full_number  # Numer faktury
    
    # P_6 (data sprzedaży) = oryginalna data z faktury
    sale_date = str(header.data) if header.data else export_date
    ET.SubElement(fa, 'P_6').text = sale_date

    # Detect EU buyer for 0% VAT classification
    zero_vat_type = 'WDT' if buyer_country != 'PL' else 'KR'

    # VAT summary by rate - pairs must be in schema order:
    # P_13_1/P_14_1 (23%), P_13_2/P_14_2 (8%), P_13_3/P_14_3 (5%), etc.
    vat_sums = _ksef_sum_by_vat(elements, zero_vat_type)
    rate_pairs = [
        ('P_13_1', 'P_14_1'),    # 23% stawka podstawowa
        ('P_13_2', 'P_14_2'),    # 8% stawka obniżona pierwsza
        ('P_13_3', 'P_14_3'),    # 5% stawka obniżona druga
        ('P_13_4', 'P_14_4'),    # ryczałt taksówki
        ('P_13_5', 'P_14_5'),    # procedura szczególna
        ('P_13_6_1', None),      # 0% krajowa
        ('P_13_6_2', None),      # 0% WDT
        ('P_13_6_3', None),      # 0% eksport
        ('P_13_7', None),        # zwolniona
    ]
    for netto_key, vat_key in rate_pairs:
        if netto_key in vat_sums:
            ET.SubElement(fa, netto_key).text = str(round(vat_sums[netto_key], 2))
        if vat_key and vat_key in vat_sums:
            ET.SubElement(fa, vat_key).text = str(round(vat_sums[vat_key], 2))

    # P_15 - Total gross amount
    try:
        total_gross = header.total + header.vat
    except Exception:
        total_gross = header.total
    ET.SubElement(fa, 'P_15').text = str(round(total_gross, 2))

    # ========== Adnotacje (wymagane!) ==========
    adnotacje = ET.SubElement(fa, 'Adnotacje')
    ET.SubElement(adnotacje, 'P_16').text = '2'  # 2 = nie stosuje metody kasowej
    ET.SubElement(adnotacje, 'P_17').text = '2'  # 2 = nie jest samofakturowaniem
    ET.SubElement(adnotacje, 'P_18').text = '2'  # 2 = nie jest odwrotnym obciążeniem
    ET.SubElement(adnotacje, 'P_18A').text = '2'  # 2 = nie stosuje mechanizmu podzielonej płatności
    
    zwolnienie = ET.SubElement(adnotacje, 'Zwolnienie')
    ET.SubElement(zwolnienie, 'P_19N').text = '1'  # 1 = nie dotyczy zwolnienia z VAT
    
    nst = ET.SubElement(adnotacje, 'NoweSrodkiTransportu')
    ET.SubElement(nst, 'P_22N').text = '1'  # 1 = nie dotyczy nowych środków transportu
    
    ET.SubElement(adnotacje, 'P_23').text = '2'  # 2 = nie jest fakturą uproszczoną
    
    pmarzy = ET.SubElement(adnotacje, 'PMarzy')
    ET.SubElement(pmarzy, 'P_PMarzyN').text = '1'  # 1 = nie dotyczy procedury marży

    # Rodzaj faktury
    ET.SubElement(fa, 'RodzajFaktury').text = 'VAT'

    # ========== FaWiersz (pozycje faktury) ==========
    for elem in sorted(elements, key=lambda x: x.lp):
        w = ET.SubElement(fa, 'FaWiersz')
        ET.SubElement(w, 'NrWierszaFa').text = str(elem.lp)
        ET.SubElement(w, 'P_7').text = elem.nazwa.strip() if elem.nazwa else ''
        if pkwiu_map:
            elem_kod = (elem.kod or '').strip()
            pkwiu_val = pkwiu_map.get(elem_kod, '')
            if pkwiu_val:
                ET.SubElement(w, 'PKWiU').text = pkwiu_val
        ET.SubElement(w, 'P_8A').text = elem.jm.strip().lower() if elem.jm else 'szt.'
        ET.SubElement(w, 'P_8B').text = str(elem.ile)
        price = _ksef_price_pln(elem)
        ET.SubElement(w, 'P_9A').text = str(round(price, 2))
        wart_netto = (elem.ile * price) if price is not None else elem.ile
        ET.SubElement(w, 'P_11').text = str(round(wart_netto, 2))
        raw_rate = elem.podatek.strip() if elem.podatek else '23'
        if raw_rate in ('0', '0.0'):
            raw_rate = f'0 {zero_vat_type}'
        ET.SubElement(w, 'P_12').text = raw_rate
        gtu = _match_gtu(elem)
        if gtu:
            ET.SubElement(w, 'GTU').text = gtu

    # ========== Platnosc ==========
    platnosc = ET.SubElement(fa, 'Platnosc')
    deferred = header.termin and header.data and header.termin != header.data
    if deferred:
        termin_el = ET.SubElement(platnosc, 'TerminPlatnosci')
        ET.SubElement(termin_el, 'Termin').text = str(header.termin)
    else:
        ET.SubElement(platnosc, 'Zaplacono').text = '1'
        ET.SubElement(platnosc, 'DataZaplaty').text = str(header.data) if header.data else sale_date
    forma = PLATNOSC_TO_KSEF.get(header.platnosc, '6')
    ET.SubElement(platnosc, 'FormaPlatnosci').text = forma

    bank_nr = seller.get('bank_nrRB', '')
    if deferred and bank_nr:
        rb = ET.SubElement(platnosc, 'RachunekBankowy')
        ET.SubElement(rb, 'NrRB').text = bank_nr
        bank_nazwa = seller.get('bank_nazwa', '')
        if bank_nazwa:
            ET.SubElement(rb, 'NazwaBanku').text = bank_nazwa

    # ========== Stopka (opcjonalna) ==========
    stopka = ET.SubElement(faktura, 'Stopka')
    info = ET.SubElement(stopka, 'Informacje')
    ET.SubElement(info, 'StopkaFaktury').text = seller.get('footer', 'Dziękujemy za zakupy')

    return faktura


def export_invoices_to_file(invoices: List[Tuple[InvoiceHeader, List[InvoiceElement], str]], 
                            filepath: str) -> None:
    """Export multiple invoices to XML file."""
    root = ET.Element('Faktury')
    root.set('xmlns', 'http://example.com/faktury')
    root.set('wersja', '1.0')
    
    for header, elements, payment_info in invoices:
        invoice_elem = export_invoice_to_xml(header, elements, payment_info)
        root.append(invoice_elem)
    
    xml_string = prettify_xml(root)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        # Remove the auto-generated declaration from prettify
        lines = xml_string.split('\n')
        if lines[0].startswith('<?xml'):
            lines = lines[1:]
        f.write('\n'.join(lines))


def validate_ksef_export(
    header: InvoiceHeader,
    elements: List[InvoiceElement],
    seller: Dict[str, str],
) -> List[str]:
    """
    Validate data before KSeF export.
    Returns list of error messages. Empty list means validation passed.
    """
    errors = []
    
    # === Podmiot1 (Sprzedawca) - WYMAGANE ===
    seller_nip = seller.get('nip', '').replace('-', '').strip()
    seller_name = seller.get('name', '').strip()
    seller_addr1 = seller.get('addr1', '').strip()
    
    if not seller_nip:
        errors.append("Sprzedawca: brak NIP (pole wymagane)")
    elif not re.match(r'^[1-9]((\d[1-9])|([1-9]\d))\d{7}$', seller_nip):
        errors.append(f"Sprzedawca: nieprawidłowy NIP '{seller_nip}' (powinien mieć 10 cyfr)")
    
    if not seller_name:
        errors.append("Sprzedawca: brak nazwy firmy (pole wymagane)")
    
    if not seller_addr1:
        errors.append("Sprzedawca: brak adresu (AdresL1 wymagany)")
    
    # === Podmiot2 (Nabywca) - WYMAGANE ===
    buyer_name = header.customer_name.strip() if header.customer_name else ''
    buyer_addr1 = header.k_adres1.strip() if header.k_adres1 else ''
    
    if not buyer_name:
        errors.append("Nabywca: brak nazwy (pole wymagane)")
    
    if not buyer_addr1:
        errors.append("Nabywca: brak adresu (AdresL1 wymagany)")
    
    # === Pozycje faktury ===
    if not elements:
        errors.append("Faktura nie ma żadnych pozycji (wymagana min. 1 pozycja)")
    else:
        sum_positions = Decimal(0)
        for i, elem in enumerate(elements, 1):
            nazwa = elem.nazwa.strip() if elem.nazwa else ''
            if not nazwa:
                errors.append(f"Pozycja {i} (LP={elem.lp}): brak nazwy towaru/usługi")
            
            jm = elem.jm.strip() if elem.jm else ''
            if not jm:
                errors.append(f"Pozycja {i} (LP={elem.lp}): brak jednostki miary")

            price = _ksef_price_pln(elem)
            sum_positions += elem.ile * price if price else Decimal(0)

        # Sprawdź spójność sumy pozycji z TOTAL+VAT
        expected_gross = header.total + header.vat
        diff = abs(round(sum_positions + header.vat, 2) - round(expected_gross, 2))
        if diff > Decimal('1.00'):
            errors.append(
                f"Suma pozycji netto ({round(sum_positions, 2)}) + VAT ({header.vat}) = "
                f"{round(sum_positions + header.vat, 2)} ≠ kwota brutto z nagłówka ({round(expected_gross, 2)}). "
                f"Różnica: {diff} PLN"
            )
    
    return errors


def export_ksef_invoice_to_file(
    header: InvoiceHeader,
    elements: List[InvoiceElement],
    payment_info: str,
    seller: Dict[str, str],
    filepath: str,
    ksef_options: Optional[Dict[str, Any]] = None,
    pkwiu_map: Optional[Dict[str, str]] = None,
) -> None:
    """Export a single invoice to KSeF FA(3) XML file with proper UTF-8 encoding."""
    faktura = export_invoice_to_ksef_xml(header, elements, payment_info, seller, ksef_options, pkwiu_map)
    xml_string = prettify_xml(faktura)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        lines = xml_string.split('\n')
        if lines[0].startswith('<?xml'):
            lines = lines[1:]
        f.write('\n'.join(lines))


# ============================================================================
# Configuration
# ============================================================================

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_APP_DIR, 'config.json')
EXPORTED_FILE = os.path.join(_APP_DIR, 'exported.json')

DEFAULT_CONFIG = {
    "seller": {
        "nip": "",
        "name": "",
        "addr1": "",
        "addr2": "",
        "city": "",
        "country": "PL",
        "footer": "Dziękujemy za zakupy",
    },
    "bank": {
        "nrRB": "",
        "nazwa": "",
    },
    "paths": {
        "tranhead": "TRANHEAD.DAT",
        "tranelem": "TRANELEM.DAT",
    },
    "gui": {
        "sash_position": 420,
        "window_geometry": "1500x800",
    },
}


def load_config() -> dict:
    """Load configuration from JSON file, falling back to defaults."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        # Merge with defaults so missing keys don't crash
        merged = {**DEFAULT_CONFIG}
        for section in ("seller", "bank", "paths", "gui"):
            merged[section] = {**DEFAULT_CONFIG.get(section, {}), **cfg.get(section, {})}
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return {**DEFAULT_CONFIG}


def save_config(cfg: dict) -> None:
    """Persist configuration to JSON file."""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_exported() -> dict:
    """Load exported invoices registry. Returns dict keyed by full_number."""
    try:
        with open(EXPORTED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {rec['number']: rec for rec in data.get('exported', [])}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_exported(exported: dict) -> None:
    """Persist exported invoices registry."""
    data = {'exported': list(exported.values())}
    with open(EXPORTED_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================================
# GUI Application
# ============================================================================

class InvoiceExporterApp:
    """Main GUI application for invoice export."""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"Clarion Invoice Exporter v{__version__} ({__date__})")
        self.root.minsize(1200, 700)
        
        # Data
        self.head_reader: Optional[TranHeadReader] = None
        self.elem_reader: Optional[TranElemReader] = None
        self.invoices: List[InvoiceHeader] = []
        self.elements_cache: Dict[int, List[InvoiceElement]] = {}
        self.payment_cache: Dict[int, str] = {}
        
        # Pagination
        self.page_size = 8  # Fits current window (8 rows)
        self.current_page = 0
        self.filtered_indices: List[int] = []  # All matching record indices (newest first)
        self.selected_row_index = 0  # Track selected row position within page
        
        self.config = load_config()
        self.exported = load_exported()
        self.pkwiu_map = {}
        
        self._create_widgets()
        self._apply_config()
        
        if self.head_path_var.get() and self.elem_path_var.get():
            self.root.after(200, self._load_database)
        
    def _create_widgets(self):
        """Create GUI widgets."""
        # Main split: left (controls + list) / right (preview)
        self.main_paned = ttk.Panedwindow(self.root, orient='horizontal')
        self.main_paned.pack(fill='both', expand=True, padx=10, pady=10)
        
        left_frame = ttk.Frame(self.main_paned)
        right_frame = ttk.LabelFrame(self.main_paned, text="Invoice Preview", padding="10")
        self.main_paned.add(left_frame, weight=1)
        self.main_paned.add(right_frame, weight=3)
        
        # Top frame - file selection (left)
        top_frame = ttk.Frame(left_frame, padding="10")
        top_frame.pack(fill='x')
        
        ttk.Label(top_frame, text="TRANHEAD.DAT:").grid(row=0, column=0, sticky='w')
        self.head_path_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.head_path_var, width=60).grid(row=0, column=1, padx=5)
        ttk.Button(top_frame, text="Browse...", command=self._browse_head).grid(row=0, column=2)
        
        ttk.Label(top_frame, text="TRANELEM.DAT:").grid(row=1, column=0, sticky='w', pady=(5,0))
        self.elem_path_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.elem_path_var, width=60).grid(row=1, column=1, padx=5, pady=(5,0))
        ttk.Button(top_frame, text="Browse...", command=self._browse_elem).grid(row=1, column=2, pady=(5,0))
        
        # Load and Refresh buttons
        btn_frame = ttk.Frame(top_frame)
        btn_frame.grid(row=2, column=1, pady=10)
        ttk.Button(btn_frame, text="Load Database", command=self._load_database).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🔄 Refresh", command=self._refresh_database).pack(side='left', padx=5)
        
        # Cache status label
        self.cache_status_var = tk.StringVar(value="")
        ttk.Label(top_frame, textvariable=self.cache_status_var, foreground='green').grid(row=2, column=2, sticky='w')

        # Seller (Podmiot1) config
        seller_frame = ttk.LabelFrame(left_frame, text="Seller (Podmiot1)", padding="10")
        seller_frame.pack(fill='x', padx=10, pady=(0, 5))

        self.seller_nip_var = tk.StringVar()
        self.seller_name_var = tk.StringVar()
        self.seller_addr1_var = tk.StringVar()
        self.seller_addr2_var = tk.StringVar()
        self.seller_city_var = tk.StringVar()

        ttk.Label(seller_frame, text="NIP:").grid(row=0, column=0, sticky='w')
        ttk.Entry(seller_frame, textvariable=self.seller_nip_var, width=25).grid(row=0, column=1, sticky='w', padx=5)
        ttk.Label(seller_frame, text="Name:").grid(row=0, column=2, sticky='w')
        ttk.Entry(seller_frame, textvariable=self.seller_name_var, width=35).grid(row=0, column=3, sticky='w', padx=5)

        ttk.Label(seller_frame, text="Address L1:").grid(row=1, column=0, sticky='w', pady=(5, 0))
        ttk.Entry(seller_frame, textvariable=self.seller_addr1_var, width=40).grid(row=1, column=1, columnspan=3, sticky='w', padx=5, pady=(5, 0))

        ttk.Label(seller_frame, text="Address L2:").grid(row=2, column=0, sticky='w', pady=(5, 0))
        ttk.Entry(seller_frame, textvariable=self.seller_addr2_var, width=40).grid(row=2, column=1, columnspan=3, sticky='w', padx=5, pady=(5, 0))

        ttk.Label(seller_frame, text="City (P_1M):").grid(row=3, column=0, sticky='w', pady=(5, 0))
        ttk.Entry(seller_frame, textvariable=self.seller_city_var, width=25).grid(row=3, column=1, sticky='w', padx=5, pady=(5, 0))
        
        ttk.Button(seller_frame, text="Save Config", command=self._on_save_config).grid(row=3, column=3, sticky='e', padx=5, pady=(5, 0))
        
        # KSeF Options (JST, GV) frame
        ksef_opts_frame = ttk.LabelFrame(left_frame, text="KSeF Options (Podmiot2 flags)", padding="5")
        ksef_opts_frame.pack(fill='x', padx=10, pady=(0, 5))
        
        self.jst_var = tk.BooleanVar(value=False)
        self.gv_var = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(ksef_opts_frame, text="JST - Nabywca jest jednostką samorządu terytorialnego", 
                        variable=self.jst_var).grid(row=0, column=0, sticky='w')
        ttk.Checkbutton(ksef_opts_frame, text="GV - Nabywca jest członkiem grupy VAT", 
                        variable=self.gv_var).grid(row=0, column=1, sticky='w', padx=(20, 0))
        
        # Podmiot3 (Third party / Receiver) frame
        podmiot3_frame = ttk.LabelFrame(left_frame, text="Podmiot3 - Odbiorca (opcjonalne)", padding="5")
        podmiot3_frame.pack(fill='x', padx=10, pady=(0, 5))
        
        self.podmiot3_enabled_var = tk.BooleanVar(value=False)
        self.podmiot3_nip_var = tk.StringVar()
        self.podmiot3_name_var = tk.StringVar()
        self.podmiot3_addr1_var = tk.StringVar()
        self.podmiot3_addr2_var = tk.StringVar()
        self.podmiot3_email_var = tk.StringVar()
        self.podmiot3_rola_var = tk.StringVar(value='2')  # Default: Odbiorca
        
        ttk.Checkbutton(podmiot3_frame, text="Dodaj Podmiot3", 
                        variable=self.podmiot3_enabled_var).grid(row=0, column=0, sticky='w')
        
        ttk.Label(podmiot3_frame, text="NIP/IDWew:").grid(row=0, column=1, sticky='w', padx=(15, 0))
        ttk.Entry(podmiot3_frame, textvariable=self.podmiot3_nip_var, width=20).grid(row=0, column=2, sticky='w', padx=2)
        
        ttk.Label(podmiot3_frame, text="Nazwa:").grid(row=0, column=3, sticky='w', padx=(10, 0))
        ttk.Entry(podmiot3_frame, textvariable=self.podmiot3_name_var, width=30).grid(row=0, column=4, sticky='w', padx=2)
        
        ttk.Label(podmiot3_frame, text="Adres:").grid(row=1, column=0, sticky='w', pady=(3, 0))
        ttk.Entry(podmiot3_frame, textvariable=self.podmiot3_addr1_var, width=35).grid(row=1, column=1, columnspan=2, sticky='w', padx=2, pady=(3, 0))
        ttk.Entry(podmiot3_frame, textvariable=self.podmiot3_addr2_var, width=25).grid(row=1, column=3, columnspan=2, sticky='w', padx=2, pady=(3, 0))
        
        ttk.Label(podmiot3_frame, text="Email:").grid(row=2, column=0, sticky='w', pady=(3, 0))
        ttk.Entry(podmiot3_frame, textvariable=self.podmiot3_email_var, width=35).grid(row=2, column=1, columnspan=2, sticky='w', padx=2, pady=(3, 0))
        
        ttk.Label(podmiot3_frame, text="Rola:").grid(row=3, column=0, sticky='w', pady=(3, 0))
        rola_combo = ttk.Combobox(podmiot3_frame, textvariable=self.podmiot3_rola_var, width=50, state='readonly')
        rola_combo['values'] = (
            '2 - Odbiorca (jednostka wewnętrzna nabywcy)',
            '8 - Jednostka samorządu terytorialnego - odbiorca',
            '10 - Członek grupy VAT - odbiorca',
            '1 - Faktor',
            '4 - Dodatkowy nabywca',
        )
        rola_combo.grid(row=3, column=1, columnspan=4, sticky='w', padx=2, pady=(3, 0))
        
        # Invoice list (left)
        list_frame = ttk.LabelFrame(left_frame, text="Invoices", padding="10")
        list_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Pagination controls at top
        page_frame = ttk.Frame(list_frame)
        page_frame.pack(fill='x', pady=(0, 5))
        
        self.prev_btn = ttk.Button(page_frame, text="◀ Prev", command=self._prev_page, width=8)
        self.prev_btn.pack(side='left')
        
        self.page_label = ttk.Label(page_frame, text="Page 0/0 (0 invoices)")
        self.page_label.pack(side='left', padx=10)
        
        self.next_btn = ttk.Button(page_frame, text="Next ▶", command=self._next_page, width=8)
        self.next_btn.pack(side='left')
        
        ttk.Label(page_frame, text="  (Page Up/Down)").pack(side='left', padx=5)
        
        # Export button in same row
        self.export_btn = ttk.Button(page_frame, text="Export to KSeF XML", command=self._export_selected)
        self.export_btn.pack(side='right', padx=5)
        
        # Treeview for invoices (without Items column - loaded on demand)
        columns = ('exp', 'id', 'number', 'year', 'date', 'customer', 'nip')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings', selectmode='extended')
        
        self.tree.heading('exp', text='Exp')
        self.tree.heading('id', text='ID')
        self.tree.heading('number', text='Number')
        self.tree.heading('year', text='Year')
        self.tree.heading('date', text='Date')
        self.tree.heading('customer', text='Customer')
        self.tree.heading('nip', text='NIP')
        
        self.tree.column('exp', width=35, anchor='center')
        self.tree.column('id', width=50)
        self.tree.column('number', width=80)
        self.tree.column('year', width=50)
        self.tree.column('date', width=100)
        self.tree.column('customer', width=300)
        self.tree.column('nip', width=120)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Bind selection event
        self.tree.bind('<<TreeviewSelect>>', self._on_select)
        
        # Bind Page Up/Down keys
        self.root.bind('<Prior>', lambda e: self._prev_page())  # Page Up
        self.root.bind('<Next>', lambda e: self._next_page())   # Page Down
        
        # Right column - preview only (graphical text panel)
        self.preview_text = tk.Text(right_frame, wrap='none', font=('Courier New', 10))
        self.preview_text.pack(side='left', fill='both', expand=True)
        preview_scroll = ttk.Scrollbar(right_frame, orient='vertical', command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=preview_scroll.set)
        preview_scroll.pack(side='right', fill='y')
        
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready. Load database files to begin.")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief='sunken', anchor='w')
        status_bar.pack(fill='x', side='bottom')
        
        # Restore sash position from config (or default 420)
        sash_pos = self.config.get('gui', {}).get('sash_position', 420)
        self.root.after(100, lambda: self.main_paned.sashpos(0, sash_pos))
        
    def _browse_head(self):
        path = filedialog.askopenfilename(
            title="Select TRANHEAD.DAT",
            filetypes=[("DAT files", "*.dat"), ("All files", "*.*")]
        )
        if path:
            self.head_path_var.set(path)
            
    def _browse_elem(self):
        path = filedialog.askopenfilename(
            title="Select TRANELEM.DAT",
            filetypes=[("DAT files", "*.dat"), ("All files", "*.*")]
        )
        if path:
            self.elem_path_var.set(path)
            
    def _apply_config(self):
        """Apply loaded config to GUI fields (seller + file paths + window geometry)."""
        gui = self.config.get('gui', {})
        geometry = gui.get('window_geometry', '1500x800')
        self.root.geometry(geometry)

        seller = self.config.get('seller', {})
        self.seller_nip_var.set(seller.get('nip', ''))
        self.seller_name_var.set(seller.get('name', ''))
        self.seller_addr1_var.set(seller.get('addr1', ''))
        self.seller_addr2_var.set(seller.get('addr2', ''))
        self.seller_city_var.set(seller.get('city', ''))

        paths = self.config.get('paths', {})
        head = paths.get('tranhead', 'TRANHEAD.DAT')
        elem = paths.get('tranelem', 'TRANELEM.DAT')
        if head and os.path.exists(head):
            self.head_path_var.set(head)
        if elem and os.path.exists(elem):
            self.elem_path_var.set(elem)

    def _save_current_config(self):
        """Persist current seller data and file paths to config.json."""
        self.config['seller'] = {
            **self.config.get('seller', {}),
            'nip': self.seller_nip_var.get().strip(),
            'name': self.seller_name_var.get().strip(),
            'addr1': self.seller_addr1_var.get().strip(),
            'addr2': self.seller_addr2_var.get().strip(),
            'city': self.seller_city_var.get().strip(),
        }
        head = self.head_path_var.get().strip()
        elem = self.elem_path_var.get().strip()
        if head or elem:
            self.config['paths'] = {
                'tranhead': head,
                'tranelem': elem,
            }
        try:
            self.config['gui'] = {
                'sash_position': self.main_paned.sashpos(0),
                'window_geometry': self.root.geometry(),
            }
        except Exception:
            pass
        save_config(self.config)

    def _on_save_config(self):
        """Button handler: save config and show confirmation."""
        self._save_current_config()
        self.status_var.set(f"Config saved to {CONFIG_FILE}")

    def _load_database(self):
        """Load the database files with pagination (newest first, 9 at a time)."""
        head_path = self.head_path_var.get()
        elem_path = self.elem_path_var.get()
        
        if not head_path or not elem_path:
            messagebox.showerror("Error", "Please select both TRANHEAD.DAT and TRANELEM.DAT files.")
            return
        
        # Check if already loaded (same files)
        if (self.head_reader and self.elem_reader and 
            str(self.head_reader.filepath) == head_path and 
            str(self.elem_reader.filepath) == elem_path):
            # Already loaded - just refresh display
            self._refresh_indices()
            return
            
        self._do_load_database(head_path, elem_path)
    
    def _refresh_database(self):
        """Refresh database from disk (re-read files)."""
        if not self.head_reader or not self.elem_reader:
            messagebox.showinfo("Info", "No database loaded. Use 'Load Database' first.")
            return
        
        head_path = str(self.head_reader.filepath)
        elem_path = str(self.elem_reader.filepath)
        self._do_load_database(head_path, elem_path)
    
    def _do_load_database(self, head_path: str, elem_path: str):
        """Actually load database files into memory."""
        try:
            self.status_var.set("Loading TRANHEAD.DAT...")
            self.cache_status_var.set("")
            self.root.update()
            
            self.head_reader = TranHeadReader(head_path)
            self.head_reader.open()
            
            self.status_var.set("Loading TRANELEM.DAT + building index...")
            self.root.update()
            
            self.elem_reader = TranElemReader(elem_path)
            self.elem_reader.open()
            
            materia_path = os.path.join(os.path.dirname(head_path), 'MATERIA.DAT')
            self.pkwiu_map = {}
            if os.path.exists(materia_path):
                self.status_var.set("Loading MATERIA.DAT (PKWiU)...")
                self.root.update()
                materia = MateriaReader(materia_path)
                materia.open()
                self.pkwiu_map = materia.pkwiu_map
            
            self._refresh_indices()
            
            # Show cache status
            head_size = len(self.head_reader._data) // 1024
            elem_size = len(self.elem_reader._data) // 1024
            pkwiu_info = f", PKWiU: {len(self.pkwiu_map)}" if self.pkwiu_map else ""
            self.cache_status_var.set(f"✓ Cached: {head_size}KB + {elem_size}KB{pkwiu_info}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load database: {e}")
            self.status_var.set(f"Error: {e}")
            self.cache_status_var.set("")
    
    def _refresh_indices(self):
        """Refresh filtered indices without reloading files from disk."""
        self.status_var.set("Indexing invoices (typ=2, seria=F*)...")
        self.root.update()
        
        # Get filtered indices (fast - only checks typ byte + seria prefix, reverse order = newest first)
        self.filtered_indices = self.head_reader.get_filtered_indices(typ_filter=2, seria_prefix='F')
        self.elements_cache = {}
        self.payment_cache = {}
        self.current_page = 0
        
        # Display first page
        self._display_current_page()
        
        self.status_var.set(f"Found {len(self.filtered_indices)} invoices. Showing page 1.")
    
    def _display_current_page(self, keep_selection: bool = False):
        """Display current page of invoices."""
        if not self.head_reader:
            return
            
        # Calculate page bounds
        total = len(self.filtered_indices)
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, total)
        
        # Update page label
        self.page_label.config(text=f"Page {self.current_page + 1}/{total_pages} ({total} invoices)")
        
        # Enable/disable navigation buttons
        self.prev_btn.config(state='normal' if self.current_page > 0 else 'disabled')
        self.next_btn.config(state='normal' if self.current_page < total_pages - 1 else 'disabled')
        
        # Get records for current page
        page_indices = self.filtered_indices[start_idx:end_idx]
        self.invoices = self.head_reader.read_records_by_indices(page_indices)
        
        # Clear and populate treeview
        self.tree.delete(*self.tree.get_children())
        
        for inv in self.invoices:
            exp_mark = '✓' if inv.full_number in self.exported else ''
            self.tree.insert('', 'end', values=(
                exp_mark,
                inv.id,
                inv.full_number,
                inv.rok,
                str(inv.data) if inv.data else '',
                inv.customer_name[:40] if inv.customer_name else '',
                inv.nip or ''
            ))
        
        # Select row at same position after page change
        if keep_selection:
            children = self.tree.get_children()
            if children:
                # Clamp selection index to available rows
                select_idx = min(self.selected_row_index, len(children) - 1)
                self.tree.selection_set(children[select_idx])
                self.tree.focus(children[select_idx])
                self.tree.see(children[select_idx])
        else:
            # Clear preview
            self.preview_text.delete('1.0', 'end')
    
    def _prev_page(self):
        """Go to previous page."""
        if self.current_page > 0:
            self._save_selection_index()
            self.current_page -= 1
            self._display_current_page(keep_selection=True)
    
    def _next_page(self):
        """Go to next page."""
        total = len(self.filtered_indices)
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)
        if self.current_page < total_pages - 1:
            self._save_selection_index()
            self.current_page += 1
            self._display_current_page(keep_selection=True)
    
    def _save_selection_index(self):
        """Save the current selection row index."""
        selection = self.tree.selection()
        if selection:
            children = self.tree.get_children()
            try:
                self.selected_row_index = children.index(selection[0])
            except ValueError:
                self.selected_row_index = 0
        else:
            self.selected_row_index = 0
            
    def _on_select(self, event):
        """Handle invoice selection - loads TRANELEM on demand."""
        selection = self.tree.selection()
        if not selection:
            self.preview_text.delete('1.0', 'end')
            return
            
        # Show details for first selected item
        item = self.tree.item(selection[0])
        values = item['values']
        inv_id = values[1]  # index 1 because 'exp' is at 0
        
        # Find the invoice
        invoice = next((inv for inv in self.invoices if inv.id == inv_id), None)
        if not invoice:
            return
        
        # Lazy load elements and payment info if not cached
        if inv_id not in self.elements_cache:
            self.status_var.set(f"Loading items for invoice {invoice.full_number}...")
            self.root.update()
            if self.elem_reader:
                self.elements_cache[inv_id] = self.elem_reader.get_elements_for_invoice(inv_id)
                self.payment_cache[inv_id] = self.elem_reader.get_payment_info_for_invoice(inv_id)
            else:
                self.elements_cache[inv_id] = []
                self.payment_cache[inv_id] = ""
            self.status_var.set(f"Loaded {len(self.elements_cache[inv_id])} items.")
            
        elements = self.elements_cache.get(inv_id, [])
        payment_info = self.payment_cache.get(inv_id, "")
        
        # Update preview panel
        preview = self._build_preview_text(invoice, elements, payment_info)
        self.preview_text.delete('1.0', 'end')
        self.preview_text.insert('1.0', preview)

    def _build_preview_text(self, invoice: InvoiceHeader, elements: List[InvoiceElement], payment_info: str) -> str:
        """Build a readable invoice preview for on-screen validation."""
        def fmt(val: Optional[str]) -> str:
            return val.strip() if val else ""

        lines = []
        lines.append(f"Faktura VAT: {invoice.full_number}")
        lines.append(f"Data wystawienia: {invoice.data if invoice.data else ''}")
        lines.append(f"Data sprzedazy:   {invoice.data if invoice.data else ''}")
        if invoice.dokument:
            lines.append(f"Dokument:         {invoice.dokument}")
            lines.append("")
        platnosc_label = PLATNOSC_LABELS.get(invoice.platnosc, f'nieznana ({invoice.platnosc})')
        lines.append(f"Forma platnosci:  {platnosc_label}")
        if invoice.termin and invoice.data and invoice.termin != invoice.data:
            lines.append(f"Termin platnosci: {invoice.termin}")
            bank_nr = self.config.get('bank', {}).get('nrRB', '')
            if bank_nr:
                lines.append(f"Nr rachunku:      {bank_nr}")
        if payment_info:
            lines.append(f"Info o platnosci: {payment_info}")
        lines.append("")
        lines.append("Nabywca:")
        lines.append(fmt(f"{invoice.k_nazwa1} {invoice.k_nazwa2}"))
        lines.append(fmt(invoice.k_adres1))
        lines.append(fmt(f"{invoice.k_kodp} {invoice.k_miasto}".strip()))
        if invoice.nip:
            lines.append(f"NIP: {invoice.nip}")
        lines.append("")
        lines.append("Odbiorca:")
        odb_name = fmt(f"{invoice.o_nazwa1} {invoice.o_nazwa2}")
        if odb_name or invoice.odb:
            lines.append(odb_name if odb_name else fmt(invoice.odb))
            lines.append(fmt(invoice.o_adres1))
            if invoice.o_adres2:
                lines.append(fmt(invoice.o_adres2))
            lines.append(fmt(f"{invoice.o_kodp} {invoice.o_miasto}".strip()))
        else:
            lines.append("(brak danych odbiorcy)")
        lines.append("")
        lines.append("Pozycje:")
        header = f"{'LP':>3} {'Nazwa/Usługa':40} {'Ilosc':>8} {'JM':>4} {'Cena netto':>11} {'Wart. netto':>12} {'VAT%':>6}"
        lines.append(header)
        lines.append("-" * len(header))
        if not elements:
            lines.append("(brak pozycji)")
        else:
            for elem in sorted(elements, key=lambda x: x.lp):
                price = _ksef_price_pln(elem)
                wart_netto = (elem.ile * price) if price is not None else elem.ile
                lines.append(
                    f"{elem.lp:>3} {elem.nazwa[:40]:40} {elem.ile:>8} {elem.jm:>4} {price:>11} {round(wart_netto, 2):>12} {elem.podatek:>6}"
                )
                gtu = _match_gtu(elem)
                pkwiu = self.pkwiu_map.get((elem.kod or '').strip(), '')
                if gtu or pkwiu:
                    tags = '  '.join(filter(None, [gtu, f"PKWiU: {pkwiu}" if pkwiu else '']))
                    lines.append(f"      {tags}")
        lines.append("")
        lines.append("Podsumowanie:")
        lines.append(f"Wartosc netto: {invoice.total}")
        lines.append(f"VAT:           {invoice.vat}")
        brutto = round(invoice.total + invoice.vat, 2)
        lines.append(f"Brutto:        {brutto}")
        if invoice.opis:
            lines.append(f"Uwagi: {invoice.opis}")
        return "\n".join(lines)
        
    def _get_seller_info(self) -> Dict[str, str]:
        bank = self.config.get('bank', {})
        return {
            'nip': self.seller_nip_var.get().strip(),
            'name': self.seller_name_var.get().strip(),
            'addr1': self.seller_addr1_var.get().strip(),
            'addr2': self.seller_addr2_var.get().strip(),
            'city': self.seller_city_var.get().strip(),
            'country': 'PL',
            'bank_nrRB': bank.get('nrRB', ''),
            'bank_nazwa': bank.get('nazwa', ''),
        }
    
    def _get_ksef_options(self) -> Dict[str, Any]:
        """Get KSeF export options including JST, GV, and Podmiot3."""
        # Parse rola from combobox (e.g., "2 - Odbiorca..." -> "2")
        rola_full = self.podmiot3_rola_var.get()
        rola = rola_full.split(' - ')[0] if ' - ' in rola_full else '2'
        
        return {
            'jst': self.jst_var.get(),
            'gv': self.gv_var.get(),
            'podmiot3_enabled': self.podmiot3_enabled_var.get(),
            'podmiot3_nip': self.podmiot3_nip_var.get().strip(),
            'podmiot3_name': self.podmiot3_name_var.get().strip(),
            'podmiot3_addr1': self.podmiot3_addr1_var.get().strip(),
            'podmiot3_addr2': self.podmiot3_addr2_var.get().strip(),
            'podmiot3_email': self.podmiot3_email_var.get().strip(),
            'podmiot3_rola': rola,
        }
        
    def _export_selected(self):
        """Export selected invoices to XML."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select at least one invoice to export.")
            return
        if len(selection) != 1:
            messagebox.showwarning("Warning", "KSeF export supports one invoice at a time.")
            return
            
        # Collect invoice data first for validation
        item = self.tree.item(selection[0])
        inv_id = item['values'][1]  # index 1 because 'exp' is at 0
        invoice = next((inv for inv in self.invoices if inv.id == inv_id), None)
        if not invoice:
            messagebox.showerror("Error", "Invoice not found.")
            return
        elements = self.elements_cache.get(inv_id, [])
        payment_info = self.payment_cache.get(inv_id, "")
        seller = self._get_seller_info()
        ksef_options = self._get_ksef_options()
        
        # === WALIDACJA ===
        validation_errors = validate_ksef_export(invoice, elements, seller)
        if validation_errors:
            error_msg = "Nie można wyeksportować faktury do KSeF.\n\nBrakujące lub nieprawidłowe dane:\n\n"
            error_msg += "\n".join(f"• {err}" for err in validation_errors)
            error_msg += "\n\nUzupełnij brakujące dane i spróbuj ponownie."
            messagebox.showerror("Błąd walidacji KSeF", error_msg)
            return
            
        # Build default filename from invoice number: FIC/8/25 -> faktura_VAT_FIC-8-25.xml
        safe_number = invoice.full_number.replace('/', '-')
        safe_number = re.sub(r'[\\/:*?"<>|]', '-', safe_number)
        default_filename = f"faktura_VAT_{safe_number}.xml"

        filepath = filedialog.asksaveasfilename(
            title="Export KSeF Invoice",
            initialfile=default_filename,
            defaultextension=".xml",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")]
        )
        
        if not filepath:
            return
            
        try:
            self._save_current_config()
            self.status_var.set("Exporting...")
            self.root.update()

            # Export KSeF FA(3)
            export_ksef_invoice_to_file(invoice, elements, payment_info, seller, filepath, ksef_options, self.pkwiu_map)
            
            self.exported[invoice.full_number] = {
                'number': invoice.full_number,
                'id': invoice.id,
                'seria': invoice.seria,
                'numer': invoice.numer,
                'rok': invoice.rok,
                'exported_at': datetime.now().isoformat(timespec='seconds'),
                'file': filepath,
            }
            save_exported(self.exported)
            self._save_selection_index()
            self._display_current_page(keep_selection=True)

            self.status_var.set(f"Exported invoice {invoice.full_number} to {filepath}")
            messagebox.showinfo("Success", f"Pomyślnie wyeksportowano fakturę do:\n{filepath}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {e}")
            self.status_var.set(f"Export error: {e}")


def main():
    """Main entry point."""
    root = tk.Tk()
    
    # Set theme
    style = ttk.Style()
    available_themes = style.theme_names()
    if 'clam' in available_themes:
        style.theme_use('clam')
    elif 'vista' in available_themes:
        style.theme_use('vista')
        
    app = InvoiceExporterApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
