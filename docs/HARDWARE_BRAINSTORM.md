# Vertex 24/7 Hardware – Brainstorm & Design Options

Goal: **Vertex around your ears 24/7** (except when charging at night), with **“Hey Vertex”** wake word → you speak → Vertex responds in your ear. Prefer **buying existing hardware** over building custom, but it must **integrate cleanly with your Vertex backend**.

---

## Implementation status (what’s in the app)

- **Long-press on buds (Vertex in assistant list)**  
  Vertex is registered as a **Voice Interaction** app. In **Settings > Apps > Default apps > Digital assistant app** (or equivalent), you can select **Vertex**. When you long-press your Bluetooth headset (e.g. Huawei Buds 4 Pro), the system starts a Vertex voice session: listen on the **earbuds’ mic** → STT → Vertex API → TTS in the earbuds.  
  On some devices, headset long-press broadcasts **VOICE_COMMAND**; the app handles that too and opens the main screen and starts a voice session.

- **Hey Vertex (hands-free)**  
  An in-app toggle enables a **foreground service** that listens for **“Hey Vertex”** using **Picovoice Porcupine**. When detected, the app comes to the foreground and runs the same voice pipeline (STT → Vertex → TTS).  
  **Setup:** Get a Picovoice AccessKey from [console.picovoice.ai](https://console.picovoice.ai), create a custom wake word **“Hey Vertex”**, download the `.ppn` file, and add it to the app as `app/src/main/assets/hey_vertex.ppn`. Add `PICOVOICE_ACCESS_KEY=your_key` to `gradle.properties` (or set in `build.gradle.kts`). See `android/app/src/main/assets/README_hey_vertex.txt`.

- **Bluetooth mic and speaker**  
  The shared voice pipeline uses **communication mode** (`MODE_IN_COMMUNICATION`) so Android routes **capture** and **playback** to the **default voice device**. When your earbuds are the **active** device for the phone (e.g. last used for voice or assistant), the earbuds’ mic is used for “Hey Vertex” and for the query, and TTS plays in the earbuds.  
  **Important:** The app cannot force the buds to stay on the phone. If the buds have switched to another device (e.g. laptop), the phone will use its own mic until the buds are active again for the phone.

- **Battery**  
  “Hey Vertex” runs in a foreground service and uses more battery than built-in assistants (no dedicated wake-word hardware). Use the in-app toggle to disable when not needed.

---

## 1. What Vertex Needs From Hardware

Your stack today:“Hey Vertex”


- **Backend**: `POST /api/v1/voice` with `{ transcript, session_id }` → streams back `reply` + `audio_base64` (TTS).
- **Android app**: Tap-to-talk → device STT (SpeechRecognizer) → transcript to backend → play TTS.

For 24/7 “Hey Vertex” the chain is:

| Step | What’s needed | Who can do it |
|------|----------------|----------------|
| **1. Wake word** | Detect “Hey Vertex” (or custom phrase) | Wearable, or phone (app in background) |
| **2. Capture speech** | Mic captures your query | Wearable or phone |
| **3. STT** | Speech → text | Phone (existing) or server or wearable (if it has STT API) |
| **4. Call Vertex** | HTTPS to your server with transcript | Phone or a device with IP (tablet, wearable with LTE/Wi‑Fi) |
| **5. Playback** | TTS in your ear | Wearable (preferred) or phone speaker |

So the main decision is: **where does the “brain” live** — phone (bridge) vs wearable (standalone)?

---

## 2. Architecture Options

### Option A: Phone as bridge (recommended to start)

- **Wearable**: earbuds or glasses that do **audio only** (mic in, speaker out) over Bluetooth to the phone.
- **Phone**: Runs Vertex app (or a background service). Handles:
  - Wake word (“Hey Vertex”) — either in-app always-listening or a companion wearable that triggers the app.
  - STT (you already use Android SpeechRecognizer).
  - HTTP to your home server; receive TTS.
  - Send TTS audio to the wearable over Bluetooth.

**Pros**: Reuses your current backend and Android app; only need to add wake word + Bluetooth audio routing. No need for wearables to have their own SIM/Wi‑Fi or custom firmware.  
**Cons**: Phone must be nearby and app (or service) running; not truly “standalone” wearable.

### Option B: Standalone wearable (phone optional)

- Wearable has **Wi‑Fi (and/or LTE)** and an OS or SDK that can run an app or script: capture audio → STT (on-device or cloud) → HTTPS to Vertex → play TTS.
- Examples: smart glasses with full OS (e.g. Ray-Ban Meta), or a small compute unit (Raspberry Pi / Android thing) in a pocket with Bluetooth earbuds.

**Pros**: Can work without phone; single device on your ear.  
**Cons**: Few products expose a clean API to *your* backend; often locked to their assistant. May need custom firmware or “companion app on another device” anyway.

### Option C: Hybrid

- **Wake word + mic** on the wearable (or a dedicated button/tap).
- Wearable streams **raw audio** to the phone (over BLE or classic Bluetooth); phone does STT + Vertex + TTS and sends audio back.
- Or: wearable has “assistant” button that wakes the phone and opens Vertex (no custom wake word on wearable).

---

## 3. Hardware Categories & Vertex Fit

### 3.1 Smart glasses (audio-first or full AR)

| Product | Form | Wake word / trigger | Audio I/O | Vertex integration |
|--------|------|----------------------|-----------|----------------------|
| **Ray-Ban Meta** | Glasses, camera, speakers, mics | “Hey Meta” (built-in); no custom phrase | Mic + speakers | **Bridge**: Use “Hey Meta” to open Meta assistant; no way to redirect to Vertex. **Workaround**: Use button to launch companion app on phone that then does “Hey Vertex” on phone. Not ideal. |
| **Bose Frames (Tempo)** | Glasses, audio-focused | Bose music/assistant; no custom | Mic + speakers | Same as above: trigger is theirs. Button could start app on phone. |
| **Echo Frames** | Glasses, Alexa | “Alexa” | Mic + speakers | Tied to Alexa. Could use Alexa “routine” to call a skill that hits your API, but then you’re in Alexa land, not “Hey Vertex”. |
| **Soundcore Frames** | Glasses, audio | Button / tap | Mic + speakers | **Good bridge**: Bluetooth to phone; you’d use **phone** for wake word + Vertex; glasses = audio I/O only. |

**Takeaway**: Glasses that are **dumb audio** (Bluetooth to phone) are easier: Vertex runs on phone, glasses are just the ear piece. Glasses with their own assistant rarely let you replace the wake word with “Hey Vertex”.

---

### 3.2 Hearables (earbuds / in-ear)

| Product | Form | Wake word / trigger | Vertex integration |
|--------|------|----------------------|----------------------|
| **AirPods (Pro / Max)** | Earbuds / over-ear | “Hey Siri” only; no custom | **Bridge**: Phone does “Hey Vertex” (e.g. Android with Vertex app listening); AirPods = mic + playback. Need Android + Vertex app with background wake word. |
| **Galaxy Buds** | Earbuds | Bixby / tap | Same: use as Bluetooth mic/speaker; wake word on phone. |
| **Pixel Buds** | Earbuds | “Hey Google” | Same. |
| **Jabra Elite / Evolve** | Earbuds, often for work | Button, sometimes assistant | **Bridge**: Button or tap to start listening; phone runs Vertex. No “Hey Vertex” on earbud itself unless phone listens. |
| **Open-ear (e.g. Oladance, Shokz OpenRun)** | Not in-ear, all-day comfort | Usually button or phone | **Bridge**: Comfortable for 24/7; mic may be less good for voice. Phone handles wake + Vertex. |

**Takeaway**: Almost no consumer earbuds support a **custom** wake word on the earbud. You get “Hey Siri” or “Hey Google” or a **button/tap**. So “Hey Vertex” implies **phone-side** wake word (or a separate small device that does wake word and talks to the phone).

---

### 3.3 Dedicated AI wearables (with their own “brain”)

| Product | What it is | Vertex fit |
|--------|------------|------------|
| **Humane Pin** | Clip-on AI, mic + speaker + projector | Its own stack; no “Hey Vertex” or direct replacement. Not a good Vertex host. |
| **Rewind Pendant** | Mic pendant, transcription / AI | Tied to their app. No open API to pipe audio to your backend. |
| **Rabbit R1** | Pocket device, not ear | Could in theory run a small client to call Vertex, but not “around your ears”. |
| **Smartwatches (Wear OS, Apple Watch)** | Watch + Bluetooth earbuds | **Bridge**: Watch or phone runs Vertex app; “Hey Vertex” on watch or phone; earbuds for mic/speaker. Possible but watch battery and background limits are real. |

**Takeaway**: Today’s “AI wearables” are closed ecosystems. For Vertex you either use them as **audio-only** (if they support BT to phone) or you don’t rely on their AI at all.

---

### 3.4 “Open” or hackable devices

- **ESP32 / Raspberry Pi + mic + small earbud**: You’d run wake word (e.g. Porcupine, Picovoice) on the device; on “Hey Vertex” it could stream audio to phone or directly to your server if you add Wi‑Fi. More DIY, you said you prefer to buy.
- **Dev kits with wake word**: e.g. **Picovoice’s dev kits**, **ReSpeaker** (see below) — useful if you ever want a **dedicated wake-word gadget** that then triggers the phone or server.

---

## 4. Recommended Directions (Buy Hardware + Vertex on Phone)

Given “buy not build” and “Hey Vertex” + 24/7 ears:

### Path 1: Comfortable earbuds + phone does everything (easiest)

- **Hardware**: Any good **Bluetooth earbuds** you’re happy to wear for hours (e.g. Jabra Elite, Pixel Buds, Galaxy Buds, or open-ear like Shokz if you want awareness). Prefer something with **good mic** and **all-day comfort**.
- **Vertex**: 
  - Extend your **Android app** to support:
    - **Background / foreground service** that listens for “Hey Vertex” (use **Android SpeechRecognizer** in partial-result mode, or a dedicated wake-word engine like **Picovoice Porcupine** on Android).
    - When triggered: take mic input (or use earbud mic via Bluetooth), run STT, call `/api/v1/voice`, play TTS to the **connected Bluetooth device** (already supported by Android audio routing).
  - No change to backend.
- **Flow**: Phone in pocket/bag; earbuds connected. You say “Hey Vertex” → phone detects it → listens for query → STT → Vertex → TTS in earbuds.

**Pros**: Minimal new hardware; reuses backend and most of the app.  
**Cons**: Phone must be carried and app/service running; battery impact of always-listening on phone.

---

### Path 2: Glasses as “always on your ears” (if you prefer glasses)

- **Hardware**: **Soundcore Frames** or similar **audio glasses** that are just Bluetooth speakers + mics (no built-in assistant).
- **Vertex**: Same as Path 1 — phone runs Vertex app with wake word; glasses are the default Bluetooth output/input.
- **Flow**: Same as Path 1; only the form factor is glasses instead of earbuds.

**Pros**: Glasses can be more “24/7” for some people; no ear fatigue.  
**Cons**: Glasses mic may be slightly worse in noise; style/comfort is personal.

---

### Path 3: Dedicated wake-word device (later, if you want phone-free trigger)

- **Hardware**: A small **always-on device** (e.g. ReSpeaker, or a dev board with mic + Wi‑Fi/BLE) running **Porcupine** or similar with custom “Hey Vertex” model. When it hears the phrase, it either:
  - Sends a BLE command to the phone (“start Vertex”), and phone does STT + Vertex + TTS to earbuds, or
  - Streams audio to your **home server** (you’d add an STT + Vertex client there) and then… you still need earbuds for playback, which likely connect to phone. So usually this still goes back to “phone plays TTS to earbuds”.
- So this path is mostly about **where** “Hey Vertex” runs (on a dedicated gadget vs on the phone), not about replacing the phone in the chain.

**Pros**: Can offload always-listening from phone; one gadget can serve multiple output devices.  
**Cons**: Extra device to carry or place; more integration work.

---

## 5. “Hey Vertex” on the phone (software you’ll need)

To make Path 1 or 2 work you need **custom wake word** on Android:

- **Option 5a – SpeechRecognizer + partial results**: Use Android’s **continuous** or **partial** recognition and look for “hey vertex” (or “vertex”) in the partial string. Possible but not designed for low-power wake word; may drain battery and have latency.
- **Option 5b – Porcupine (Picovoice)**: Train a custom wake word “Hey Vertex” in Picovoice Console; use their Android SDK in a **foreground service** with a low-power listener. When it fires, switch to full STT (SpeechRecognizer or their STT) and then call Vertex. This is the **robust** approach for “Hey Vertex”.
- **Option 5c – Button / tap on earbuds**: Many earbuds support “double-tap” or “long-press” to invoke assistant. You could map that to “start Vertex listening” instead of Siri/Google — no custom wake word, but very reliable and no extra battery cost.

Recommendation: **5b (Porcupine)** for true “Hey Vertex”; **5c** as a quick win so you can use any earbuds with a single tap to talk to Vertex.

---

## 6. Summary Table

| Approach | Hardware | Who does “Hey Vertex” | Who does STT / Vertex / TTS | Complexity |
|----------|----------|------------------------|-----------------------------|------------|
| **Path 1** | BT earbuds + Android phone | Phone (app + Porcupine or tap) | Phone → your server | Low (add wake word or tap to app) |
| **Path 2** | BT glasses + Android phone | Phone | Phone → your server | Low (same as Path 1) |
| **Path 3** | Wake-word gadget + phone + earbuds | Dedicated device | Phone or server | Medium (extra device + BLE or API) |
| **Standalone wearable** | Glasses/earbuds with own OS + connectivity | Their assistant (no “Hey Vertex”) | Their cloud | N/A for Vertex unless they open API |

---

## 7. Concrete next steps (done vs optional)

**Done in the app:**  
- Tap-to-talk (already present) and routing to the connected Bluetooth device via communication mode.  
- Long-press on buds: Vertex in the assistant list (VoiceInteractionService + Session) and VOICE_COMMAND fallback.  
- “Hey Vertex” via Porcupine in a foreground service, with an in-app toggle.

**Optional later**:  
- Tune battery (e.g. “Hey Vertex” only during certain hours or when charging).  
- If you want “Hey Vertex” without the phone in pocket (e.g. at home): add a **ReSpeaker** or Pi + mic running Porcupine to trigger the phone via BLE.  
- Or explore **Wear OS** so the watch runs the Vertex client; earbuds still for audio.
