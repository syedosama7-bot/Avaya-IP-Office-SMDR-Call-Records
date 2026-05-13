import csv
import re
import logging
import sqlite3
from io import StringIO

logger = logging.getLogger(__name__)

def parse_and_save(raw_data, db_path):
    match = re.search(r'(\d{4}/\d{2}/\d{2}\s\d{2}:\d{2}:\d{2},.*)', raw_data)
    if not match:
        logger.debug(f"No SMDR record found in data: {raw_data[:100]}")
        return
    try:
        line = match.group(1).strip()
        row = next(csv.reader(StringIO(line)))
        # Pad up to 30 fields
        while len(row) < 30:
            row.append('')

        call_start   = row[0]
        duration     = row[1]
        ring_time    = int(row[2]) if row[2].strip().isdigit() else 0
        caller       = row[3]
        direction    = "Inbound" if row[4] == "I" else "Outbound"
        called_num   = row[5]
        dialled_num  = row[6]
        account_code = row[7]
        is_int_raw   = int(row[8]) if row[8].strip().isdigit() else 0
        call_id      = int(row[9]) if row[9].strip().isdigit() else None
        continuation = int(row[10]) if row[10].strip().isdigit() else 0
        party1_dev   = row[11]
        party1_name  = row[12]
        party2_dev   = row[13]
        party2_name  = row[14]
        hold_time    = int(row[15]) if row[15].strip().isdigit() else 0
        park_time    = int(row[16]) if row[16].strip().isdigit() else 0
        auth_valid   = int(row[17]) if row[17].strip().isdigit() else 0
        auth_code    = row[18] if row[18] != 'n/a' else None

        # New fields (28‑30)
        external_targeting_cause = row[27] if len(row) > 27 else ''
        external_targeter_id     = row[28] if len(row) > 28 else ''
        external_targeted_number = row[29] if len(row) > 29 else ''

        h, m, s = map(int, duration.split(':'))
        sec = (h * 3600) + (m * 60) + s

        # Direct DB insert – no Flask context needed
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO calls
            (call_start, duration_raw, duration_seconds, ring_time,
             caller, direction, called_num, dialled_num, account_code,
             is_internal, call_id, continuation, party1_device, party1_name,
             party2_device, party2_name, hold_time, park_time,
             auth_valid, auth_code, cost,
             external_targeting_cause, external_targeter_id, external_targeted_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?)
        ''', (call_start, duration, sec, ring_time,
              caller, direction, called_num, dialled_num, account_code,
              is_int_raw, call_id, continuation, party1_dev, party1_name,
              party2_dev, party2_name, hold_time, park_time,
              auth_valid, auth_code, 0.0,
              external_targeting_cause, external_targeter_id, external_targeted_number))
        conn.commit()
        conn.close()
        logger.info(f"SMDR saved: {party1_name} | {caller} -> {called_num}")
    except Exception as e:
        logger.error(f"SMDR parse error: {e}, raw data: {raw_data[:200]}")