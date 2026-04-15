package com.vertex.app.voice

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.vertex.app.BuildConfig
import com.vertex.app.MainActivity
import com.vertex.app.R
import com.vertex.app.audio.AudioSessionHelper
import com.vertex.app.di.VertexVoiceRunnerEntryPoint
import dagger.hilt.android.EntryPointAccessors
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/**
 * Foreground service that listens for "Hey Vertex" using Picovoice Porcupine.
 * When detected, runs the voice pipeline (STT → API → TTS) in the background; no UI is shown.
 * Reply is played through the phone/Bluetooth speakers only.
 */
class VertexWakeWordService : Service() {

    private var porcupineManager: ai.picovoice.porcupine.PorcupineManager? = null
    private val serviceJob = Job()
    private val scope = CoroutineScope(Dispatchers.Main + serviceJob)
    private val audioSessionHelper = AudioSessionHelper(this)

    override fun onCreate() {
        super.onCreate()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Call startForeground immediately (required within ~5s on Android 12+)
        when (intent?.action) {
            ACTION_START -> startListening()
            ACTION_STOP -> stopSelf()
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    /** Release mic so STT can use it. Call before starting the voice session or when restarting. */
    private fun stopAndReleasePorcupine() {
        try {
            porcupineManager?.stop()
            porcupineManager?.delete()
        } catch (_: Exception) { }
        porcupineManager = null
        audioSessionHelper.restoreMode()
    }

    private fun startListening() {
        stopAndReleasePorcupine()
        val channelId = "vertex_wakeword"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                getString(R.string.notification_channel_hey_vertex),
                NotificationManager.IMPORTANCE_LOW
            ).apply { setShowBadge(false) }
            (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(channel)
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification: Notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle(getString(R.string.notification_hey_vertex_title))
            .setContentText(getString(R.string.notification_hey_vertex_text))
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }

        val accessKey = BuildConfig.PICOVOICE_ACCESS_KEY?.takeIf { it.isNotBlank() }
        if (accessKey.isNullOrBlank()) {
            Log.w(TAG, "PICOVOICE_ACCESS_KEY not set; Hey Vertex disabled. Add to gradle.properties.")
            return
        }

        audioSessionHelper.setCommunicationMode()
        scope.launch {
            kotlinx.coroutines.withContext(Dispatchers.Main) {
                audioSessionHelper.waitForScoConnected(3000)
            }
            kotlinx.coroutines.delay(400)
            kotlinx.coroutines.withContext(Dispatchers.Main) {
                startPorcupine(accessKey)
            }
        }
    }

    private fun startPorcupine(accessKey: String) {
        try {
            val assetPath = "Hey-Vertex_en_android_v4_0_0.ppn"
            val builder = ai.picovoice.porcupine.PorcupineManager.Builder()
                .setAccessKey(accessKey)
                .setKeywordPath(assetPath)
                .setSensitivity(0.85f)
                .setErrorCallback { e -> Log.e(TAG, "Porcupine error", e) }
            val callback = ai.picovoice.porcupine.PorcupineManagerCallback { _ ->
                onWakeWordDetected()
            }
            porcupineManager = builder.build(this, callback)
            porcupineManager?.start()
            Log.d(TAG, "Hey Vertex listening")
        } catch (e: Throwable) {
            Log.e(TAG, "Failed to start Porcupine (add .ppn to assets and PICOVOICE_ACCESS_KEY?)", e)
            audioSessionHelper.restoreMode()
            stopSelf()
        }
    }

    private fun onWakeWordDetected() {
        stopAndReleasePorcupine()
        try {
            val entryPoint = EntryPointAccessors.fromApplication(
                applicationContext,
                VertexVoiceRunnerEntryPoint::class.java
            )
            val runner = entryPoint.vertexVoiceRunner()
            scope.launch {
                runner.runVoiceSession(null, object : VoiceSessionCallbacks {
                    override fun onListening() {}
                    override fun onTranscript(transcript: String) {}
                    override fun onProcessing() {}
                    override fun onStatus(message: String) {}
                    override fun onAudioSourceChanged(isBluetooth: Boolean) {}
                    override fun onResult(
                        sessionId: String?,
                        reply: String,
                        latencyMs: Int,
                        toolsUsed: List<String>,
                        audioBase64: String?
                    ) {
                        restartListening()
                    }
                    override fun onError(message: String) {
                        Log.w(TAG, "Headless voice session error: $message")
                        restartListening()
                    }
                })
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to run headless voice session", e)
            restartListening()
        }
    }

    private fun restartListening() {
        val intent = Intent(this, VertexWakeWordService::class.java).apply {
            action = ACTION_START
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }

    override fun onDestroy() {
        serviceJob.cancel()
        try {
            porcupineManager?.stop()
            porcupineManager?.delete()
        } catch (_: Exception) { }
        porcupineManager = null
        audioSessionHelper.restoreMode()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "VertexWakeWord"
        private const val NOTIFICATION_ID = 9001
        const val ACTION_START = "com.vertex.app.ACTION_START_WAKE_WORD"
        const val ACTION_STOP = "com.vertex.app.ACTION_STOP_WAKE_WORD"
    }
}
