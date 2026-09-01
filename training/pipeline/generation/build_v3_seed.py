"""Initial high-quality WOW dataset batch for the v3+ (long-term, 1M+
target) pipeline track. See docs/DATASET.md "Dataset philosophy" for why
this is explicitly an *initial* batch, not a claim of reaching 1M.

Every example here is hand-authored for this project. Target language mix
is Hindi-dominant (~60% Hindi, primarily Devanagari; ~30% Hinglish;
~10% English) - the inverse of the v1/v1.1 English-dominant track - because
this batch is meant to seed the *production* dataset direction WOW is
actually heading toward (a primarily Hindi/Hinglish-speaking user base),
not to replace v1.1's already-prepared, already-validated dataset.

Intent/context/action strings are validated against the WOW taxonomy by
the pipeline (training/pipeline/label_validate.py), not at construction
time here - so this file intentionally uses plain strings rather than
importing the enum types, matching the schema the pipeline's RawExample
already documents.

Run: python -m training.pipeline.generation.build_v3_seed
Writes training/datasets/v3_raw/seed.jsonl (RawExample-shaped JSONL, NOT
yet scored/split - run the pipeline CLI's `stats`/`split` commands on it,
see docs/DATASET.md "How to add new examples").
"""

import json
from pathlib import Path

from training.pipeline.schema import RawExample

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "datasets" / "v3_raw"
SOURCE = "hand_authored_v3"


def _add(ex_list, text, language, intent, **kw):
    ex_list.append(RawExample(text=text, language=language, intent=intent, source=SOURCE, **kw))


def _add_many(ex_list, items, intent, **shared):
    for text, language in items:
        _add(ex_list, text, language, intent, **shared)


def build_set_context(ex: list[RawExample]) -> None:
    # SLEEPING
    _add_many(ex, [
        ("मुझे नींद आ रही है, मेरी कॉल्स संभाल लो।", "hi"),
        ("मैं सोने जा रहा हूँ, किसी को जगाना मत।", "hi"),
        ("बिस्तर पर जा रहा हूँ, सुबह बात करेंगे।", "hi"),
        ("अभी सोना है मुझे, फ़ोन साइलेंट पर रख रहा हूँ।", "hi"),
        ("रात हो गई है, अब मैं आराम करने जा रहा हूँ।", "hi"),
        ("Sone ja raha hoon yaar, thodi der ke liye disturb mat karna.", "hi"),
        ("Bahut neend aa rahi hai bhai, so jaunga ab.", "hinglish"),
        ("I'm heading to bed, please hold my calls.", "en"),
    ], "SET_CONTEXT", context_mode="SLEEPING", action="SET_CONTEXT")

    # BUSY
    _add_many(ex, [
        ("मैं अभी व्यस्त हूँ, संदेश ले लेना।", "hi"),
        ("काम में उलझा हूँ, थोड़ी देर बाद बात करूँगा।", "hi"),
        ("अभी हाथ खाली नहीं है मेरा, संदेश छोड़ दीजिए।", "hi"),
        ("ऑफिस का काम निपटा रहा हूँ, थोड़ी देर लगेगी।", "hi"),
        ("क्लाइंट कॉल पर हूँ अभी, बाद में बात करेंगे।", "hi"),
        ("Kaam mein busy hoon yaar, thodi der handle kar lo.", "hinglish"),
        ("Office ka kaam nipta raha hoon, message le lena unse.", "hi"),
        ("Swamped with deadlines today, take a message please.", "en"),
    ], "SET_CONTEXT", context_mode="BUSY", action="SET_CONTEXT")

    # MEETING
    _add_many(ex, [
        ("मैं मीटिंग में हूँ, कॉल्स रोक कर रखना।", "hi"),
        ("बोर्ड मीटिंग चल रही है, डिस्टर्ब मत करना।", "hi"),
        ("क्लाइंट के साथ मीटिंग में हूँ अभी।", "hi"),
        ("कॉन्फ्रेंस कॉल पर हूँ, थोड़ी देर बाद।", "hi"),
        ("प्रेजेंटेशन दे रहा हूँ अभी, फ़ोन साइलेंट है।", "hi"),
        ("Review meeting chal rahi hai, hold karo calls thodi der.", "hi"),
        ("Team ke saath discussion mein hoon, back in 20 minutes.", "hinglish"),
        ("Stuck in back-to-back meetings all afternoon.", "en"),
    ], "SET_CONTEXT", context_mode="MEETING", action="SET_CONTEXT")

    # TRAVELLING
    _add_many(ex, [
        ("मैं यात्रा पर हूँ, नेटवर्क कमज़ोर रहेगा।", "hi"),
        ("हवाई अड्डे पर हूँ, उड़ान का इंतज़ार कर रहा हूँ।", "hi"),
        ("सड़क यात्रा पर हूँ आज, संकेत आता जाता रहेगा।", "hi"),
        ("ट्रेन में हूँ, नेटवर्क थोड़ा कमज़ोर है यहाँ।", "hi"),
        ("जहाज़ पर सवार हूँ, थोड़ी देर संपर्क नहीं हो पाएगा।", "hi"),
        ("Highway pe hoon abhi, signal aata jaata rahega.", "hinglish"),
        ("Cab mein hoon airport ke liye, thodi der out of reach.", "hinglish"),
        ("On a long drive today, might not answer immediately.", "en"),
    ], "SET_CONTEXT", context_mode="TRAVELLING", action="SET_CONTEXT")

    # UNAVAILABLE
    _add_many(ex, [
        ("मैं आज बाकी दिन के लिए उपलब्ध नहीं हूँ।", "hi"),
        ("पूरे दिन के लिए संपर्क से बाहर रहूँगा।", "hi"),
        ("फ़िलहाल किसी से बात नहीं कर सकता, माफ़ करना।", "hi"),
        ("कल सुबह तक उपलब्ध नहीं रहूँगा मैं।", "hi"),
        ("अभी के लिए पूरी तरह अनुपलब्ध हूँ।", "hi"),
        ("Kal tak thoda unreachable rahunga, sorry yaar.", "hi"),
        ("Aaj shaam tak available nahi ho paunga main.", "hi"),
        ("Completely off the grid for the next few hours.", "en"),
    ], "SET_CONTEXT", context_mode="UNAVAILABLE", action="SET_CONTEXT")

    # CUSTOM (driving/studying/eating/exercising/with family/at hospital/etc -
    # the taxonomy's CUSTOM mode covers these situational states; see
    # docs/DATASET.md "Proposed taxonomy expansion" for why these aren't
    # separate ContextMode values)
    _add_many(ex, [
        ("गाड़ी चला रहा हूँ अभी, सिर्फ ज़रूरी कॉल्स लेना।", "hi"),
        ("पढ़ाई कर रहा हूँ, सिर्फ खास बात के लिए फोन करना।", "hi"),
        ("जिम में हूँ वर्कआउट पर, थोड़ी देर बिज़ी रहूँगा।", "hi"),
        ("परिवार के साथ अस्पताल में हूँ, सिर्फ आपातकाल के लिए कॉल करना।", "hi"),
        ("खाना खा रहा हूँ, पाँच मिनट में वापस आता हूँ।", "hi"),
        ("क्लास में हूँ अभी, फ़ोन साइलेंट पर है।", "hi"),
        ("दोस्तों के साथ बाहर हूँ, सिर्फ ज़रूरी होने पर कॉल करना।", "hi"),
        ("दूसरी कॉल पर हूँ अभी, एक मिनट रुको।", "hi"),
        ("Driving right now, sirf emergency calls lena.", "hinglish"),
        ("Exam de raha hoon, phone silent pe rakha hai.", "hi"),
        ("Gym mein hoon workout pe, thodi der busy rahunga.", "hi"),
        ("At a family function today, only urgent calls please.", "en"),
    ], "SET_CONTEXT", context_mode="CUSTOM", action="SET_CONTEXT",
       notes="CUSTOM covers situational states (driving/studying/eating/exercising/class/hospital/on-another-call) "
             "not modeled as separate ContextMode values - see docs/DATASET.md.")

    # NORMAL (explicit set, not a clear)
    _add_many(ex, [
        ("आज कुछ खास नहीं है, सामान्य ही रखना।", "hi"),
        ("सब कुछ सामान्य है, कोई विशेष मोड नहीं चाहिए।", "hi"),
        ("मुझे सामान्य मोड में रखो अभी के लिए।", "hi"),
        ("Sab normal rakho aaj, koi special mode nahi chahiye.", "hinglish"),
        ("Keep everything as usual today, nothing special going on.", "en"),
    ], "SET_CONTEXT", context_mode="NORMAL", action="SET_CONTEXT")


