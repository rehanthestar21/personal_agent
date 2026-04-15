package com.vertex.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import com.vertex.app.voice.VertexWakeWordService

/**
 * Starts the Hey Vertex wake word service after device boot if the user had it enabled.
 * Ensures "Hey Vertex" works when the phone is on the desk without opening the app first.
 */
class VertexBootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        if (!prefs.getBoolean(KEY_HEY_VERTEX_ENABLED, false)) return
        try {
            val serviceIntent = Intent(context, VertexWakeWordService::class.java).apply {
                action = VertexWakeWordService.ACTION_START
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent)
            } else {
                context.startService(serviceIntent)
            }
            Log.d(TAG, "Hey Vertex service started after boot")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start Hey Vertex after boot", e)
        }
    }

    companion object {
        private const val TAG = "VertexBootReceiver"
        private const val PREFS_NAME = "vertex_prefs"
        private const val KEY_HEY_VERTEX_ENABLED = "hey_vertex_enabled"
    }
}
