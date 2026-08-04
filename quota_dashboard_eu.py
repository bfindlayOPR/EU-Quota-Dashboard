"""
quota_dashboard_eu.py  (self-contained / cloud version)
-------------------------------------------------------
Builds the EU steel quota dashboard. The quota list (order number, category and
quarterly volumes) is baked in below from Commission Implementing Regulation
(EU) 2026/1457. For each order number it reads the live remaining balance from
the EU's tariff quota database and writes public/index.html.

The EU has no clean API, so the fetcher does a session "handshake" (loads the
consultation page to get a cookie) then requests quota_list.jsp per order number
and parses the balance out of the returned table. Balances are published in
kilograms and converted to tonnes.

Requires: requests, beautifulsoup4  ->  pip install requests beautifulsoup4
"""

import os
import re
import time
import html as htmllib
from datetime import datetime, date

try:
    from zoneinfo import ZoneInfo
    UK_TZ = ZoneInfo("Europe/London")
except Exception:
    UK_TZ = None

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------- settings
OUTPUT_HTML = os.path.join("public", "index.html")
YEAR        = 2026
WARN_PCT    = 0.20
CRIT_PCT    = 0.10
BASE = "https://ec.europa.eu/taxation_customs/dds2/taric/"
UA   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

# Category code -> readable name (standard EU steel safeguard categories)
CATEGORY_NAMES = {
    "1.A": "Non-alloy & other alloy hot rolled sheets/strips",
    "1.B": "Non-alloy & other alloy hot rolled sheets/strips (7212 60)",
    "2":   "Non-alloy & other alloy cold rolled sheets",
    "3.A": "Electrical sheets (non grain-oriented)",
    "3.B": "Electrical sheets (grain-oriented)",
    "4.A": "Metallic coated sheets",
    "4.B": "Metallic coated sheets (automotive)",
    "5":   "Organic coated sheets",
    "6":   "Tin mill products",
    "7":   "Non-alloy & other alloy quarto plates",
    "8":   "Stainless hot rolled sheets and strips",
    "9":   "Stainless cold rolled sheets and strips",
    "10":  "Stainless hot rolled quarto plates",
    "12":  "Non-alloy & other alloy merchant bars & light sections",
    "13":  "Rebars",
    "14":  "Stainless bars and light sections",
    "15":  "Stainless wire rod",
    "16":  "Non-alloy & other alloy wire rod",
    "17":  "Angles, shapes and sections of iron/non-alloy steel",
    "18":  "Sheet piling",
    "19":  "Railway material",
    "20":  "Gas pipes",
    "21":  "Hollow sections",
    "22":  "Seamless stainless tubes and pipes",
    "24":  "Other seamless tubes",
    "25.A": "Large welded tubes",
    "25.B": "Large welded tubes (line pipe)",
    "26":  "Other welded tubes",
    "27":  "Non-alloy & alloy cold finished bars",
}

