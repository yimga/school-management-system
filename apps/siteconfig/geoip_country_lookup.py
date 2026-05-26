"""
Wave 10 (v3.62.10 — 2026-05-22) — GeoIP-driven country resolution.

The existing country resolver chain
``apps.siteconfig.country_localization_service.resolve_country_for_request``
uses tenant.country → session → cookie → Accept-Language. This module adds an
OPTIONAL IP-based lookup that the chain consults when none of those signals
fired (configurable via env var; OFF by default).

Architecture (sister of the older `apps.siteconfig.geoip_service` cache
helper — both are intentionally separate; this one is read-only country
resolution, the other is the broader lat/lon cache layer):

  - Stdlib-only by default; no MaxMind dependency required at import time.
  - Lazy backend selection via env var ``RMC_GEOIP_BACKEND``:
      * ``"noop"`` (default)   — always returns ""
      * ``"cloudflare"``       — reads ``CF-IPCountry`` header (zero-config
                                  when deployed behind Cloudflare)
      * ``"x-country-code"``   — reads a custom ``X-Country-Code`` header
                                  ops can inject from an upstream WAF / LB
      * ``"maxmind-lite2"``    — reads ``GEOIP_COUNTRY_DATABASE_PATH`` env
                                  (.mmdb file); requires ``geoip2`` PyPI;
                                  auto-falls-back to noop with one-time
                                  WARNING if the package is missing or path
                                  is invalid
  - All backends fail-safe (return "" on any error).
  - PII safety: NEVER logs the raw IP; the IP only crosses a method boundary
    into the MaxMind reader, never into a logger or DB row.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_BACKEND_ENV = "RMC_GEOIP_BACKEND"
_DB_PATH_ENV = "GEOIP_COUNTRY_DATABASE_PATH"

# Wave 14 (v3.62.19 — 2026-05-23) — city-tier resolver. Separate from country
# tier so deployments can opt into city WITHOUT switching their country
# backend (e.g. Cloudflare country header + MaxMind City .mmdb for city).
_CITY_BACKEND_ENV = "RMC_GEOIP_CITY_BACKEND"
_CITY_DB_PATH_ENV = "GEOIP_CITY_DATABASE_PATH"


def _selected_backend() -> str:
    return (os.environ.get(_BACKEND_ENV) or "noop").strip().lower()


def _client_ip(request) -> str:
    """Best-effort client IP extraction. NEVER raises."""
    try:
        xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
        if xff:
            for tok in xff.split(","):
                t = tok.strip()
                if t:
                    return t
        real = (request.META.get("HTTP_X_REAL_IP") or "").strip()
        if real:
            return real
        return (request.META.get("REMOTE_ADDR") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _normalize_cc(value: str) -> str:
    out = (value or "").strip().upper()
    if len(out) != 2 or not out.isascii() or not out.isalpha():
        return ""
    return out


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

def _lookup_cloudflare(request) -> str:
    try:
        return _normalize_cc(request.META.get("HTTP_CF_IPCOUNTRY", ""))
    except Exception:  # noqa: BLE001
        return ""


def _lookup_x_country_code(request) -> str:
    try:
        return _normalize_cc(request.META.get("HTTP_X_COUNTRY_CODE", ""))
    except Exception:  # noqa: BLE001
        return ""


_MAXMIND_READER = None
_MAXMIND_INIT_FAILED = False


def _lookup_maxmind_lite2(request) -> str:
    """MaxMind GeoLite2 country lookup via geoip2. Lazy + cached + fail-open."""
    global _MAXMIND_READER, _MAXMIND_INIT_FAILED
    if _MAXMIND_INIT_FAILED:
        return ""
    if _MAXMIND_READER is None:
        try:
            import geoip2.database  # type: ignore
        except ImportError:
            logger.warning(
                "GeoIP backend 'maxmind-lite2' selected but `geoip2` package "
                "is not installed. Falling back to noop. `pip install geoip2`."
            )
            _MAXMIND_INIT_FAILED = True
            return ""
        db_path = (os.environ.get(_DB_PATH_ENV) or "").strip()
        if not db_path or not os.path.isfile(db_path):
            logger.warning(
                "GeoIP backend 'maxmind-lite2' selected but %s is empty or "
                "the file does not exist. Falling back to noop.", _DB_PATH_ENV,
            )
            _MAXMIND_INIT_FAILED = True
            return ""
        try:
            _MAXMIND_READER = geoip2.database.Reader(db_path)
        except Exception:  # noqa: BLE001
            logger.exception(
                "GeoIP backend 'maxmind-lite2' failed to open database; "
                "falling back to noop."
            )
            _MAXMIND_INIT_FAILED = True
            return ""

    ip = _client_ip(request)
    if not ip:
        return ""
    try:
        result = _MAXMIND_READER.country(ip)
        cc = getattr(getattr(result, "country", None), "iso_code", "") or ""
        return _normalize_cc(cc)
    except Exception:  # noqa: BLE001 — AddressNotFoundError / etc.
        return ""


_BACKEND_DISPATCH = {
    "noop":           lambda _req: "",
    "cloudflare":     _lookup_cloudflare,
    "x-country-code": _lookup_x_country_code,
    "maxmind-lite2":  _lookup_maxmind_lite2,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lookup_country(request) -> str:
    """Return the visitor's ISO 3166-1 alpha-2 country code from GeoIP.

    Returns "" when backend is noop / not configured / cannot resolve.
    Never raises.
    """
    if request is None:
        return ""
    backend = _selected_backend()
    handler = _BACKEND_DISPATCH.get(backend)
    if handler is None:
        logger.warning(
            "GeoIP backend '%s' unknown; valid options: %s. Using noop.",
            backend, ", ".join(sorted(_BACKEND_DISPATCH.keys())),
        )
        return ""
    try:
        return handler(request) or ""
    except Exception:  # noqa: BLE001
        return ""


def reset_cache_for_tests() -> None:
    """Test helper — clear cached MaxMind reader."""
    global _MAXMIND_READER, _MAXMIND_INIT_FAILED, _MAXMIND_CITY_READER, _MAXMIND_CITY_INIT_FAILED
    if _MAXMIND_READER is not None:
        try:
            _MAXMIND_READER.close()
        except Exception:  # noqa: BLE001
            pass
    _MAXMIND_READER = None
    _MAXMIND_INIT_FAILED = False
    if _MAXMIND_CITY_READER is not None:
        try:
            _MAXMIND_CITY_READER.close()
        except Exception:  # noqa: BLE001
            pass
    _MAXMIND_CITY_READER = None
    _MAXMIND_CITY_INIT_FAILED = False


# ---------------------------------------------------------------------------
# Wave 14 (v3.62.19 — 2026-05-23) — City-tier resolver.
#
# Adds OPTIONAL city-level localization on top of the country-tier above.
# Use case: when a visitor's IP resolves to São Paulo BR, the marketing band
# anchors to "São Paulo" instead of the generic "São Paulo / Rio de Janeiro"
# country anchor. Falls back to "" silently when city tier is not configured
# OR resolution fails, so the country anchor still wins.
#
# Backends (env var ``RMC_GEOIP_CITY_BACKEND``):
#   * ``"noop"`` (default)   — always returns ""
#   * ``"cloudflare"``       — reads ``CF-IPCity`` header (only present on
#                              CF Enterprise plans — falls open on other plans)
#   * ``"x-city"``           — reads ``X-City`` custom header from upstream LB
#   * ``"maxmind-lite2"``    — reads ``GEOIP_CITY_DATABASE_PATH`` env (.mmdb
#                              file); requires ``geoip2`` PyPI; same fail-open
#                              semantics as the country tier
#
# PII safety: city name is broad-stroke (metro level) and inherent to public
# GeoIP databases — NOT PII at the platform's data classification level
# (PII triage doc § 4.2). Still never logged with raw IP.
# ---------------------------------------------------------------------------

_MAXMIND_CITY_READER = None
_MAXMIND_CITY_INIT_FAILED = False


# Wave 15 (v3.62.20 — 2026-05-23) — canonical city-name map.
#
# Some GeoIP databases return city names with different conventions:
# `São Paulo` vs `Sao Paulo` vs `SAO PAULO` vs `São Paulo`. Headers
# from Cloudflare (CF-IPCity), MaxMind GeoLite2-City, and operator-injected
# X-City headers each ship their own normalization. This canonical map
# folds the most common variants for the 60+ priority markets into a
# single canonical form that matches the country-pack's `anchor_city`
# convention. Anything not in the map passes through verbatim (so the
# operator still sees the correct local city even on unknown metros).
#
# Folding rules: case-insensitive ASCII slugify lookup (handles "Sao Paulo"
# AND "São Paulo" AND "SAO PAULO" → same key). Values are the canonical
# display form (correct diacritics, mixed case, often "City / Metro").
_CITY_CANONICAL_MAP: dict[str, str] = {
    # Brazil
    "sao paulo": "São Paulo",
    "rio de janeiro": "Rio de Janeiro",
    "salvador": "Salvador",
    "fortaleza": "Fortaleza",
    "brasilia": "Brasília",
    "belo horizonte": "Belo Horizonte",
    "curitiba": "Curitiba",
    # France
    "paris": "Paris",
    "marseille": "Marseille",
    "lyon": "Lyon",
    "toulouse": "Toulouse",
    # Mexico / Spain Spanish
    "ciudad de mexico": "Ciudad de México",
    "guadalajara": "Guadalajara",
    "monterrey": "Monterrey",
    "madrid": "Madrid",
    "barcelona": "Barcelona",
    "sevilla": "Sevilla",
    # Germany
    "muenchen": "München",
    "munchen": "München",
    "munich": "München",
    "berlin": "Berlin",
    "hamburg": "Hamburg",
    "koeln": "Köln",
    "koln": "Köln",
    "cologne": "Köln",
    "frankfurt am main": "Frankfurt am Main",
    "frankfurt": "Frankfurt am Main",
    # Italy
    "roma": "Roma",
    "rome": "Roma",
    "milano": "Milano",
    "milan": "Milano",
    "napoli": "Napoli",
    "naples": "Napoli",
    "torino": "Torino",
    "turin": "Torino",
    # Türkiye
    "istanbul": "İstanbul",
    "i̇stanbul": "İstanbul",
    "ankara": "Ankara",
    "izmir": "İzmir",
    # India (major metros — IN per-state map already covers states)
    "mumbai": "Mumbai",
    "bombay": "Mumbai",
    "delhi": "Delhi",
    "new delhi": "New Delhi",
    "bengaluru": "Bengaluru",
    "bangalore": "Bengaluru",
    "chennai": "Chennai",
    "madras": "Chennai",
    "kolkata": "Kolkata",
    "calcutta": "Kolkata",
    "hyderabad": "Hyderabad",
    "ahmedabad": "Ahmedabad",
    "pune": "Pune",
    # China / Taiwan / Hong Kong
    "beijing": "北京",
    "peking": "北京",
    "shanghai": "上海",
    "guangzhou": "广州",
    "shenzhen": "深圳",
    "taipei": "臺北",
    "kaohsiung": "高雄",
    "hong kong": "香港",
    "kowloon": "九龍",
    # Japan / Korea
    "tokyo": "東京",
    "osaka": "大阪",
    "kyoto": "京都",
    "seoul": "서울",
    "busan": "부산",
    # SE Asia
    "manila": "Manila",
    "quezon city": "Quezon City",
    "cebu": "Cebu",
    "kuala lumpur": "Kuala Lumpur",
    "george town": "George Town",
    "johor bahru": "Johor Bahru",
    "jakarta": "Jakarta",
    "surabaya": "Surabaya",
    "bangkok": "กรุงเทพมหานคร",
    "hanoi": "Hà Nội",
    "ho chi minh city": "TP. Hồ Chí Minh",
    "hcmc": "TP. Hồ Chí Minh",
    "saigon": "TP. Hồ Chí Minh",
    "singapore": "Singapore",
    # Middle East / North Africa
    "dubai": "Dubai",
    "abu dhabi": "Abu Dhabi",
    "doha": "Doha",
    "riyadh": "Riyadh",
    "jeddah": "Jeddah",
    "cairo": "Cairo",
    "alexandria": "Alexandria",
    "casablanca": "Casablanca",
    "rabat": "Rabat",
    "marrakech": "Marrakech",
    "tel aviv": "Tel Aviv",
    "tel aviv-yafo": "Tel Aviv",
    "jerusalem": "Jerusalem",
    # West Africa
    "lagos": "Lagos",
    "abuja": "Abuja",
    "kano": "Kano",
    "ibadan": "Ibadan",
    "accra": "Accra",
    "kumasi": "Kumasi",
    "abidjan": "Abidjan",
    "dakar": "Dakar",
    "douala": "Douala",
    "yaounde": "Yaoundé",
    "yaoundé": "Yaoundé",
    # East / Southern Africa
    "nairobi": "Nairobi",
    "mombasa": "Mombasa",
    "kampala": "Kampala",
    "dar es salaam": "Dar es Salaam",
    "kigali": "Kigali",
    "addis ababa": "አዲስ አበባ",
    "asmara": "ኣስመራ",
    "khartoum": "الخرطوم",
    "johannesburg": "Johannesburg",
    "cape town": "Cape Town",
    "durban": "Durban",
    "pretoria": "Pretoria",
    # UK / Ireland
    "london": "London",
    "manchester": "Manchester",
    "birmingham": "Birmingham",
    "edinburgh": "Edinburgh",
    "glasgow": "Glasgow",
    "dublin": "Dublin",
    "cork": "Cork",
    # Americas
    "new york": "New York",
    "new york city": "New York",
    "los angeles": "Los Angeles",
    "chicago": "Chicago",
    "toronto": "Toronto",
    "montreal": "Montréal",
    "montréal": "Montréal",
    "vancouver": "Vancouver",
    "buenos aires": "Buenos Aires",
    "cordoba": "Córdoba",
    "córdoba": "Córdoba",
    "bogota": "Bogotá",
    "bogotá": "Bogotá",
    "medellin": "Medellín",
    "medellín": "Medellín",
    # Oceania
    "sydney": "Sydney",
    "melbourne": "Melbourne",
    "brisbane": "Brisbane",
    "perth": "Perth",
    "auckland": "Auckland",
    "wellington": "Wellington",
    "christchurch": "Christchurch",
    # South Asia
    "karachi": "Karachi",
    "lahore": "Lahore",
    "islamabad": "Islamabad",
    "rawalpindi": "Rawalpindi",
    "faisalabad": "Faisalabad",
    "peshawar": "Peshawar",
    "quetta": "Quetta",
    "multan": "Multan",
    "dhaka": "ঢাকা",
    "chittagong": "চট্টগ্রাম",
    "chattogram": "চট্টগ্রাম",
    "sylhet": "সিলেট",
    "rajshahi": "রাজশাহী",
    "khulna": "খুলনা",
    "colombo": "කොළඹ",
    "kandy": "මහනුවර",
    "jaffna": "யாழ்ப்பாணம்",
    "galle": "ගාල්ල",
    "kathmandu": "काठमाडौं",
    "pokhara": "पोखरा",
    "thimphu": "ཐིམ་ཕུ་",
    "malé": "މާލެ",
    "male": "މާލެ",
    # Wave 16 tier-2: Brazil
    "porto alegre": "Porto Alegre",
    "recife": "Recife",
    "manaus": "Manaus",
    "belem": "Belém",
    "belém": "Belém",
    "goiania": "Goiânia",
    "goiânia": "Goiânia",
    "campinas": "Campinas",
    "natal": "Natal",
    # Wave 16 tier-2: India tier-2 metros
    "jaipur": "Jaipur",
    "lucknow": "लखनऊ",
    "kanpur": "कानपुर",
    "nagpur": "नागपुर",
    "indore": "इंदौर",
    "bhopal": "भोपाल",
    "patna": "पटना",
    "vadodara": "વડોદરા",
    "surat": "સુરત",
    "coimbatore": "கோயம்புத்தூர்",
    "kochi": "കൊച്ചി",
    "thiruvananthapuram": "തിരുവനന്തപുരം",
    "trivandrum": "തിരുവനന്തപുരം",
    "visakhapatnam": "విశాఖపట్నం",
    "guwahati": "গুৱাহাটী",
    # Wave 16 tier-2: China
    "chengdu": "成都",
    "hangzhou": "杭州",
    "wuhan": "武汉",
    "xi'an": "西安",
    "xian": "西安",
    "chongqing": "重庆",
    "nanjing": "南京",
    "tianjin": "天津",
    "qingdao": "青岛",
    "suzhou": "苏州",
    "harbin": "哈尔滨",
    # Wave 16 tier-2: Japan
    "nagoya": "名古屋",
    "yokohama": "横浜",
    "sapporo": "札幌",
    "fukuoka": "福岡",
    "kobe": "神戸",
    # Wave 16 tier-2: Korea
    "incheon": "인천",
    "daegu": "대구",
    "daejeon": "대전",
    "gwangju": "광주",
    "ulsan": "울산",
    # Wave 16 tier-2: SE Asia
    "davao": "Davao",
    "iloilo": "Iloilo",
    "bacolod": "Bacolod",
    "ipoh": "Ipoh",
    "kuching": "Kuching",
    "kota kinabalu": "Kota Kinabalu",
    "bandung": "Bandung",
    "medan": "Medan",
    "semarang": "Semarang",
    "yogyakarta": "Yogyakarta",
    "denpasar": "Denpasar",
    "makassar": "Makassar",
    "chiang mai": "เชียงใหม่",
    "phuket": "ภูเก็ต",
    "pattaya": "พัทยา",
    "da nang": "Đà Nẵng",
    "đà nẵng": "Đà Nẵng",
    "haiphong": "Hải Phòng",
    "phnom penh": "ភ្នំពេញ",
    "siem reap": "សៀមរាប",
    "vientiane": "ວຽງຈັນ",
    "yangon": "ရန်ကုန်",
    "mandalay": "မန္တလေး",
    # Wave 16 tier-2: MENA
    "sharjah": "Sharjah",
    "ajman": "Ajman",
    "kuwait city": "Kuwait City",
    "manama": "Manama",
    "muscat": "Muscat",
    "amman": "عمّان",
    "beirut": "بيروت",
    "damascus": "دمشق",
    "baghdad": "بغداد",
    "tehran": "تهران",
    "isfahan": "اصفهان",
    "shiraz": "شیراز",
    "tunis": "Tunis",
    "algiers": "Alger",
    "alger": "Alger",
    "tripoli": "طرابلس",
    "giza": "Giza",
    "luxor": "Luxor",
    "fes": "Fès",
    "fès": "Fès",
    "tanger": "Tanger",
    # Wave 16 tier-2: Africa expanded
    "harcourt": "Port Harcourt",
    "port harcourt": "Port Harcourt",
    "benin city": "Benin City",
    "tamale": "Tamale",
    "takoradi": "Takoradi",
    "bouake": "Bouaké",
    "bouaké": "Bouaké",
    "yamoussoukro": "Yamoussoukro",
    "saint-louis": "Saint-Louis",
    "thies": "Thiès",
    "thiès": "Thiès",
    "garoua": "Garoua",
    "kribi": "Kribi",
    "kinshasa": "Kinshasa",
    "lubumbashi": "Lubumbashi",
    "brazzaville": "Brazzaville",
    "luanda": "Luanda",
    "maputo": "Maputo",
    "antananarivo": "Antananarivo",
    "lome": "Lomé",
    "lomé": "Lomé",
    "cotonou": "Cotonou",
    "ouagadougou": "Ouagadougou",
    "bamako": "Bamako",
    "niamey": "Niamey",
    "ndjamena": "N'Djamena",
    "n'djamena": "N'Djamena",
    # Wave 16 tier-2: UK/Ireland
    "liverpool": "Liverpool",
    "leeds": "Leeds",
    "sheffield": "Sheffield",
    "bristol": "Bristol",
    "newcastle": "Newcastle",
    "cardiff": "Cardiff",
    "belfast": "Belfast",
    "aberdeen": "Aberdeen",
    "limerick": "Limerick",
    "galway": "Galway",
    # Wave 16 tier-2: Americas
    "houston": "Houston",
    "phoenix": "Phoenix",
    "philadelphia": "Philadelphia",
    "san antonio": "San Antonio",
    "san diego": "San Diego",
    "dallas": "Dallas",
    "san francisco": "San Francisco",
    "austin": "Austin",
    "boston": "Boston",
    "miami": "Miami",
    "atlanta": "Atlanta",
    "seattle": "Seattle",
    "denver": "Denver",
    "washington": "Washington",
    "ottawa": "Ottawa",
    "calgary": "Calgary",
    "edmonton": "Edmonton",
    "winnipeg": "Winnipeg",
    "quebec": "Québec",
    "québec": "Québec",
    "halifax": "Halifax",
    "rosario": "Rosario",
    "mendoza": "Mendoza",
    "la paz": "La Paz",
    "santa cruz": "Santa Cruz de la Sierra",
    "asuncion": "Asunción",
    "asunción": "Asunción",
    "montevideo": "Montevideo",
    "lima": "Lima",
    "cusco": "Cusco",
    "quito": "Quito",
    "guayaquil": "Guayaquil",
    "santiago": "Santiago",
    "valparaiso": "Valparaíso",
    "valparaíso": "Valparaíso",
    "caracas": "Caracas",
    "panama city": "Panamá",
    "panamá": "Panamá",
    "san jose": "San José",
    "san josé": "San José",
    "guatemala city": "Guatemala",
    "tegucigalpa": "Tegucigalpa",
    "managua": "Managua",
    "san salvador": "San Salvador",
    "santo domingo": "Santo Domingo",
    "havana": "La Habana",
    "la habana": "La Habana",
    "kingston": "Kingston",
    "puebla": "Puebla",
    "tijuana": "Tijuana",
    # Wave 16 tier-2: Europe expanded
    "amsterdam": "Amsterdam",
    "rotterdam": "Rotterdam",
    "brussels": "Brussel",
    "brussel": "Brussel",
    "bruxelles": "Brussel",
    "antwerp": "Antwerpen",
    "antwerpen": "Antwerpen",
    "vienna": "Wien",
    "wien": "Wien",
    "zurich": "Zürich",
    "zürich": "Zürich",
    "geneva": "Genève",
    "genève": "Genève",
    "stockholm": "Stockholm",
    "gothenburg": "Göteborg",
    "göteborg": "Göteborg",
    "oslo": "Oslo",
    "copenhagen": "København",
    "københavn": "København",
    "helsinki": "Helsinki",
    "warsaw": "Warszawa",
    "warszawa": "Warszawa",
    "krakow": "Kraków",
    "kraków": "Kraków",
    "prague": "Praha",
    "praha": "Praha",
    "budapest": "Budapest",
    "bucharest": "București",
    "bucurești": "București",
    "athens": "Αθήνα",
    "lisbon": "Lisboa",
    "lisboa": "Lisboa",
    "porto": "Porto",
    "valencia": "València",
    "valència": "València",
    "bilbao": "Bilbao",
    "florence": "Firenze",
    "firenze": "Firenze",
    "venice": "Venezia",
    "venezia": "Venezia",
    "sofia": "София",
    "kiev": "Київ",
    "kyiv": "Київ",
    "moscow": "Москва",
    "saint petersburg": "Санкт-Петербург",
    # Wave 16 tier-2: Oceania expanded
    "adelaide": "Adelaide",
    "hobart": "Hobart",
    "canberra": "Canberra",
    "darwin": "Darwin",
    "gold coast": "Gold Coast",
    "newcastle au": "Newcastle",
    "hamilton": "Hamilton",
    "tauranga": "Tauranga",
    "dunedin": "Dunedin",
    "suva": "Suva",
    "port moresby": "Port Moresby",
    "noumea": "Nouméa",
    "nouméa": "Nouméa",
    "papeete": "Papeete",
    "honiara": "Honiara",
    "apia": "Apia",
    "nuku'alofa": "Nukuʻalofa",
}


def _slugify_city_key(value: str) -> str:
    """Lower-case + strip diacritics + collapse whitespace for map lookup.

    Doesn't touch CJK / Arabic / Devanagari — those land as-is and only
    match if the original input already exists in the map as a CJK key.
    """
    import unicodedata
    norm = unicodedata.normalize("NFKD", value or "")
    out_chars = []
    for ch in norm:
        # Drop combining marks (diacritics)
        if unicodedata.combining(ch):
            continue
        out_chars.append(ch.lower())
    return " ".join("".join(out_chars).split())


def canonicalize_city(value: str) -> str:
    """Wave 15 (v3.62.20) — fold a raw GeoIP city name to canonical form.

    Returns the canonical display form when the input matches a known
    variant (case-insensitive, diacritic-insensitive). Unknown cities
    pass through verbatim (after _normalize_city() control-char strip).

    Safe to call with empty / None / non-string inputs (returns "").
    """
    s = (value or "").strip()
    if not s:
        return ""
    key = _slugify_city_key(s)
    if not key:
        return s
    if key in _CITY_CANONICAL_MAP:
        return _CITY_CANONICAL_MAP[key]
    # Also try the raw lower-cased input (covers CJK / Arabic / Devanagari
    # already in canonical form but submitted lowercased by some clients).
    raw_lower = s.lower()
    if raw_lower in _CITY_CANONICAL_MAP:
        return _CITY_CANONICAL_MAP[raw_lower]
    return s


def _selected_city_backend() -> str:
    return (os.environ.get(_CITY_BACKEND_ENV) or "noop").strip().lower()


def _normalize_city(value: str) -> str:
    out = (value or "").strip()
    # Drop control chars + trim absurd lengths.
    out = "".join(ch for ch in out if ch.isprintable())
    return out[:80]


def _lookup_city_cloudflare(request) -> str:
    try:
        return _normalize_city(request.META.get("HTTP_CF_IPCITY", ""))
    except Exception:  # noqa: BLE001
        return ""


def _lookup_city_x_header(request) -> str:
    try:
        return _normalize_city(request.META.get("HTTP_X_CITY", ""))
    except Exception:  # noqa: BLE001
        return ""


def _lookup_city_maxmind_lite2(request) -> str:
    """MaxMind GeoLite2 City lookup. Lazy + cached + fail-open."""
    global _MAXMIND_CITY_READER, _MAXMIND_CITY_INIT_FAILED
    if _MAXMIND_CITY_INIT_FAILED:
        return ""
    if _MAXMIND_CITY_READER is None:
        try:
            import geoip2.database  # type: ignore
        except ImportError:
            logger.warning(
                "GeoIP city backend 'maxmind-lite2' selected but `geoip2` "
                "package is not installed. Falling back to noop."
            )
            _MAXMIND_CITY_INIT_FAILED = True
            return ""
        db_path = (os.environ.get(_CITY_DB_PATH_ENV) or "").strip()
        if not db_path or not os.path.isfile(db_path):
            logger.warning(
                "GeoIP city backend 'maxmind-lite2' selected but %s is empty "
                "or the file does not exist. Falling back to noop.", _CITY_DB_PATH_ENV,
            )
            _MAXMIND_CITY_INIT_FAILED = True
            return ""
        try:
            _MAXMIND_CITY_READER = geoip2.database.Reader(db_path)
        except Exception:  # noqa: BLE001
            logger.exception(
                "GeoIP city backend 'maxmind-lite2' failed to open database; "
                "falling back to noop."
            )
            _MAXMIND_CITY_INIT_FAILED = True
            return ""

    ip = _client_ip(request)
    if not ip:
        return ""
    try:
        result = _MAXMIND_CITY_READER.city(ip)
        # Prefer English name; fall back to native script. Returns "" when
        # the city tier of the .mmdb has no city for this IP (rural / mobile
        # carrier / VPN exits with country-only records).
        city_obj = getattr(result, "city", None)
        if city_obj is None:
            return ""
        name = getattr(city_obj, "name", "") or ""
        if not name:
            names = getattr(city_obj, "names", None) or {}
            name = names.get("en") if isinstance(names, dict) else ""
        return _normalize_city(name or "")
    except Exception:  # noqa: BLE001 — AddressNotFoundError / etc.
        return ""


_CITY_BACKEND_DISPATCH = {
    "noop":           lambda _req: "",
    "cloudflare":     _lookup_city_cloudflare,
    "x-city":         _lookup_city_x_header,
    "maxmind-lite2":  _lookup_city_maxmind_lite2,
}


def lookup_city(request) -> str:
    """Wave 14 (v3.62.19) — return the visitor's metro / city name from GeoIP.

    Returns "" when backend is noop / not configured / cannot resolve OR the
    .mmdb city tier has no city record for the IP. Never raises.

    Wave 15 (v3.62.20): result is fed through ``canonicalize_city`` so the
    output uses the canonical display form ("São Paulo" not "Sao Paulo",
    "Bengaluru" not "Bangalore", "東京" not "Tokyo" when CJK is preferred).
    Unknown cities pass through verbatim.
    """
    if request is None:
        return ""
    backend = _selected_city_backend()
    handler = _CITY_BACKEND_DISPATCH.get(backend)
    if handler is None:
        logger.warning(
            "GeoIP city backend '%s' unknown; valid options: %s. Using noop.",
            backend, ", ".join(sorted(_CITY_BACKEND_DISPATCH.keys())),
        )
        return ""
    try:
        raw = handler(request) or ""
        return canonicalize_city(raw) if raw else ""
    except Exception:  # noqa: BLE001
        return ""