def build_clear_context(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("अब मैं फ्री हूँ, वापस सामान्य कर दो।", "hi"),
        ("मीटिंग खत्म हो गई, अब कॉल्स आने दो।", "hi"),
        ("नींद पूरी हो गई, अब सामान्य मोड कर दो।", "hi"),
        ("यात्रा खत्म हुई, अब वापस उपलब्ध हूँ।", "hi"),
        ("काम हो गया मेरा, अब स्थिति साफ़ कर दो।", "hi"),
        ("अब उपलब्ध हूँ, फ़िल्टरिंग बंद कर दो।", "hi"),
        ("वापस आ गया हूँ यात्रा से, सामान्य कर दो।", "hi"),
        ("अब कोई विशेष स्थिति नहीं है, सामान्य कर दो।", "hi"),
        ("Ab free hoon, normal mode pe le aao please.", "hinglish"),
        ("Meeting khatam ho gayi, wapas normal kar do sab.", "hinglish"),
        ("Kaam khatam, ab calls normally lena shuru kar do.", "hinglish"),
        ("All caught up now, treat calls normally again.", "en"),
        ("I'm free now, you can clear my status.", "en"),
    ], "CLEAR_CONTEXT", context_mode="NORMAL", action="CLEAR_CONTEXT")


def build_get_context(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("अभी कौन सा मोड चल रहा है मेरा?", "hi"),
        ("मेरी स्थिति क्या सेट है इस समय?", "hi"),
        ("मैं किस मोड में हूँ अभी?", "hi"),
        ("क्या अभी भी मीटिंग मोड चालू है?", "hi"),
        ("क्या कॉल हैंडलिंग अभी भी चालू है?", "hi"),
        ("पिछली बार मैंने क्या सेट किया था, याद दिलाओ।", "hi"),
        ("क्या मैं अभी अनुपलब्ध मोड में हूँ?", "hi"),
        ("मेरा वर्तमान मोड क्या है, बताओ।", "hi"),
        ("Abhi mera kya status set hai, bata do.", "hi"),
        ("Kya abhi bhi busy mode on hai mera?", "hi"),
        ("Current mode kya hai mera abhi, yaad nahi mujhe.", "hi"),
        ("What mode am I in right now?", "en"),
        ("Can you remind me what context I'm currently in?", "en"),
    ], "GET_CONTEXT", action="NO_ACTION")