# order, category, origin(country/allocation), Q1(Jul-Sep), Q2(Oct-Dec), Q3(Jan-Mar), Q4(Apr-Jun) in net tonnes
QUOTAS_EU = [
    ("09.9801", "1.A", "Türkiye", 160573.74, 160573.74, 160573.74, 160573.74),
    ("09.9802", "1.A", "Japan", 137884.78, 137884.78, 137884.78, 137884.78),
    ("09.9803", "1.A", "India", 149318.61, 149318.61, 149318.61, 149318.61),
    ("09.9804", "1.A", "Taiwan", 69730.64, 69730.64, 69730.64, 69730.64),
    ("09.9805", "1.A", "Ukraine", 120882.35, 120882.35, 120882.35, 120882.35),
    ("09.9806", "1.A", "Korea", 115457.52, 115457.52, 115457.52, 115457.52),
    ("09.9807", "1.A", "Viet Nam", 103743.08, 103743.08, 103743.08, 103743.08),
    ("09.9808", "1.A", "Egypt", 101232.21, 101232.21, 101232.21, 101232.21),
    ("09.9809", "1.A", "Serbia", 64523.65, 64523.65, 64523.65, 64523.65),
    ("09.9500", "1.A", "FTA Quota – CSQ", 120920.56, 120920.56, 120920.56, 120920.56),
    ("09.9701", "1.A", "Brazil", 42512.75, 42512.75, 42512.75, 42512.75),
    ("09.9705", "1.A", "United Kingdom", 38481.14, 38481.14, 38481.14, 38481.14),
    ("09.9702", "1.A", "Indonesia", 31834.46, 31834.46, 31834.46, 31834.46),
    ("09.9810", "1.A", "Australia", 11830.05, 11830.05, 11830.05, 11830.05),
    ("09.9811", "1.A", "Saudi Arabia", 9545.08, 9545.08, 9545.08, 9545.08),
    ("09.9704", "1.A", "Switzerland", 5472.5, 5472.5, 5472.5, 5472.5),
    ("09.9812", "1.A", "Kazakhstan", 2377.67, 2377.67, 2377.67, 2377.67),
    ("09.9703", "1.A", "North Macedonia", 3531.91, 3531.91, 3531.91, 3531.91),
    ("09.9600", "1.A", "Other countries", 5564.01, 5564.01, 5564.01, 5564.01),
    ("09.9700", "1.A", "FTA Quota – Other countries", 4271.87, 4271.87, 4271.87, 4271.87),
    ("09.9813", "1.B", "United Kingdom", 526.03, 526.03, 526.03, 526.03),
    ("09.9814", "1.B", "United States", 127.34, 127.34, 127.34, 127.34),
    ("09.9815", "1.B", "Japan", 243.93, 243.93, 243.93, 243.93),
    ("09.9816", "1.B", "China", 35.59, 35.59, 35.59, 35.59),
    ("09.9501", "1.B", "FTA Quota – CSQ", 106.52, 106.52, 106.52, 106.52),
    ("09.9601", "1.B", "Other countries", 44.89, 44.89, 44.89, 44.89),
    ("09.9706", "1.B", "FTA Quota – Other countries", 60.94, 60.94, 60.94, 60.94),
    ("09.9817", "2", "Taiwan", 33586.54, 33586.54, 33586.54, 33586.54),
    ("09.9818", "2", "India", 67493.58, 67493.58, 67493.58, 67493.58),
    ("09.9819", "2", "Korea", 63652.67, 63652.67, 63652.67, 63652.67),
    ("09.9820", "2", "Türkiye", 60152.91, 60152.91, 60152.91, 60152.91),
    ("09.9821", "2", "United Kingdom", 19834.63, 19834.63, 19834.63, 19834.63),
    ("09.9822", "2", "Japan", 29457.81, 29457.81, 29457.81, 29457.81),
    ("09.9823", "2", "Ukraine", 26549.48, 26549.48, 26549.48, 26549.48),
    ("09.9502", "2", "FTA Quota – CSQ", 33670.61, 33670.61, 33670.61, 33670.61),
    ("09.9602", "2", "Other countries", 24933.92, 24933.92, 24933.92, 24933.92),
    ("09.9707", "2", "FTA Quota – Other countries", 21283.6, 21283.6, 21283.6, 21283.6),
    ("09.9709", "2", "Egypt", 1294.54, 1294.54, 1294.54, 1294.54),
    ("09.9710", "2", "Switzerland", 745.65, 745.65, 745.65, 745.65),
    ("09.9708", "2", "Brazil", 3533.82, 3533.82, 3533.82, 3533.82),
    ("09.9824", "3.A", "Japan", 77.95, 77.95, 77.95, 77.95),
    ("09.9825", "3.A", "United Kingdom", 19.56, 19.56, 19.56, 19.56),
    ("09.9826", "3.A", "China", 4.98, 4.98, 4.98, 4.98),
    ("09.9827", "3.A", "Türkiye", 8.69, 8.69, 8.69, 8.69),
    ("09.9503", "3.A", "FTA Quota – CSQ", 29.05, 29.05, 29.05, 29.05),
    ("09.9603", "3.A", "Other countries", 7.27, 7.27, 7.27, 7.27),
    ("09.9711", "3.A", "FTA Quota – Other countries", 5.43, 5.43, 5.43, 5.43),
    ("09.9828", "3.B", "China", 11837.81, 11837.81, 11837.81, 11837.81),
    ("09.9829", "3.B", "Taiwan", 5166.66, 5166.66, 5166.66, 5166.66),
    ("09.9830", "3.B", "Korea", 15495.38, 15495.38, 15495.38, 15495.38),
    ("09.9831", "3.B", "Viet Nam", 6925.39, 6925.39, 6925.39, 6925.39),
    ("09.9504", "3.B", "FTA Quota – CSQ", 4217.06, 4217.06, 4217.06, 4217.06),
    ("09.9604", "3.B", "Other countries", 1478.75, 1478.75, 1478.75, 1478.75),
    ("09.9712", "3.B", "FTA Quota – Other countries", 4094.55, 4094.55, 4094.55, 4094.55),
    ("09.9713", "3.B", "Japan", 554.14, 554.14, 554.14, 554.14),
    ("09.9832", "4.A", "Viet Nam", 117496.92, 117496.92, 117496.92, 117496.92),
    ("09.9833", "4.A", "Taiwan", 33783.39, 33783.39, 33783.39, 33783.39),
    ("09.9834", "4.A", "Türkiye", 63925.33, 63925.33, 63925.33, 63925.33),
    ("09.9835", "4.A", "India", 58295.85, 58295.85, 58295.85, 58295.85),
    ("09.9836", "4.A", "Korea", 26119.93, 26119.93, 26119.93, 26119.93),
    ("09.9505", "4.A", "FTA Quota – CSQ", 38881.49, 38881.49, 38881.49, 38881.49),
    ("09.9605", "4.A", "Other countries", 33338.76, 33338.76, 33338.76, 33338.76),
    ("09.9714", "4.A", "FTA Quota – Other countries", 12761.32, 12761.32, 12761.32, 12761.32),
    ("09.9718", "4.A", "United Kingdom", 11600.08, 11600.08, 11600.08, 11600.08),
    ("09.9716", "4.A", "Japan", 2874.21, 2874.21, 2874.21, 2874.21),
    ("09.9715", "4.A", "Egypt", 2943.83, 2943.83, 2943.83, 2943.83),
    ("09.9717", "4.A", "South Africa", 3150.34, 3150.34, 3150.34, 3150.34),
    ("09.9837", "4.B", "Korea", 110698.86, 110698.86, 110698.86, 110698.86),
    ("09.9838", "4.B", "China", 45749.21, 45749.21, 45749.21, 45749.21),
    ("09.9839", "4.B", "United Kingdom", 34302.33, 34302.33, 34302.33, 34302.33),
    ("09.9840", "4.B", "Türkiye", 26019.96, 26019.96, 26019.96, 26019.96),
    ("09.9841", "4.B", "India", 25510.91, 25510.91, 25510.91, 25510.91),
    ("09.9506", "4.B", "FTA Quota – CSQ", 19514.4, 19514.4, 19514.4, 19514.4),
    ("09.9606", "4.B", "Other countries", 23174.68, 23174.68, 23174.68, 23174.68),
    ("09.9719", "4.B", "FTA Quota – Other countries", 22585.17, 22585.17, 22585.17, 22585.17),
    ("09.9720", "4.B", "Egypt", 1878.7, 1878.7, 1878.7, 1878.7),
    ("09.9721", "4.B", "Switzerland", 314.48, 314.48, 314.48, 314.48),
    ("09.9842", "5", "India", 54334.43, 54334.43, 54334.43, 54334.43),
    ("09.9843", "5", "Korea", 41828.13, 41828.13, 41828.13, 41828.13),
    ("09.9844", "5", "Viet Nam", 12605.9, 12605.9, 12605.9, 12605.9),
    ("09.9845", "5", "Türkiye", 11568.94, 11568.94, 11568.94, 11568.94),
    ("09.9846", "5", "Taiwan", 5322.29, 5322.29, 5322.29, 5322.29),
    ("09.9847", "5", "United Kingdom", 7995.14, 7995.14, 7995.14, 7995.14),
    ("09.9507", "5", "FTA Quota – CSQ", 12575.71, 12575.71, 12575.71, 12575.71),
    ("09.9607", "5", "Other countries", 6968.09, 6968.09, 6968.09, 6968.09),
    ("09.9722", "5", "FTA Quota – Other countries", 1937.67, 1937.67, 1937.67, 1937.67),
    ("09.9723", "5", "North Macedonia", 1831.54, 1831.54, 1831.54, 1831.54),
    ("09.9848", "6", "China", 38352.2, 38352.2, 38352.2, 38352.2),
    ("09.9849", "6", "Serbia", 15211.06, 15211.06, 15211.06, 15211.06),
    ("09.9850", "6", "United Kingdom", 15618.02, 15618.02, 15618.02, 15618.02),
    ("09.9851", "6", "Türkiye", 14278.53, 14278.53, 14278.53, 14278.53),
    ("09.9852", "6", "Korea", 13880.42, 13880.42, 13880.42, 13880.42),
    ("09.9853", "6", "India", 11752.33, 11752.33, 11752.33, 11752.33),
    ("09.9508", "6", "FTA Quota – CSQ", 11254.86, 11254.86, 11254.86, 11254.86),
    ("09.9608", "6", "Other countries", 6446.51, 6446.51, 6446.51, 6446.51),
    ("09.9724", "6", "FTA Quota – Other countries", 5977.74, 5977.74, 5977.74, 5977.74),
    ("09.9725", "6", "Japan", 2917.88, 2917.88, 2917.88, 2917.88),
    ("09.9726", "6", "Singapore", 20.53, 20.53, 20.53, 20.53),
    ("09.9854", "7", "Korea", 79917.56, 79917.56, 79917.56, 79917.56),
    ("09.9855", "7", "Indonesia", 53152.58, 53152.58, 53152.58, 53152.58),
    ("09.9856", "7", "India", 52709.57, 52709.57, 52709.57, 52709.57),
    ("09.9857", "7", "Japan", 23294.11, 23294.11, 23294.11, 23294.11),
    ("09.9858", "7", "North Macedonia", 20671.86, 20671.86, 20671.86, 20671.86),
    ("09.9859", "7", "United Kingdom", 8284.85, 8284.85, 8284.85, 8284.85),
    ("09.9509", "7", "FTA Quota – CSQ", 22682.31, 22682.31, 22682.31, 22682.31),
    ("09.9609", "7", "Other countries", 18829.77, 18829.77, 18829.77, 18829.77),
    ("09.9727", "7", "FTA Quota – Other countries", 7414.97, 7414.97, 7414.97, 7414.97),
    ("09.9728", "7", "Türkiye", 7007.71, 7007.71, 7007.71, 7007.71),
    ("09.9491", "7", "United Kingdom (to Northern Ireland from other parts of the United Kingdom)", 5260.44, 5260.44, 5260.44, 5260.44),
    ("09.9860", "8", "Taiwan", 4995.96, 4995.96, 4995.96, 4995.96),
    ("09.9861", "8", "Indonesia", 8960.7, 8960.7, 8960.7, 8960.7),
    ("09.9862", "8", "India", 6504.78, 6504.78, 6504.78, 6504.78),
    ("09.9863", "8", "China", 2378.85, 2378.85, 2378.85, 2378.85),
    ("09.9864", "8", "Korea", 5183.78, 5183.78, 5183.78, 5183.78),
    ("09.9865", "8", "Türkiye", 3431.79, 3431.79, 3431.79, 3431.79),
    ("09.9866", "8", "South Africa", 3021.64, 3021.64, 3021.64, 3021.64),
    ("09.9510", "8", "FTA Quota – CSQ", 2806.15, 2806.15, 2806.15, 2806.15),
    ("09.9610", "8", "Other countries", 572.32, 572.32, 572.32, 572.32),
    ("09.9729", "8", "FTA Quota – Other countries", 427.29, 427.29, 427.29, 427.29),
    ("09.9492", "8", "United Kingdom (to Northern Ireland from other parts of the United Kingdom)", 13.35, 13.35, 13.35, 13.35),
    ("09.9867", "9", "Taiwan", 13246.22, 13246.22, 13246.22, 13246.22),
    ("09.9868", "9", "China", 10107.74, 10107.74, 10107.74, 10107.74),
    ("09.9869", "9", "Korea", 25471.04, 25471.04, 25471.04, 25471.04),
    ("09.9870", "9", "Türkiye", 17259.54, 17259.54, 17259.54, 17259.54),
    ("09.9871", "9", "South Africa", 13151.64, 13151.64, 13151.64, 13151.64),
    ("09.9872", "9", "Viet Nam", 10963.33, 10963.33, 10963.33, 10963.33),
    ("09.9873", "9", "India", 9513.44, 9513.44, 9513.44, 9513.44),
    ("09.9511", "9", "FTA Quota – CSQ", 9935.34, 9935.34, 9935.34, 9935.34),
    ("09.9611", "9", "Other countries", 8442.57, 8442.57, 8442.57, 8442.57),
    ("09.9730", "9", "FTA Quota – Other countries", 5554.25, 5554.25, 5554.25, 5554.25),
    ("09.9731", "9", "Switzerland", 409.05, 409.05, 409.05, 409.05),
    ("09.9493", "9", "United Kingdom (to Northern Ireland from other parts of the United Kingdom)", 31.27, 31.27, 31.27, 31.27),
    ("09.9874", "10", "China", 928.49, 928.49, 928.49, 928.49),
    ("09.9875", "10", "India", 1497.03, 1497.03, 1497.03, 1497.03),
    ("09.9876", "10", "Korea", 515.2, 515.2, 515.2, 515.2),
    ("09.9877", "10", "South Africa", 494.45, 494.45, 494.45, 494.45),
    ("09.9512", "10", "FTA Quota – CSQ", 278.54, 278.54, 278.54, 278.54),
    ("09.9612", "10", "Other countries", 271.38, 271.38, 271.38, 271.38),
    ("09.9732", "10", "FTA Quota – Other countries", 271.23, 271.23, 271.23, 271.23),
    ("09.9878", "12", "China", 39484.18, 39484.18, 39484.18, 39484.18),
    ("09.9879", "12", "Türkiye", 60495.57, 60495.57, 60495.57, 60495.57),
    ("09.9880", "12", "United Kingdom", 26097.89, 26097.89, 26097.89, 26097.89),
    ("09.9881", "12", "Switzerland", 24360.31, 24360.31, 24360.31, 24360.31),
    ("09.9882", "12", "Korea", 14043.12, 14043.12, 14043.12, 14043.12),
    ("09.9883", "12", "North Macedonia", 13617.58, 13617.58, 13617.58, 13617.58),
    ("09.9513", "12", "FTA Quota – CSQ", 14063.24, 14063.24, 14063.24, 14063.24),
    ("09.9613", "12", "Other countries", 11809.9, 11809.9, 11809.9, 11809.9),
    ("09.9733", "12", "FTA Quota – Other countries", 10862.95, 10862.95, 10862.95, 10862.95),
    ("09.9734", "12", "Brazil", 3046.26, 3046.26, 3046.26, 3046.26),
    ("09.9735", "12", "Egypt", 2552.66, 2552.66, 2552.66, 2552.66),
    ("09.9884", "13", "Türkiye", 59919.02, 59919.02, 59919.02, 59919.02),
    ("09.9885", "13", "Egypt", 36091.95, 36091.95, 36091.95, 36091.95),
    ("09.9886", "13", "Algeria", 15940.36, 15940.36, 15940.36, 15940.36),
    ("09.9887", "13", "Moldova", 9929.78, 9929.78, 9929.78, 9929.78),
    ("09.9888", "13", "China", 5054.03, 5054.03, 5054.03, 5054.03),
    ("09.9889", "13", "Ukraine", 16927.54, 16927.54, 16927.54, 16927.54),
    ("09.9514", "13", "FTA Quota – CSQ", 39700.84, 39700.84, 39700.84, 39700.84),
    ("09.9614", "13", "Other countries", 15830.59, 15830.59, 15830.59, 15830.59),
    ("09.9736", "13", "FTA Quota – Other countries", 9574.81, 9574.81, 9574.81, 9574.81),
    ("09.9494", "13", "United Kingdom (to Northern Ireland from other parts of the United Kingdom)", 2162.48, 2162.48, 2162.48, 2162.48),
    ("09.9890", "14", "India", 23139.2, 23139.2, 23139.2, 23139.2),
    ("09.9891", "14", "Switzerland", 2696.52, 2696.52, 2696.52, 2696.52),
    ("09.9892", "14", "United Kingdom", 2029.23, 2029.23, 2029.23, 2029.23),
    ("09.9893", "14", "China", 896.35, 896.35, 896.35, 896.35),
    ("09.9515", "14", "FTA Quota – CSQ", 2398.59, 2398.59, 2398.59, 2398.59),
    ("09.9615", "14", "Other countries", 1530.08, 1530.08, 1530.08, 1530.08),
    ("09.9737", "14", "FTA Quota – Other countries", 708.72, 708.72, 708.72, 708.72),
    ("09.9894", "15", "India", 4693.08, 4693.08, 4693.08, 4693.08),
    ("09.9895", "15", "Taiwan", 1076.23, 1076.23, 1076.23, 1076.23),
    ("09.9896", "15", "Korea", 1303.11, 1303.11, 1303.11, 1303.11),
    ("09.9897", "15", "United Kingdom", 998.52, 998.52, 998.52, 998.52),
    ("09.9898", "15", "China", 343.53, 343.53, 343.53, 343.53),
    ("09.9899", "15", "Japan", 600.0, 600.0, 600.0, 600.0),
    ("09.9516", "15", "FTA Quota – CSQ", 810.14, 810.14, 810.14, 810.14),
    ("09.9616", "15", "Other countries", 145.21, 145.21, 145.21, 145.21),
    ("09.9738", "15", "FTA Quota – Other countries", 145.69, 145.69, 145.69, 145.69),
    ("09.9900", "16", "Türkiye", 61147.25, 61147.25, 61147.25, 61147.25),
    ("09.9901", "16", "Malaysia", 21670.85, 21670.85, 21670.85, 21670.85),
    ("09.9902", "16", "United Kingdom", 43849.88, 43849.88, 43849.88, 43849.88),
    ("09.9903", "16", "Ukraine", 47286.26, 47286.26, 47286.26, 47286.26),
    ("09.9904", "16", "Switzerland", 40548.83, 40548.83, 40548.83, 40548.83),
    ("09.9905", "16", "Viet Nam", 24271.66, 24271.66, 24271.66, 24271.66),
    ("09.9906", "16", "Moldova", 23959.81, 23959.81, 23959.81, 23959.81),
    ("09.9907", "16", "Egypt", 21678.72, 21678.72, 21678.72, 21678.72),
    ("09.9517", "16", "FTA Quota – CSQ", 30720.34, 30720.34, 30720.34, 30720.34),
    ("09.9617", "16", "Other countries", 38481.84, 38481.84, 38481.84, 38481.84),
    ("09.9739", "16", "FTA Quota – Other countries", 34610.24, 34610.24, 34610.24, 34610.24),
    ("09.9740", "16", "Korea", 2833.69, 2833.69, 2833.69, 2833.69),
    ("09.9741", "16", "Japan", 1323.5, 1323.5, 1323.5, 1323.5),
    ("09.9908", "17", "Türkiye", 13455.55, 13455.55, 13455.55, 13455.55),
    ("09.9909", "17", "United Kingdom", 5964.05, 5964.05, 5964.05, 5964.05),
    ("09.9910", "17", "Switzerland", 2590.81, 2590.81, 2590.81, 2590.81),
    ("09.9911", "17", "United Arab Emirates", 1491.1, 1491.1, 1491.1, 1491.1),
    ("09.9518", "17", "FTA Quota – CSQ", 3032.46, 3032.46, 3032.46, 3032.46),
    ("09.9618", "17", "Other countries", 3153.55, 3153.55, 3153.55, 3153.55),
    ("09.9742", "17", "FTA Quota – Other countries", 1073.81, 1073.81, 1073.81, 1073.81),
    ("09.9743", "17", "Korea", 1251.71, 1251.71, 1251.71, 1251.71),
    ("09.9495", "17", "United Kingdom (to Northern Ireland from other parts of the United Kingdom)", 14138.78, 14138.78, 14138.78, 14138.78),
    ("09.9912", "18", "China", 2480.61, 2480.61, 2480.61, 2480.61),
    ("09.9913", "18", "United Arab Emirates", 903.08, 903.08, 903.08, 903.08),
    ("09.9914", "18", "United Kingdom", 1666.94, 1666.94, 1666.94, 1666.94),
    ("09.9519", "18", "FTA Quota – CSQ", 1234.34, 1234.34, 1234.34, 1234.34),
    ("09.9619", "18", "Other countries", 85.28, 85.28, 85.28, 85.28),
    ("09.9744", "18", "FTA Quota – Other countries", 1445.52, 1445.52, 1445.52, 1445.52),
    ("09.9915", "19", "United Kingdom", 1758.07, 1758.07, 1758.07, 1758.07),
    ("09.9916", "19", "Türkiye", 1280.1, 1280.1, 1280.1, 1280.1),
    ("09.9917", "19", "China", 421.09, 421.09, 421.09, 421.09),
    ("09.9520", "19", "FTA Quota – CSQ", 286.0, 286.0, 286.0, 286.0),
    ("09.9620", "19", "Other countries", 220.46, 220.46, 220.46, 220.46),
    ("09.9745", "19", "FTA Quota – Other countries", 152.35, 152.35, 152.35, 152.35),
    ("09.9918", "20", "Türkiye", 28163.03, 28163.03, 28163.03, 28163.03),
    ("09.9919", "20", "India", 10036.89, 10036.89, 10036.89, 10036.89),
    ("09.9920", "20", "United Arab Emirates", 2521.72, 2521.72, 2521.72, 2521.72),
    ("09.9921", "20", "North Macedonia", 3636.32, 3636.32, 3636.32, 3636.32),
    ("09.9922", "20", "United Kingdom", 3264.36, 3264.36, 3264.36, 3264.36),
    ("09.9521", "20", "FTA Quota – CSQ", 3910.55, 3910.55, 3910.55, 3910.55),
    ("09.9621", "20", "Other countries", 2339.12, 2339.12, 2339.12, 2339.12),
    ("09.9746", "20", "FTA Quota – Other countries", 1731.37, 1731.37, 1731.37, 1731.37),
    ("09.9923", "21", "Türkiye", 59849.63, 59849.63, 59849.63, 59849.63),
    ("09.9924", "21", "United Kingdom", 22227.12, 22227.12, 22227.12, 22227.12),
    ("09.9925", "21", "North Macedonia", 10958.74, 10958.74, 10958.74, 10958.74),
    ("09.9926", "21", "China", 3680.24, 3680.24, 3680.24, 3680.24),
    ("09.9927", "21", "Ukraine", 6640.34, 6640.34, 6640.34, 6640.34),
    ("09.9522", "21", "FTA Quota – CSQ", 8487.11, 8487.11, 8487.11, 8487.11),
    ("09.9622", "21", "Other countries", 7174.14, 7174.14, 7174.14, 7174.14),
    ("09.9747", "21", "FTA Quota – Other countries", 5149.92, 5149.92, 5149.92, 5149.92),
    ("09.9748", "21", "Switzerland", 705.94, 705.94, 705.94, 705.94),
    ("09.9928", "22", "India", 3832.13, 3832.13, 3832.13, 3832.13),
    ("09.9929", "22", "Ukraine", 1631.12, 1631.12, 1631.12, 1631.12),
    ("09.9930", "22", "China", 268.27, 268.27, 268.27, 268.27),
    ("09.9931", "22", "Korea", 598.03, 598.03, 598.03, 598.03),
    ("09.9523", "22", "FTA Quota – CSQ", 512.63, 512.63, 512.63, 512.63),
    ("09.9623", "22", "Other countries", 774.33, 774.33, 774.33, 774.33),
    ("09.9749", "22", "FTA Quota – Other countries", 446.75, 446.75, 446.75, 446.75),
    ("09.9750", "22", "Japan", 178.57, 178.57, 178.57, 178.57),
    ("09.9932", "24", "China", 13158.84, 13158.84, 13158.84, 13158.84),
    ("09.9933", "24", "Ukraine", 20167.62, 20167.62, 20167.62, 20167.62),
    ("09.9934", "24", "Brazil", 7756.96, 7756.96, 7756.96, 7756.96),
    ("09.9524", "24", "FTA Quota – CSQ", 3052.2, 3052.2, 3052.2, 3052.2),
    ("09.9624", "24", "Other countries", 9824.98, 9824.98, 9824.98, 9824.98),
    ("09.9751", "24", "FTA Quota – Other countries", 11895.7, 11895.7, 11895.7, 11895.7),
    ("09.9752", "24", "Argentina", 1258.1, 1258.1, 1258.1, 1258.1),
    ("09.9753", "24", "Singapore", 110.77, 110.77, 110.77, 110.77),
    ("09.9935", "25.A", "Türkiye", 1947.08, 1947.08, 1947.08, 1947.08),
    ("09.9936", "25.A", "Israel", 834.24, 834.24, 834.24, 834.24),
    ("09.9937", "25.A", "China", 662.75, 662.75, 662.75, 662.75),
    ("09.9938", "25.A", "India", 1091.2, 1091.2, 1091.2, 1091.2),
    ("09.9525", "25.A", "FTA Quota – CSQ", 1387.41, 1387.41, 1387.41, 1387.41),
    ("09.9625", "25.A", "Other countries", 666.56, 666.56, 666.56, 666.56),
    ("09.9754", "25.A", "FTA Quota – Other countries", 584.19, 584.19, 584.19, 584.19),
    ("09.9496", "25.A", "United Kingdom (to Northern Ireland from other parts of the United Kingdom)", 13.93, 13.93, 13.93, 13.93),
    ("09.9939", "25.B", "Türkiye", 10935.66, 10935.66, 10935.66, 10935.66),
    ("09.9940", "25.B", "China", 2480.89, 2480.89, 2480.89, 2480.89),
    ("09.9941", "25.B", "United Kingdom", 2013.16, 2013.16, 2013.16, 2013.16),
    ("09.9942", "25.B", "Algeria", 584.75, 584.75, 584.75, 584.75),
    ("09.9526", "25.B", "FTA Quota – CSQ", 2029.75, 2029.75, 2029.75, 2029.75),
    ("09.9626", "25.B", "Other countries", 1402.23, 1402.23, 1402.23, 1402.23),
    ("09.9755", "25.B", "FTA Quota – Other countries", 1436.41, 1436.41, 1436.41, 1436.41),
    ("09.9756", "25.B", "Singapore", 21.07, 21.07, 21.07, 21.07),
    ("09.9943", "26", "Türkiye", 22453.26, 22453.26, 22453.26, 22453.26),
    ("09.9944", "26", "Switzerland", 11860.66, 11860.66, 11860.66, 11860.66),
    ("09.9945", "26", "China", 3220.17, 3220.17, 3220.17, 3220.17),
    ("09.9946", "26", "India", 6158.62, 6158.62, 6158.62, 6158.62),
    ("09.9947", "26", "United Kingdom", 4688.38, 4688.38, 4688.38, 4688.38),
    ("09.9948", "26", "Taiwan", 1597.91, 1597.91, 1597.91, 1597.91),
    ("09.9527", "26", "FTA Quota – CSQ", 4057.59, 4057.59, 4057.59, 4057.59),
    ("09.9627", "26", "Other countries", 4358.64, 4358.64, 4358.64, 4358.64),
    ("09.9757", "26", "FTA Quota – Other countries", 4282.85, 4282.85, 4282.85, 4282.85),
    ("09.9758", "26", "Singapore", 11.18, 11.18, 11.18, 11.18),
    ("09.9949", "27", "China", 3960.92, 3960.92, 3960.92, 3960.92),
    ("09.9950", "27", "Türkiye", 7045.08, 7045.08, 7045.08, 7045.08),
    ("09.9951", "27", "Switzerland", 6054.7, 6054.7, 6054.7, 6054.7),
    ("09.9952", "27", "Ukraine", 1715.77, 1715.77, 1715.77, 1715.77),
    ("09.9528", "27", "FTA Quota – CSQ", 1491.29, 1491.29, 1491.29, 1491.29),
    ("09.9628", "27", "Other countries", 1838.58, 1838.58, 1838.58, 1838.58),
    ("09.9759", "27", "FTA Quota – Other countries", 2222.43, 2222.43, 2222.43, 2222.43),
    ("09.9953", "27", "China", 14298.15, 14298.15, 14298.15, 14298.15),
    ("09.9954", "27", "Türkiye", 24235.3, 24235.3, 24235.3, 24235.3),
    ("09.9955", "27", "Ukraine", 20689.52, 20689.52, 20689.52, 20689.52),
    ("09.9529", "27", "FTA Quota – CSQ", 4496.4, 4496.4, 4496.4, 4496.4),
    ("09.9629", "27", "Other countries", 7072.28, 7072.28, 7072.28, 7072.28),
    ("09.9760", "27", "FTA Quota – Other countries", 8489.22, 8489.22, 8489.22, 8489.22),
    ("09.9497", "27", "United Kingdom (to Northern Ireland from other parts of the United Kingdom)", 190.57, 190.57, 190.57, 190.57),
]

