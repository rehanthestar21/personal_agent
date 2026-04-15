package com.vertex.app.notifications

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.vertex.app.MainActivity

/**
 * Shows escalation notification and plays alarm ringer. Used by both
 * ViewModel (when app finds pending escalation) and FirebaseMessagingService (when FCM arrives).
 */
object EscalationNotifier {

    private const val CHANNEL_ID = "vertex_escalation"
    private const val NOTIFICATION_ID = 2001
    private const val RINGER_DURATION_MS = 30_000L

    private var mediaPlayer: MediaPlayer? = null
    private val handler = Handler(Looper.getMainLooper())
    private val stopRunnable = Runnable { stopRinger() }

    fun show(context: android.content.Context, contactName: String, reason: String) {
        val name = contactName.takeIf { it.isNotBlank() } ?: "Someone"
        val body = reason.takeIf { it.isNotBlank() } ?: "wants you to take over"
        val title = "$name wants you"
        val text = body.take(100) + " – open WhatsApp"

        val alarmUri: Uri? = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Vertex – someone wants you",
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                setShowBadge(true)
                enableVibration(true)
                if (alarmUri != null) {
                    setSound(
                        alarmUri,
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_ALARM)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                            .build()
                    )
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    setBypassDnd(true)
                }
            }
            (context.getSystemService(NotificationManager::class.java))
                ?.createNotificationChannel(channel)
        }

        val fullScreenIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or
                Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS
        }
        val pendingFullScreen = PendingIntent.getActivity(
            context, 0, fullScreenIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(true)
            .setSound(alarmUri)
            .setVibrate(longArrayOf(0, 500, 200, 500))
            .setFullScreenIntent(pendingFullScreen, true)
            .setTimeoutAfter(60_000)
            .build()

        try {
            NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, notification)
            startRinger(context, alarmUri)
        } catch (_: SecurityException) { }
    }

    private fun startRinger(context: android.content.Context, uri: Uri?) {
        if (uri == null) return
        stopRinger()
        try {
            val player = MediaPlayer().apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build()
                )
                setDataSource(context, uri)
                isLooping = true
                setOnPreparedListener {
                    start()
                    handler.postDelayed(stopRunnable, RINGER_DURATION_MS)
                }
                setOnErrorListener { _, _, _ -> true }
                prepareAsync()
            }
            mediaPlayer = player
        } catch (_: Exception) { }
    }

    fun stopRinger() {
        handler.removeCallbacks(stopRunnable)
        mediaPlayer?.apply {
            try { stop(); release() } catch (_: Exception) { }
        }
        mediaPlayer = null
    }
}
