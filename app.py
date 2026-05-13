import os
import tempfile
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, FileResponse, Response, JSONResponse
import uvicorn
from groq import Groq
import edge_tts
from urllib.parse import quote
from twilio.twiml.voice_response import VoiceResponse, Gather

# ── Config ──
api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else Groq()
app = FastAPI()

# ── Mock Data ──
TARIFF_DATA = """
PINIFIED — TARIFF CARD (per shipment):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Route                    | Standard | Express
Delhi → Mumbai           | ₹850     | ₹1,400
Mumbai → Bangalore       | ₹920     | ₹1,550
Delhi → Kolkata          | ₹780     | ₹1,300
Hyderabad → Chennai      | ₹650     | ₹1,100
Pan-India (Avg per Kg)   | ₹45/kg   | ₹72/kg
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Surcharges: Fuel +8%, Sunday/Holiday +15%, Fragile +₹200 flat.
Free pickup for orders above ₹2,000.
"""

BOOKING_DATA = """
RECENT BOOKINGS DATABASE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Booking MJK-10234:
  Route: Delhi → Mumbai | Status: In Transit
  Picked: May 10 | ETA: May 13
  Driver: Rajesh K. | Vehicle: MH-04-AB-1234
  Last Location: Jaipur Highway Toll, 340km remaining

Booking MJK-10235:
  Route: Mumbai → Bangalore | Status: Delivered
  Delivered: May 11, 2:30 PM
  Signed by: Warehouse Manager — Priya S.

Booking MJK-10236:
  Route: Hyderabad → Chennai | Status: Pickup Scheduled
  Pickup Date: May 13, 10:00 AM
  Driver: Suresh M. | Vehicle: TN-07-CD-5678

Booking MJK-10237:
  Route: Delhi → Kolkata | Status: Out for Delivery
  ETA: Today by 6 PM
  Driver: Amit P. | Vehicle: WB-02-EF-9012
  Last Location: Durgapur, 180km remaining
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

SYSTEM_PROMPT = f"""You are the AI voice assistant for **Pinified** — an Uber-for-logistics company that provides on-demand trucking and delivery services across India.

Your name is "Pinified Assistant". You are friendly, professional, and concise. Your answers will be spoken aloud, so keep them natural and conversational (2-3 sentences max).

You can help callers with:
1. **Tariff / Pricing** — quote rates for routes, explain surcharges.
2. **Booking Status** — look up bookings by ID (MJK-XXXXX) and give status updates.
3. **General Queries** — pickup scheduling, service areas, delivery timelines.

Here is the current tariff data:
{TARIFF_DATA}

Here is the current bookings database:
{BOOKING_DATA}

