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
import com.vertex.app.MainActivity
import com.vertex.app.R
import com.vertex.app.di.VertexVoiceRunnerEntryPoint
import dagger.hilt.android.EntryPointAccessors
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/**
 * Foreground service that maintains a continuous voice session ("Call Mode").
 * This ensures the app isn't throttled or killed by Android while Vertex is "on the line."
 */
class VertexVoiceService : Service() {

    private val serviceJob = Job()
    private val scope = CoroutineScope(Dispatchers.Main + serviceJob)
    private var isRunning = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }

        // Immediate feedback
        try {
            val vibrator = getSystemService(NOTIFICATION_SERVICE) as android.os.Vibrator
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                vibrator.vibrate(android.os.VibrationEffect.createOneShot(100, android.os.VibrationEffect.DEFAULT_AMPLITUDE))
            } else {
                @Suppress("DEPRECATION")
                vibrator.vibrate(100)
            }
        } catch (_: Exception) {}

        if (!isRunning) {
            startForegroundService()
            runContinuousSession()
        } else {
            // If already running, ensure we are listening and not stuck in a state
            Log.d(TAG, "Service already running, ignoring start request")
        }
        return START_STICKY
    }

    private fun startForegroundService() {
        val channelId = "vertex_voice_session"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Vertex Voice Session",
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
            .setContentTitle("Vertex is active")
            .setContentText("Listening via Bluetooth...")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
        isRunning = true
    }

    private fun runContinuousSession() {
        try {
            val entryPoint = EntryPointAccessors.fromApplication(
                applicationContext,
                VertexVoiceRunnerEntryPoint::class.java
            )
            val runner = entryPoint.vertexVoiceRunner()
            scope.launch {
                Log.d(TAG, "Starting continuous voice session in foreground service")
                runner.startContinuousSession(null, object : VoiceSessionCallbacks {
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
                    ) {}
                    override fun onError(message: String) {
                        Log.e(TAG, "Continuous session error: $message")
                    }
                })
                Log.d(TAG, "Continuous session ended, stopping service")
                stopSelf()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start continuous session", e)
            stopSelf()
        }
    }

    override fun onDestroy() {
        serviceJob.cancel()
        isRunning = false
        super.onDestroy()
    }

    companion object {
        private const val TAG = "VertexVoiceService"
        private const val NOTIFICATION_ID = 9002
        const val ACTION_START = "com.vertex.app.ACTION_START_VOICE_SERVICE"
        const val ACTION_STOP = "com.vertex.app.ACTION_STOP_VOICE_SERVICE"
    }
}
