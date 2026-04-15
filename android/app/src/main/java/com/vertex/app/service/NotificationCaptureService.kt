package com.vertex.app.service

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import com.vertex.app.BuildConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class NotificationCaptureService : NotificationListenerService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .build()

    private val ignoredPackages = setOf(
        "com.vertex.app",
        "android",
        "com.android.systemui",
        "com.android.providers.downloads",
    )

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName in ignoredPackages) return
        if (sbn.isOngoing) return

        val notification = sbn.notification ?: return
        val extras = notification.extras ?: return

        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: ""
        val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: ""
        val bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString()

        if (title.isBlank() && text.isBlank()) return

        val appName = try {
            val pm = packageManager
            val appInfo = pm.getApplicationInfo(sbn.packageName, 0)
            pm.getApplicationLabel(appInfo).toString()
        } catch (e: Exception) {
            sbn.packageName
        }

        val payload = JSONObject().apply {
            put("app", appName)
            put("package", sbn.packageName)
            put("title", title)
            put("text", bigText ?: text)
            put("timestamp", sbn.postTime)
            put("key", sbn.key)
        }

        Log.d("VertexNotif", "Captured: $appName - $title: ${(bigText ?: text).take(50)}")

        scope.launch {
            try {
                val request = Request.Builder()
                    .url("${BuildConfig.DEFAULT_BACKEND_URL}api/v1/notifications")
                    .post(payload.toString().toRequestBody("application/json".toMediaType()))
                    .build()
                httpClient.newCall(request).execute().close()
            } catch (e: Exception) {
                Log.w("VertexNotif", "Failed to send notification to backend", e)
            }
        }
    }
}