# ------------------------------------------------------------------- fetch

def current_quarter_index():
    """EU steel quota year runs Jul->Jun. Returns 0..3 for Q1..Q4."""
    m = date.today().month
    if 7 <= m <= 9:   return 0   # Jul-Sep
    if 10 <= m <= 12: return 1   # Oct-Dec
    if 1 <= m <= 3:   return 2   # Jan-Mar
    return 3                     # Apr-Jun


def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en"})
    # handshake: load the consultation page so we get a JSESSIONID cookie
    s.get(BASE + "quota_consultation.jsp?Lang=en", timeout=30)
    return s


def fetch_balance(sess, order):
    """Return (balance_tonnes, origin) for an order number like '09.9801'."""
    code = order.replace(".", "")
    url = (BASE + "quota_list.jsp?Lang=en&Code=" + code +
           "&Year=" + str(YEAR) + "&Expand=true&Offset=0")
    r = sess.get(url, headers={"Referer": BASE + "quota_consultation.jsp?Lang=en"}, timeout=30)
    r.raise_for_status()
    text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    # find the segment for this order: "<code> <origins...> <dd-mm-yyyy> <dd-mm-yyyy> <balance> <Unit>"
    # the QUOTA database prints the balance as a plain number, e.g. "47367661.683 Kilogram"
    # (dot = decimal, no thousands separators).
    m = re.search(code + r"\s+(.+?)\s+\d{2}-\d{2}-\d{4}\s+\d{2}-\d{2}-\d{4}\s+(\d+(?:\.\d+)?)\s*(Kilogram|Tonne|Ton|Litre|Piece|\w+)?", text)
    if not m:
        return None, None
    origin = m.group(1).strip()
    try:
        val = float(m.group(2))   # already a plain float in the source
    except ValueError:
        return None, origin
    unit = (m.group(3) or "").lower()
    if unit.startswith("kilogram"):
        val /= 1000.0   # kilograms -> tonnes
    return round(val, 3), origin