def build_call_person(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("प्रिया को कॉल लगाओ।", "hi"),
        ("मम्मी को फ़ोन मिलाओ अभी।", "hi"),
        ("ज़रा राहुल को कॉल कर दो।", "hi"),
        ("भाई को एक कॉल लगा दो अभी।", "hi"),
        ("ऑफिस वाले को फ़ोन मिलाओ ज़रा।", "hi"),
        ("डॉक्टर को कॉल लगा दो प्लीज़।", "hi"),
        ("मुझे अपनी बहन से बात करनी है, कॉल करो।", "hi"),
        ("ड्राइवर को एक कॉल लगाओ।", "hi"),
        ("अंकल को कॉल करो अभी।", "hi"),
        ("Papa ko call laga do please.", "hinglish"),
        ("Zara Rahul ko ek baar try karo call karke.", "hinglish"),
        ("Boss ko call kardo abhi ke abhi.", "hi"),
        ("Doctor sahab ko call laga do please.", "hinglish"),
        ("Call Rahul for me right now.", "en"),
        ("Can you dial my mother please?", "en"),
    ], "CALL_PERSON", action="NO_ACTION")


def build_handle_calls(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("मेरे कॉल्स कुछ घंटों के लिए संभाल लो।", "hi"),
        ("अब से मेरी कॉल्स तुम देख लेना।", "hi"),
        ("मेरी तरफ से कॉल्स उठाना शुरू कर दो।", "hi"),
        ("जब तक मैं वापस न आऊँ, कॉल्स तुम संभालना।", "hi"),
        ("आज पूरे दिन मेरी कॉल्स तुम देखना।", "hi"),
        ("कल से मेरी कॉल्स तुम्हें संभालनी हैं।", "hi"),
        ("Bhai mere calls handle kar lena thodi der.", "hinglish"),
        ("Ek kaam kar, calls sambhal le meri ab.", "hinglish"),
        ("Weekend ke liye calls tum dekhna mere.", "hi"),
        ("Handle my calls for the next few hours please.", "en"),
        ("Please screen my calls while I'm out.", "en"),
    ], "HANDLE_CALLS", action="ENABLE_CALL_ASSISTANT")
    _add_many(ex, [
        ("अब कॉल्स मत संभालो, मैं वापस आ गया हूँ।", "hi"),
        ("कॉल हैंडलिंग बंद कर दो अब।", "hi"),
        ("अब मुझे खुद कॉल्स लेनी हैं।", "hi"),
        ("अब स्क्रीनिंग बंद कर दो, मैं संभाल लूँगा।", "hi"),
        ("अब से कॉल्स मत उठाना, मैं फ्री हूँ।", "hi"),
        ("Bas ab calls mat le, main free hoon ab.", "hinglish"),
        ("Call assistant band kar do yaar, main aa gaya.", "hinglish"),
        ("Ab handle mat karo calls, main dekh lunga.", "hinglish"),
        ("Stop handling my calls now, I'm back.", "en"),
        ("You can stop screening my calls, I'm free.", "en"),
    ], "HANDLE_CALLS", action="DISABLE_CALL_ASSISTANT")


def build_unknown_caller(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("यह नंबर मेरी सूची में नहीं है, पूछो कौन है।", "hi"),
        ("अनजान नंबर है, पहले कभी कॉल नहीं आया।", "hi"),
        ("मुझे यह नंबर पहचान में नहीं आ रहा।", "hi"),
        ("पहली बार इस नंबर से कॉल आया है, वजह पूछो।", "hi"),
        ("यह किसी सेव किए गए नंबर से मेल नहीं खाता।", "hi"),
        ("कोई अनजान व्यक्ति कॉल कर रहा है, पूछो क्या चाहिए।", "hi"),
        ("Ye number pehchana nahi mujhe, pooch lo pehle.", "hinglish"),
        ("Naya number hai bilkul, pehle wajah pooch lo.", "hinglish"),
        ("Unknown number hai, pehle poochho kya kaam hai.", "hinglish"),
        ("This number isn't in my contacts, ask why they're calling.", "en"),
        ("Never seen this number before, check the reason first.", "en"),
    ], "UNKNOWN_CALLER", action="ASK_CALLER_REASON")
    _add_many(ex, [
        ("यह बैंक बनकर ओटीपी माँग रहा है, यह धोखाधड़ी है।", "hi"),
        ("यह फ़र्ज़ी लोन ऑफर वाला रोबोकॉल लग रहा है।", "hi"),
        ("यह नंबर पिछले हफ्ते कई बार स्पैम कॉल कर चुका है।", "hi"),
        ("यह कोई टेक सपोर्ट वाला घोटाला लग रहा है, काट दो।", "hi"),
        ("यह संदिग्ध कॉल है, जानकारी मत देना कुछ भी।", "hi"),
        ("Bank se bol raha hai bolke OTP maang raha hai, scam hai yeh.", "hi"),
        ("Yeh spam lag raha hai bhai, call kaat do abhi.", "hi"),
        ("Fake lottery wala call hai, paise maang raha hai.", "hi"),
        ("Caller claims to be from a bank asking for OTP.", "en"),
        ("This sounds like a scam call, end it immediately.", "en"),
    ], "UNKNOWN_CALLER", action="END_CALL",
       notes="Spam/suspicious flavor - action is END_CALL, not ASK_CALLER_REASON.")


