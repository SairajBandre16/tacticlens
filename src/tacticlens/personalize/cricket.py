"""Cricket analogy pack: one hand-written line per moment shape, in en / hi / es.

Analogy lines carry no numbers; each cites the evidence item that justifies picking it, so the verifier still
passes them.
"""
from __future__ import annotations

from ..agents.state import EvidencePack
from ..agents.templates import Facts

PACK = {
    "goal_low": {
        "en": "In cricket terms, this was like a tailender clearing the ropes off a good ball: rare, but it counts.",
        "hi": "क्रिकेट की भाषा में, यह किसी टेलएंडर के अच्छी गेंद पर छक्का मारने जैसा था: दुर्लभ, लेकिन गिना जाता है।",
        "es": "En términos de críquet, fue como un bateador de cola que la manda fuera del campo ante una buena bola: "
              "raro, pero cuenta.",
    },
    "goal_mid": {
        "en": "In cricket terms, this was a well-timed boundary: a fair chance, taken well.",
        "hi": "क्रिकेट की भाषा में, यह सही टाइमिंग वाली बाउंड्री थी: ठीक-ठाक मौक़ा, अच्छी तरह भुनाया गया।",
        "es": "En términos de críquet, fue un límite bien medido: una ocasión razonable, bien aprovechada.",
    },
    "goal_high": {
        "en": "In cricket terms, this was like dispatching a full toss: the chance was clear and the finish was clean.",
        "hi": "क्रिकेट की भाषा में, यह फ़ुल टॉस को बाउंड्री के पार भेजने जैसा था: मौक़ा साफ़ था और फ़िनिश भी।",
        "es": "En términos de críquet, fue como castigar un full toss: la ocasión era clara y la definición, limpia.",
    },
    "big_chance": {
        "en": "In cricket terms, this was like a dropped catch in the slips: the chance was there, but it went down.",
        "hi": "क्रिकेट की भाषा में, यह स्लिप में कैच छोड़ने जैसा था: मौक़ा था, पर हाथ से निकल गया।",
        "es": "En términos de críquet, fue como soltar una atrapada en el slip: la ocasión estaba ahí, pero se escapó.",
    },
    "red_card": {
        "en": "In cricket terms, it was like batting the rest of the innings with a wicket fewer to lose.",
        "hi": "क्रिकेट की भाषा में, यह बाक़ी पारी एक विकेट कम के साथ बल्लेबाज़ी करने जैसा था।",
        "es": "En términos de críquet, fue como batear el resto de la entrada con un wicket menos.",
    },
    "momentum_shift": {
        "en": "In cricket terms, this was like a batting side taking charge in the powerplay and scoring off "
              "almost every over.",
        "hi": "क्रिकेट की भाषा में, यह पावरप्ले में बल्लेबाज़ी टीम के लगभग हर ओवर में रन बटोरने जैसा था।",
        "es": "En términos de críquet, fue como un equipo bateador que toma el mando en el powerplay y anota en casi "
              "cada over.",
    },
    "press_collapse": {
        "en": "In cricket terms, the bowlers tired at the death, and the batting side found scoring much easier.",
        "hi": "क्रिकेट की भाषा में, डेथ ओवरों में गेंदबाज़ थक गए और बल्लेबाज़ी टीम के लिए रन बनाना आसान हो गया।",
        "es": "En términos de críquet, los lanzadores se cansaron al final y al equipo bateador le resultó mucho más "
              "fácil anotar.",
    },
    "sub_effect": {
        "en": "In cricket terms, it was like bringing on a specialist bowler to change the shape of the innings.",
        "hi": "क्रिकेट की भाषा में, यह पारी का रुख़ बदलने के लिए किसी विशेषज्ञ गेंदबाज़ को लाने जैसा था।",
        "es": "En términos de críquet, fue como traer a un lanzador especialista para cambiar el rumbo de la entrada.",
    },
}


def pick(pack: EvidencePack) -> tuple[str, dict] | None:
    """(pack entry key, cited evidence item) for this moment, or None when no analogy fits."""
    f = Facts(pack)
    if f.kind == "goal" and f.xg:
        xg = f.v(f.xg)
        return ("goal_low" if xg < 0.1 else "goal_high" if xg >= 0.3 else "goal_mid"), f.xg
    cite = {"big_chance": f.xg or f.shooter, "red_card": f.players_left or f.sent_off,
            "momentum_shift": f.mom_peak or f.team, "press_collapse": f.press_after or f.team,
            "sub_effect": f.on}.get(f.kind)
    return (f.kind, cite) if cite else None


def analogy_sentence(pack: EvidencePack, lang: str) -> dict | None:
    """Sentence dict in the contract shape; non-English lines carry their English version in en_text."""
    hit = pick(pack)
    if not hit:
        return None
    key, item = hit
    lines = PACK[key]
    out = {"text": lines.get(lang, lines["en"]), "evidence_ids": [item["id"]]}
    if lang != "en":
        out["en_text"] = lines["en"]
    return out