def build_rows():
    qi = current_quarter_index()
    sess = make_session()
    rows = []
    for order, cat, origin, q1, q2, q3, q4 in QUOTAS_EU:
        base = [q1, q2, q3, q4][qi]
        row = {"order": order, "cat": cat, "origin": origin,
               "category": CATEGORY_NAMES.get(cat, cat), "base": base}
        try:
            bal, _live_origin = fetch_balance(sess, order)
            row["balance"] = bal
            row["error"] = None if bal is not None else "no balance returned"
        except Exception as e:
            row["balance"] = None
            row["error"] = str(e)
        if row["balance"] is not None and base:
            row["pct"] = max(0.0, row["balance"] / base)
        elif row["balance"] is not None:
            row["pct"] = 0.0
        else:
            row["pct"] = None
        rows.append(row)
        time.sleep(0.15)
    return rows


def band(pct):
    if pct is None: return "err"
    if pct < CRIT_PCT: return "crit"
    if pct < WARN_PCT: return "warn"
    return "ok"


def fmt(v, dp=0):
    if v is None: return "-"
    return "{:,.{}f}".format(v, dp)


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<script>
(function(){
  var p = location.pathname;
  if(location.search.indexOf('fresh')===-1){ location.replace(p+'?fresh='+Date.now()); return; }
  setTimeout(function(){ location.replace(p+'?fresh='+Date.now()); }, 1800000);
})();
</script>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EU Steel Quota Dashboard</title>
<style>
:root{--ok:#1a7f37;--ok-bg:#e6f4ea;--warn:#b26a00;--warn-bg:#fff4e0;--crit:#c62828;--crit-bg:#fdecea;--ink:#1a1f26;--mut:#5b6572;--line:#e3e7ec;--card:#fff;--bg:#f4f6f8;}
*{box-sizing:border-box;}
body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink);}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 60px;}
header{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:8px;border-bottom:2px solid var(--ink);padding-bottom:14px;}
h1{font-size:22px;margin:0;letter-spacing:-.2px;}
.sub{color:var(--mut);font-size:13px;}
.summary{display:flex;gap:12px;margin:20px 0 8px;flex-wrap:wrap;}
.stat{flex:1;min-width:120px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;}
.stat .n{font-size:26px;font-weight:700;}
.stat .l{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px;}
.stat.ok .n{color:var(--ok);}.stat.warn .n{color:var(--warn);}.stat.crit .n{color:var(--crit);}
h2{font-size:14px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);margin:26px 0 10px;}
.chips{display:flex;flex-wrap:wrap;gap:8px;}
.chip{display:flex;flex-direction:column;gap:2px;border-radius:9px;padding:9px 12px;border:1px solid var(--line);min-width:150px;}
.chip.warn{background:var(--warn-bg);border-color:#f0d9ac;}
.chip.crit{background:var(--crit-bg);border-color:#f3c0bb;}
.chip-ctry{font-weight:700;font-size:13px;}
.chip-cat{font-size:11px;color:var(--mut);}
.chip-pct{font-size:20px;font-weight:800;}
.chip.warn .chip-pct{color:var(--warn);}.chip.crit .chip-pct{color:var(--crit);}
.chip-mt{font-size:11px;color:var(--mut);}
.none{color:var(--ok);font-weight:600;}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:13px;}
th{text-align:left;padding:9px 12px;font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--mut);border-bottom:1px solid var(--line);}
td{padding:8px 12px;border-bottom:1px solid var(--line);}
tr:last-child td{border-bottom:none;}
.grouphead td{background:#eef1f5;font-weight:700;font-size:12px;text-transform:uppercase;letter-spacing:.3px;color:var(--ink);}
.num{text-align:right;font-variant-numeric:tabular-nums;}
.strong{font-weight:700;}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--mut);}
.ctry{font-weight:600;}
.barcell{width:150px;}
.bar{position:relative;height:18px;background:#eef1f5;border-radius:5px;overflow:hidden;}
.bar .fill{position:absolute;left:0;top:0;bottom:0;}
.bar.ok .fill{background:var(--ok);}.bar.warn .fill{background:var(--warn);}
.bar.crit .fill{background:var(--crit);}.bar.err .fill{background:#bbb;}
.pctlabel{position:absolute;right:6px;top:1px;font-size:11px;font-weight:700;color:var(--ink);}
.r-crit td{background:#fef7f6;}.r-warn td{background:#fffaf0;}
.errbox{margin-top:20px;background:var(--crit-bg);border:1px solid #f3c0bb;border-radius:10px;padding:12px 16px;font-size:13px;}
.errbox ul{margin:6px 0 0;padding-left:18px;}
footer{margin-top:26px;color:var(--mut);font-size:12px;}
</style></head>
<body><div class="wrap">
<header>
  <div><h1>EU Steel Safeguard &mdash; Quota Dashboard</h1>
  <div class="sub">Live quota remaining per order number &middot; %%QLABEL%%</div></div>
  <div class="sub">Refreshed<br><strong>%%TS%%</strong></div>
</header>
<div class="summary">
  <div class="stat"><div class="n">%%NROWS%%</div><div class="l">Quotas tracked</div></div>
  <div class="stat ok"><div class="n">%%OK%%</div><div class="l">Healthy (20%+)</div></div>
  <div class="stat warn"><div class="n">%%WARN%%</div><div class="l">Watch (10-20%)</div></div>
  <div class="stat crit"><div class="n">%%CRIT%%</div><div class="l">Critical (under 10%)</div></div>
</div>
<h2>Low-quota alerts</h2>
%%ALERTS%%
<h2>All quotas by category</h2>
<table>
<thead><tr>
  <th>Origin</th><th>Order</th>
  <th class="num">Q base (t)</th><th class="num">Quota remaining (t)</th>
  <th>% of base remaining</th>
</tr></thead>
<tbody>
%%TABLE%%
</tbody></table>
%%ERR%%
<footer>Source: EU tariff quota (QUOTA) database &middot; category volumes from Reg (EU) 2026/1457 &middot; refreshed automatically<br>
Figures are the live EU quota remaining only &mdash; they do not include our own open orders or material in transit.</footer>
</div></body></html>"""


def build_html(rows):
    now = datetime.now(UK_TZ) if UK_TZ else datetime.now()
    ts = now.strftime("%A %d %B %Y, %H:%M") + (" UK time" if UK_TZ else " UTC")
    qlabels = ["Q1 (1 Jul - 30 Sep)", "Q2 (1 Oct - 31 Dec)",
               "Q3 (1 Jan - 31 Mar)", "Q4 (1 Apr - 30 Jun)"]
    qlabel = "current quarter: " + qlabels[current_quarter_index()]

    groups = {}
    for r in rows:
        groups.setdefault((r["cat"], r["category"]), []).append(r)

    def bar(r):
        b = band(r["pct"]); pct = r["pct"]
        width = 0 if pct is None else min(100, pct * 100)
        label = "-" if pct is None else "{:.0f}%".format(pct * 100)
        return ('<div class="bar ' + b + '"><div class="fill" style="width:'
                + "{:.1f}".format(width) + '%"></div>'
                + '<span class="pctlabel">' + label + '</span></div>')

    rows_html = []
    def catkey(item):
        code = item[0][0]
        mm = re.match(r"(\d+)", code)
        return (int(mm.group(1)) if mm else 99, code)
    for (cat, catname), grp in sorted(groups.items(), key=catkey):
        head = htmllib.escape(cat + " - " + catname)
        rows_html.append('<tr class="grouphead"><td colspan="5">' + head + '</td></tr>')
        for r in grp:
            b = band(r["pct"])
            rows_html.append(
                '<tr class="r-' + b + '">'
                + '<td class="ctry">' + htmllib.escape(r["origin"] or "-") + '</td>'
                + '<td class="mono">' + r["order"] + '</td>'
                + '<td class="num">' + fmt(r["base"]) + '</td>'
                + '<td class="num strong">' + fmt(r["balance"], 0) + '</td>'
                + '<td class="barcell">' + bar(r) + '</td>'
                + '</tr>')
    table = "\n".join(rows_html)

    alerts = sorted([r for r in rows if band(r["pct"]) in ("crit", "warn")], key=lambda r: r["pct"])
    if alerts:
        chips = "".join(
            '<div class="chip ' + band(r["pct"]) + '">'
            + '<span class="chip-ctry">' + htmllib.escape(r["origin"] or r["order"]) + '</span>'
            + '<span class="chip-cat">Cat ' + htmllib.escape(r["cat"]) + '</span>'
            + '<span class="chip-pct">' + "{:.0f}%".format(r["pct"] * 100) + '</span>'
            + '<span class="chip-mt">' + fmt(r["balance"], 0) + ' t left</span>'
            + '</div>' for r in alerts)
        alerts_html = '<div class="chips">' + chips + '</div>'
    else:
        alerts_html = '<p class="none">No quotas below 20% - all healthy.</p>'

    errs = [r for r in rows if r["error"]]
    if errs:
        items = "".join('<li>' + r["order"] + ' (cat ' + htmllib.escape(r["cat"]) + '): '
                        + htmllib.escape(str(r["error"])) + '</li>' for r in errs[:40])
        extra = "" if len(errs) <= 40 else "<li>...and " + str(len(errs) - 40) + " more</li>"
        err_html = ('<div class="errbox"><strong>Could not fetch ' + str(len(errs))
                    + ':</strong><ul>' + items + extra + '</ul></div>')
    else:
        err_html = ""

    ok = sum(1 for r in rows if band(r["pct"]) == "ok")
    warn = sum(1 for r in rows if band(r["pct"]) == "warn")
    crit = sum(1 for r in rows if band(r["pct"]) == "crit")

    out = PAGE
    for tok, val in (("%%TS%%", ts), ("%%QLABEL%%", qlabel), ("%%NROWS%%", str(len(rows))),
                     ("%%OK%%", str(ok)), ("%%WARN%%", str(warn)), ("%%CRIT%%", str(crit)),
                     ("%%ALERTS%%", alerts_html), ("%%TABLE%%", table), ("%%ERR%%", err_html)):
        out = out.replace(tok, val)
    return out


def main():
    print("Fetching live EU balances for {} quotas...".format(len(QUOTAS_EU)))
    rows = build_rows()
    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(build_html(rows))
    ok = sum(1 for r in rows if r["error"] is None)
    print("Done. {}/{} live. Wrote {}".format(ok, len(rows), OUTPUT_HTML))


if __name__ == "__main__":
    main()