def build_known_caller(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("यह नंबर पापा का है, कॉल ले लो।", "hi"),
        ("मम्मी का कॉल है, ले लो।", "hi"),
        ("यह मेरे भाई का नंबर है, कॉल लो।", "hi"),
        ("यह मेरी बहन का कॉल है, ले लो।", "hi"),
        ("यह मेरे सबसे करीबी दोस्त का कॉल है, जाने दो।", "hi"),
        ("Arre yeh toh mera bhai hai, connect kar do.", "hinglish"),
        ("Yeh papa ka number hai, le lo call.", "hi"),
        ("This caller is saved as my brother, answer it.", "en"),
    ], "KNOWN_CALLER", action="ANSWER_CALL")
    _add_many(ex, [
        ("ऑफिस का सहकर्मी है, पूछो किस बारे में कॉल किया।", "hi"),
        ("यह मेरे क्लाइंट का कॉल है, वजह पूछ लो।", "hi"),
        ("बैंक रिलेशनशिप मैनेजर का कॉल है, पूछो किस बारे में।", "hi"),
        ("यह मेरे बॉस का नंबर है, पूछो क्या बात है।", "hi"),
        ("Yeh manager hai mera, pooch lo kis baare mein call kiya.", "hinglish"),
        ("Vendor ka call hai, reason pooch lo pehle.", "hinglish"),
        ("Office colleague is calling, ask what it's about.", "en"),
    ], "KNOWN_CALLER", action="ASK_CALLER_REASON")
    _add_many(ex, [
        ("दोस्त का कॉल है, संदेश ले लो।", "hi"),
        ("कॉलेज वाला दोस्त है, जो बोले नोट कर लेना।", "hi"),
        ("यह मेरी सहेली का कॉल है, संदेश ले लो।", "hi"),
        ("पड़ोसी का कॉल है, संदेश ले लेना उनका।", "hi"),
        ("Dost ka call hai, message le lo bas.", "hinglish"),
        ("Purana roommate hai, jo bole note kar lena.", "hinglish"),
        ("It's a friend just calling to chat, take a message.", "en"),
    ], "KNOWN_CALLER", action="COLLECT_MESSAGE")


def build_urgent_call(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("यह आपातकाल है, अभी बात करनी है।", "hi"),
        ("बहुत ज़रूरी है, तुरंत सूचित करो उन्हें।", "hi"),
        ("ऑफिस का सर्वर डाउन है, उन्हें अभी चाहिए।", "hi"),
        ("पापा की तबियत ठीक नहीं है, बहुत ज़रूरी है।", "hi"),
        ("घर में कुछ समस्या हो गई है, तुरंत बता दो।", "hi"),
        ("क्लाइंट का कॉन्ट्रैक्ट आज ही साइन होना है, ज़रूरी है।", "hi"),
        ("यह देरी नहीं हो सकती, अभी के अभी बताना है।", "hi"),
        ("डॉक्टर ने तुरंत बुलाया है, बहुत ज़रूरी है।", "hi"),
        ("Urgent hai yaar, turant baat karao unse.", "hi"),
        ("Office se call hai, server down hai turant chahiye.", "hi"),
        ("Ekdum zaroori hai bhai, abhi bata do unhe.", "hi"),
        ("This is an emergency, I need to speak to him right now!", "en"),
        ("Mark this as urgent, hospital is calling about my father.", "en"),
    ], "URGENT_CALL", action="MARK_URGENT")


def build_non_urgent_call(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("कोई जल्दी नहीं है, जब समय मिले तब बात करेंगे।", "hi"),
        ("ज़रूरी नहीं है यह, आराम से बता देना।", "hi"),
        ("यह इंतज़ार कर सकता है, कोई हड़बड़ी नहीं।", "hi"),
        ("बस हालचाल पूछने के लिए कॉल किया था, कुछ खास नहीं।", "hi"),
        ("जब भी सुविधा हो तब बात कर लेंगे, कोई जल्दी नहीं।", "hi"),
        ("कल भी बात हो जाए तो चलेगा, कोई फर्क नहीं पड़ेगा।", "hi"),
        ("Koi jaldi nahi hai, jab free ho tab baat kar lenge.", "hinglish"),
        ("Bilkul zaroori nahi hai, jab time mile tab call karna.", "hi"),
        ("Sirf haal chaal poochne ke liye call kiya tha bas.", "hinglish"),
        ("No rush at all, whenever he's free is fine.", "en"),
        ("This can definitely wait a day or two, no hurry.", "en"),
    ], "NON_URGENT_CALL", action="COLLECT_MESSAGE")


def build_message_for_user(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("उनसे कह देना कि मैं शाम को कॉल करूँगा।", "hi"),
        ("उन्हें बता देना कि पार्सल आ गया है।", "hi"),
        ("उनको बता देना कि मीटिंग टल गई है।", "hi"),
        ("बता देना उनसे कि मैं थोड़ा देर से आऊँगा।", "hi"),
        ("कह देना कि पैसे ट्रांसफर कर दिए मैंने।", "hi"),
        ("बता देना कि घर पर सब ठीक है।", "hi"),
        ("संदेश पहुँचा देना कि कल सुबह मिलना है।", "hi"),
        ("Usko keh dena ki meeting reschedule ho gayi.", "hinglish"),
        ("Bata dena unko ki call karunga shaam ko.", "hi"),
        ("Bhai bata do usse ki kal wala plan cancel ho gaya.", "hi"),
        ("Please tell him I'll be 10 minutes late.", "en"),
        ("Let her know I called about the invoice.", "en"),
    ], "MESSAGE_FOR_USER", action="COLLECT_MESSAGE")


def build_schedule_request(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("कल सुबह के लिए कॉल शेड्यूल कर दो प्लीज़।", "hi"),
        ("अगले सोमवार मीटिंग रख दो कृपया।", "hi"),
        ("डॉक्टर से अपॉइंटमेंट के बारे में बात करनी थी।", "hi"),
        ("कल शाम की कॉल शेड्यूल कर दो।", "hi"),
        ("एक मीटिंग फिक्स कर दो अगले हफ्ते के लिए।", "hi"),
        ("सुबह नौ बजे का अपॉइंटमेंट रख दो।", "hi"),
        ("Kal subah call schedule kar do please.", "hi"),
        ("Weekend pe milne ka time fix kar do na.", "hinglish"),
        ("Client ke saath ek call schedule karni hai jaldi.", "hinglish"),
        ("Can we schedule a callback for tomorrow at 5pm?", "en"),
        ("Please arrange a callback once he's free tomorrow.", "en"),
    ], "SCHEDULE_REQUEST", action="COLLECT_MESSAGE")


