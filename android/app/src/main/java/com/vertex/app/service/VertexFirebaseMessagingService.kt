package com.vertex.app.service

import android.util.Log
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class VertexFirebaseMessagingService : FirebaseMessagingService() {

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data ?: return
        if (data["type"] != "escalation") return
        val contactName = data["contact_name"] ?: "Someone"
        val reason = data["reason"] ?: "wants you to take over"
        Log.d(TAG, "FCM escalation: $contactName – $reason")
        EscalationNotifier.showNotificationAndStartRinger(this, contactName, reason)
    }

    override fun onNewToken(token: String) {
        Log.d(TAG, "FCM new token")
        // Token will be re-registered when the app next calls checkEscalation / registerFcmToken
    }

    companion object {
        private const val TAG = "VertexFCM"
    }
}
