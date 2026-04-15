package com.vertex.app.audio

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import java.util.Locale

class SpeechRecognizerWrapper(private val context: Context) {

    suspend fun listen(): Result<String> = withContext(Dispatchers.Main) {
        val channel = Channel<Result<String>>(1)

        // CRITICAL: Don't use the default createSpeechRecognizer(context) because if Vertex 
        // is the default assistant, it might try to bind to our own (empty) RecognitionService.
        // We explicitly find the system's default recognizer instead.
        val recognizer = try {
            val serviceIntent = Intent(android.speech.RecognitionService.SERVICE_INTERFACE)
            val packageManager = context.packageManager
            val resolveInfos = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                packageManager.queryIntentServices(serviceIntent, android.content.pm.PackageManager.ResolveInfoFlags.of(0))
            } else {
                @Suppress("DEPRECATION")
                packageManager.queryIntentServices(serviceIntent, 0)
            }
            
            // Find a recognizer that isn't us (prefer Google if available)
            val systemRecognizer = resolveInfos.firstOrNull { 
                it.serviceInfo.packageName != context.packageName && 
                (it.serviceInfo.packageName.contains("google") || it.serviceInfo.packageName.contains("android"))
            } ?: resolveInfos.firstOrNull { it.serviceInfo.packageName != context.packageName }

            if (systemRecognizer != null) {
                val componentName = android.content.ComponentName(systemRecognizer.serviceInfo.packageName, systemRecognizer.serviceInfo.name)
                SpeechRecognizer.createSpeechRecognizer(context, componentName)
            } else {
                SpeechRecognizer.createSpeechRecognizer(context)
            }
        } catch (e: Exception) {
            Log.w("SpeechRecognizer", "Failed to find specific recognizer, falling back to default")
            SpeechRecognizer.createSpeechRecognizer(context)
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            // Indian English for better accent handling; Hindi for mixed Hinglish
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale("en", "IN"))
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            
            // CRITICAL: Force the use of the Bluetooth SCO/Communication device for recording
            // This ensures the system uses the mic from the earbuds when in MODE_IN_COMMUNICATION
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                // On Android 12+, the system should respect setCommunicationDevice(bluetooth)
                // but we add this as a hint to the recognizer.
                putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE, android.media.MediaRecorder.AudioSource.VOICE_COMMUNICATION)
                // Additional hint for some devices to use the communication device mic
                putExtra("android.speech.extra.GET_AUDIO_PER_UTTERANCE", true)
            } else {
                // Older versions might need this to prefer the SCO mic
                @Suppress("DEPRECATION")
                putExtra("android.speech.extra.DICTATION_MODE", true)
            }

            // Android 14+: enable mid-utterance language switching for Hinglish (Hindi+English in same sentence)
            if (Build.VERSION.SDK_INT >= 34) {
                putExtra(RecognizerIntent.EXTRA_ENABLE_LANGUAGE_SWITCH, RecognizerIntent.LANGUAGE_SWITCH_QUICK_RESPONSE)
                putExtra(
                    RecognizerIntent.EXTRA_LANGUAGE_SWITCH_ALLOWED_LANGUAGES,
                    arrayOf("en-IN", "hi-IN")
                )
            }
        }

        val listener = object : RecognitionListener {
            override fun onResults(results: Bundle?) {
                val matches = results
                    ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                val text = matches?.firstOrNull() ?: ""
                channel.trySend(Result.success(text))
                recognizer.destroy()
            }

            override fun onError(error: Int) {
                val msg = when (error) {
                    SpeechRecognizer.ERROR_NO_MATCH -> "No speech detected"
                    SpeechRecognizer.ERROR_AUDIO -> "Audio recording error"
                    SpeechRecognizer.ERROR_NETWORK -> "Network error"
                    SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Network timeout"
                    else -> "Speech recognition error ($error)"
                }
                channel.trySend(Result.failure(RuntimeException(msg)))
                recognizer.destroy()
            }

            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onPartialResults(partialResults: Bundle?) {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
        }

        recognizer.setRecognitionListener(listener)
        recognizer.startListening(intent)

        try {
            withTimeout(30_000) {
                channel.receive()
            }
        } catch (e: Exception) {
            recognizer.destroy()
            Result.failure(e)
        }
    }
}