def build_cancel_request(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("जो कॉलबैक शेड्यूल किया था वह रद्द कर दो।", "hi"),
        ("कल वाली मीटिंग रद्द कर दो।", "hi"),
        ("वह अपॉइंटमेंट रद्द कर दो जो मैंने बुक किया था।", "hi"),
        ("डॉक्टर की अपॉइंटमेंट रद्द कर दो, योजना बदल गई है।", "hi"),
        ("वह जो फॉलो-अप कॉल थी, रद्द कर दो।", "hi"),
        ("Woh jo callback schedule kiya tha usko cancel kar do.", "hinglish"),
        ("Kal wala plan cancel kar do bhai, nahi ho payega.", "hinglish"),
        ("Wo demo call cancel kar do, client ne mana kar diya.", "hinglish"),
        ("Cancel the callback we scheduled for tomorrow.", "en"),
        ("The interview is off, please cancel that slot.", "en"),
    ], "CANCEL_REQUEST", action="NO_ACTION")


def build_summarize_conversation(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("आज की सारी कॉल्स का सारांश दे दो।", "hi"),
        ("जितनी भी कॉल्स आईं उनका संक्षेप बना दो।", "hi"),
        ("मैं बाहर था, बताओ क्या-क्या हुआ छोटे में।", "hi"),
        ("आज दिन भर में क्या-क्या हुआ, संक्षेप में बताओ।", "hi"),
        ("इस हफ्ते की सारी कॉल्स का सारांश चाहिए।", "hi"),
        ("Aaj ke saare calls ka summary de do please.", "hinglish"),
        ("Jitne bhi calls aaye unka short summary bana do.", "hinglish"),
        ("Give me a quick summary of what happened while I was out.", "en"),
        ("Can you summarize what happened while I was out?", "en"),
    ], "SUMMARIZE_CONVERSATION", action="CREATE_SUMMARY")


def build_end_conversation(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("ठीक है, बस इतना ही था, धन्यवाद।", "hi"),
        ("अच्छा चलिए, फिर बात करते हैं, बाय।", "hi"),
        ("बस हो गई बात, धन्यवाद, अब रखता हूँ फ़ोन।", "hi"),
        ("ठीक है, दूसरी कोई बात नहीं, अलविदा।", "hi"),
        ("सब स्पष्ट है, अब फ़ोन रखता हूँ।", "hi"),
        ("Chalo bye, thanks yaar, milte hain phir.", "hinglish"),
        ("Theek hai bas itna hi tha, thanks bhai bye.", "hinglish"),
        ("Okay that's all, thank you, bye.", "en"),
        ("Alright, I think we've covered everything, see you.", "en"),
    ], "END_CONVERSATION", action="END_CALL")


def build_transfer_to_user(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("मुझे सीधे उनसे बात करनी है, कनेक्ट कर दो।", "hi"),
        ("नहीं मुझे उनसे ही सीधे बात करनी है।", "hi"),
        ("कृपया मुझे सीधे उनसे मिलाओ।", "hi"),
        ("कोई संदेश नहीं चाहिए, सीधे कॉल कनेक्ट करो।", "hi"),
        ("मुझे अभी उनसे बात करनी है, कोई देरी नहीं।", "hi"),
        ("Directly unhi se connect kara do please.", "hinglish"),
        ("Mujhe seedha unse baat karni hai, transfer kar do.", "hinglish"),
        ("Bas unko de do phone, main khud baat karta hoon.", "hinglish"),
        ("Actually let me talk to him directly, please.", "en"),
        ("I need to speak to him right now, no messages, connect me.", "en"),
    ], "TRANSFER_TO_USER", action="TRANSFER_CALL")


def build_general_conversation(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("नमस्ते, कैसे हो आप?", "hi"),
        ("आजकल सब ठीक चल रहा है?", "hi"),
        ("बहुत दिन हो गए बात किए, कैसे हो?", "hi"),
        ("जन्मदिन की बधाई देने के लिए कॉल किया था।", "hi"),
        ("बस यूँ ही कॉल कर लिया, कैसे हो सब?", "hi"),
        ("परिवार में सब कुशल मंगल है ना?", "hi"),
        ("Kya haal chaal hai bhai, sab badhiya?", "hinglish"),
        ("Bas hi bol raha tha, kaisa hai sab ghar mein?", "hinglish"),
        ("Kaafi din ho gaye baat kiye, kaise ho aap?", "hinglish"),
        ("Hi, how are you doing today?", "en"),
        ("Just wanted to say happy birthday!", "en"),
    ], "GENERAL_CONVERSATION", action="NO_ACTION")
    _add_many(ex, [
        ("याद रखना, मेरा नया पता यह वाला है।", "hi"),
        ("बस बता रहा था, मेरी शादी अगले महीने है।", "hi"),
        ("यह नोट कर लो, मुझे मूँगफली से एलर्जी है।", "hi"),
        ("मेरा नया नंबर यह है, सेव कर लेना।", "hi"),
        ("बता दूँ, मैंने नौकरी बदल ली है अभी।", "hi"),
        ("Yaad rakhna, mera naya ghar Pune mein hai ab.", "hinglish"),
        ("Note kar lena, mera naya office address yeh hai.", "hinglish"),
        ("Just so you know, I moved to a new city last month.", "en"),
        ("Remember I mentioned I'm allergic to peanuts? Just a reminder.", "en"),
    ], "GENERAL_CONVERSATION", action="SAVE_MEMORY",
       notes="Caller volunteers a durable fact WOW should persist, not just log the turn.")


