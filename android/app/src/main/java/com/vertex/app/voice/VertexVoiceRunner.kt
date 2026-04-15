package com.vertex.app.voice

import android.content.Context
import com.vertex.app.audio.AudioSessionHelper
import dagger.hilt.android.qualifiers.ApplicationContext
import com.vertex.app.audio.SpeechRecognizerWrapper
import com.vertex.app.audio.TextToSpeechEngine
import com.vertex.app.network.VertexApiClient
import com.vertex.app.network.VoiceEvent
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
import android.util.Log
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Callbacks for the shared voice session (STT -> Vertex API -> TTS).
 * Used by the main UI, VoiceInteractionSession, and wake-word service.
 */
interface VoiceSessionCallbacks {
    fun onListening()
    fun onTranscript(transcript: String)
    fun onProcessing()
    fun onStatus(message: String)
    fun onAudioSourceChanged(isBluetooth: Boolean)
    fun onResult(sessionId: String?, reply: String, latencyMs: Int, toolsUsed: List<String>, audioBase64: String?)
    fun onError(message: String)
}

private val newChatPhrases = listOf(
    "new chat", "new conversation", "start over", "fresh start",
    "reset chat", "clear chat", "start a new chat", "start new chat",
    "new session", "reset conversation", "forget this conversation",
)

