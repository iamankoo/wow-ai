"""Builds the WOW Brain v1 seed dataset.

This is NOT a bulk synthetic generator - every example below is
hand-authored, deliberately covering English, Hindi (Devanagari and Roman),
and Hinglish phrasings across formal/casual/short/indirect/incomplete
registers. Nothing here is derived from real user conversations (see
docs/TRAINING.md "Privacy" section).

v1 supersedes the v0 seed set (~117 examples), which was too small and too
imbalanced to train past majority-class collapse (see docs/TRAINING.md
"WOW Brain v0 post-mortem"). v1 targets 30-50+ examples per intent and per
action, keeps context modes reasonably balanced, and adds a dedicated set of
hard negatives - utterances whose surface keywords would mislead a
keyword/majority-class classifier but that a competent model must still get
right.

Run: python -m training.generation.build_seed_dataset
Writes JSONL files into training/datasets/{intents,contexts,conversations,call_scenarios,summaries}/
and refreshes training/datasets/DATASET_METADATA.json.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from training.datasets.schemas.call_scenario_example import CallScenarioExample
from training.datasets.schemas.common import SCHEMA_VERSION
from training.datasets.schemas.conversation_example import ConversationExample
from training.datasets.schemas.intent_example import IntentExample
from training.datasets.schemas.summary_example import SummaryExample
from training.wow_taxonomy import Action, CallerRelationship, ContextMode, Intent

DATASETS_DIR = Path(__file__).resolve().parents[1] / "datasets"


# ---------------------------------------------------------------------------
# Intent examples (general intents; SET_CONTEXT/CLEAR_CONTEXT live in
# build_context_examples for dedicated per-mode coverage)
# ---------------------------------------------------------------------------

def build_intent_examples() -> list[IntentExample]:
    ex: list[IntentExample] = []

    def add(text, language, intent, **kw):
        ex.append(IntentExample(text=text, language=language, intent=intent, **kw))

    def add_many(items, intent, **shared_kw):
        for text, language in items:
            add(text, language, intent, **shared_kw)

    # ---- HANDLE_CALLS: enable ----
    add_many([
        ("Handle my calls for the next few hours.", "en"),
        ("Please pick up my calls while I'm out.", "en"),
        ("Can you take over my calls starting now?", "en"),
        ("Start answering calls on my behalf.", "en"),
        ("Go ahead and manage my incoming calls.", "en"),
        ("Take charge of my calls for a while.", "en"),
        ("I need you to screen my calls from now on.", "en"),
        ("Mere calls sambhaal lo.", "hi"),
        ("Ab se mere calls tum dekh lena.", "hi"),
        ("Calls uthana shuru kar do mere liye.", "hi"),
        ("मेरे कॉल्स संभाल लो, मैं व्यस्त हूँ।", "hi"),
        ("अब से मेरी कॉल्स तुम देख लेना।", "hi"),
        ("Bhai mere calls handle kar lena thodi der.", "hinglish"),
        ("Yaar calls tu dekh le kuch der ke liye.", "hinglish"),
        ("Ek kaam kar, calls sambhal le meri ab.", "hinglish"),
        ("Please calls le lo mere, main busy hoon.", "hinglish"),
        ("Calls le lo.", "hinglish"),
        ("Can you cover my calls?", "en"),
        ("Screen my calls for the next hour, please.", "en"),
        ("Aaj poore din mere calls tum dekhna.", "hi"),
        ("आज पूरे दिन मेरी कॉल्स तुम संभालना।", "hi"),
        ("Filter my calls while I'm in the studio.", "en"),
        ("Bas ab se tu hi calls lena mere, main out of station hoon.", "hinglish"),
        ("Take my calls for the weekend, I'm switching off.", "en"),
        ("Kal se calls tum sambhalna jab tak main wapas na aaun.", "hi"),
        ("Please answer on my behalf until further notice.", "en"),
        ("Ab se poori shift ke liye calls tum lena.", "hinglish"),
        ("Go ahead and start filtering, I don't want interruptions.", "en"),
        ("Jab tak main na bolun, tab tak calls tum hi lena.", "hi"),
    ], Intent.HANDLE_CALLS, call_handling=True, action=Action.ENABLE_CALL_ASSISTANT)

    # ---- HANDLE_CALLS: disable ----
    add_many([
        ("Stop handling my calls now.", "en"),
        ("You can stop screening my calls.", "en"),
        ("Turn off call handling, I'll take it from here.", "en"),
        ("No need to manage my calls anymore.", "en"),
        ("Cancel the call assistant, I'm back.", "en"),
        ("Switch off call answering for me.", "en"),
        ("Ab calls mat sambhaalo.", "hi"),
        ("Calls handle karna band kar do.", "hi"),
        ("Ab mujhe khud calls lene hain.", "hi"),
        ("अब कॉल्स मत संभालो, मैं वापस आ गया हूँ।", "hi"),
        ("कॉल हैंडलिंग बंद कर दो अब।", "hi"),
        ("Bas ab calls mat le, main free hoon.", "hinglish"),
        ("Call assistant band kar do yaar, main aa gaya.", "hinglish"),
        ("Ab handle mat karo calls, main dekh lunga.", "hinglish"),
        ("Stop it, I'm here now.", "en"),
        ("Band karo calls lena.", "hinglish"),
        ("I'm back, you can stop now.", "en"),
        ("Disable karo isko.", "hinglish"),
        ("You don't need to filter my calls anymore, I've got it.", "en"),
        ("Ab screening band kar do, main handle kar lunga.", "hi"),
        ("अब स्क्रीनिंग बंद कर दो, मैं संभाल लूँगा।", "hi"),
        ("I'm off the flight now, stop taking my calls.", "en"),
        ("Studio se nikal gaya, ab calls tum mat lena.", "hinglish"),
        ("Weekend khatam, ab se calls main khud lunga.", "hi"),
        ("Shift over, please stop answering for me now.", "en"),
        ("Bas ab se main khud uthaunga apne calls.", "hi"),
        ("No more filtering needed, I've landed and I'm reachable.", "en"),
        ("Meeting khatam, ab tum calls mat lena, main free hoon.", "hinglish"),
    ], Intent.HANDLE_CALLS, call_handling=False, action=Action.DISABLE_CALL_ASSISTANT,
       notes="Negative form of HANDLE_CALLS - disable, not enable.")

    # ---- CALL_PERSON ----
    add_many([
        ("Call Rahul for me.", "en"),
        ("Can you dial my mom right now?", "en"),
        ("Please connect me to Priya.", "en"),
        ("Get Arjun on the line.", "en"),
        ("I want to talk to my manager, call him.", "en"),
        ("Ring up my brother please.", "en"),
        ("Try calling Neha again.", "en"),
        ("Priya ko call karo.", "hi"),
        ("Papa ko phone laga do.", "hi"),
        ("Zara Rahul ko call kar do.", "hi"),
        ("मम्मी को कॉल लगाओ।", "hi"),
        ("भाई को फ़ोन मिलाओ अभी।", "hi"),
        ("Zara mummy ko call laga do na.", "hinglish"),
        ("Ek baar Arjun ko try karo call karke.", "hinglish"),
        ("Boss ko call kardo abhi ke abhi.", "hinglish"),
        ("Doctor ko call laga do please.", "hinglish"),
        ("Call Mom.", "en"),
        ("Ring Rahul.", "en"),
        ("Papa ko call.", "hi"),
        ("I really need to reach my sister, can you dial her?", "en"),
        ("Would you mind connecting me with the office?", "en"),
        ("Suno, zara office wale ko call kar do.", "hinglish"),
        ("Call... uh, Rahul, yeah him.", "en"),
        ("Dial - the number saved as Amit.", "en"),
        ("Get me through to customer support.", "en"),
        ("Try my landlord's number.", "en"),
        ("Phone karo dukaan wale ko.", "hi"),
        ("Ek call lagao driver ko.", "hinglish"),
        ("Connect me with HR please.", "en"),
        ("Uncle ko ek call kardo.", "hinglish"),
    ], Intent.CALL_PERSON, action=Action.NO_ACTION)

    # ---- GET_CONTEXT ----
    add_many([
        ("What mode am I in right now?", "en"),
        ("What's my current status?", "en"),
        ("Am I set to busy or normal right now?", "en"),
        ("Tell me what context is active.", "en"),
        ("Is call handling even on right now?", "en"),
        ("What did I set my availability to?", "en"),
        ("Abhi kaunsa mode chal raha hai?", "hi"),
        ("Mera status kya set hai abhi?", "hi"),
        ("Main kis mode mein hoon?", "hi"),
        ("अभी कौन सा मोड चल रहा है?", "hi"),
        ("मेरी स्थिति क्या सेट है इस समय?", "hi"),
        ("Currently mera status kya set hai?", "hinglish"),
        ("Abhi main kya mode mein hoon yaar?", "hinglish"),
        ("Kya call handling on hai abhi bhi?", "hinglish"),
        ("Current mode?", "en"),
        ("Status?", "en"),
        ("Mera mode kya hai?", "hi"),
        ("I forget - did I set myself to sleeping or busy?", "en"),
        ("Just checking, what did I leave my status as?", "en"),
        ("Yaad nahi mujhe, kya set kiya tha maine?", "hi"),
        ("What's my... status thing right now?", "en"),
        ("Can you remind me what context I'm in?", "en"),
        ("Which persona is active at the moment?", "en"),
        ("Mujhe bata do abhi kaunsa context active hai.", "hi"),
        ("Is the assistant still filtering my calls?", "en"),
        ("Kya abhi bhi meeting mode on hai?", "hinglish"),
        ("Double checking - am I still marked as travelling?", "en"),
        ("Kya main abhi unavailable pe hoon?", "hi"),
        ("What was the last mode I set?", "en"),
        ("Pichhli baar maine kya set kiya tha, yaad dila do.", "hi"),
        ("Do you know if I'm still in busy mode?", "en"),
        ("Bata do zara, abhi kaunsa mode active hai mera.", "hinglish"),
    ], Intent.GET_CONTEXT, action=Action.NO_ACTION)

    # ---- KNOWN_CALLER: answer ----
    add_many([
        ("This caller is saved as my brother.", "en"),
        ("It's my wife calling, that's fine.", "en"),
        ("Oh that's my best friend, go ahead and let them through.", "en"),
        ("This number belongs to my dad, I'll take it.", "en"),
        ("Yeh number papa ka hai.", "hi"),
        ("Mummy ka call hai, le lo.", "hi"),
        ("यह मेरी बहन का नंबर है।", "hi"),
        ("यह मेरे दोस्त का कॉल है।", "hi"),
        ("Arre yeh toh mera bhai hai, connect kar do.", "hinglish"),
        ("Yeh dost hai mera college wala, le lo call.", "hinglish"),
        ("That's family, answer it.", "en"),
        ("Papa ka call hai.", "hi"),
        ("This is my closest friend from school calling.", "en"),
        ("Yeh mera relative hai, jaana pehchana number hai.", "hinglish"),
        ("It's my son calling from school.", "en"),
        ("Yeh meri nani ka number hai.", "hi"),
        ("यह मेरे चाचा का नंबर है, ले लो कॉल।", "hi"),
        ("That's my closest college roommate, go ahead and answer.", "en"),
        ("Bhabhi ka call hai, le lo.", "hinglish"),
        ("This is definitely my daughter's school teacher, answer it.", "en"),
        ("Saas ka call hai, le lo turant.", "hi"),
        ("It's my longtime business partner, always answer his calls.", "en"),
        ("Yeh mera bachpan ka dost hai, hamesha connect karna.", "hinglish"),
        ("Number saved as 'Doctor Sharma', I always take his calls.", "en"),
    ], Intent.KNOWN_CALLER, action=Action.ANSWER_CALL)

    # ---- KNOWN_CALLER: ask reason ----
    add_many([
        ("Office colleague is calling, ask what it's about.", "en"),
        ("It's a coworker, find out why they're calling.", "en"),
        ("This is my client, see what they need first.", "en"),
        ("That's my landlord, ask what the call is regarding.", "en"),
        ("Office colleague hai, poochho kis baare mein hai.", "hi"),
        ("Yeh business partner hai, kaaran poochho.", "hi"),
        ("यह मेरे बॉस का नंबर है, पूछो क्या बात है।", "hi"),
        ("यह मेरे क्लाइंट का कॉल है, वजह पूछ लो।", "hi"),
        ("Yeh manager hai mera, pooch lo kis baare mein call kiya.", "hinglish"),
        ("Vendor ka call hai, reason pooch lo pehle.", "hinglish"),
        ("Colleague hai, wajah pooch lo.", "hinglish"),
        ("Ask my accountant why he's calling.", "en"),
        ("This is a known business contact, check what they want.", "en"),
        ("Bank relationship manager hai, unse pooch lo kis baare mein hai.", "hi"),
    ], Intent.KNOWN_CALLER, action=Action.ASK_CALLER_REASON)

    # ---- KNOWN_CALLER: collect message ----
    add_many([
        ("It's a friend just calling to chat, take a message.", "en"),
        ("That's my cousin, note down whatever they say.", "en"),
        ("This is a college friend, just log the message.", "en"),
        ("Dost ka call hai, message le lo.", "hi"),
        ("College wala dost hai, note kar lo jo bole.", "hi"),
        ("यह मेरी सहेली का कॉल है, संदेश ले लो।", "hi"),
        ("Yeh dost hai casual baat karne wala, message le lo bas.", "hinglish"),
        ("Purana roommate hai, jo bole note kar lena.", "hinglish"),
        ("Friend hai, note kar lo.", "hinglish"),
        ("Known contact, nothing urgent, just take down what they say.", "en"),
        ("Neighbour ka call hai, message le lena unka.", "hi"),
        ("This is my gym buddy, just jot down the message.", "en"),
        ("Cousin hai, kuch bolna chahta hai, likh lo.", "hinglish"),
        ("It's an old classmate, take whatever message they leave.", "en"),
    ], Intent.KNOWN_CALLER, action=Action.COLLECT_MESSAGE)

    # ---- UNKNOWN_CALLER: ask reason ----
    add_many([
        ("This number isn't in my contacts, ask why they're calling.", "en"),
        ("I don't recognize this caller, find out what they want.", "en"),
        ("Never seen this number before, check the reason.", "en"),
        ("Unknown number calling, ask them what it's about.", "en"),
        ("This is a new number, no history - ask first.", "en"),
        ("Yeh number mere contacts mein nahi hai.", "hi"),
        ("Anjaan number hai, pehle kabhi call nahi aaya.", "hi"),
        ("Pehchana nahi mujhe yeh number, poochho kaun hai.", "hi"),
        ("यह नंबर मेरी लिस्ट में नहीं है, पूछो कौन है।", "hi"),
        ("अनजान नंबर है, पहले वजह पूछो।", "hi"),
        ("Ye number pehchana nahi mujhe.", "hinglish"),
        ("Naya number hai bilkul, pooch lo pehle kaun hai.", "hinglish"),
        ("Unknown number, ask first.", "en"),
        ("Kaun hai yeh, pooch lo.", "hinglish"),
        ("Not saved anywhere, find out the reason before anything else.", "en"),
        ("First time is number se call aaya hai, poochho kya kaam hai.", "hinglish"),
        ("Someone I don't know is calling, check what they need.", "en"),
        ("Naya caller hai, samajh nahi aa raha kaun hai.", "hinglish"),
        ("Doesn't match any of my saved contacts, ask around.", "en"),
        ("Yeh toh bilkul naya number hai, pehle poochho.", "hinglish"),
    ], Intent.UNKNOWN_CALLER, action=Action.ASK_CALLER_REASON)

    # ---- UNKNOWN_CALLER: spam / end call ----
    add_many([
        ("Caller claims to be from a bank asking for OTP.", "en"),
        ("Robotic caller offering a fake loan approval.", "en"),
        ("This sounds like a scam call, hang up.", "en"),
        ("Someone pretending to be tech support, end this.", "en"),
        ("This number has spammed me multiple times this week.", "en"),
        ("Recorded voice pushing a credit card offer, end the call.", "en"),
        ("Caller keeps asking for my PIN, that's suspicious.", "en"),
        ("Number pichhle hafte kai baar spam call kar chuka hai.", "hi"),
        ("Yeh fraud call lag raha hai, kaat do.", "hi"),
        ("यह धोखाधड़ी वाली कॉल लग रही है, काट दो।", "hi"),
        ("बैंक बनकर ओटीपी माँग रहा है, यह फ्रॉड है।", "hi"),
        ("Bank se bol raha hai bolke OTP maang raha hai, scam hai yeh.", "hinglish"),
        ("Yeh spam lag raha hai bhai, call kaat do.", "hinglish"),
        ("Scam call, end it.", "en"),
        ("Spam hai, kaat do.", "hinglish"),
        ("Automated voice claiming I've won a prize - obviously fake.", "en"),
        ("This caller refuses to say who they are and keeps pushing for money.", "en"),
        ("Fraud alert - caller is asking to confirm my card number.", "en"),
        ("Number pehle bhi kai logon ne spam report kiya hai.", "hi"),
        ("Suspicious robocall about a loan I never applied for, hang up.", "en"),
    ], Intent.UNKNOWN_CALLER, action=Action.END_CALL,
       notes="Spam/suspicious flavor of UNKNOWN_CALLER - action is END_CALL, not ASK_CALLER_REASON.")

    # ---- URGENT_CALL ----
    add_many([
        ("This is an emergency, I need to speak to him right now!", "en"),
        ("Please mark this as urgent, it can't wait.", "en"),
        ("Something serious happened, flag this immediately.", "en"),
        ("It's about my dad's health, this is critical.", "en"),
        ("The office server is down, they need him now.", "en"),
        ("I need an answer within the next five minutes, please.", "en"),
        ("Bahut zaroori hai, abhi baat karni hai.", "hi"),
        ("Emergency hai, turant batana unko.", "hi"),
        ("बहुत ज़रूरी है, अभी बात करनी है उनसे।", "hi"),
        ("यह आपातकाल है, तुरंत सूचित करो।", "hi"),
        ("Office se call hai, server down hai turant chahiye unko.", "hi"),
        ("Ekdum zaroori hai bhai, abhi bata do unhe.", "hinglish"),
        ("It's urgent.", "en"),
        ("Emergency hai.", "hi"),
        ("Turant chahiye.", "hi"),
        ("Mark it urgent, hospital is calling about my father.", "en"),
        ("This absolutely cannot wait until later.", "en"),
        ("Zaroori kaam hai office ka, turant call chahiye.", "hinglish"),
        ("Boss ka call hai, server down hone ke baare mein, turant.", "hinglish"),
        ("This is time-critical, get them on the phone now.", "en"),
        ("Manager calling about an urgent production issue.", "en"),
        ("Ambulance wale bol rahe hain, jaldi karo.", "hi"),
        ("Client here, contract needs signature today or the deal falls through.", "en"),
        ("Please treat this as priority one, it's about the accident.", "en"),
        ("Turant connect karo, ghar mein problem ho gayi hai.", "hinglish"),
        ("Flight miss ho raha hai, unhe abhi batana zaroori hai.", "hinglish"),
        ("Critical issue in production, need him on call immediately.", "en"),
        ("Doctor ne turant bulaya hai, ekdum urgent hai.", "hinglish"),
        ("Please treat this like a five-alarm fire, it's that serious.", "en"),
        ("Bahut hi jaldi baat karni hai, ek minute bhi wait nahi kar sakte.", "hi"),
        ("This is about a break-in at the house, extremely urgent.", "en"),
        ("Turant maan lena isko, delay mat karna.", "hinglish"),
    ], Intent.URGENT_CALL, action=Action.MARK_URGENT)

    # ---- NON_URGENT_CALL ----
    add_many([
        ("No rush, whenever he's free is fine.", "en"),
        ("This can wait until tomorrow, no hurry.", "en"),
        ("Nothing important, just a casual call.", "en"),
        ("Take your time getting back to me.", "en"),
        ("It's not urgent, just checking in.", "en"),
        ("Koi jaldi nahi hai, jab free ho tab baat kar lenge.", "hi"),
        ("Zaroori nahi hai, aaram se bata dena.", "hi"),
        ("कोई जल्दी नहीं है, जब समय मिले बता देना।", "hi"),
        ("ज़रूरी नहीं है यह कॉल, आराम से बताना।", "hi"),
        ("College ka dost, weekend plan ke liye call kar raha hai.", "hinglish"),
        ("Bas hi bolne ke liye call kiya tha, kaise ho?", "hinglish"),
        ("Kuch khaas nahi hai yaar, jab time mile tab dekh lena.", "hinglish"),
        ("No rush.", "en"),
        ("Koi jaldi nahi.", "hi"),
        ("Whenever, no hurry.", "en"),
        ("Friend calling to just chat casually.", "en"),
        ("Just a social call, nothing pressing.", "en"),
        ("This can definitely wait a day or two.", "en"),
        ("Bilkul zaroori nahi hai, jab free ho tab call karna.", "hinglish"),
        ("Sirf haal chaal poochne ke liye call kiya tha.", "hi"),
        ("Whenever you get a chance is totally fine.", "en"),
        ("Kal bhi baat ho jaaye toh chalega.", "hi"),
        ("Nothing to worry about, just a friendly check-in.", "en"),
        ("Free time mile tab hi call karna, jaldi nahi.", "hinglish"),
        ("This is low priority, feel free to reply later.", "en"),
        ("Bas gapshap karni thi, kuch important nahi.", "hi"),
        ("Take your time, there's no deadline on this.", "en"),
        ("Jab bhi convenient ho, tab baat kar lenge.", "hinglish"),
        ("Just a routine check-in, no urgency at all.", "en"),
        ("Kal bhi call kar loge toh koi farak nahi padega.", "hinglish"),
    ], Intent.NON_URGENT_CALL, action=Action.COLLECT_MESSAGE)

    # ---- MESSAGE_FOR_USER ----
    add_many([
        ("Please tell him I'll be 10 minutes late.", "en"),
        ("Let her know I called about the invoice.", "en"),
        ("Can you pass along that dinner is at 8?", "en"),
        ("Tell him the package arrived safely.", "en"),
        ("Just let her know I'll call back tonight.", "en"),
        ("Usko keh dena ki meeting reschedule ho gayi.", "hi"),
        ("Bata dena unko ki call karunga shaam ko.", "hi"),
        ("उनको बता देना कि पार्सल आ गया है।", "hi"),
        ("उनसे कह देना कि मैं शाम को कॉल करूँगा।", "hi"),
        ("Bhai bata do usse ki kal wala plan cancel ho gaya.", "hinglish"),
        ("Usko bol dena ki main thoda late aaunga.", "hinglish"),
        ("Keh dena unse ki paisa transfer kar diya maine.", "hinglish"),
        ("Tell him I called.", "en"),
        ("Bata dena maine call kiya.", "hi"),
        ("Message de do please.", "hinglish"),
        ("Pass on that the flight got delayed by two hours.", "en"),
        ("Let them know the documents are ready for pickup.", "en"),
        ("Bata dena ki ghar pe sab theek hai.", "hi"),
        ("Tell her the order got cancelled by the store.", "en"),
        ("Usse keh do ki party postpone ho gayi hai.", "hinglish"),
        ("Just tell him I stopped by and he wasn't around.", "en"),
        ("Note this down: rent has been paid for this month.", "en"),
        ("Unhe bata dena ki gaadi service ke liye chali gayi hai.", "hi"),
        ("Please tell him not to worry, everything's sorted.", "en"),
        ("Let them know the meeting notes have been shared.", "en"),
        ("Bata dena maine unka gift bhej diya.", "hi"),
        ("Message pahucha dena ki kal subah milna hai.", "hinglish"),
        ("Tell her I picked up the kids from school already.", "en"),
        ("Usko yeh bata do ki bill jama ho gaya hai.", "hinglish"),
        ("Just relay that everything went fine at the doctor's.", "en"),
    ], Intent.MESSAGE_FOR_USER, action=Action.COLLECT_MESSAGE)

    # ---- SCHEDULE_REQUEST ----
    add_many([
        ("Can we schedule a callback for tomorrow at 5pm?", "en"),
        ("Set up a call with him for next Monday.", "en"),
        ("I'd like to book a time to talk this week.", "en"),
        ("Can you arrange a meeting for Friday afternoon?", "en"),
        ("Let's fix a call for tomorrow morning.", "en"),
        ("Kal subah call schedule kar do please.", "hi"),
        ("Ek meeting fix kar do agle hafte ke liye.", "hi"),
        ("कल शाम की कॉल शेड्यूल कर दो।", "hi"),
        ("अगले सोमवार मीटिंग रख दो कृपया।", "hi"),
        ("Doctor se appointment ke baare mein baat karni thi.", "hinglish"),
        ("Hey, are you free for a call in 10 minutes?", "en"),
        ("Kal 4 baje ek call set kar do na.", "hinglish"),
        ("Book a slot tomorrow.", "en"),
        ("Kal ke liye time fix karo.", "hi"),
        ("Can we reschedule tomorrow's appointment to next week?", "en"),
        ("Please pencil in a call for Thursday evening.", "en"),
        ("Weekend pe milne ka time fix kar do.", "hinglish"),
        ("I want to set up a follow-up call next week.", "en"),
        ("Client ke saath ek call schedule karni hai jaldi.", "hinglish"),
        ("Would 3pm work for a quick sync tomorrow?", "en"),
        ("Agle hafte ek call rakh do office ke saath.", "hi"),
        ("Let's lock in a time for the demo call.", "en"),
        ("Subah 9 baje ka appointment fix kar do.", "hi"),
        ("Can we set a reminder call for his birthday?", "en"),
        ("Interview ke liye ek slot book kar do.", "hinglish"),
        ("Please arrange a callback once he's free tomorrow.", "en"),
        ("Ek call rakh do parso ke liye, subah ke time.", "hinglish"),
        ("Can you pencil me in for a 15-minute chat later this week?", "en"),
    ], Intent.SCHEDULE_REQUEST, action=Action.COLLECT_MESSAGE)

    # ---- CANCEL_REQUEST ----
    add_many([
        ("Cancel the callback we scheduled.", "en"),
        ("Please cancel tomorrow's meeting.", "en"),
        ("That appointment isn't needed anymore, cancel it.", "en"),
        ("Scratch that call we set up for Friday.", "en"),
        ("I need to cancel the demo we booked.", "en"),
        ("Woh jo callback schedule kiya tha usko cancel kar do.", "hi"),
        ("Kal wali meeting cancel kar do.", "hi"),
        ("कल की अपॉइंटमेंट रद्द कर दो।", "hi"),
        ("वह मीटिंग कैंसिल कर दो जो शेड्यूल की थी।", "hi"),
        ("Woh appointment cancel kar do jo maine book kiya tha.", "hinglish"),
        ("Kal wala plan cancel kar do bhai.", "hinglish"),
        ("Wo call cancel kardo jo subah rakhi thi.", "hinglish"),
        ("Cancel it.", "en"),
        ("Cancel kar do.", "hinglish"),
        ("No longer needed, cancel.", "en"),
        ("The interview is off, cancel that slot.", "en"),
        ("Please drop the reminder call, it's not required now.", "en"),
        ("Doctor ki appointment cancel kar do, plan badal gaya.", "hi"),
        ("That meeting won't happen anymore, take it off the calendar.", "en"),
        ("Wo demo call cancel kar do, client ne mana kar diya.", "hinglish"),
        ("Cancel the reschedule request from earlier.", "en"),
        ("Kal ka callback hata do, zaroorat nahi hai ab.", "hinglish"),
        ("Please void the booking we made yesterday.", "en"),
        ("Woh follow-up call cancel karo, kaam ho gaya already.", "hinglish"),
        ("The event's been called off, cancel any related calls.", "en"),
        ("Us appointment ko cancel kar dena, main nahi aa paunga.", "hi"),
    ], Intent.CANCEL_REQUEST, action=Action.NO_ACTION)

    # ---- SUMMARIZE_CONVERSATION ----
    add_many([
        ("Give me a summary of the calls I missed today.", "en"),
        ("Can you summarize what happened while I was out?", "en"),
        ("Recap the last conversation for me.", "en"),
        ("What did I miss - give me the highlights.", "en"),
        ("Summarize today's calls in a few lines.", "en"),
        ("Aaj ke saare calls ka summary de do.", "hi"),
        ("Jitne bhi calls aaye unka short summary bana do.", "hi"),
        ("आज की सारी कॉल्स का सारांश दे दो।", "hi"),
        ("जो भी बातचीत हुई उसका संक्षेप में बताओ।", "hi"),
        ("Give me a quick summary of what happened while I was out.", "hinglish"),
        ("Aaj din bhar mein kya kya hua, short mein bata do.", "hinglish"),
        ("Ek chhota summary bana do saare calls ka.", "hinglish"),
        ("Summarize today.", "en"),
        ("Summary de do.", "hinglish"),
        ("Recap please.", "en"),
        ("Walk me through what I missed in two sentences.", "en"),
        ("Can you condense today's calls into a quick brief?", "en"),
        ("Jo bhi important tha wahi bata do, summary mein.", "hi"),
        ("What are the key points from this morning's calls?", "en"),
        ("Aaj shaam tak jitne calls aaye unka overview de do.", "hi"),
        ("Give me the TL;DR of today's missed calls.", "en"),
        ("Ek summary chahiye is hafte ke saare calls ka.", "hinglish"),
        ("Just the important bits, summarize please.", "en"),
        ("Pura din kaisa raha calls ke hisaab se, bata do.", "hi"),
        ("Brief me on everything I missed since this morning.", "en"),
        ("Short mein bata do, aaj kya kya baat hui.", "hinglish"),
        ("Compile a quick summary of today's interactions.", "en"),
        ("Jo bhi log call kiye unka ek line summary chahiye.", "hinglish"),
        ("Roll up today's calls into one summary for me.", "en"),
        ("Din bhar ke calls ka ek summary chahiye mujhe raat tak.", "hi"),
    ], Intent.SUMMARIZE_CONVERSATION, action=Action.CREATE_SUMMARY)

    # ---- END_CONVERSATION ----
    add_many([
        ("Okay that's all, thank you, bye.", "en"),
        ("Alright, thanks, that's everything.", "en"),
        ("We're done here, goodbye.", "en"),
        ("That's it for now, talk later.", "en"),
        ("Okay, nothing else, bye bye.", "en"),
        ("Theek hai, bas itna hi tha, dhanyavaad.", "hi"),
        ("Achha theek hai, bas yehi tha, bye.", "hi"),
        ("ठीक है, बस इतना ही था, धन्यवाद।", "hi"),
        ("अच्छा चलिए, फिर बात करते हैं, बाय।", "hi"),
        ("Chalo bye, thanks yaar.", "hinglish"),
        ("Theek hai bas itna hi tha, thanks bhai bye.", "hinglish"),
        ("Achha chalta hoon, baad mein baat karte hain.", "hinglish"),
        ("Bye.", "en"),
        ("That's all, bye.", "en"),
        ("Okay, done, bye.", "en"),
        ("Bas, chalta hoon.", "hi"),
        ("Alright, I think we've covered everything, see you.", "en"),
        ("Nothing more from my side, take care, bye.", "en"),
        ("Theek hai, dhanyavaad, milte hain phir.", "hi"),
        ("That wraps it up, thanks for your time.", "en"),
        ("Okay cool, I'll let you go now, bye.", "en"),
        ("Bas hogaya baat, chalta hoon ab.", "hinglish"),
        ("We're good here, have a nice day, bye.", "en"),
        ("Achha theek hai, phone rakhta hoon ab.", "hi"),
        ("Alright then, that concludes it, goodbye.", "en"),
        ("Sab clear hai, ab rakhta hoon phone.", "hinglish"),
        ("Cool, that's everything from me, catch you later.", "en"),
        ("Bahut bahut dhanyavaad, ab chalti hoon.", "hi"),
        ("Okay no more questions, thanks and goodbye.", "en"),
        ("Yehi tha bas, ab main rakhta hoon.", "hinglish"),
    ], Intent.END_CONVERSATION, action=Action.END_CALL)

    # ---- TRANSFER_TO_USER ----
    add_many([
        ("Actually let me talk to him directly.", "en"),
        ("Can you connect me directly, it's about a family emergency?", "en"),
        ("I need to speak to him right now, no messages, connect me.", "en"),
        ("Please just put me through to her.", "en"),
        ("Skip the assistant, get him on the line.", "en"),
        ("Nahi mujhe unse hi baat karni hai seedhe.", "hi"),
        ("Seedhe unhi se connect kar do please.", "hi"),
        ("मुझे सीधे उनसे बात करनी है, कनेक्ट कर दो।", "hi"),
        ("कृपया मुझे सीधे उनसे मिलाओ।", "hi"),
        ("Directly unhi se connect kara do please.", "hinglish"),
        ("Mujhe seedha unse baat karni hai, transfer kar do.", "hinglish"),
        ("Bas unko de do phone, main khud baat karta hoon.", "hinglish"),
        ("Transfer me.", "en"),
        ("Connect me directly.", "en"),
        ("Seedha unse milao.", "hi"),
        ("No message needed, just patch me through now.", "en"),
        ("This needs to go straight to him, please transfer.", "en"),
        ("Can you hand the call over to her personally?", "en"),
        ("Main khud se baat karna chahta hoon, transfer kar do.", "hi"),
        ("Put me on with him immediately, please.", "en"),
        ("I don't want to leave a message, connect the call.", "en"),
        ("Unse hi baat karwa do, koi aur nahi.", "hi"),
        ("Direct line chahiye unse abhi ke abhi.", "hinglish"),
        ("Please bypass the assistant and connect us.", "en"),
        ("Mujhe unse abhi baat karni hai, koi delay nahi.", "hi"),
        ("Transfer the call to him right away.", "en"),
        ("Seedhe unse connect karo, zaroori baat hai.", "hinglish"),
        ("Get her on the phone with me now, please.", "en"),
    ], Intent.TRANSFER_TO_USER, action=Action.TRANSFER_CALL)

    # ---- GENERAL_CONVERSATION: no action ----
    add_many([
        ("Hi, how are you doing today?", "en"),
        ("Just wanted to say happy birthday!", "en"),
        ("Hey, how's everything going?", "en"),
        ("Nice weather today, isn't it?", "en"),
        ("Just checking in, no particular reason.", "en"),
        ("Hope you're doing well these days.", "en"),
        ("Namaste, kaise ho?", "hi"),
        ("Kya haal chaal hai bhai?", "hi"),
        ("नमस्ते, कैसे हो आप?", "hi"),
        ("आजकल सब ठीक चल रहा है?", "hi"),
        ("Bas hi bol raha tha, kaisa hai sab?", "hinglish"),
        ("Hi there.", "en"),
        ("How's it going?", "en"),
        ("Sab badhiya?", "hinglish"),
        ("Just wanted to catch up, it's been a while.", "en"),
        ("Aaj mausam kaafi accha hai, is not it?", "hinglish"),
        ("Happy anniversary to you both!", "en"),
        ("Just called to say hello, nothing else.", "en"),
        ("Kaafi din ho gaye baat kiye, kaise ho?", "hi"),
        ("Congratulations on the new job, by the way!", "en"),
        ("Bas yun hi call kar liya, kaise ho sab?", "hinglish"),
        ("Hope the family is doing great.", "en"),
        ("Kal ka match dekha kya, kya scene tha!", "hinglish"),
    ], Intent.GENERAL_CONVERSATION, action=Action.NO_ACTION)

    # ---- GENERAL_CONVERSATION: caller shares a fact worth remembering ----
    add_many([
        ("Just so you know, I moved to Pune last month.", "en"),
        ("By the way, my new number is this one, save it.", "en"),
        ("Remember I mentioned I'm allergic to peanuts? Just a reminder.", "en"),
        ("Just letting you know I got married last week.", "en"),
        ("FYI I changed jobs, I'm at a new company now.", "en"),
        ("Quick note - my anniversary is in October, remember that.", "en"),
        ("Yaad rakhna, mera naya ghar Pune mein hai ab.", "hi"),
        ("Bas bata raha tha, mera birthday agle mahine hai.", "hi"),
        ("याद रखना, मेरा नया पता यह वाला है।", "hi"),
        ("बस बता रहा था, मेरी शादी अगले महीने है।", "hi"),
        ("Note kar lena, mera naya office address yeh hai.", "hinglish"),
        ("Bas yaad rakhna, main lactose intolerant hoon.", "hinglish"),
        ("Just noting - I'm vegetarian now.", "en"),
        ("Remember this: new address, Pune.", "en"),
        ("For future reference, I prefer calls after 6pm.", "en"),
        ("Keep in mind, I'm allergic to penicillin.", "en"),
        ("Bata dena, mera pet ka naam Bruno hai, bas yaad rahe.", "hinglish"),
        ("Just so it's on record, I switched my email address.", "en"),
        ("Yaad rakhna agli baar, mujhe subah jaldi call mat karna.", "hinglish"),
        ("Note this down for later - my birthday's next Tuesday.", "en"),
        ("Mera blood group O positive hai, kabhi zaroorat pade toh yaad rakhna.", "hi"),
        ("मेरा नया दफ्तर का पता यह है, आगे के लिए नोट कर लो।", "hi"),
        ("Just so you have it on record, I quit smoking last year.", "en"),
        ("Ek baat yaad rakhna, mujhe dair raat call mat karna kabhi.", "hinglish"),
        ("For the record, I go by a nickname now, call me Rick.", "en"),
        ("Bata dena, mera driving license renew ho gaya hai.", "hi"),
        ("Keep this noted - my emergency contact is now my sister, not my mom.", "en"),
        ("Yaad rakhna, main non-vegetarian nahi khata ab.", "hinglish"),
    ], Intent.GENERAL_CONVERSATION, action=Action.SAVE_MEMORY,
       notes="Caller volunteers a durable fact - WOW should persist it, not just log the turn.")

    # ---- UNKNOWN ----
    add_many([
        ("asdkj qwoeiu random text", "en"),
        ("blah blah nothing here", "en"),
        ("xyz nonsense input", "en"),
        ("purple elephants dancing on the moon", "en"),
        ("...", "en"),
        ("Handle it.", "en"),
        ("Woh kar do na jo pehle bola tha.", "hi"),
        ("Kuch samajh nahi aa raha kya bol rahe ho.", "hi"),
        ("पता नहीं क्या कहना चाहते हो।", "hi"),
        ("कुछ समझ नहीं आया, दोबारा बोलो।", "hi"),
        ("Kya bol rahe ho yaar samajh nahi aaya.", "hinglish"),
        ("Wahi wala kaam kar do na, tumhe pata hai.", "hinglish"),
        ("Uh... never mind.", "en"),
        ("Hmm okay so...", "en"),
        ("Wait what?", "en"),
        ("Kuch bhi.", "hi"),
        ("Do the thing we talked about.", "en"),
        ("You know what I mean, right?", "en"),
        ("It's complicated, I'll explain later.", "en"),
        ("Just... deal with it somehow.", "en"),
        ("Wahi purana wala scene hai bas.", "hinglish"),
        ("I don't even know why I called.", "en"),
        ("Kuch nahi bas aise hi try kar raha tha.", "hi"),
        ("asdf jkl; random keys", "en"),
        ("Testing testing one two three.", "en"),
        ("Woh, matlab, aap samajh hi gaye honge.", "hi"),
        ("qwerty asdf zxcv", "en"),
        ("Um, so, anyway.", "en"),
        ("Kuch toh bolna tha, bhool gaya.", "hi"),
        ("न जाने क्या कहना था, याद नहीं आ रहा।", "hi"),
        ("Never mind, forget it.", "en"),
    ], Intent.UNKNOWN, action=Action.NO_ACTION,
       notes="Genuinely unclassifiable/gibberish/ambiguous - must not be force-fit into any real intent.")

    # ---- UNKNOWN: v1.1 additions (dataset_version 2.1.0) ----
    # v1's evaluation showed UNKNOWN as its weakest per-intent accuracy
    # (20%, n=5) - this block specifically grows that category.
    add_many([
        ("I forgot what I was going to say.", "en"),
        ("Zzz... sorry, dozed off, what was I saying.", "en"),
        ("मुझे नहीं पता मैं क्यों बोल रहा हूँ।", "hi"),
        ("Kaise batau, samajh hi nahi aa raha.", "hi"),
        ("This call is about... you know, the thing.", "en"),
        ("Aap samajh gaye na, wahi wala matter.", "hinglish"),
        ("क्या बकवास है यह, कुछ समझ नहीं आया।", "hi"),
        ("Random gibberish xyzzy plugh foobar.", "en"),
        ("बस ऐसे ही, कोई खास बात नहीं थी शायद।", "hi"),
        ("It's kind of hard to explain over the phone.", "en"),
        ("Wo scene alag hai bhai, chhodo.", "hinglish"),
        ("..hmm..", "en"),
        ("११२२३३ यह क्या है पता नहीं।", "hi"),
        ("I'll figure it out later, don't worry about it.", "en"),
        ("Bas yun hi, kuch bhi keh sakte hain aap.", "hinglish"),
        ("??? not sure what to say here.", "en"),
        ("Isko kya bole samajh nahi aa raha mujhe khud.", "hinglish"),
        ("मुझे भी नहीं पता क्या बोलूं अभी।", "hi"),
        ("This doesn't really fit anywhere, does it?", "en"),
        ("Kuch gadbad hai lekin pata nahi kya.", "hinglish"),
        ("Ek minute, main bhool gaya kya bolna tha.", "hinglish"),
        ("aeiou random vowels test string", "en"),
        ("समझ से बाहर है यह पूरा मामला।", "hi"),
        ("You get it, right? Yeah, that.", "en"),
        ("Bas aise hi, matlab kuch nahi.", "hinglish"),
        ("Sorry, wrong thought, ignore that.", "en"),
        ("म म म म क्या बोलूं।", "hi"),
        ("That's a whole other conversation, not now.", "en"),
        ("Kuch pooch rahe the aap? Bhool gaya.", "hinglish"),
        ("फिर से बताओ, समझ नहीं पाया मैं।", "hi"),
    ], Intent.UNKNOWN, action=Action.NO_ACTION,
       notes="v1.1 addition - grows UNKNOWN coverage (v1's weakest per-intent accuracy).")

    # ---- Corrections (user correcting a prior misunderstanding) ----
    add("No I didn't mean sleeping, I meant I'm in a meeting.", "en", Intent.SET_CONTEXT,
        context_mode=ContextMode.MEETING, action=Action.SET_CONTEXT,
        notes="Correction of a prior SLEEPING misclassification.")
    add("Nahi yaar sleeping nahi, meeting mein hoon main.", "hinglish", Intent.SET_CONTEXT,
        context_mode=ContextMode.MEETING, action=Action.SET_CONTEXT,
        notes="Correction, Hinglish.")
    add("Not busy anymore, I'm actually done, clear the status.", "en", Intent.CLEAR_CONTEXT,
        context_mode=ContextMode.NORMAL, call_handling=False, action=Action.CLEAR_CONTEXT,
        notes="Correction retracting an earlier BUSY context.")

    # ---- Follow-up commands (continuing a prior turn) ----
    add("And also let my brother through if he calls.", "en", Intent.KNOWN_CALLER,
        action=Action.ANSWER_CALL, parameters={"relationship": "FAMILY"},
        notes="Follow-up to a prior SET_CONTEXT turn.")
    add("Aur haan, agar office se call aaye to urgent maan lena.", "hi", Intent.URGENT_CALL,
        action=Action.MARK_URGENT, notes="Follow-up conditioning a future call as urgent.")

    ex.extend(build_hard_negative_examples())

    return ex


# ---------------------------------------------------------------------------
# Hard negatives: utterances whose surface keywords would mislead a
# keyword-matching or majority-class classifier, but that have one clear
# correct label. This is the direct countermeasure to the v0 SET_CONTEXT/
# BUSY mode-collapse failure mode documented in docs/TRAINING.md.
# ---------------------------------------------------------------------------

def build_hard_negative_examples() -> list[IntentExample]:
    ex: list[IntentExample] = []

    def add(text, language, intent, **kw):
        ex.append(IntentExample(text=text, language=language, intent=intent, **kw))

    add("Urgent hai yaar, turant baat karao.", "hinglish", Intent.URGENT_CALL,
        action=Action.MARK_URGENT,
        notes="Hard negative: contains no context-mode keyword despite superficially "
              "resembling a command; must not default to SET_CONTEXT.")
    add("The meeting isn't urgent anymore.", "en", Intent.NON_URGENT_CALL,
        action=Action.COLLECT_MESSAGE,
        notes="Hard negative: contains both 'meeting' and 'urgent', but negated - "
              "must not become SET_CONTEXT/MEETING or URGENT_CALL.")
    add("I'm sleeping.", "en", Intent.SET_CONTEXT, context_mode=ContextMode.SLEEPING,
        action=Action.SET_CONTEXT, notes="Hard negative: minimal SLEEPING declaration.")
    add("I called because I wanted to know whether Aniket is sleeping.", "en",
        Intent.GENERAL_CONVERSATION, action=Action.NO_ACTION,
        notes="Hard negative: contains 'sleeping' but is a caller asking ABOUT the "
              "user's status, not the user declaring their own context - must not "
              "become SET_CONTEXT/SLEEPING.")
    add("Happy birthday!", "en", Intent.GENERAL_CONVERSATION, action=Action.NO_ACTION,
        notes="Hard negative: short, purely social, no actionable content.")
    add("Okay, that's all, thank you.", "en", Intent.END_CONVERSATION, action=Action.END_CALL,
        notes="Hard negative: politeness-only closing phrase, no explicit 'bye'.")
    add("Someone is calling from an unknown number.", "en", Intent.UNKNOWN_CALLER,
        action=Action.ASK_CALLER_REASON,
        notes="Hard negative: plain statement of an unrecognized caller.")
    add("An unknown caller is asking about my meeting.", "en", Intent.UNKNOWN_CALLER,
        action=Action.ASK_CALLER_REASON,
        notes="Hard negative: contains 'meeting' but the caller identity signal "
              "(unknown) dominates - must resolve to UNKNOWN_CALLER, not "
              "GENERAL_CONVERSATION or SET_CONTEXT/MEETING.")
    add("Don't mark this as urgent, it can wait.", "en", Intent.NON_URGENT_CALL,
        action=Action.COLLECT_MESSAGE,
        notes="Hard negative: contains 'urgent' but negated by 'don't mark'.")
    add("This isn't a real emergency, just take a message.", "en", Intent.NON_URGENT_CALL,
        action=Action.COLLECT_MESSAGE,
        notes="Hard negative: contains 'emergency' but explicitly denied.")
    add("I'm not asleep, don't switch on do-not-disturb.", "en", Intent.CLEAR_CONTEXT,
        context_mode=ContextMode.NORMAL, call_handling=False, action=Action.CLEAR_CONTEXT,
        notes="Hard negative: contains 'asleep' but negated - must not become "
              "SET_CONTEXT/SLEEPING.")
    add("He said he's busy, so I'll call back later.", "en", Intent.NON_URGENT_CALL,
        action=Action.COLLECT_MESSAGE,
        notes="Hard negative: 'busy' describes a third party from the caller's side, "
              "not the user's own context - must not become SET_CONTEXT/BUSY.")
    add("I know the meeting got moved, no need to hold my calls anymore.", "en",
        Intent.CLEAR_CONTEXT, context_mode=ContextMode.NORMAL, call_handling=False,
        action=Action.CLEAR_CONTEXT,
        notes="Hard negative: mentions 'meeting' but the instruction is to stop "
              "holding calls - must resolve to CLEAR_CONTEXT, not SET_CONTEXT/MEETING.")
    add("Is he still in his meeting? I really need him urgently.", "en", Intent.URGENT_CALL,
        action=Action.MARK_URGENT,
        notes="Hard negative: mentions 'meeting' as a question about the user's "
              "status, but the caller's own urgency is the actionable signal.")
    add("Unknown number called earlier asking about the meeting time, not sure what "
        "they wanted.", "en", Intent.UNKNOWN_CALLER, action=Action.ASK_CALLER_REASON,
        notes="Hard negative: second instance of 'meeting' co-occurring with an "
              "unknown-caller signal - caller identity wins.")
    add("I wanted to know if the office is handling my calls or not.", "en",
        Intent.GET_CONTEXT, action=Action.NO_ACTION,
        notes="Hard negative: contains 'handling my calls' but is a question, not an "
              "instruction - must not become HANDLE_CALLS.")
    add("Stop worrying, it's not urgent, I'll message whenever.", "en", Intent.NON_URGENT_CALL,
        action=Action.COLLECT_MESSAGE,
        notes="Hard negative: contains 'urgent' but explicitly negated.")
    add("He's not busy, he's actually free the whole afternoon.", "en",
        Intent.GENERAL_CONVERSATION, action=Action.NO_ACTION,
        notes="Hard negative: contains 'busy' but negated and describes a third "
              "party's schedule informationally - not a context command.")
    add("That's not a real bank calling, it's definitely a scam.", "en",
        Intent.UNKNOWN_CALLER, action=Action.END_CALL,
        notes="Hard negative: mentions 'bank' (which could suggest a known business "
              "contact) but is flagged as fraudulent - must resolve to END_CALL.")
    add("He said thanks but it's not over yet, one more thing.", "en",
        Intent.GENERAL_CONVERSATION, action=Action.NO_ACTION,
        notes="Hard negative: contains 'thanks' (an END_CONVERSATION cue) but "
              "explicitly continues - must not end the call.")
    add("It's my brother, but honestly this one can wait, no rush.", "en",
        Intent.NON_URGENT_CALL, action=Action.COLLECT_MESSAGE,
        notes="Hard negative: family relationship alone does not imply urgency when "
              "the caller explicitly says there's no rush.")

    # ---- v1.1 additions (dataset_version 2.1.0) ----
    add("I'm not in a meeting anymore, you can put calls through.", "en",
        Intent.CLEAR_CONTEXT, context_mode=ContextMode.NORMAL, call_handling=False,
        action=Action.CLEAR_CONTEXT,
        notes="Hard negative: contains 'meeting' but negated - resolves to CLEAR_CONTEXT.")
    add("This isn't urgent, but the meeting did get moved to 3pm.", "en",
        Intent.NON_URGENT_CALL, action=Action.COLLECT_MESSAGE,
        notes="Hard negative: contains both 'urgent' (negated) and 'meeting' - neither "
              "should override the explicitly stated non-urgency.")
    add("Woh abhi so nahi rahe, connect kar sakte ho unse.", "hi",
        Intent.TRANSFER_TO_USER, action=Action.TRANSFER_CALL,
        notes="Hard negative: contains 'sleeping' negated - must not become SET_CONTEXT/SLEEPING.")
    add("Not a known number, but the message says it's about my package.", "en",
        Intent.UNKNOWN_CALLER, action=Action.ASK_CALLER_REASON,
        notes="Hard negative: caller-identity signal (unknown) wins over the topic mentioned.")
    add("He's busy but this really can't wait.", "en",
        Intent.URGENT_CALL, action=Action.MARK_URGENT,
        notes="Hard negative: contains 'busy' but the urgency signal is decision-relevant.")
    add("I called to check if the office is still holding my calls from earlier.", "en",
        Intent.GET_CONTEXT, action=Action.NO_ACTION,
        notes="Hard negative: contains 'holding my calls' but is a status question, not a command.")
    add("Don't worry, it's nothing serious, just wanted to say hi.", "en",
        Intent.GENERAL_CONVERSATION, action=Action.NO_ACTION,
        notes="Hard negative: reassurance phrasing that could be misread as urgency-adjacent.")
    add("वो जो अर्जेंट काम था, वो टल गया है अब।", "hi",
        Intent.NON_URGENT_CALL, action=Action.COLLECT_MESSAGE,
        notes="Hard negative: contains 'urgent' (अर्जेंट) but the matter is now resolved/postponed.")
    add("Not the bank calling, it's actually my real bank relationship manager, Rahul.", "en",
        Intent.KNOWN_CALLER, action=Action.ASK_CALLER_REASON,
        notes="Hard negative: mentions 'bank' (spam-adjacent keyword) but is explicitly a known contact.")
    add("Please don't wake him, it's not that important.", "en",
        Intent.NON_URGENT_CALL, action=Action.COLLECT_MESSAGE,
        notes="Hard negative: contains 'wake' (SLEEPING-adjacent) but is a non-urgency statement.")
    add("Turant nahi, lekin haan office wala kaam hai.", "hinglish",
        Intent.NON_URGENT_CALL, action=Action.COLLECT_MESSAGE,
        notes="Hard negative: 'turant nahi' (not immediate) explicitly negates urgency.")
    add("He mentioned the meeting but honestly I just called to catch up.", "en",
        Intent.GENERAL_CONVERSATION, action=Action.NO_ACTION,
        notes="Hard negative: mentions 'meeting' but the actual purpose is casual conversation.")
    add("यह कोई अजनबी नंबर नहीं, यह तो मेरे भाई का नया नंबर है।", "hi",
        Intent.KNOWN_CALLER, action=Action.ANSWER_CALL,
        notes="Hard negative: 'stranger number' explicitly negated - this is a known contact.")
    add("I know he's travelling, but I still need to reach him right now.", "en",
        Intent.URGENT_CALL, action=Action.MARK_URGENT,
        notes="Hard negative: contains 'travelling' but the caller's urgency is decision-relevant.")
    add("Not cancelling anything, just confirming the schedule.", "en",
        Intent.SCHEDULE_REQUEST, action=Action.COLLECT_MESSAGE,
        notes="Hard negative: contains 'cancel' but explicitly negated - this is a scheduling confirmation.")
    add("बैठक नहीं है आज, बस ऐसे ही फोन किया।", "hi",
        Intent.GENERAL_CONVERSATION, action=Action.NO_ACTION,
        notes="Hard negative: 'meeting' (बैठक) explicitly negated - purely casual call.")
    add("He's not on a call anymore, you can put me through now.", "en",
        Intent.TRANSFER_TO_USER, action=Action.TRANSFER_CALL,
        notes="Hard negative: BUSY-like signal negated - resolves to a direct transfer.")
    add("Nahi yaar, spam nahi hai yeh, mera dost hi hai.", "hinglish",
        Intent.KNOWN_CALLER, action=Action.ANSWER_CALL,
        notes="Hard negative: 'spam' explicitly negated - this is a known friend.")
    add("This isn't a sales call, I'm your actual doctor's office calling.", "en",
        Intent.KNOWN_CALLER, action=Action.ASK_CALLER_REASON,
        notes="Hard negative: unsolicited-call pattern explicitly denied as spam/sales.")
    add("Kuch cancel nahi karna, bas time confirm karna tha.", "hi",
        Intent.SCHEDULE_REQUEST, action=Action.COLLECT_MESSAGE,
        notes="Hard negative: 'cancel' negated - this is a scheduling confirmation.")
    add("He didn't reject anything, he just needs more time to decide.", "en",
        Intent.NON_URGENT_CALL, action=Action.COLLECT_MESSAGE,
        notes="Hard negative: 'reject' mentioned but negated - not an urgent rejection.")
    add("It's not that I'm ignoring calls, I'm literally on a flight.", "en",
        Intent.SET_CONTEXT, context_mode=ContextMode.TRAVELLING, action=Action.SET_CONTEXT,
        notes="Hard negative: 'ignoring calls' negated - the real signal is TRAVELLING context.")
    add("Emergency nahi hai koi, bas dua salam ke liye call kiya.", "hi",
        Intent.GENERAL_CONVERSATION, action=Action.NO_ACTION,
        notes="Hard negative: 'emergency' explicitly negated - purely a courtesy call.")
    add("टेक सपोर्ट नहीं है यह, मेरा असली आईटी वाला दोस्त है।", "hi",
        Intent.KNOWN_CALLER, action=Action.ASK_CALLER_REASON,
        notes="Hard negative: 'tech support' (scam-adjacent pattern) explicitly denied as a known friend.")
    add("Not asking to cancel, just want to push it a day later.", "en",
        Intent.SCHEDULE_REQUEST, action=Action.COLLECT_MESSAGE,
        notes="Hard negative: 'cancel' negated - this is a reschedule request.")

    return ex


# ---------------------------------------------------------------------------
# Context-switching examples (dedicated coverage of every ContextMode)
# ---------------------------------------------------------------------------

def build_context_examples() -> list[IntentExample]:
    ex: list[IntentExample] = []

    def add(text, language, mode, intent=Intent.SET_CONTEXT, call_handling=True, **kw):
        action = Action.CLEAR_CONTEXT if intent == Intent.CLEAR_CONTEXT else Action.SET_CONTEXT
        ex.append(IntentExample(
            text=text, language=language, intent=intent, context_mode=mode,
            call_handling=call_handling, action=action, **kw,
        ))

    # SLEEPING
    add("I'm going to sleep, handle my calls.", "en", ContextMode.SLEEPING)
    add("Main so raha hoon, calls sambhaal lena.", "hi", ContextMode.SLEEPING)
    add("सोने जा रहा हूँ, कॉल्स संभाल लेना।", "hi", ContextMode.SLEEPING)
    add("Sone ja raha hoon yaar, calls dekh lena tum.", "hinglish", ContextMode.SLEEPING)
    add("Going to bed now, don't wake me up for calls.", "en", ContextMode.SLEEPING)
    add("Neend aa rahi hai, so jaunga ab.", "hi", ContextMode.SLEEPING)
    # v1.1 additions (dataset_version 2.1.0)
    add("Lights off, I'm turning in for the night.", "en", ContextMode.SLEEPING)
    add("Bahut neend aa rahi hai, so jaana hai ab.", "hi", ContextMode.SLEEPING)
    add("थोड़ी देर में सो जाऊँगा, कॉल्स मत देना।", "hi", ContextMode.SLEEPING)
    add("Bistar pe ja raha hoon, kal baat karenge.", "hinglish", ContextMode.SLEEPING)
    add("It's late, I'm heading to bed now.", "en", ContextMode.SLEEPING)
    add("Aankh lag rahi hai, so raha hoon main.", "hi", ContextMode.SLEEPING)
    add("सोने का समय हो गया है, जगाना मत।", "hi", ContextMode.SLEEPING)
    add("Kaafi thak gaya hoon, sona hai ab.", "hinglish", ContextMode.SLEEPING)
    add("Dozing off now, catch you in the morning.", "en", ContextMode.SLEEPING)
    add("Raat ho gayi, main sone ja raha hoon.", "hinglish", ContextMode.SLEEPING)

    # BUSY
    add("I'm busy right now, take messages instead.", "en", ContextMode.BUSY)
    add("Main busy hoon abhi, message le lena.", "hi", ContextMode.BUSY)
    add("अभी व्यस्त हूँ, संदेश ले लेना।", "hi", ContextMode.BUSY)
    add("Kaafi busy hoon yaar, thodi der handle kar lo.", "hinglish", ContextMode.BUSY)
    add("Can't take calls, I'm swamped with work.", "en", ContextMode.BUSY)
    add("Busy.", "en", ContextMode.BUSY, notes="Short command form.")
    # v1.1 additions (dataset_version 2.1.0)
    add("Deep in work right now, hold my calls.", "en", ContextMode.BUSY)
    add("Kaam mein doob gaya hoon, baad mein baat karenge.", "hi", ContextMode.BUSY)
    add("अभी काम में उलझा हूँ, थोड़ी देर बाद।", "hi", ContextMode.BUSY)
    add("Bohot kaam pada hai aaj, busy rahunga.", "hinglish", ContextMode.BUSY)
    add("Slammed with deadlines today, take messages.", "en", ContextMode.BUSY)
    add("Office ka kaam nipta raha hoon, thodi der lagegi.", "hi", ContextMode.BUSY)
    add("व्यस्त हूँ अभी, ज़रा रुक कर बताना।", "hi", ContextMode.BUSY)
    add("Client call chal rahi hai, thodi der busy hoon.", "hinglish", ContextMode.BUSY)
    add("Can't talk now, elbow deep in paperwork.", "en", ContextMode.BUSY)
    add("Abhi hands full hain mere, message chhod dena.", "hinglish", ContextMode.BUSY)

    # MEETING
    add("I'm in a meeting, please hold all calls.", "en", ContextMode.MEETING)
    add("Meeting mein hoon, calls hold kar do.", "hi", ContextMode.MEETING)
    add("मीटिंग में हूँ, कॉल्स रोक कर रखो।", "hi", ContextMode.MEETING)
    add("Client ke saath meeting mein hoon abhi.", "hinglish", ContextMode.MEETING)
    add("Going into a board meeting for the next hour.", "en", ContextMode.MEETING)
    add("Ek ghante ke liye meeting mein ja raha hoon.", "hi", ContextMode.MEETING)
    # v1.1 additions (dataset_version 2.1.0)
    add("Stuck in back-to-back meetings all afternoon.", "en", ContextMode.MEETING)
    add("Review meeting chal rahi hai, hold karo calls.", "hi", ContextMode.MEETING)
    add("अभी कॉन्फ्रेंस कॉल पर हूँ, थोड़ी देर बाद।", "hi", ContextMode.MEETING)
    add("Client meeting mein hoon, phone silent pe hai.", "hinglish", ContextMode.MEETING)
    add("In a standup right now, back in 15.", "en", ContextMode.MEETING)
    add("Board room mein hoon, disturb mat karna.", "hi", ContextMode.MEETING)
    add("मीटिंग रूम में हूँ, बाद में कॉल करूँगा।", "hi", ContextMode.MEETING)
    add("Presentation de raha hoon abhi, busy hoon.", "hinglish", ContextMode.MEETING)
    add("On a video call with the whole team.", "en", ContextMode.MEETING)
    add("Discussion chal rahi hai important, hold karo.", "hinglish", ContextMode.MEETING)

    # TRAVELLING
    add("I'm travelling today, might not answer immediately.", "en", ContextMode.TRAVELLING)
    add("Safar mein hoon aaj, turant reply nahi kar paunga.", "hi", ContextMode.TRAVELLING)
    add("यात्रा पर हूँ आज, तुरंत जवाब नहीं दे पाऊँगा।", "hi", ContextMode.TRAVELLING)
    add("Flight mein hoon, thodi der out of reach rahunga.", "hinglish", ContextMode.TRAVELLING)
    add("On a road trip right now, spotty network.", "en", ContextMode.TRAVELLING)
    add("Train mein hoon, network thoda kharab hai.", "hi", ContextMode.TRAVELLING)
    # v1.1 additions (dataset_version 2.1.0)
    add("Boarding a flight shortly, might go quiet.", "en", ContextMode.TRAVELLING)
    add("Highway pe hoon, signal aata jaata rahega.", "hi", ContextMode.TRAVELLING)
    add("सड़क यात्रा पर हूँ, नेटवर्क कमज़ोर है।", "hi", ContextMode.TRAVELLING)
    add("Cab mein hoon airport ke liye, thodi der out.", "hinglish", ContextMode.TRAVELLING)
    add("On the metro right now, patchy signal.", "en", ContextMode.TRAVELLING)
    add("Bus mein hoon, kabhi kabhi call drop ho sakta hai.", "hi", ContextMode.TRAVELLING)
    add("हवाई अड्डे पर हूँ, उड़ान का इंतज़ार है।", "hi", ContextMode.TRAVELLING)
    add("Driving cross-country today, limited availability.", "en", ContextMode.TRAVELLING)
    add("Station pe hoon train pakadne, thoda busy rahunga.", "hinglish", ContextMode.TRAVELLING)
    add("जहाज़ पर सवार हूँ, नेटवर्क नहीं मिलेगा।", "hi", ContextMode.TRAVELLING)
    add("Long drive ahead, might not pick up quickly.", "en", ContextMode.TRAVELLING)
    add("Safar shuru ho gaya hai, thodi der baad baat karte hain.", "hinglish", ContextMode.TRAVELLING)

    # UNAVAILABLE
    add("I'm unavailable for the rest of the day.", "en", ContextMode.UNAVAILABLE)
    add("Aaj ke baaki din ke liye available nahi hoon.", "hi", ContextMode.UNAVAILABLE)
    add("आज बाकी दिन के लिए उपलब्ध नहीं हूँ।", "hi", ContextMode.UNAVAILABLE)
    add("Baaki din ke liye out of reach hoon main.", "hinglish", ContextMode.UNAVAILABLE)
    add("Not reachable until tomorrow morning.", "en", ContextMode.UNAVAILABLE)
    add("Kal subah tak available nahi rahunga.", "hi", ContextMode.UNAVAILABLE)
    # v1.1 additions (dataset_version 2.1.0)
    add("Off the grid for the next few hours.", "en", ContextMode.UNAVAILABLE)
    add("Aaj shaam tak available nahi ho paunga.", "hi", ContextMode.UNAVAILABLE)
    add("पूरे दिन के लिए संपर्क में नहीं रहूँगा।", "hi", ContextMode.UNAVAILABLE)
    add("Kal tak thoda unreachable rahunga, sorry.", "hinglish", ContextMode.UNAVAILABLE)
    add("Taking the day off from calls entirely.", "en", ContextMode.UNAVAILABLE)
    add("Abhi kisi se baat nahi kar sakta, sorry.", "hi", ContextMode.UNAVAILABLE)
    add("फ़िलहाल उपलब्ध नहीं हूँ, बाद में कोशिश करना।", "hi", ContextMode.UNAVAILABLE)
    add("Not picking up anything till further notice.", "en", ContextMode.UNAVAILABLE)
    add("Kuch ghanton ke liye contact mein nahi rahunga.", "hinglish", ContextMode.UNAVAILABLE)
    add("पूरी तरह अनुपलब्ध हूँ अभी, माफ़ करना।", "hi", ContextMode.UNAVAILABLE)
    add("Completely unreachable until this evening.", "en", ContextMode.UNAVAILABLE)
    add("Abhi ke liye sampark se bahar hoon main.", "hi", ContextMode.UNAVAILABLE)

    # CUSTOM
    add("I'm at a family function, only let urgent calls through.", "en", ContextMode.CUSTOM,
        notes="Custom context with an embedded urgency rule.")
    add("Ghar pe function chal raha hai, sirf zaroori calls hi.", "hi", ContextMode.CUSTOM)
    add("घर पर एक फंक्शन है, सिर्फ ज़रूरी कॉल्स ही लेना।", "hi", ContextMode.CUSTOM)
    add("Family function mein hoon, sirf zaroori calls lena.", "hinglish", ContextMode.CUSTOM)
    add("I'm in a movie theatre, only emergencies please.", "en", ContextMode.CUSTOM)
    add("Wedding mein hoon, sirf close family ke calls lena.", "hinglish", ContextMode.CUSTOM)
    # v1.1 additions (dataset_version 2.1.0)
    add("At the hospital with family, only emergencies please.", "en", ContextMode.CUSTOM)
    add("Interview de raha hoon, sirf zaroori calls lena.", "hinglish", ContextMode.CUSTOM)
    add("अस्पताल में हूँ, केवल आपातकालीन कॉल्स लेना।", "hi", ContextMode.CUSTOM)
    add("In court all day, nothing but urgent matters.", "en", ContextMode.CUSTOM)
    add("Puja chal rahi hai ghar mein, thoda time lagega.", "hi", ContextMode.CUSTOM)
    add("फ्लाइट पकड़नी है, सिर्फ ज़रूरी बात के लिए फोन करना।", "hi", ContextMode.CUSTOM)
    add("Exam de raha hoon, phone silent pe hai.", "hinglish", ContextMode.CUSTOM)
    add("At a religious ceremony, please only urgent calls.", "en", ContextMode.CUSTOM)
    add("Bachcha so raha hai, dheere se baat karna agar zaroori ho.", "hinglish", ContextMode.CUSTOM)
    add("मेहमान आए हुए हैं घर पर, सिर्फ खास बात के लिए।", "hi", ContextMode.CUSTOM)
    add("In a job interview right now, emergencies only.", "en", ContextMode.CUSTOM)
    add("Gym mein hoon workout pe, thodi der busy.", "hinglish", ContextMode.CUSTOM)

    # NORMAL (explicit SET, not a clear/reset)
    add("Set my status to normal please.", "en", ContextMode.NORMAL)
    add("Mujhe normal mode pe rakho abhi ke liye.", "hi", ContextMode.NORMAL)
    add("मुझे सामान्य मोड में रखो अभी के लिए।", "hi", ContextMode.NORMAL)
    add("Sab normal rakho, koi special mode nahi chahiye.", "hinglish", ContextMode.NORMAL)
    add("Keep everything as usual today.", "en", ContextMode.NORMAL)
    add("Aaj kuch special nahi, normal hi rakhna.", "hi", ContextMode.NORMAL)
    # v1.1 additions (dataset_version 2.1.0)
    add("Nothing special going on, keep it business as usual.", "en", ContextMode.NORMAL)
    add("Sab kuch normal hai aaj, koi special mode nahi.", "hi", ContextMode.NORMAL)

    # NORMAL / clearing
    add("I'm free now, back to normal.", "en", ContextMode.NORMAL, intent=Intent.CLEAR_CONTEXT,
        call_handling=False)
    add("Available again, you can stop filtering calls.", "en", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Meeting's done, switch me back to normal.", "en", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("I'm done travelling, back to usual now.", "en", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Clear my status, I'm around again.", "en", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Turn off do-not-disturb, I'm free.", "en", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Ab free hoon, normal mode pe le aao.", "hi", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Meeting khatam ho gayi, wapas normal kar do.", "hinglish", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Ab available hoon, normal pe kar do.", "hi", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("अब फ्री हूँ, सामान्य मोड में वापस ले आओ।", "hi", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("मीटिंग खत्म हो गई, वापस सामान्य कर दो।", "hi", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Free ho gaya hoon ab, normal pe le aao.", "hinglish", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("So ke uth gaya, ab normal mode kar do.", "hinglish", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Back to normal.", "en", ContextMode.NORMAL, intent=Intent.CLEAR_CONTEXT,
        call_handling=False)
    add("Normal pe wapas kar do sab.", "hi", ContextMode.NORMAL, intent=Intent.CLEAR_CONTEXT,
        call_handling=False)
    add("I'm free now.", "en", ContextMode.NORMAL, intent=Intent.CLEAR_CONTEXT,
        call_handling=False)
    add("Flight land ho gayi, ab normal kar do sab kuch.", "hinglish", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Function khatam ho gaya, ab sab normal.", "hi", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Done with the trip, switch everything back.", "en", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Wapas available hoon, normal kar do please.", "hi", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("The meeting wrapped up early, clear my status.", "en", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Neend poori ho gayi, ab calls le sakta hoon.", "hi", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Travelling khatam, ab reachable hoon phir se.", "hinglish", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Function se wapas aa gaya, normal kar do.", "hinglish", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("I'm reachable again, remove the do-not-disturb.", "en", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Sab kaam ho gaya, ab normal mode kar do.", "hi", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Back from the trip, clear the travelling status.", "en", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Available hoon ab, filtering band kar do.", "hi", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Everything's settled, put me back to normal.", "en", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    # v1.1 additions (dataset_version 2.1.0)
    add("Wapas apne regular schedule pe hoon ab.", "hi", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("All caught up now, treat calls normally again.", "en", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)
    add("Kaam khatam, ab normal tarike se calls lena.", "hinglish", ContextMode.NORMAL,
        intent=Intent.CLEAR_CONTEXT, call_handling=False)

    return ex


# ---------------------------------------------------------------------------
# Caller scenario examples
# ---------------------------------------------------------------------------

def build_call_scenario_examples() -> list[CallScenarioExample]:
    ex: list[CallScenarioExample] = []

    def add(desc, rel, language, intent, action, urgency, notes=None):
        ex.append(CallScenarioExample(
            caller_description=desc, caller_relationship=rel, language=language,
            expected_intent=intent, expected_action=action, urgency=urgency, notes=notes,
        ))

    # FAMILY
    add("Caller is saved as 'Mom' in contacts.", CallerRelationship.FAMILY, "en",
        Intent.KNOWN_CALLER, Action.ANSWER_CALL, "urgent",
        notes="Family calls default to higher priority even without explicit urgency words.")
    add("Number saved as 'Papa'.", CallerRelationship.FAMILY, "hi",
        Intent.KNOWN_CALLER, Action.ANSWER_CALL, "urgent")
    add("Caller is the user's sister, calling twice in a row.", CallerRelationship.FAMILY, "en",
        Intent.URGENT_CALL, Action.MARK_URGENT, "urgent",
        notes="Repeated calls from family is itself an urgency signal.")
    add("Chhoti behen ka call hai, contacts mein save hai.", CallerRelationship.FAMILY, "hi",
        Intent.KNOWN_CALLER, Action.ANSWER_CALL, "non_urgent")
    add("Caller is the user's grandmother, first call in weeks.", CallerRelationship.FAMILY,
        "en", Intent.KNOWN_CALLER, Action.ANSWER_CALL, "non_urgent")
    add("Mausi ka call hai, contacts mein saved hai.", CallerRelationship.FAMILY, "hi",
        Intent.KNOWN_CALLER, Action.ANSWER_CALL, "non_urgent")
    add("Caller is the user's spouse, calling from a new number.", CallerRelationship.FAMILY,
        "en", Intent.KNOWN_CALLER, Action.ANSWER_CALL, "urgent")
    add("Bade bhaiya ka phone hai, savings account ke baare mein.",
        CallerRelationship.FAMILY, "hi", Intent.KNOWN_CALLER, Action.ASK_CALLER_REASON,
        "non_urgent")
    add("Caller is the user's cousin, just wants to say hi.", CallerRelationship.FAMILY, "en",
        Intent.KNOWN_CALLER, Action.COLLECT_MESSAGE, "non_urgent")
    add("Nana ji ka call hai, unhone kai baar try kiya hai.", CallerRelationship.FAMILY, "hi",
        Intent.URGENT_CALL, Action.MARK_URGENT, "urgent")

    # FRIEND
    add("Caller saved as a close friend from college.", CallerRelationship.FRIEND, "en",
        Intent.KNOWN_CALLER, Action.ANSWER_CALL, "non_urgent")
    add("Dost ka number hai, contacts mein hai.", CallerRelationship.FRIEND, "hi",
        Intent.KNOWN_CALLER, Action.COLLECT_MESSAGE, "non_urgent")
    add("Friend calling to just chat casually.", CallerRelationship.FRIEND, "en",
        Intent.NON_URGENT_CALL, Action.COLLECT_MESSAGE, "non_urgent")
    add("College ka dost, weekend plan ke liye call kar raha hai.", CallerRelationship.FRIEND,
        "hinglish", Intent.NON_URGENT_CALL, Action.COLLECT_MESSAGE, "non_urgent")
    add("Friend calling repeatedly, says it's about a hospital visit.",
        CallerRelationship.FRIEND, "en", Intent.URGENT_CALL, Action.MARK_URGENT, "urgent")
    add("School ka purana dost hai, saalon baad call kiya.", CallerRelationship.FRIEND, "hi",
        Intent.KNOWN_CALLER, Action.COLLECT_MESSAGE, "non_urgent")
    add("Friend wants to know if the user is free this evening.",
        CallerRelationship.FRIEND, "en", Intent.KNOWN_CALLER, Action.ASK_CALLER_REASON,
        "non_urgent")
    add("Roommate hai, ghar ki chaabi ke baare mein poochh raha hai.",
        CallerRelationship.FRIEND, "hi", Intent.KNOWN_CALLER, Action.ASK_CALLER_REASON,
        "non_urgent")

    # COLLEAGUE
    add("Caller is a coworker asking about a work deadline.", CallerRelationship.COLLEAGUE, "en",
        Intent.KNOWN_CALLER, Action.ASK_CALLER_REASON, "non_urgent")
    add("Office colleague, project ke baare mein poochh raha hai.", CallerRelationship.COLLEAGUE,
        "hi", Intent.KNOWN_CALLER, Action.ASK_CALLER_REASON, "non_urgent")
    add("Manager calling about an urgent production issue.", CallerRelationship.COLLEAGUE, "en",
        Intent.URGENT_CALL, Action.MARK_URGENT, "urgent")
    add("Boss ka call hai, server down hone ke baare mein.", CallerRelationship.COLLEAGUE, "hi",
        Intent.URGENT_CALL, Action.MARK_URGENT, "urgent")
    add("Teammate calling just to sync on tomorrow's standup.",
        CallerRelationship.COLLEAGUE, "en", Intent.NON_URGENT_CALL, Action.COLLECT_MESSAGE,
        "non_urgent")
    add("HR ka call hai, offer letter ke baare mein.", CallerRelationship.COLLEAGUE, "hi",
        Intent.KNOWN_CALLER, Action.ASK_CALLER_REASON, "non_urgent")
    add("Intern calling to ask a quick clarification question.",
        CallerRelationship.COLLEAGUE, "en", Intent.KNOWN_CALLER, Action.ASK_CALLER_REASON,
        "non_urgent")

    # BUSINESS_CONTACT
    add("Caller is a known vendor confirming a delivery.", CallerRelationship.BUSINESS_CONTACT,
        "en", Intent.KNOWN_CALLER, Action.COLLECT_MESSAGE, "non_urgent")
    add("Bank relationship manager, account ke baare mein.", CallerRelationship.BUSINESS_CONTACT,
        "hi", Intent.KNOWN_CALLER, Action.ASK_CALLER_REASON, "non_urgent")
    add("Client calling about a signed contract, time-sensitive.", CallerRelationship.BUSINESS_CONTACT,
        "en", Intent.URGENT_CALL, Action.MARK_URGENT, "urgent")
    add("Insurance agent, policy renewal ke baare mein reminder.",
        CallerRelationship.BUSINESS_CONTACT, "hi", Intent.KNOWN_CALLER, Action.COLLECT_MESSAGE,
        "non_urgent")
    add("Known supplier calling to reschedule a delivery window.",
        CallerRelationship.BUSINESS_CONTACT, "en", Intent.KNOWN_CALLER,
        Action.ASK_CALLER_REASON, "non_urgent")
    add("CA ka call hai, tax filing deadline aane wali hai.",
        CallerRelationship.BUSINESS_CONTACT, "hi", Intent.URGENT_CALL, Action.MARK_URGENT,
        "urgent")

    # UNKNOWN
    add("Number not saved in contacts, no prior history.", CallerRelationship.UNKNOWN, "en",
        Intent.UNKNOWN_CALLER, Action.ASK_CALLER_REASON, "non_urgent")
    add("Anjaan number hai, pehle kabhi call nahi aaya.", CallerRelationship.UNKNOWN, "hi",
        Intent.UNKNOWN_CALLER, Action.ASK_CALLER_REASON, "non_urgent")
    add("Unknown number, caller says it's about a delivery.", CallerRelationship.UNKNOWN, "en",
        Intent.UNKNOWN_CALLER, Action.ASK_CALLER_REASON, "non_urgent")
    add("Unknown caller repeatedly calling within a few minutes.", CallerRelationship.UNKNOWN,
        "en", Intent.URGENT_CALL, Action.MARK_URGENT, "urgent",
        notes="Unrecognized caller can still be urgent if the pattern suggests it.")
    add("Anjaan number hai, meeting ke baare mein pooch raha hai.", CallerRelationship.UNKNOWN,
        "hi", Intent.UNKNOWN_CALLER, Action.ASK_CALLER_REASON, "non_urgent",
        notes="Hard negative: mentions 'meeting' but the caller-identity signal dominates.")
    add("Unrecognized number, no caller ID, silent for a few seconds then hangs up.",
        CallerRelationship.UNKNOWN, "en", Intent.UNKNOWN_CALLER, Action.ASK_CALLER_REASON,
        "non_urgent")

    # SPAM_SUSPICIOUS
    add("Caller claims to be from a bank asking for OTP.", CallerRelationship.SPAM_SUSPICIOUS,
        "en", Intent.UNKNOWN_CALLER, Action.END_CALL, "non_urgent",
        notes="Never disclose OTP/credentials - end call rather than engage.")
    add("Robotic voice offering a loan, unknown number.", CallerRelationship.SPAM_SUSPICIOUS,
        "en", Intent.UNKNOWN_CALLER, Action.END_CALL, "non_urgent")
    add("Number pichhle hafte kai baar spam call kar chuka hai.", CallerRelationship.SPAM_SUSPICIOUS,
        "hi", Intent.UNKNOWN_CALLER, Action.END_CALL, "non_urgent")
    add("Caller impersonating tech support, asking for remote access.",
        CallerRelationship.SPAM_SUSPICIOUS, "en", Intent.UNKNOWN_CALLER, Action.END_CALL,
        "non_urgent")
    add("Lottery jeetne ka jhoothaa call, paise maang raha hai.",
        CallerRelationship.SPAM_SUSPICIOUS, "hi", Intent.UNKNOWN_CALLER, Action.END_CALL,
        "non_urgent")
    add("Automated survey call with no option to opt out.",
        CallerRelationship.SPAM_SUSPICIOUS, "en", Intent.UNKNOWN_CALLER, Action.END_CALL,
        "non_urgent")

    # Additional variety across relationships (broadens coverage beyond the
    # per-relationship blocks above without changing any existing example).
    add("Caller is the user's father-in-law, calling about a family event.",
        CallerRelationship.FAMILY, "en", Intent.KNOWN_CALLER, Action.ASK_CALLER_REASON,
        "non_urgent")
    add("Chachi ka call hai, ghar ke function ke baare mein.", CallerRelationship.FAMILY,
        "hi", Intent.KNOWN_CALLER, Action.ASK_CALLER_REASON, "non_urgent")
    add("Caller is the user's nephew, wants to say hi before school.",
        CallerRelationship.FAMILY, "en", Intent.KNOWN_CALLER, Action.COLLECT_MESSAGE,
        "non_urgent")
    add("Caller is a childhood friend visiting the city this weekend.",
        CallerRelationship.FRIEND, "en", Intent.SCHEDULE_REQUEST, Action.COLLECT_MESSAGE,
        "non_urgent")
    add("Gym ka dost hai, kal ke session ke baare mein poochh raha hai.",
        CallerRelationship.FRIEND, "hi", Intent.SCHEDULE_REQUEST, Action.COLLECT_MESSAGE,
        "non_urgent")
    add("Caller is a friend who wants to cancel weekend plans.",
        CallerRelationship.FRIEND, "en", Intent.CANCEL_REQUEST, Action.NO_ACTION,
        "non_urgent")
    add("Team lead calling to ask if the user can join a call now.",
        CallerRelationship.COLLEAGUE, "en", Intent.SCHEDULE_REQUEST, Action.COLLECT_MESSAGE,
        "non_urgent")
    add("Colleague ne wo review meeting cancel karne ko kaha hai.",
        CallerRelationship.COLLEAGUE, "hi", Intent.CANCEL_REQUEST, Action.NO_ACTION,
        "non_urgent")
    add("Junior colleague asking for a quick status update, nothing urgent.",
        CallerRelationship.COLLEAGUE, "en", Intent.NON_URGENT_CALL, Action.COLLECT_MESSAGE,
        "non_urgent")
    add("Recruiter calling about a new job opportunity.",
        CallerRelationship.BUSINESS_CONTACT, "en", Intent.KNOWN_CALLER,
        Action.ASK_CALLER_REASON, "non_urgent")
    add("Property dealer ka call hai, rent renewal ke baare mein.",
        CallerRelationship.BUSINESS_CONTACT, "hi", Intent.KNOWN_CALLER,
        Action.ASK_CALLER_REASON, "non_urgent")
    add("Known contractor calling to confirm tomorrow's site visit.",
        CallerRelationship.BUSINESS_CONTACT, "en", Intent.SCHEDULE_REQUEST,
        Action.COLLECT_MESSAGE, "non_urgent")
    add("Unknown number asking to reschedule a delivery for next week.",
        CallerRelationship.UNKNOWN, "en", Intent.SCHEDULE_REQUEST, Action.COLLECT_MESSAGE,
        "non_urgent")
    add("Anjaan number se ek baar call aaya aur turant kaat diya.",
        CallerRelationship.UNKNOWN, "hi", Intent.UNKNOWN_CALLER, Action.ASK_CALLER_REASON,
        "non_urgent")
    add("Caller asking for a summary of the last few missed calls.",
        CallerRelationship.UNKNOWN, "en", Intent.SUMMARIZE_CONVERSATION,
        Action.CREATE_SUMMARY, "non_urgent")
    add("Prerecorded voice demanding immediate payment to avoid arrest, classic scam.",
        CallerRelationship.SPAM_SUSPICIOUS, "en", Intent.UNKNOWN_CALLER, Action.END_CALL,
        "urgent", notes="Scam urgency pressure - still resolves to END_CALL, not MARK_URGENT.")
    add("Fake courier call asking for a customs fee payment over the phone.",
        CallerRelationship.SPAM_SUSPICIOUS, "en", Intent.UNKNOWN_CALLER, Action.END_CALL,
        "non_urgent")
    add("Naya number hai, khud ko relative bata raha hai lekin details match nahi kar rahi.",
        CallerRelationship.SPAM_SUSPICIOUS, "hi", Intent.UNKNOWN_CALLER, Action.END_CALL,
        "non_urgent",
        notes="Claims a family relationship but is unverifiable/suspicious - resolves as spam, not KNOWN_CALLER.")
    add("Caller wants the assistant to stop screening calls for the rest of the day.",
        CallerRelationship.UNKNOWN, "en", Intent.HANDLE_CALLS, Action.DISABLE_CALL_ASSISTANT,
        "non_urgent")
    add("User ne khud call kiya hai assistant ko calls sambhalne ke liye.",
        CallerRelationship.UNKNOWN, "hi", Intent.HANDLE_CALLS, Action.ENABLE_CALL_ASSISTANT,
        "non_urgent")

    return ex


# ---------------------------------------------------------------------------
# Conversation examples (single-turn caller <-> WOW exchanges)
# ---------------------------------------------------------------------------

def build_conversation_examples() -> list[ConversationExample]:
    ex: list[ConversationExample] = []

    def add(caller_msg, wow_resp, ctx, rel, language, intent, action, outcome):
        ex.append(ConversationExample(
            caller_message=caller_msg, wow_response=wow_resp, context_mode=ctx,
            caller_relationship=rel, language=language, expected_intent=intent,
            expected_action=action, expected_outcome=outcome,
        ))

    add(
        "Hi, is he around? It's urgent.",
        "He's asleep right now, but this sounds important - can I take a message and flag it as urgent for when he wakes up?",
        ContextMode.SLEEPING, CallerRelationship.COLLEAGUE, "en",
        Intent.URGENT_CALL, Action.MARK_URGENT,
        "Message collected and marked urgent; user notified immediately despite sleeping context.",
    )
    add(
        "Bhai bata do usse ki kal wala plan cancel ho gaya.",
        "Theek hai, main unhe bata dunga jab woh available honge. Aapka number save kar loon?",
        ContextMode.BUSY, CallerRelationship.FRIEND, "hinglish",
        Intent.MESSAGE_FOR_USER, Action.COLLECT_MESSAGE,
        "Non-urgent message collected for later delivery.",
    )
    add(
        "This is the bank, we need to verify your OTP.",
        "I'm not able to share or verify any OTP over a call. I'll let them know you called.",
        ContextMode.NORMAL, CallerRelationship.SPAM_SUSPICIOUS, "en",
        Intent.UNKNOWN_CALLER, Action.END_CALL,
        "Call ended without disclosing any credential; flagged as suspicious for user review.",
    )
    add(
        "Mummy hoon beta, jaldi call karo mujhe.",
        "Aap so rahe the, lekin family ka call hai isliye main abhi unhe jagata hoon.",
        ContextMode.SLEEPING, CallerRelationship.FAMILY, "hi",
        Intent.KNOWN_CALLER, Action.TRANSFER_CALL,
        "Family caller during sleeping context triggers a transfer/wake-up per user's standing preference.",
    )
    add(
        "Hey, are you free for a call in 10 minutes?",
        "He's in a meeting right now. I'll pass along that you'd like a callback in 10 minutes.",
        ContextMode.MEETING, CallerRelationship.FRIEND, "en",
        Intent.SCHEDULE_REQUEST, Action.COLLECT_MESSAGE,
        "Callback request logged for after the meeting.",
    )
    add(
        "Client yahan hai, contract sign karna hai aaj hi.",
        "Yeh time-sensitive lag raha hai, main isse urgent mark karke unhe turant batata hoon.",
        ContextMode.MEETING, CallerRelationship.BUSINESS_CONTACT, "hi",
        Intent.URGENT_CALL, Action.MARK_URGENT,
        "Marked urgent and surfaced despite the active meeting context.",
    )
    add(
        "Can you connect me directly, it's about a family emergency?",
        "Of course, connecting you right now.",
        ContextMode.TRAVELLING, CallerRelationship.FAMILY, "en",
        Intent.TRANSFER_TO_USER, Action.TRANSFER_CALL,
        "Immediate transfer to the user given the stated emergency.",
    )
    add(
        "Bas hi bolne ke liye call kiya tha, kaise ho?",
        "Woh abhi thoda busy hain, lekin main bata dunga ki aapne call kiya tha.",
        ContextMode.BUSY, CallerRelationship.FRIEND, "hinglish",
        Intent.NON_URGENT_CALL, Action.COLLECT_MESSAGE,
        "Logged as a casual, non-urgent call.",
    )
    add(
        "This is a courier company, need address confirmation.",
        "I can note that down and pass it along - what's the confirmation you need?",
        ContextMode.UNAVAILABLE, CallerRelationship.UNKNOWN, "en",
        Intent.UNKNOWN_CALLER, Action.ASK_CALLER_REASON,
        "Reason for calling requested before deciding how to proceed.",
    )
    add(
        "Office se call hai, server down hai turant chahiye unko.",
        "Yeh production issue lag raha hai, main abhi unhe alert karta hoon.",
        ContextMode.SLEEPING, CallerRelationship.COLLEAGUE, "hi",
        Intent.URGENT_CALL, Action.MARK_URGENT,
        "Work emergency overrides sleeping context per urgency rules.",
    )
    add(
        "Just wanted to say happy birthday!",
        "That's sweet, I'll let them know you called to wish them.",
        ContextMode.NORMAL, CallerRelationship.FRIEND, "en",
        Intent.GENERAL_CONVERSATION, Action.NO_ACTION,
        "Logged as a routine, non-actionable call.",
    )
    add(
        "Aap kaun ho? Yeh number kiska hai?",
        "Main inka call assistant hoon. Aap kisse baat karna chahte hain?",
        ContextMode.CUSTOM, CallerRelationship.UNKNOWN, "hi",
        Intent.UNKNOWN_CALLER, Action.ASK_CALLER_REASON,
        "Unknown caller asked to clarify purpose before proceeding.",
    )
    add(
        "Can we reschedule tomorrow's appointment to next week?",
        "Sure, I'll note the reschedule request and confirm with them shortly.",
        ContextMode.NORMAL, CallerRelationship.BUSINESS_CONTACT, "en",
        Intent.SCHEDULE_REQUEST, Action.COLLECT_MESSAGE,
        "Reschedule request captured for confirmation.",
    )
    add(
        "Woh appointment cancel kar do jo maine book kiya tha.",
        "Theek hai, cancel request note kar li hai, confirm ho jayega jald hi.",
        ContextMode.NORMAL, CallerRelationship.BUSINESS_CONTACT, "hi",
        Intent.CANCEL_REQUEST, Action.NO_ACTION,
        "Cancellation logged for follow-up confirmation.",
    )
    add(
        "Give me a quick summary of what happened while I was out.",
        "You had two calls - one from your brother marked urgent, and one from a client about rescheduling.",
        ContextMode.TRAVELLING, CallerRelationship.UNKNOWN, "en",
        Intent.SUMMARIZE_CONVERSATION, Action.CREATE_SUMMARY,
        "Summary of missed interactions generated on request.",
    )
    add(
        "Robotic caller offering a fake loan approval.",
        "I'm not able to proceed with this, ending the call now.",
        ContextMode.NORMAL, CallerRelationship.SPAM_SUSPICIOUS, "en",
        Intent.UNKNOWN_CALLER, Action.END_CALL,
        "Suspicious spam call ended without engagement.",
    )
    add(
        "Theek hai bas itna hi tha, thanks bhai bye.",
        "Bilkul, dhanyavaad! Bye.",
        ContextMode.NORMAL, CallerRelationship.FRIEND, "hinglish",
        Intent.END_CONVERSATION, Action.END_CALL,
        "Call wrapped up cleanly.",
    )
    add(
        "Family function mein hoon, sirf zaroori calls lena.",
        "Samajh gaya, sirf urgent calls hi through karunga baaki sab message le lunga.",
        ContextMode.CUSTOM, CallerRelationship.FAMILY, "hinglish",
        Intent.SET_CONTEXT, Action.SET_CONTEXT,
        "Custom context established with an urgency-only filtering rule.",
    )
    add(
        "Hey it's me, I landed, can you tell them I'm on my way?",
        "Got it, I'll let them know you've landed and are heading over.",
        ContextMode.MEETING, CallerRelationship.FAMILY, "en",
        Intent.MESSAGE_FOR_USER, Action.COLLECT_MESSAGE,
        "Simple status update logged as a message.",
    )
    add(
        "Doctor se appointment ke baare mein baat karni thi.",
        "Zaroor, main note kar leta hoon aur unhe bata dunga.",
        ContextMode.BUSY, CallerRelationship.BUSINESS_CONTACT, "hi",
        Intent.SCHEDULE_REQUEST, Action.COLLECT_MESSAGE,
        "Appointment-related request logged for follow-up.",
    )
    add(
        "I need to speak to him right now, no messages, connect me.",
        "Understood, connecting you directly right now.",
        ContextMode.BUSY, CallerRelationship.FAMILY, "en",
        Intent.TRANSFER_TO_USER, Action.TRANSFER_CALL,
        "Explicit transfer request honored immediately.",
    )
    add(
        "By the way, just so it's on file, I moved to a new flat last week.",
        "Got it, I'll make a note of your new address for the future.",
        ContextMode.NORMAL, CallerRelationship.FRIEND, "en",
        Intent.GENERAL_CONVERSATION, Action.SAVE_MEMORY,
        "Durable fact saved to memory for future reference.",
    )
    add(
        "Woh, main so raha hoon kya yeh poochne ke liye call kiya tha ki Aniket so rahe hain kya.",
        "Woh abhi so rahe hain, main unhe bata dunga ki aapne poochha tha.",
        ContextMode.SLEEPING, CallerRelationship.FRIEND, "hinglish",
        Intent.GENERAL_CONVERSATION, Action.NO_ACTION,
        "Hard negative: caller is asking ABOUT the user's sleeping status, not "
        "declaring their own context - must not be misread as SET_CONTEXT.",
    )
    add(
        "Not urgent at all, the meeting thing got sorted on its own.",
        "Good to hear, I'll just note that down, no action needed.",
        ContextMode.NORMAL, CallerRelationship.COLLEAGUE, "en",
        Intent.NON_URGENT_CALL, Action.COLLECT_MESSAGE,
        "Hard negative: mentions both 'urgent' and 'meeting' but both are "
        "explicitly resolved/negated - correctly logged as non-urgent.",
    )
    add(
        "Ek unknown number se call aaya, meeting time confirm karna chahta tha.",
        "Theek hai, main pehle unse call karne ki wajah poochta hoon.",
        ContextMode.NORMAL, CallerRelationship.UNKNOWN, "hi",
        Intent.UNKNOWN_CALLER, Action.ASK_CALLER_REASON,
        "Hard negative: mentions 'meeting' but caller-identity (unknown) is the "
        "decision-relevant signal.",
    )
    add(
        "Not busy anymore, that call earlier got cancelled, you can clear my status.",
        "Sure, clearing your status back to normal now.",
        ContextMode.BUSY, CallerRelationship.FRIEND, "en",
        Intent.CLEAR_CONTEXT, Action.CLEAR_CONTEXT,
        "Hard negative: contains 'busy' but negated - resolves to CLEAR_CONTEXT, "
        "not SET_CONTEXT/BUSY.",
    )
    add(
        "Wahi purana number hai jo baar baar spam call karta hai, ignore kar do.",
        "Samajh gaya, main is call ko yahin khatam karta hoon.",
        ContextMode.NORMAL, CallerRelationship.SPAM_SUSPICIOUS, "hinglish",
        Intent.UNKNOWN_CALLER, Action.END_CALL,
        "Repeat spam caller ended without engagement.",
    )
    add(
        "Turant nahi chahiye jawab, jab time mile tab reply kar dena.",
        "Theek hai, main note kar leta hoon, koi jaldi nahi hai.",
        ContextMode.NORMAL, CallerRelationship.COLLEAGUE, "hinglish",
        Intent.NON_URGENT_CALL, Action.COLLECT_MESSAGE,
        "Explicitly non-urgent request logged for later.",
    )
    add(
        "Can you check what mode he's in right now? I don't want to disturb him.",
        "He's currently set to busy - I can take a message instead.",
        ContextMode.BUSY, CallerRelationship.FRIEND, "en",
        Intent.GET_CONTEXT, Action.NO_ACTION,
        "Caller's question about status answered without disturbing the user.",
    )
    add(
        "Uska naya number yeh hai, purana wala band ho gaya, yaad rakhna.",
        "Theek hai, naya number note kar liya hai future ke liye.",
        ContextMode.NORMAL, CallerRelationship.FAMILY, "hi",
        Intent.GENERAL_CONVERSATION, Action.SAVE_MEMORY,
        "Updated contact detail saved to memory.",
    )
    add(
        "Please cancel the callback we set up for tomorrow, plans changed.",
        "Done, I've cancelled tomorrow's callback.",
        ContextMode.NORMAL, CallerRelationship.BUSINESS_CONTACT, "en",
        Intent.CANCEL_REQUEST, Action.NO_ACTION,
        "Previously scheduled callback cancelled on request.",
    )
    add(
        "Kal subah 9 baje ek call rakh do doctor ke office se baat karne ke liye.",
        "Theek hai, kal subah 9 baje ka slot note kar liya hai.",
        ContextMode.NORMAL, CallerRelationship.BUSINESS_CONTACT, "hi",
        Intent.SCHEDULE_REQUEST, Action.COLLECT_MESSAGE,
        "Callback request scheduled for tomorrow morning.",
    )
    add(
        "You can stop handling my calls now, I'm free for the rest of the day.",
        "Got it, switching off call handling now.",
        ContextMode.NORMAL, CallerRelationship.UNKNOWN, "en",
        Intent.HANDLE_CALLS, Action.DISABLE_CALL_ASSISTANT,
        "Call-handling automation disabled per the user's own instruction.",
    )
    add(
        "Mere calls thodi der ke liye sambhal lo, main meeting mein jaa raha hoon.",
        "Theek hai, main aapke calls sambhal leta hoon jab tak aap meeting mein hain.",
        ContextMode.MEETING, CallerRelationship.UNKNOWN, "hi",
        Intent.HANDLE_CALLS, Action.ENABLE_CALL_ASSISTANT,
        "Call-handling automation enabled ahead of the meeting.",
    )
    add(
        "He's not actually busy, that call earlier finished quickly, put this one through.",
        "Understood, connecting you directly since he's free now.",
        ContextMode.BUSY, CallerRelationship.COLLEAGUE, "en",
        Intent.TRANSFER_TO_USER, Action.TRANSFER_CALL,
        "Hard negative: contains 'busy' but negated - correctly resolves to a direct transfer.",
    )
    add(
        "Isse pehle bhi teen baar spam call aa chuka hai isi number se.",
        "Samajh gaya, main is call ko yahin end kar deta hoon.",
        ContextMode.NORMAL, CallerRelationship.SPAM_SUSPICIOUS, "hi",
        Intent.UNKNOWN_CALLER, Action.END_CALL,
        "Repeat spam pattern recognized and call ended.",
    )
    add(
        "Give me the highlights of everything that came in since this morning.",
        "Sure - two calls, one marked urgent from a colleague, one casual check-in from a friend.",
        ContextMode.MEETING, CallerRelationship.UNKNOWN, "en",
        Intent.SUMMARIZE_CONVERSATION, Action.CREATE_SUMMARY,
        "Requested recap generated from the day's call log.",
    )

    return ex


# ---------------------------------------------------------------------------
# Summary examples
# ---------------------------------------------------------------------------

def build_summary_examples() -> list[SummaryExample]:
    ex: list[SummaryExample] = []

    def add(transcript, reason, facts, requested_action, urgency, summary, language):
        ex.append(SummaryExample(
            transcript=transcript, reason_for_call=reason, important_facts=facts,
            requested_action=requested_action, urgency=urgency, summary=summary,
            language=language,
        ))

    add(
        "Caller: Hi, is he there? WOW: He's asleep right now, can I help? "
        "Caller: It's urgent, my car broke down and I need him to pick me up. WOW: I'll wake him and let him know right away.",
        "Caller's car broke down and needs a pickup.",
        ["Caller's car broke down.", "Caller needs an immediate pickup."],
        "Wake the user and relay the pickup request.",
        "urgent",
        "Brother's car broke down and he needs an urgent pickup - flagged for immediate attention.",
        "en",
    )
    add(
        "Caller: Namaste, main office se bol raha hoon. WOW: Ji boliye. "
        "Caller: Kal ki meeting 3 baje se 5 baje kar di gayi hai, unhe bata dijiyega.",
        "Office colleague informing about a meeting time change.",
        ["Tomorrow's meeting moved from 3pm to 5pm."],
        "Inform the user of the new meeting time.",
        "non_urgent",
        "Colleague moved tomorrow's meeting from 3pm to 5pm - no action needed beyond passing along.",
        "hi",
    )
    add(
        "Caller: This is the bank, we need your OTP to verify a transaction. WOW: I can't share any OTP over a call. "
        "Caller: It's urgent, please. WOW: I still can't disclose it, ending the call now.",
        "Caller requested OTP disclosure, refused and call ended.",
        ["Caller requested an OTP.", "No credentials were disclosed."],
        "Flag as suspicious for the user's review; no credential was shared.",
        "urgent",
        "Suspicious caller attempted to extract an OTP under urgency pressure - refused and call ended; flagged for review.",
        "en",
    )
    add(
        "Caller: Beta, kal shaadi ki taiyaari mein help chahiye. WOW: Zaroor, main bata dunga. "
        "Caller: Subah 9 baje aana bol dena.",
        "Family member requesting help with wedding preparations.",
        ["Help needed for wedding preparations.", "Requested arrival time: 9am tomorrow."],
        "Inform the user to arrive at 9am tomorrow to help.",
        "non_urgent",
        "Family member asked for help with wedding preparations tomorrow at 9am.",
        "hi",
    )
    add(
        "Caller: Hey, just checking in, no need to call back unless you want to. WOW: Got it, I'll pass that along.",
        "Friend checking in casually.",
        ["No action requested."],
        "None - informational only.",
        "non_urgent",
        "Friend called just to check in - no action needed.",
        "en",
    )
    add(
        "Caller: Delivery company here, aapka parcel deliver nahi ho paya, address confirm karna hai. "
        "WOW: Address kya hona chahiye bataiye, main note kar leta hoon.",
        "Courier needs address confirmation for a failed delivery.",
        ["Delivery attempt failed.", "Address confirmation required."],
        "Confirm delivery address with the courier or user.",
        "non_urgent",
        "Courier could not deliver a parcel and needs address confirmation.",
        "hi",
    )
    add(
        "Caller: Production is down, we need him on a call immediately! WOW: This sounds critical, connecting you to him right now.",
        "Colleague reporting a critical production outage.",
        ["Production system is down.", "Immediate response required."],
        "Connect the caller to the user immediately.",
        "urgent",
        "Critical production outage reported - caller connected to the user immediately.",
        "en",
    )
    add(
        "Caller: Bhai, weekend trip ka plan finalize karna hai, jab time mile batana. WOW: Theek hai, note kar liya, woh aapko contact karenge.",
        "Friend wants to finalize weekend trip plans.",
        ["Weekend trip plan needs finalizing."],
        "User to contact caller to finalize the plan.",
        "non_urgent",
        "Friend wants to finalize weekend trip plans - no urgency, message noted.",
        "hinglish",
    )
    add(
        "Caller: Client here, contract needs signature today or the deal falls through. WOW: This is time-sensitive, I'm flagging it urgent and notifying them now.",
        "Client needs contract signed today or the deal is lost.",
        ["Contract must be signed today.", "Deal at risk if delayed."],
        "Notify user urgently to review and sign the contract today.",
        "urgent",
        "Client's contract needs same-day signature or the deal is lost - marked urgent.",
        "en",
    )
    add(
        "Caller: Sirf hi bolne ke liye call kiya tha, kuch zaroori nahi hai. WOW: Bahut badhiya, main unhe bata dunga.",
        "Friend called just to say hi.",
        [],
        "None - informational only.",
        "non_urgent",
        "Friend called just to say hello - nothing actionable.",
        "hi",
    )
    add(
        "Caller: This is the doctor's office, your appointment tomorrow is confirmed for 10am. WOW: Got it, I'll make sure they see this.",
        "Doctor's office confirming an appointment time.",
        ["Appointment confirmed for tomorrow 10am."],
        "Inform the user of the confirmed appointment time.",
        "non_urgent",
        "Doctor's office confirmed tomorrow's appointment for 10am.",
        "en",
    )
    add(
        "Caller: Number galat lag gaya shayad, sorry. WOW: Koi baat nahi, dhyan rakhiyega.",
        "Caller reached the wrong number.",
        ["Wrong number - no relevant content."],
        "None.",
        "non_urgent",
        "Wrong-number call, nothing actionable.",
        "hi",
    )
    add(
        "Caller: Bank yahan se, aapke card mein suspicious activity dikh rahi hai, PIN confirm kariye. "
        "WOW: Main PIN kabhi confirm nahi karunga, main yeh call yahin khatam kar raha hoon.",
        "Caller impersonating a bank, requesting PIN.",
        ["Caller requested card PIN.", "No credentials disclosed."],
        "Flag as suspicious for user review; end call.",
        "urgent",
        "Suspected bank-impersonation scam attempting to extract a card PIN - refused and ended, flagged for review.",
        "hi",
    )
    add(
        "Caller: Hi, just confirming I'll see you at the event Saturday. WOW: Noted, I'll let them know.",
        "Friend confirming attendance at a Saturday event.",
        ["Event attendance confirmed for Saturday."],
        "Inform the user of the confirmed attendance.",
        "non_urgent",
        "Friend confirmed they'll attend Saturday's event.",
        "en",
    )
    add(
        "Caller: Zaroori kaam hai office ka, turant call chahiye. WOW: Samajh gaya, main unhe abhi connect karta hoon.",
        "Office colleague needs an immediate call for urgent work.",
        ["Urgent office work requires immediate call."],
        "Connect the caller to the user immediately.",
        "urgent",
        "Colleague needs an urgent work call - connected immediately.",
        "hi",
    )
    add(
        "Caller: By the way, just so you know, I moved to a new city last month, update your records. "
        "WOW: Noted, I'll save that for future reference.",
        "Caller sharing an updated personal detail for the record.",
        ["Caller moved to a new city last month."],
        "Save the updated detail to memory; no urgent action needed.",
        "non_urgent",
        "Caller shared an address update to be remembered for future interactions.",
        "en",
    )

    return ex


def _write_jsonl(path: Path, examples: list) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in examples:
            f.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False) + "\n")
    return len(examples)


def main() -> None:
    intents = build_intent_examples()
    contexts = build_context_examples()
    scenarios = build_call_scenario_examples()
    conversations = build_conversation_examples()
    summaries = build_summary_examples()

    counts = {
        "intents": _write_jsonl(DATASETS_DIR / "intents" / "seed.jsonl", intents),
        "contexts": _write_jsonl(DATASETS_DIR / "contexts" / "seed.jsonl", contexts),
        "call_scenarios": _write_jsonl(DATASETS_DIR / "call_scenarios" / "seed.jsonl", scenarios),
        "conversations": _write_jsonl(DATASETS_DIR / "conversations" / "seed.jsonl", conversations),
        "summaries": _write_jsonl(DATASETS_DIR / "summaries" / "seed.jsonl", summaries),
    }
    total = sum(counts.values())

    languages = sorted({"en", "hi", "hinglish"})
    metadata = {
        "dataset_version": "2.1.0",
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "num_examples": total,
        "counts_by_category": counts,
        "languages": languages,
        "categories": list(counts.keys()),
        "source_type": "synthetic_hand_authored",
        "validation_status": "unvalidated",
        "notes": (
            "v2.1.0 (WOW Brain v1.1 training data) - targeted expansion of "
            "v2.0.0 (WOW Brain v1's dataset, frozen at "
            "training/datasets/versions/v2.0.0/), which is unchanged and was "
            "not overwritten. Adds UNKNOWN coverage (v1's weakest per-intent "
            "accuracy at 20%), context-mode coverage across all 7 modes "
            "(context accuracy was v1's weakest head at 50%), and 25 more "
            "hard negatives. v2.0.0 in turn expanded the v0/dataset_version "
            "1.0.0 seed (~117 examples) to fix the SET_CONTEXT/BUSY "
            "majority-class mode collapse documented in docs/TRAINING.md. "
            "No real user/production conversation data is included."
        ),
    }
    (DATASETS_DIR / "DATASET_METADATA.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Wrote {total} examples across {len(counts)} categories:")
    for k, v in counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