def build_unknown(ex: list[RawExample]) -> None:
    _add_many(ex, [
        ("पता नहीं क्या कहना चाहते हो।", "hi"),
        ("कुछ समझ नहीं आया, दोबारा बोलो।", "hi"),
        ("मुझे भी नहीं पता क्या बोलूं अभी।", "hi"),
        ("समझ से बाहर है यह पूरा मामला।", "hi"),
        ("वो, मतलब, आप समझ ही गए होंगे।", "hi"),
        ("कुछ गड़बड़ है लेकिन पता नहीं क्या।", "hi"),
        ("Kya bol rahe ho yaar samajh nahi aaya mujhe.", "hinglish"),
        ("Wahi wala kaam kar do na, tumhe pata hai.", "hinglish"),
        ("Bas yun hi, kuch bhi keh sakte hain aap.", "hinglish"),
        ("asdkj qwoeiu random text", "en"),
        ("I forgot what I was going to say.", "en"),
        ("This doesn't really fit anywhere, does it?", "en"),
    ], "UNKNOWN", action="NO_ACTION",
       notes="Genuinely unclassifiable/gibberish/ambiguous.")


def build_hard_negatives(ex: list[RawExample]) -> None:
    """Explicitly targets the 8 confusable pairs called out in
    docs/DATASET.md "Hard negatives" - training/pipeline/label_validate.py's
    CONFUSABLE_PAIRS is the single source of truth these strings must match."""

    # URGENT_CALL_vs_NON_URGENT_CALL
    _add(ex, "यह अर्जेंट नहीं है, बस मीटिंग का समय बदल गया है बताना था।", "hi",
         "NON_URGENT_CALL", action="COLLECT_MESSAGE", hard_negative=True,
         confusable_pair="URGENT_CALL_vs_NON_URGENT_CALL",
         notes="Contains 'urgent' (negated) - must not become URGENT_CALL.")
    _add(ex, "Urgent hai yaar, turant baat karao unse abhi.", "hi",
         "URGENT_CALL", action="MARK_URGENT", hard_negative=True,
         confusable_pair="URGENT_CALL_vs_NON_URGENT_CALL",
         notes="Clear urgency signal despite short/casual phrasing.")
    _add(ex, "Not urgent at all, the meeting thing got sorted on its own.", "en",
         "NON_URGENT_CALL", action="COLLECT_MESSAGE", hard_negative=True,
         confusable_pair="URGENT_CALL_vs_NON_URGENT_CALL",
         notes="Contains 'meeting' and negated urgency - both signals resolve to non-urgent.")

    # KNOWN_CALLER_vs_UNKNOWN_CALLER
    _add(ex, "यह कोई अजनबी नंबर नहीं, यह तो मेरे भाई का नया नंबर है।", "hi",
         "KNOWN_CALLER", action="ANSWER_CALL", hard_negative=True,
         confusable_pair="KNOWN_CALLER_vs_UNKNOWN_CALLER",
         notes="'Stranger number' explicitly negated - a known contact.")
    _add(ex, "Not a known number, but the message says it's about my package.", "en",
         "UNKNOWN_CALLER", action="ASK_CALLER_REASON", hard_negative=True,
         confusable_pair="KNOWN_CALLER_vs_UNKNOWN_CALLER",
         notes="Caller-identity signal (unknown) wins over the topic mentioned.")
    _add(ex, "Nahi yaar, spam nahi hai yeh, mera dost hi hai purana wala.", "hi",
         "KNOWN_CALLER", action="ANSWER_CALL", hard_negative=True,
         confusable_pair="KNOWN_CALLER_vs_UNKNOWN_CALLER",
         notes="'Spam' negated - explicitly a known friend.")

    # SET_CONTEXT_vs_GENERAL_CONVERSATION
    _add(ex, "मैंने कॉल इसलिए किया था कि पूछूं क्या अनिकेत सो रहे हैं।", "hi",
         "GENERAL_CONVERSATION", action="NO_ACTION", hard_negative=True,
         confusable_pair="SET_CONTEXT_vs_GENERAL_CONVERSATION",
         notes="Caller asking ABOUT someone else's status, not declaring their own context.")
    _add(ex, "बैठक नहीं है आज, बस ऐसे ही फोन किया था।", "hi",
         "GENERAL_CONVERSATION", action="NO_ACTION", hard_negative=True,
         confusable_pair="SET_CONTEXT_vs_GENERAL_CONVERSATION",
         notes="'Meeting' (बैठक) explicitly negated - purely casual call.")
    _add(ex, "मुझे नींद आ रही है।", "hi",
         "SET_CONTEXT", context_mode="SLEEPING", action="SET_CONTEXT", hard_negative=True,
         confusable_pair="SET_CONTEXT_vs_GENERAL_CONVERSATION",
         notes="Minimal genuine SLEEPING declaration - the positive contrast case.")

    # GET_CONTEXT_vs_SET_CONTEXT
    _add(ex, "मुझे पता करना था कि क्या ऑफिस मेरी कॉल्स संभाल रहा है या नहीं।", "hi",
         "GET_CONTEXT", action="NO_ACTION", hard_negative=True,
         confusable_pair="GET_CONTEXT_vs_SET_CONTEXT",
         notes="Contains 'handling calls' but is a status question, not a command.")
    _add(ex, "Abhi kaunsa mode chal raha hai mera, bata do zara.", "hinglish",
         "GET_CONTEXT", action="NO_ACTION", hard_negative=True,
         confusable_pair="GET_CONTEXT_vs_SET_CONTEXT",
         notes="Question about current context, not an instruction to change it.")
    _add(ex, "मुझे बिज़ी मोड पर सेट कर दो अभी।", "hi",
         "SET_CONTEXT", context_mode="BUSY", action="SET_CONTEXT", hard_negative=True,
         confusable_pair="GET_CONTEXT_vs_SET_CONTEXT",
         notes="Explicit imperative to change context - the positive contrast case.")

    # END_CALL_vs_END_CONVERSATION
    _add(ex, "यह धोखाधड़ी वाली कॉल लग रही है, काट दो अभी।", "hi",
         "UNKNOWN_CALLER", action="END_CALL", hard_negative=True,
         confusable_pair="END_CALL_vs_END_CONVERSATION",
         notes="END_CALL here is about ending a suspicious call, not a polite wrap-up (END_CONVERSATION).")
    _add(ex, "ठीक है, बस इतना ही था, धन्यवाद, अलविदा।", "hi",
         "END_CONVERSATION", action="END_CALL", hard_negative=True,
         confusable_pair="END_CALL_vs_END_CONVERSATION",
         notes="Polite natural wrap-up - the END_CONVERSATION contrast case (action is still END_CALL).")
    _add(ex, "He said thanks but it's not over yet, one more thing to add.", "en",
         "GENERAL_CONVERSATION", action="NO_ACTION", hard_negative=True,
         confusable_pair="END_CALL_vs_END_CONVERSATION",
         notes="Contains 'thanks' (an END_CONVERSATION cue) but explicitly continues.")

    # MESSAGE_FOR_USER_vs_GENERAL_CONVERSATION
    _add(ex, "बस हालचाल पूछने के लिए कॉल किया था, कोई संदेश नहीं है।", "hi",
         "GENERAL_CONVERSATION", action="NO_ACTION", hard_negative=True,
         confusable_pair="MESSAGE_FOR_USER_vs_GENERAL_CONVERSATION",
         notes="Explicitly no message to relay - purely social.")
    _add(ex, "उनसे कह देना कि पार्सल आ गया है, यह ज़रूरी सूचना है।", "hi",
         "MESSAGE_FOR_USER", action="COLLECT_MESSAGE", hard_negative=True,
         confusable_pair="MESSAGE_FOR_USER_vs_GENERAL_CONVERSATION",
         notes="A concrete message to relay - the positive contrast case.")
    _add(ex, "Just wanted to say happy birthday, nothing to pass along really.", "en",
         "GENERAL_CONVERSATION", action="NO_ACTION", hard_negative=True,
         confusable_pair="MESSAGE_FOR_USER_vs_GENERAL_CONVERSATION",
         notes="Sounds message-adjacent but explicitly has no content to relay.")

    # CALL_PERSON_vs_HANDLE_CALLS
    _add(ex, "मुझे बहन से बात करनी है, उसे कॉल लगाओ।", "hi",
         "CALL_PERSON", action="NO_ACTION", hard_negative=True,
         confusable_pair="CALL_PERSON_vs_HANDLE_CALLS",
         notes="A request to place ONE outgoing call, not to manage incoming calls generally.")
    _add(ex, "मेरी सारी कॉल्स कुछ घंटों के लिए संभाल लो।", "hi",
         "HANDLE_CALLS", action="ENABLE_CALL_ASSISTANT", hard_negative=True,
         confusable_pair="CALL_PERSON_vs_HANDLE_CALLS",
         notes="General incoming-call management request - the positive contrast case.")
    _add(ex, "I need you to screen my calls from now on, not just this one.", "en",
         "HANDLE_CALLS", action="ENABLE_CALL_ASSISTANT", hard_negative=True,
         confusable_pair="CALL_PERSON_vs_HANDLE_CALLS",
         notes="Explicitly general/ongoing, not a single CALL_PERSON request.")

    # CLEAR_CONTEXT_vs_DISABLE_CALL_ASSISTANT
    _add(ex, "अब सामान्य मोड में वापस ले आओ, लेकिन कॉल्स अभी भी तुम ही संभालना।", "hi",
         "CLEAR_CONTEXT", context_mode="NORMAL", action="CLEAR_CONTEXT",
         hard_negative=True, confusable_pair="CLEAR_CONTEXT_vs_DISABLE_CALL_ASSISTANT",
         notes="Clearing the context (busy/sleeping/etc) does NOT necessarily mean disabling call handling entirely.")
    _add(ex, "अब कॉल हैंडलिंग पूरी तरह बंद कर दो, मैं खुद ले लूँगा।", "hi",
         "HANDLE_CALLS", action="DISABLE_CALL_ASSISTANT", hard_negative=True,
         confusable_pair="CLEAR_CONTEXT_vs_DISABLE_CALL_ASSISTANT",
         notes="Explicit request to disable call-handling automation entirely - the contrast case.")
    _add(ex, "Meeting khatam ho gayi, status normal kar do, calls tum hi lena abhi.", "hinglish",
         "CLEAR_CONTEXT", context_mode="NORMAL", action="CLEAR_CONTEXT",
         hard_negative=True, confusable_pair="CLEAR_CONTEXT_vs_DISABLE_CALL_ASSISTANT",
         notes="Context cleared but call assistant explicitly kept on - distinct from disabling it.")


