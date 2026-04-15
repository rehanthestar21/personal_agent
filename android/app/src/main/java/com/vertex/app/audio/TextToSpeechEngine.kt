package com.vertex.app.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Build
import android.speech.tts.TextToSpeech
import android.util.Base64
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume

@Singleton
class TextToSpeechEngine @Inject constructor(
    private val context: Context,
) {
    private var currentPlayer: MediaPlayer? = null
    private var openingTts: TextToSpeech? = null

    suspend fun speak(audioBase64: String?) {
        if (audioBase64.isNullOrBlank()) {
            Log.w("VertexTTS", "No audio data to play")
            return
        }

        val audioFile = withContext(Dispatchers.IO) {
            try {
                val bytes = Base64.decode(audioBase64, Base64.DEFAULT)
                val file = File.createTempFile("vertex_tts_", ".mp3", context.cacheDir)
                file.writeBytes(bytes)
                Log.d("VertexTTS", "Audio decoded: ${bytes.size} bytes")
                file
            } catch (e: Exception) {
                Log.e("VertexTTS", "Failed to decode audio", e)
                null
            }
        } ?: return

        playAudio(audioFile)
        audioFile.delete()
    }

    fun stop() {
        try {
            currentPlayer?.let {
                if (it.isPlaying) it.stop()
                it.release()
            }
        } catch (e: Exception) {
            Log.w("VertexTTS", "Stop error", e)
        }
        currentPlayer = null
    }

    private suspend fun playAudio(file: File) {
        suspendCancellableCoroutine { cont ->
            val player = MediaPlayer()
            currentPlayer = player
            try {
                // Use STREAM_VOICE_CALL when in a call-like state (Bluetooth SCO)
                // This ensures audio routes to the same place as the microphone
                val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
                if (audioManager.mode == android.media.AudioManager.MODE_IN_COMMUNICATION) {
                    @Suppress("DEPRECATION")
                    player.setAudioStreamType(android.media.AudioManager.STREAM_VOICE_CALL)
                } else {
                    @Suppress("DEPRECATION")
                    player.setAudioStreamType(android.media.AudioManager.STREAM_MUSIC)
                }

                player.setDataSource(file.absolutePath)
                player.prepare()
                player.setOnCompletionListener {
                    currentPlayer = null
                    it.release()
                    if (cont.isActive) cont.resume(Unit)
                }
                player.setOnErrorListener { mp, _, _ ->
                    currentPlayer = null
                    mp.release()
                    if (cont.isActive) cont.resume(Unit)
                    true
                }
                player.start()
                Log.d("VertexTTS", "Playing audio, duration=${player.duration}ms")

                cont.invokeOnCancellation {
                    currentPlayer = null
                    player.stop()
                    player.release()
                }
            } catch (e: Exception) {
                Log.e("VertexTTS", "Playback failed", e)
                currentPlayer = null
                player.release()
                if (cont.isActive) cont.resume(Unit)
            }
        }
    }

    /**
     * Speaks a short opening phrase (e.g. "Hey Vertex here") using on-device TTS
     * so it plays immediately without a network call. Uses VOICE_CALL stream when
     * in communication mode so it routes to Bluetooth earbuds.
     */
    suspend fun speakOpening(text: String) {
        if (text.isBlank()) return
        withContext(Dispatchers.Main) {
            suspendCancellableCoroutine { cont ->
                cont.invokeOnCancellation { openingTts?.stop() }
                val existing = openingTts
                if (existing != null) {
                    doSpeakOpening(existing, text, cont)
                    return@suspendCancellableCoroutine
                }
                var ttsInstance: TextToSpeech? = null
                ttsInstance = TextToSpeech(context) { status ->
                    if (status != TextToSpeech.SUCCESS) {
                        Log.w("VertexTTS", "Opening TTS init failed: $status")
                        if (cont.isActive) cont.resume(Unit)
                        return@TextToSpeech
                    }
                    val engine = ttsInstance!!
                    openingTts = engine
                    doSpeakOpening(engine, text, cont)
                }
            }
        }
    }

    private fun doSpeakOpening(
        tts: TextToSpeech,
        text: String,
        cont: kotlinx.coroutines.CancellableContinuation<Unit>,
    ) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
            val useVoiceCall = audioManager.mode == android.media.AudioManager.MODE_IN_COMMUNICATION
            val attrs = AudioAttributes.Builder()
                .setUsage(
                    if (useVoiceCall) AudioAttributes.USAGE_VOICE_COMMUNICATION
                    else AudioAttributes.USAGE_ASSISTANT
                )
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()
            tts.setAudioAttributes(attrs)
        }
        // Use Indian English to match backend TTS (en-IN); fallback to US if not available
        val indianLocale = Locale("en", "IN")
        val langResult = tts.setLanguage(indianLocale)
        if (langResult == TextToSpeech.LANG_MISSING_DATA || langResult == TextToSpeech.LANG_NOT_SUPPORTED) {
            tts.setLanguage(Locale.US)
        }
        val utteranceId = "vertex_opening_${System.currentTimeMillis()}"
        tts.setOnUtteranceProgressListener(object : android.speech.tts.UtteranceProgressListener() {
            override fun onStart(id: String?) {}
            override fun onDone(id: String?) {
                if (id == utteranceId && cont.isActive) cont.resume(Unit)
            }
            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) {
                if (utteranceId == utteranceId && cont.isActive) cont.resume(Unit)
            }
            override fun onError(utteranceId: String?, errorCode: Int) {
                if (utteranceId == utteranceId && cont.isActive) cont.resume(Unit)
            }
        })
        val speakResult = tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, utteranceId)
        if (speakResult != TextToSpeech.SUCCESS && cont.isActive) cont.resume(Unit)
    }

    fun shutdown() {
        stop()
        openingTts?.shutdown()
        openingTts = null
    }
}
