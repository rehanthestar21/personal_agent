package com.vertex.app.voice

import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import com.vertex.app.MainActivity
import com.vertex.app.di.VertexVoiceRunnerEntryPoint
import dagger.hilt.android.EntryPointAccessors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.launch

/**
 * Handles ACTION_VOICE_COMMAND from Bluetooth headset long-press on devices that broadcast it.
 * Runs the voice session headless (no UI); reply plays through phone/Bud speakers only.
 */
class VoiceCommandActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Ensure the activity can show over the lock screen
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                android.view.WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
            )
        }

        if (Intent.ACTION_VOICE_COMMAND == intent?.action) {
            runVoiceSessionHeadless()
        }
        finish()
    }

    private fun runVoiceSessionHeadless() {
        val intent = Intent(this, VertexVoiceService::class.java).apply {
            action = VertexVoiceService.ACTION_START
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }

    companion object {
        const val EXTRA_START_VOICE_SESSION = "com.vertex.app.START_VOICE_SESSION"
    }
}
