package com.vertex.app.voice

import android.content.Intent
import android.speech.RecognitionService
import android.util.Log

/**
 * Required for the app to show up in the "Digital assistant app" list in Android settings.
 * This service handles the low-level speech recognition requests from the system.
 */
class VertexRecognitionService : RecognitionService() {
    override fun onStartListening(recognizerIntent: Intent?, listener: Callback?) {
        Log.d("VertexRecognition", "onStartListening")
        // We handle our own recognition in the session, but the system needs this service to exist.
    }

    override fun onCancel(listener: Callback?) {
        Log.d("VertexRecognition", "onCancel")
    }

    override fun onStopListening(listener: Callback?) {
        Log.d("VertexRecognition", "onStopListening")
    }
}
