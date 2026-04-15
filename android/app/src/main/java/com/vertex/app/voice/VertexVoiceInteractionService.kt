package com.vertex.app.voice

import android.service.voice.VoiceInteractionService
import android.util.Log

/**
 * Top-level voice interaction service. When the user selects Vertex as the default
 * assistant (Settings > Apps > Default apps > Digital assistant app), the system
 * keeps this service running and delivers push-to-talk (e.g. headset long-press) to us.
 */
class VertexVoiceInteractionService : VoiceInteractionService() {

    override fun onReady() {
        super.onReady()
        Log.d("VertexService", "onReady")
    }

    override fun onShutdown() {
        super.onShutdown()
        Log.d("VertexService", "onShutdown")
    }

    // This is called when the user triggers the assistant (e.g. long-press)
    override fun onLaunchVoiceAssistFromKeyguard() {
        super.onLaunchVoiceAssistFromKeyguard()
        Log.d("VertexService", "onLaunchVoiceAssistFromKeyguard")
        showSession(null, 0)
    }
}
