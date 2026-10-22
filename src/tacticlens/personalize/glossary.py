"""Football glossary and name transliteration tables (hi, es).

Spanish keeps the Latin-script names unchanged. Hindi names are built from the same name parts the simulator
uses (sim/teams.py), so every generated player has a stable Devanagari form.
"""
from __future__ import annotations

import re

LANGS = ("en", "hi", "es")
LANG_NAMES = {"en": "English", "hi": "Hindi", "es": "Spanish"}

CLUBS_HI = {
    "Northbridge United": "नॉर्थब्रिज यूनाइटेड", "Kestrel Town": "केस्ट्रल टाउन",
    "Harbor Athletic": "हार्बर एथलेटिक", "Redmere FC": "रेडमियर एफ़सी",
    "Greyhaven Rovers": "ग्रेहेवन रोवर्स", "Thornvale City": "थॉर्नवेल सिटी",
    "Elmstead Wanderers": "एल्मस्टेड वांडरर्स", "Copperbay FC": "कॉपरबे एफ़सी",
}

FIRST_HI = {
    "Arin": "अरिन", "Bastian": "बास्टियन", "Caio": "काइओ", "Dario": "डारियो", "Elio": "एलियो",
    "Femi": "फ़ेमी", "Gael": "गाएल", "Hugo": "ह्यूगो", "Ilan": "इलान", "Jari": "यारी", "Kofi": "कोफ़ी",
    "Luca": "लूका", "Mateo": "माटेओ", "Niko": "निको", "Omar": "ओमार", "Pavel": "पावेल", "Rafa": "राफ़ा",
    "Soren": "सोरेन", "Tomas": "टोमस", "Umar": "उमर", "Viktor": "विक्टर", "Wen": "वेन", "Yusuf": "यूसुफ़",
    "Zane": "ज़ेन", "Aleks": "एलेक्स", "Bruno": "ब्रूनो", "Cyril": "सिरिल", "Dev": "देव", "Emre": "एमरे",
    "Felix": "फ़ेलिक्स", "Idris": "इदरीस", "Joon": "जून", "Kenji": "केंजी", "Leon": "लियोन", "Milan": "मिलान",
    "Nils": "नील्स", "Otto": "ओटो", "Remi": "रेमी", "Sami": "सामी", "Teo": "टेओ", "Arjun": "अर्जुन",
    "Rohan": "रोहन", "Iker": "इकेर", "Diego": "डिएगो",
}

SUR_A_HI = {
    "Hal": "हल", "Mor": "मोर", "Bren": "ब्रेन", "Cal": "कैल", "Dun": "डन", "Fal": "फ़ॉल", "Gar": "गार",
    "Hol": "हॉल", "Kel": "केल", "Lin": "लिन", "Nor": "नॉर", "Os": "ओस", "Pen": "पेन", "Quil": "क्विल",
    "Rav": "रैव", "Sel": "सेल", "Tor": "टॉर", "Wyn": "विन", "Ald": "ऑल्ड", "Brom": "ब्रॉम", "Cor": "कॉर",
    "Dray": "ड्रे", "Ev": "एव", "Ferr": "फ़ेर", "Gul": "गुल", "Im": "इम",
}

SUR_B_HI = {
    "wick": "विक", "more": "मोर", "vane": "वेन", "ley": "ली", "ton": "टन", "by": "बी", "ridge": "रिज",
    "stone": "स्टोन", "vale": "वेल", "holt": "होल्ट", "croft": "क्रॉफ़्ट", "mere": "मियर", "worth": "वर्थ",
    "brook": "ब्रुक", "den": "डेन", "hame": "हेम", "iva": "इवा", "aro": "आरो", "enko": "एंको",
    "ssen": "सेन", "ier": "इयर", "ando": "आंडो",
}

# An independent vowel after a bare consonant becomes its vowel sign: ओस + इवा -> ओसिवा.
_MATRA = {"इ": "ि", "ई": "ी", "आ": "ा", "ए": "े", "उ": "ु", "ओ": "ो", "ऐ": "ै", "औ": "ौ"}
_VOWEL_SIGNS = set("ािीुूृेैोौंँ्")

# Terms the Localizer must render this way (football vocabulary, metric names).
TERMS = {
    "hi": {"xG": "xG (अपेक्षित गोल)", "win chance": "जीत की संभावना", "win probability": "जीत की संभावना",
           "per cent": "प्रतिशत", "percentage points": "प्रतिशत अंक", "pp": "प्रतिशत अंक", "momentum": "मोमेंटम",
           "pressing": "प्रेसिंग", "pressures per minute": "प्रति मिनट प्रेशर", "PPDA": "PPDA",
           "threat per minute": "प्रति मिनट ख़तरा", "red card": "रेड कार्ड", "sent off": "बाहर भेजा गया",
           "substitution": "बदलाव", "big chance": "बड़ा मौक़ा", "goal": "गोल", "minute": "मिनट",
           "simulated rollouts": "सिम्युलेशन", "80% interval": "80% अंतराल"},
    "es": {"xG": "xG (goles esperados)", "win chance": "probabilidad de ganar",
           "win probability": "probabilidad de victoria", "per cent": "por ciento",
           "percentage points": "puntos porcentuales", "pp": "pp", "momentum": "impulso", "pressing": "presión",
           "pressures per minute": "presiones por minuto", "PPDA": "PPDA", "threat per minute": "amenaza por minuto",
           "red card": "tarjeta roja", "sent off": "expulsado", "substitution": "cambio", "big chance": "ocasión clara",
           "goal": "gol", "minute": "minuto", "simulated rollouts": "simulaciones", "80% interval": "intervalo del 80%"},
}

_NUKTA = "़"


def _surname_hi(sur: str) -> str | None:
    for a, a_hi in SUR_A_HI.items():
        b = sur[len(a):]
        if sur.startswith(a) and b in SUR_B_HI:
            b_hi = SUR_B_HI[b]
            if b_hi[0] in _MATRA and a_hi[-1] not in _VOWEL_SIGNS:
                b_hi = _MATRA[b_hi[0]] + b_hi[1:]
            return a_hi + b_hi
    return None


def localize_name(name: str, lang: str) -> str:
    """Club or player name in the target script. Unknown names are returned unchanged."""
    if lang != "hi":
        return name
    if name in CLUBS_HI:
        return CLUBS_HI[name]
    first, _, sur = name.partition(" ")
    first_hi, sur_hi = FIRST_HI.get(first), _surname_hi(sur)
    return f"{first_hi} {sur_hi}" if first_hi and sur_hi else name


def match_names(meta: dict) -> list[str]:
    """Every club and player name of one match, longest first (so full names win over parts)."""
    names = [meta[s]["name"] for s in ("home", "away")]
    names += [p["name"] for s in ("home", "away") for p in meta[s]["players"]]
    return sorted(set(names), key=len, reverse=True)


def name_table(meta: dict, lang: str) -> dict[str, str]:
    return {n: localize_name(n, lang) for n in match_names(meta)}


def names_in(text: str, meta: dict) -> list[str]:
    found, rest = [], text
    for n in match_names(meta):
        if re.search(rf"\b{re.escape(n)}\b", rest):
            found.append(n)
            rest = rest.replace(n, " ")
    return found


def fold(text: str) -> str:
    """Comparison form for Devanagari: drop nukta, collapse spaces."""
    return re.sub(r"\s+", " ", text.replace(_NUKTA, ""))

