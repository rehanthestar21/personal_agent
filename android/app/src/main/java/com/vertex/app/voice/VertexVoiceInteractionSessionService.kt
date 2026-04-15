package com.vertex.app.voice

import android.os.Bundle
import android.service.voice.VoiceInteractionSession
import android.service.voice.VoiceInteractionSessionService

/**
 * Creates a voice interaction session when the user triggers the assistant (e.g. long-press on buds).
 * The session runs the Vertex voice pipeline (STT -> API -> TTS).
 */
class VertexVoiceInteractionSessionService : VoiceInteractionSessionService() {

    override fun onNewSession(args: Bundle?): VoiceInteractionSession {
        return VertexVoiceInteractionSession(this)
    }
}