Rules:
- If the user asks about a booking, look it up from the data above and give a clear status update.
- If the user asks about tariff/pricing, quote from the tariff card.
- If you don't have info, politely say you'll connect them to a human agent.
- Always be brief — this is a phone-style voice conversation.
- Start by greeting and asking how you can help if the conversation just started.
"""

# ── Conversation History ──
chat_history = [{"role": "system", "content": SYSTEM_PROMPT}]

# ── Per-call sessions for phone (keyed by Twilio CallSid) ──
call_sessions = {}

# ── Helpers ──
def cleanup_files(*file_paths):
    for path in file_paths:
        if path and os.path.exists(path):
            try: os.remove(path)
            except: pass

TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"

# ── Routes ──
@app.get("/")
async def get_index():
    html = TEMPLATE_PATH.read_text()
    return HTMLResponse(content=html)

@app.post("/talk")
async def talk(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    tmp_in_path = ""
    tmp_out_path = ""

    try:
        # 1. Save uploaded audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp_in:
            content = await file.read()
            tmp_in.write(content)
            tmp_in_path = tmp_in.name

        # 2. Transcribe with Groq Whisper
        with open(tmp_in_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(tmp_in_path, f.read()),
                model="whisper-large-v3-turbo",
                response_format="text"
            )

        user_text = transcription.strip()
        print(f"👤 User: {user_text}")

        if not user_text or user_text == ".":
            user_text = "(silence)"

        # 3. LLM response via Groq
        chat_history.append({"role": "user", "content": user_text})
        chat_completion = client.chat.completions.create(
            messages=chat_history,
            model="llama-3.3-70b-versatile",
            max_tokens=200,
            temperature=0.6
        )
        ai_response = chat_completion.choices[0].message.content
        print(f"🤖 Agent: {ai_response}")
        chat_history.append({"role": "assistant", "content": ai_response})

        # 4. Edge TTS synthesis
        tmp_out_path = tmp_in_path.replace(".webm", ".mp3")
        communicate = edge_tts.Communicate(ai_response, "en-US-AvaNeural")
        await communicate.save(tmp_out_path)

        background_tasks.add_task(cleanup_files, tmp_in_path, tmp_out_path)

        # Return audio + text in headers for the frontend transcript
        response = FileResponse(tmp_out_path, media_type="audio/mpeg")
        response.headers["X-User-Text"] = quote(user_text)
        response.headers["X-Agent-Text"] = quote(ai_response)
        response.headers["Access-Control-Expose-Headers"] = "X-User-Text, X-Agent-Text"
        return response

    except Exception as e:
        print(f"❌ Error: {e}")
        background_tasks.add_task(cleanup_files, tmp_in_path, tmp_out_path)
        return JSONResponse(content={"detail": str(e)}, status_code=500)

# ══════════════════════════════════════════════════════════════
# ── TWILIO PHONE CALLING ENDPOINTS ──
# ══════════════════════════════════════════════════════════════

@app.post("/incoming-call")
async def incoming_call(request: Request):
    """Twilio hits this when someone calls your number."""
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    print(f"📞 Incoming call: {call_sid}")

    # Create a fresh conversation for this call
    call_sessions[call_sid] = [{"role": "system", "content": SYSTEM_PROMPT}]

    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/handle-speech",
        speech_timeout="auto",
        language="en-IN"
    )
    gather.say(
        "Welcome to Pinified! I can help you with tariff rates, "
        "booking status, and shipment tracking. How can I help you today?",
        voice="Polly.Aditi"
    )
    resp.append(gather)
    resp.say("I didn't hear anything. Please call back. Goodbye.")

    return Response(content=str(resp), media_type="application/xml")


@app.post("/handle-speech")
async def handle_speech(request: Request):
    """Twilio sends transcribed speech here. We respond with LLM + TTS."""
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    speech_result = form.get("SpeechResult", "")

    print(f"📞 [{call_sid}] User said: {speech_result}")

    # Get or create session
    history = call_sessions.get(call_sid, [{"role": "system", "content": SYSTEM_PROMPT}])
    history.append({"role": "user", "content": speech_result})

    # LLM response
    completion = client.chat.completions.create(
        messages=history,
        model="llama-3.3-70b-versatile",
        max_tokens=200,
        temperature=0.6
    )
    ai_response = completion.choices[0].message.content
    print(f"📞 [{call_sid}] Agent: {ai_response}")
    history.append({"role": "assistant", "content": ai_response})
    call_sessions[call_sid] = history

    # Generate TTS audio
    filename = f"{call_sid}_{len(history)}.mp3"
    filepath = os.path.join(tempfile.gettempdir(), filename)
    communicate = edge_tts.Communicate(ai_response, "en-US-AvaNeural")
    await communicate.save(filepath)

    # Build TwiML: play audio, then listen again (loop)
    resp = VoiceResponse()
    resp.play(f"/audio/{filename}")
    gather = Gather(
        input="speech",
        action="/handle-speech",
        speech_timeout="auto",
        language="en-IN"
    )
    gather.say("Is there anything else I can help with?", voice="Polly.Aditi")
    resp.append(gather)
    resp.say("Thank you for calling Pinified. Have a great day. Goodbye.")

    return Response(content=str(resp), media_type="application/xml")


@app.get("/audio/{filename}")
async def serve_audio(filename: str, background_tasks: BackgroundTasks):
    """Serves TTS audio files for Twilio to play."""
    filepath = os.path.join(tempfile.gettempdir(), filename)
    if os.path.exists(filepath):
        background_tasks.add_task(cleanup_files, filepath)
        return FileResponse(filepath, media_type="audio/mpeg")
    return Response(status_code=404)


if __name__ == "__main__":
    print("🚚 Pinified Voice Agent — http://localhost:8000")
    print("📞 Phone: Configure Twilio webhook → <ngrok-url>/incoming-call")
    uvicorn.run(app, host="0.0.0.0", port=8000)