@Singleton
class VertexVoiceRunner @Inject constructor(
    @ApplicationContext private val context: Context,
    private val apiClient: VertexApiClient,
    private val ttsEngine: TextToSpeechEngine,
    private val stt: SpeechRecognizerWrapper,
) {

    private val audioSessionHelper = AudioSessionHelper(context)
    private var isContinuousSessionActive = false

    /**
     * Starts a continuous voice session: Listen -> Process -> Speak -> Repeat.
     * Stays active until the user says a "hang up" phrase or an error occurs.
     */
    suspend fun startContinuousSession(
        sessionId: String?,
        callbacks: VoiceSessionCallbacks,
    ): String? = withContext(Dispatchers.Main) {
        var currentSessionId = sessionId ?: UUID.randomUUID().toString()
        isContinuousSessionActive = true
        
        try {
            // Immediate feedback
            try {
                val vibrator = context.getSystemService(Context.VIBRATOR_SERVICE) as android.os.Vibrator
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                    vibrator.vibrate(android.os.VibrationEffect.createOneShot(100, android.os.VibrationEffect.DEFAULT_AMPLITUDE))
                } else {
                    @Suppress("DEPRECATION")
                    vibrator.vibrate(100)
                }
            } catch (_: Exception) {}

            playAcknowledgementBeep(android.media.AudioManager.STREAM_NOTIFICATION)

            audioSessionHelper.startCallMode()
            delay(400)
            callbacks.onAudioSourceChanged(audioSessionHelper.isBluetoothActive())
            // Opening phrase once at session start (headless / call mode only)
            ttsEngine.speakOpening("Hello, this is Vertex")

            while (isContinuousSessionActive) {
                ttsEngine.stop()
                callbacks.onListening()

                // Re-apply Bluetooth routing before each listen so the mic stays on earbuds
                // (Android can revert to phone mic after TTS or between recognizer runs)
                audioSessionHelper.ensureBluetoothRouting()
                callbacks.onAudioSourceChanged(audioSessionHelper.isBluetoothActive())

                val transcript = try {
                    stt.listen().getOrThrow()
                } catch (e: Exception) {
                    Log.e("VertexVoiceRunner", "STT error: ${e.message}")
                    // If it's a transient error, we might want to retry rather than break
                    if (e.message?.contains("No speech detected") == true) {
                        delay(500)
                        continue
                    }
                    break
                }

                if (transcript.isBlank()) {
                    // If no speech, we can either wait or end. Let's wait a bit and retry.
                    delay(1000)
                    continue
                }

                if (isHangUpPhrase(transcript)) {
                    Log.d("VertexVoiceRunner", "Hang up phrase detected: $transcript")
                    playAcknowledgementBeep(android.media.AudioManager.STREAM_VOICE_CALL)
                    break
                }

                val (actualMessage, isNewChat) = parseNewChat(transcript)
                if (isNewChat) {
                    currentSessionId = UUID.randomUUID().toString()
                }

                callbacks.onTranscript(transcript)
                callbacks.onProcessing()

                apiClient.ensureAuthenticated(context)
                apiClient.sendVoiceStream(actualMessage, currentSessionId)
                    .flowOn(Dispatchers.IO)
                    .collect { event ->
                        when (event) {
                            is VoiceEvent.Status -> callbacks.onStatus(event.message)
                            is VoiceEvent.Result -> {
                                currentSessionId = event.sessionId ?: currentSessionId
                                callbacks.onResult(
                                    currentSessionId,
                                    event.reply,
                                    event.latencyMs,
                                    event.toolsUsed,
                                    event.audioBase64,
                                )
                                ttsEngine.speak(event.audioBase64)
                            }
                            is VoiceEvent.Error -> callbacks.onError(event.message)
                        }
                    }
                
                // Small delay before listening again to avoid catching the end of TTS
                delay(300)
            }
        } catch (e: Exception) {
            callbacks.onError(e.message ?: "Unknown error")
        } finally {
            isContinuousSessionActive = false
            audioSessionHelper.endCallMode()
        }
        currentSessionId
    }

    private fun isHangUpPhrase(transcript: String): Boolean {
        val lower = transcript.lowercase().trim()
        return lower.contains("bye vertex") || 
               lower.contains("hang up") || 
               lower.contains("stop vertex") ||
               lower.contains("goodbye vertex")
    }

    /**
     * Runs one voice session: listen (STT) -> Vertex API -> TTS.
     * @param playOpeningPhrase When true, plays "Hey Vertex here" before listening (headless, long-press, wake word). When false, no greeting (in-app button tap).
     * @return The new session ID (or the one passed in) after the session, or null on error.
     */
    suspend fun runVoiceSession(
        sessionId: String?,
        callbacks: VoiceSessionCallbacks,
        playOpeningPhrase: Boolean = true,
    ): String? = withContext(Dispatchers.Main) {
        var currentSessionId = sessionId ?: UUID.randomUUID().toString()
        try {
            // Immediate feedback: start UI and vibrate
            callbacks.onListening()
            try {
                val vibrator = context.getSystemService(Context.VIBRATOR_SERVICE) as android.os.Vibrator
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                    vibrator.vibrate(android.os.VibrationEffect.createOneShot(50, android.os.VibrationEffect.DEFAULT_AMPLITUDE))
                } else {
                    @Suppress("DEPRECATION")
                    vibrator.vibrate(50)
                }
            } catch (_: Exception) {}

            // Play acknowledgement beep immediately (no wait for Bluetooth) so user gets instant feedback
            playAcknowledgementBeep(android.media.AudioManager.STREAM_NOTIFICATION)

            audioSessionHelper.startCallMode()
            delay(200)
            val isBT = audioSessionHelper.isBluetoothActive()
            callbacks.onAudioSourceChanged(isBT)

            ttsEngine.stop()
            // Re-trigger listening callback in case UI needs to refresh after BT setup
            callbacks.onListening()

            if (playOpeningPhrase) {
                ttsEngine.speakOpening("Hello, this is Vertex")
            }

            val transcript = try {
                stt.listen().getOrThrow()
            } finally {
                // No cleanup needed for now
            }

            if (transcript.isBlank()) {
                callbacks.onError("No speech detected")
                return@withContext currentSessionId
            }

            val (actualMessage, isNewChat) = parseNewChat(transcript)
            if (isNewChat) {
                currentSessionId = UUID.randomUUID().toString()
            }

            callbacks.onTranscript(transcript)
            callbacks.onProcessing()

            apiClient.ensureAuthenticated(context)
            apiClient.sendVoiceStream(actualMessage, currentSessionId)
                .flowOn(Dispatchers.IO)
                .collect { event ->
                    when (event) {
                        is VoiceEvent.Status -> callbacks.onStatus(event.message)
                        is VoiceEvent.Result -> {
                            currentSessionId = event.sessionId ?: currentSessionId
                            callbacks.onResult(
                                currentSessionId,
                                event.reply,
                                event.latencyMs,
                                event.toolsUsed,
                                event.audioBase64,
                            )
                            ttsEngine.speak(event.audioBase64)
                        }
                        is VoiceEvent.Error -> callbacks.onError(event.message)
                    }
                }
            currentSessionId
        } catch (e: Exception) {
            callbacks.onError(e.message ?: "Unknown error")
            currentSessionId
        } finally {
            audioSessionHelper.restoreMode()
        }
    }

    private suspend fun playAcknowledgementBeep(streamType: Int) {
        try {
            val toneG = android.media.ToneGenerator(streamType, 80)
            toneG.startTone(android.media.ToneGenerator.TONE_PROP_BEEP, 200)
            delay(250)
            toneG.release()
        } catch (_: Exception) {}
    }

    private fun parseNewChat(transcript: String): Pair<String, Boolean> {
        val lower = transcript.lowercase().trim()
        val isNewChat = newChatPhrases.any { lower.contains(it) }
        if (!isNewChat) return transcript to false
        var remaining = lower
        for (phrase in newChatPhrases) {
            remaining = remaining.replace(phrase, "")
        }
        remaining = remaining.replace(Regex("^[\\s,.and]+"), "").replace(Regex("[\\s,]+$"), "").trim()
        val actualMessage = if (remaining.length > 5) {
            remaining.replaceFirstChar { it.uppercase() }
        } else {
            "The user just started a new conversation. Greet them briefly and ask what they need."
        }
        return actualMessage to true
    }
}