def build_extra_hinglish(ex: list[RawExample]) -> None:
    """Genuine grammatical code-switching (English clauses/phrases mixed
    with Hindi grammar, not just Hindi sentences using English nouns) -
    added after the initial batch skewed lower on hinglish than the
    60/30/10 target once the loanword-only examples above were correctly
    relabeled to "hi" (see docs/DATASET.md "Language classification" for
    why that relabeling happened)."""
    _add(ex, "I think usko bata dena chahiye ki main busy hoon abhi.", "hinglish",
         "SET_CONTEXT", context_mode="BUSY", action="SET_CONTEXT")
    _add(ex, "Can you please unse ek baar baat karwao, it's important.", "hinglish",
         "TRANSFER_TO_USER", action="TRANSFER_CALL")
    _add(ex, "Actually mujhe lagta hai ki this is quite urgent.", "hinglish",
         "URGENT_CALL", action="MARK_URGENT")
    _add(ex, "I mean, woh busy hain shayad, just take a message.", "hinglish",
         "NON_URGENT_CALL", action="COLLECT_MESSAGE")
    _add(ex, "Honestly speaking, mujhe nahi pata kya bolna hai ab.", "hinglish",
         "UNKNOWN", action="NO_ACTION")
    _add(ex, "Just tell him ki maine call kiya tha, please.", "hinglish",
         "MESSAGE_FOR_USER", action="COLLECT_MESSAGE")
    _add(ex, "By the way, mera number change ho gaya hai, yaad rakhna.", "hinglish",
         "GENERAL_CONVERSATION", action="SAVE_MEMORY")
    _add(ex, "I don't think yeh koi real bank hai, scam lagta hai mujhe.", "hinglish",
         "UNKNOWN_CALLER", action="END_CALL")
    _add(ex, "Basically woh unavailable hain kal tak, so please call later.", "hinglish",
         "SET_CONTEXT", context_mode="UNAVAILABLE", action="SET_CONTEXT")
    _add(ex, "Trust me, yeh mera bhai hi hai, please connect kar do.", "hinglish",
         "KNOWN_CALLER", action="ANSWER_CALL")
    _add(ex, "Wait, let me check ki abhi konsa mode chal raha hai.", "hinglish",
         "GET_CONTEXT", action="NO_ACTION")
    _add(ex, "Sorry to bother you, but can you cancel that appointment please.", "hinglish",
         "CANCEL_REQUEST", action="NO_ACTION")
    _add(ex, "I guess we should schedule it for kal subah, would that work?", "hinglish",
         "SCHEDULE_REQUEST", action="COLLECT_MESSAGE")
    _add(ex, "To be honest, aaj ka din bahut hectic tha, give me a summary.", "hinglish",
         "SUMMARIZE_CONVERSATION", action="CREATE_SUMMARY")
    _add(ex, "Alright then, bas itna hi tha, thank you so much, bye.", "hinglish",
         "END_CONVERSATION", action="END_CALL")
    _add(ex, "Well, ab main free hoon, so you can clear my status.", "hinglish",
         "CLEAR_CONTEXT", context_mode="NORMAL", action="CLEAR_CONTEXT")
    _add(ex, "Could you please Rahul ko ek call laga do, it's quick.", "hinglish",
         "CALL_PERSON", action="NO_ACTION")
    _add(ex, "Look, main abhi bahar hoon, so handle my calls for a bit.", "hinglish",
         "HANDLE_CALLS", action="ENABLE_CALL_ASSISTANT")
    _add(ex, "Honestly ab zaroorat nahi hai, you can stop handling my calls.", "hinglish",
         "HANDLE_CALLS", action="DISABLE_CALL_ASSISTANT")
    _add(ex, "I just called kyunki mujhe pata karna tha ki sab theek hai.", "hinglish",
         "GENERAL_CONVERSATION", action="NO_ACTION")
    _add(ex, "So basically meeting cancel ho gayi hai, thought I'd let you know.", "hinglish",
         "MESSAGE_FOR_USER", action="COLLECT_MESSAGE")
    _add(ex, "I know woh so rahe hain, but this really can't wait.", "hinglish",
         "URGENT_CALL", action="MARK_URGENT",
         hard_negative=True, confusable_pair="URGENT_CALL_vs_NON_URGENT_CALL",
         notes="Mentions 'sleeping' context but the caller's stated urgency is decision-relevant.")
    _add(ex, "It's fine, koi jaldi nahi hai, whenever he gets a chance.", "hinglish",
         "NON_URGENT_CALL", action="COLLECT_MESSAGE")
    _add(ex, "Honestly, yeh number toh bilkul anjaan hai, ask them why they're calling.", "hinglish",
         "UNKNOWN_CALLER", action="ASK_CALLER_REASON")
    _add(ex, "I promise ki yeh bilkul zaroori nahi hai, don't worry about it.", "hinglish",
         "NON_URGENT_CALL", action="COLLECT_MESSAGE")
    _add(ex, "Frankly speaking mujhe khud nahi pata I called for what reason.", "hinglish",
         "UNKNOWN", action="NO_ACTION")
    _add(ex, "So the thing is, mera flight hai, might not be reachable.", "hinglish",
         "SET_CONTEXT", context_mode="TRAVELLING", action="SET_CONTEXT")
    _add(ex, "I hope aap samajh gaye honge, waisi hi baat hai jaisi pehle thi.", "hinglish",
         "UNKNOWN", action="NO_ACTION")
    _add(ex, "Please just note down ki delivery address change ho gaya hai.", "hinglish",
         "MESSAGE_FOR_USER", action="COLLECT_MESSAGE")
    _add(ex, "I'm pretty sure yeh spam hai, please just end the call.", "hinglish",
         "UNKNOWN_CALLER", action="END_CALL")


