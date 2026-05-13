# 🚚 Pinified AI Voice Agent

A full-stack, two-way AI voice assistant built for **Pinified**, an Uber-for-logistics company. This system acts exactly like a human customer support agent, capable of handling inquiries about tariff rates, booking statuses, and shipment tracking in real-time.

It features a dual-channel architecture: users can interact with the agent either through a **web browser interface** or by calling a **real phone number**.

---

## ✨ Features
- **Dual-Channel Interface:** Works natively in the web browser (via WebRTC/MediaRecorder) and over standard phone calls (via Twilio).
- **Ultra-Fast STT:** Powered by **Groq Whisper** (`whisper-large-v3-turbo`) for near-instant transcription of spoken audio.
- **Intelligent Routing (LLM):** Uses **Groq LLaMA 3** (`llama-3.3-70b-versatile`) infused with a custom system prompt containing mock logistics tariff cards and a booking database to accurately answer domain-specific questions.
- **Natural Voice Synthesis (TTS):** Utilizes **Edge-TTS** (`en-US-AvaNeural`) to convert the AI's text responses back into fluid, natural-sounding speech.
- **Modern UI:** A clean, dark-themed, glassmorphism web interface that provides live chat transcripts of the conversation.

---

## 🛠️ Technology Stack
- **Backend:** Python, FastAPI, Uvicorn
- **AI Processing:** Groq SDK (Whisper STT, LLaMA 3 LLM)
- **Speech Synthesis:** Edge-TTS
- **Telephony:** Twilio (VoiceResponse, Gather TwiML)
- **Frontend:** Vanilla HTML/CSS/JS (embedded)

---

## 🚀 Getting Started

### 1. Prerequisites
Ensure you have Python 3.10+ installed. Install the required dependencies:
```bash
pip install fastapi uvicorn groq edge-tts python-multipart twilio
```

### 2. Environment Variables
You will need a free Groq API key to power the STT and LLM. 
```bash
export GROQ_API_KEY="your_groq_api_key_here"
```

### 3. Run the Server
Start the FastAPI server locally:
```bash
python3 app.py
```
*The web interface will immediately be available at `http://localhost:8000`.*

---

## 📞 Phone Calling Setup (Twilio)

To enable real phone calls to the agent:

1. Start an **ngrok** tunnel to expose your local server:
   ```bash
   ngrok http 8000
   ```
2. Copy your public ngrok URL (e.g., `https://abc123.ngrok-free.app`).
3. In your **Twilio Console**, purchase an active phone number.
4. Go to the active number configuration, and under **"A call comes in"**, set the Webhook URL to:
   ```
   https://YOUR_NGROK_URL/incoming-call
   ```
   *Method: `HTTP POST`*
5. Dial the Twilio number from your phone to speak with the agent!
