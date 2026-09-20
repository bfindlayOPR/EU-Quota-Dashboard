"""
One-off diagnostic. Prints every quota period row TARIC currently returns for
a few order numbers, so we can see whether two periods now exist and which
column the balance is really in.

Run:  python debug_periods.py            (uses the default sample orders)
      python debug_periods.py 09.9801    (or pass your own)

Changes nothing. Writes nothing. Safe to run any time.
"""

import re
import sys
import requests
from bs4 import BeautifulSoup
from datetime import date

BASE = "https://ec.europa.eu/taxation_customs/dds2/taric/"
YEAR = date.today().year
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# A few orders worth looking at: one that was exhausted in August, plus others.
DEFAULT_ORDERS = ["09.9801", "09.9802", "09.8805"]


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en"})
    s.get(BASE + "quota_consultation.jsp?Lang=en", timeout=60)
    return s


def dump(sess, order):
    code = order.replace(".", "")
    url = (BASE + "quota_list.jsp?Lang=en&Code=" + code +
           "&Year=" + str(YEAR) + "&Expand=true&Offset=0")
    print("\n" + "=" * 70)
    print("ORDER", order)
    print(url)
    print("=" * 70)

    r = sess.get(url, headers={"Referer": BASE + "quota_consultation.jsp?Lang=en"},
                 timeout=60)
    r.raise_for_status()
    text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)

    # (A) What the CURRENT code finds -- first match only.
    old = re.search(code + r"\s+(.+?)\s+\d{2}-\d{2}-\d{4}\s+\d{2}-\d{2}-\d{4}\s+"
                    r"(\d+(?:\.\d+)?)\s*(Kilogram|Tonne|Ton|Litre|Piece|\w+)?", text)
    print("\n[A] What the live script picks up (first match only):")
    print("   ", old.group(0)[:160] if old else "NO MATCH")

    # (B) Every period row present.
    pat = (code + r"\s+(.+?)\s+(\d{2}-\d{2}-\d{4})\s+(\d{2}-\d{2}-\d{4})\s+"
           r"(\d+(?:\.\d+)?)\s*(Kilogram|Tonne|Ton|Litre|Piece|\w+)?")
    hits = list(re.finditer(pat, text))
    print("\n[B] Period rows found: %d" % len(hits))
    for i, m in enumerate(hits, 1):
        print("    %d. %s | %s -> %s | %s %s"
              % (i, m.group(1).strip()[:34], m.group(2), m.group(3),
                 m.group(4), m.group(5) or ""))

    # (C) Raw text around the order code, to confirm column order.
    i = text.find(code)
    print("\n[C] Raw page text around the order code "
          "(check whether the number after the dates is the BALANCE "
          "or the INITIAL VOLUME):")
    print("   ", text[max(0, i - 60):i + 400].replace("  ", " ") if i >= 0
          else "order code not found in page text")


def main():
    orders = sys.argv[1:] or DEFAULT_ORDERS
    print("Today:", date.today(), "| Year param:", YEAR)
    s = session()
    for o in orders:
        try:
            dump(s, o)
        except Exception as e:                       # noqa: BLE001
            print("\nORDER %s FAILED: %s" % (o, e))


if __name__ == "__main__":
    main()