def build() -> list[RawExample]:
    ex: list[RawExample] = []
    build_set_context(ex)
    build_clear_context(ex)
    build_get_context(ex)
    build_call_person(ex)
    build_handle_calls(ex)
    build_unknown_caller(ex)
    build_known_caller(ex)
    build_urgent_call(ex)
    build_non_urgent_call(ex)
    build_message_for_user(ex)
    build_schedule_request(ex)
    build_cancel_request(ex)
    build_summarize_conversation(ex)
    build_end_conversation(ex)
    build_transfer_to_user(ex)
    build_general_conversation(ex)
    build_extra_hinglish(ex)
    build_unknown(ex)
    build_hard_negatives(ex)
    return ex


def main() -> None:
    examples = build()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "seed.jsonl"
    with output_path.open("w", encoding="utf-8") as f:
        for e in examples:
            f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")

    from collections import Counter
    lang_counts = Counter(e.language for e in examples)
    intent_counts = Counter(e.intent for e in examples)
    print(f"Wrote {len(examples)} examples to {output_path}")
    print(f"Language distribution: {dict(lang_counts)}")
    print(f"Intent count: {len(intent_counts)} distinct intents")
    print(f"Hard negatives: {sum(1 for e in examples if e.hard_negative)}")


if __name__ == "__main__":
    main()
