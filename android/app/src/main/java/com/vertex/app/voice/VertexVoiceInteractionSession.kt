package com.vertex.app.voice

import android.os.Handler
import android.os.Looper
import android.util.Log
import android.service.voice.VoiceInteractionSession
import com.vertex.app.di.VertexVoiceRunnerEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Session that runs when the user triggers Vertex from the assistant list (e.g. long-press on buds).
 * Runs the shared voice pipeline (STT -> Vertex API -> TTS) using the default voice device (e.g. BT headset).
 */
class VertexVoiceInteractionSession(
    context: android.content.Context,
) : VoiceInteractionSession(context, Handler(Looper.getMainLooper())) {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var sessionId: String? = null

    override fun onShow(args: android.os.Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        Log.d("VertexSession", "onShow triggered")
        
        // Immediate haptic feedback
        try {
            val vibrator = context.getSystemService(android.content.Context.VIBRATOR_SERVICE) as android.os.Vibrator
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                vibrator.vibrate(android.os.VibrationEffect.createOneShot(70, android.os.VibrationEffect.DEFAULT_AMPLITUDE))
            } else {
                @Suppress("DEPRECATION")
                vibrator.vibrate(70)
            }
        } catch (_: Exception) {}

        // Ensure the session is visible even if the screen is locked
        try {
            window?.window?.let { win ->
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O_MR1) {
                    win.addFlags(android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED)
                    win.addFlags(android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON)
                    win.addFlags(android.view.WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD)
                }
            }
        } catch (e: Exception) {
            Log.e("VertexSession", "Failed to set window flags: ${e.message}")
        }

        val app = context.applicationContext
        val entryPoint = dagger.hilt.android.EntryPointAccessors.fromApplication(app, VertexVoiceRunnerEntryPoint::class.java)
        val runner = entryPoint.vertexVoiceRunner()

        scope.launch {
            Log.d("VertexSession", "Starting voice session")
            val callbacks = object : VoiceSessionCallbacks {
                override fun onListening() {
                    Log.d("VertexSession", "onListening")
                }
                override fun onTranscript(transcript: String) {
                    Log.d("VertexSession", "onTranscript: $transcript")
                }
                override fun onProcessing() {
                    Log.d("VertexSession", "onProcessing")
                }
                override fun onStatus(message: String) {
                    Log.d("VertexSession", "onStatus: $message")
                }
                override fun onAudioSourceChanged(isBluetooth: Boolean) {
                    Log.d("VertexSession", "onAudioSourceChanged: isBluetooth=$isBluetooth")
                }
                override fun onResult(
                    newSessionId: String?,
                    reply: String,
                    latencyMs: Int,
                    toolsUsed: List<String>,
                    audioBase64: String?,
                ) {
                    Log.d("VertexSession", "onResult: $reply")
                    sessionId = newSessionId
                }
                override fun onError(message: String) {
                    Log.e("VertexSession", "onError: $message")
                }
            }
            try {
                sessionId = runner.runVoiceSession(sessionId, callbacks)
            } catch (e: Exception) {
                Log.e("VertexSession", "Session crashed: ${e.message}")
            } finally {
                // Wait a tiny bit before hiding to ensure any final audio starts
                kotlinx.coroutines.delay(500)
                Log.d("VertexSession", "Hiding session")
                hide()
            }
        }
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
