"""تحليل ذكي اختياري عبر Claude API: تلخيص الأخبار وشرح الإشارة بالعربي.

يشتغل فقط إذا ANTHROPIC_API_KEY موجود (في secrets أو متغيرات البيئة).
"""
import logging

log = logging.getLogger("sniper.ai")

MODEL = "claude-opus-5-5"

SYSTEM = (
    "أنت محلل أسواق يكتب بالعربية الواضحة (لهجة خليجية خفيفة مقبولة) لمستخدم تطبيق تداول تجريبي "
    "لأسهم متوافقة مع الشريعة. تستلم لقطة فنية لسهم وعناوين أخبار إنجليزية. المطلوب:\n"
    "1) ملخص الأخبار في 3 نقاط كحد أقصى، مع الحكم: إيجابية / سلبية / محايدة.\n"
    "2) شرح مبسط لسبب قرار النظام (النقاط والمؤشرات) وهل الأخبار تدعمه أو تعارضه.\n"
    "3) أهم المخاطر اللي لازم ينتبه لها (مثل قرب الأرباح، تشبع شرائي، ضعف السوق).\n"
    "اكتب بإيجاز (أقل من 200 كلمة) وبعناوين قصيرة. لا تعطي توصية شخصية بالشراء أو البيع ولا "
    "تتوقع سعراً محدداً؛ هذا تحليل تعليمي. إذا ما في أخبار قل ذلك باختصار."
)


def available(api_key):
    if not api_key:
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _snapshot(info):
    keys = ["الرمز", "القطاع", "السعر", "التغير %", "القرار", "النقاط", "RSI", "MACD", "السيولة",
            "VWAP", "اختراق", "قوة نسبية", "ترتيب RS", "قالب الترند", "الإطار الأكبر", "الشمعة",
            "الأرباح", "وقف (ATR)", "الهدف", "timeframe"]
    lines = [k + ": " + str(info.get(k, "-")) for k in keys]
    heads = info.get("headlines") or []
    lines.append("\nالعناوين:")
    lines += ["- " + h["title"] + " (" + h.get("date", "") + ")" for h in heads] or ["- لا توجد"]
    return "\n".join(lines)


def analyze(info, api_key):
    """يرجّع (نص التحليل، رسالة خطأ)."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, timeout=120.0)
    try:
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM,
            messages=[{"role": "user", "content": _snapshot(info)}],
        )
    except anthropic.AuthenticationError:
        return None, "مفتاح Claude API غير صحيح."
    except anthropic.RateLimitError:
        return None, "تجاوزت حد الطلبات. جرّب بعد شوي."
    except anthropic.APIStatusError as e:
        log.warning("claude api %s", e.status_code)
        return None, "خطأ من خدمة Claude (" + str(e.status_code) + ")."
    except anthropic.APIConnectionError:
        return None, "تعذر الاتصال بخدمة Claude."
    if resp.stop_reason == "refusal":
        return None, "اعتذر النموذج عن هذا الطلب."
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return (text or None), (None if text else "ما رجع نص.")
