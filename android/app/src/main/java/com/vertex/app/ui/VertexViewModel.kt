package com.vertex.app.ui

import android.app.Application
import android.content.Context
import android.content.Intent
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.google.firebase.messaging.FirebaseMessaging
import com.vertex.app.audio.TextToSpeechEngine
import com.vertex.app.voice.VertexWakeWordService
import com.vertex.app.network.EscalationItem
import com.vertex.app.network.VertexApiClient
import com.vertex.app.service.EscalationNotifier
import com.vertex.app.voice.VoiceSessionCallbacks
import com.vertex.app.voice.VertexVoiceRunner
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.tasks.await
import android.util.Log
import java.util.UUID
import javax.inject.Inject

enum class VertexState {
    IDLE,
    LISTENING,
    PROCESSING,
    SPEAKING,
    ERROR,
}

data class VertexUiState(
    val state: VertexState = VertexState.IDLE,
    val transcript: String = "",
    val statusMessage: String = "Tap to speak",
    val reply: String = "",
    val error: String = "",
    val latencyMs: Int = 0,
    val toolsUsed: List<String> = emptyList(),
    val statusLog: List<String> = emptyList(),
    val isBluetoothActive: Boolean = false,
)

@HiltViewModel
class VertexViewModel @Inject constructor(
    application: Application,
    private val apiClient: VertexApiClient,
    private val ttsEngine: TextToSpeechEngine,
    private val voiceRunner: VertexVoiceRunner,
) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(VertexUiState())
    val uiState: StateFlow<VertexUiState> = _uiState.asStateFlow()

    private val prefs = getApplication<Application>().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    private val _heyVertexEnabled = MutableStateFlow(prefs.getBoolean(KEY_HEY_VERTEX_ENABLED, false))
    val heyVertexEnabled: StateFlow<Boolean> = _heyVertexEnabled.asStateFlow()

    private var sessionId: String? = UUID.randomUUID().toString()

    init {
        if (_heyVertexEnabled.value) {
            startWakeWordService()
        }
    }
    private var currentJob: Job? = null

    fun onMicTap() {
        ttsEngine.stop()
        currentJob?.cancel()
        currentJob = null
        startNewRequest()
    }

    fun onNewChat() {
        ttsEngine.stop()
        currentJob?.cancel()
        currentJob = null
        sessionId = UUID.randomUUID().toString()
        _uiState.value = VertexUiState(
            statusMessage = "New conversation started",
        )
    }

    /** Call when app/screen is visible: register FCM token, fetch pending escalations, show notification + ringer if any, stop ringer when opening app. */
    fun checkEscalation() {
        EscalationNotifier.stopRinger()
        viewModelScope.launch {
            try {
                apiClient.ensureAuthenticated(getApplication())
                withContext(Dispatchers.IO) {
                    val tokenResult = runCatching { FirebaseMessaging.getInstance().token.await() }
                    val token: String? = tokenResult.getOrNull()
                    if (token.isNullOrBlank()) {
                        Log.w(TAG, "checkEscalation: no FCM token (${tokenResult.exceptionOrNull()})")
                    } else {
                        val ok = runCatching { apiClient.registerFcmToken(getApplication(), token!!) }.getOrElse { false }
                        if (ok) Log.d(TAG, "checkEscalation: FCM token registered")
                        else Log.w(TAG, "checkEscalation: FCM token registration failed")
                    }
                }
                val pending = withContext(Dispatchers.IO) {
                    apiClient.getPendingEscalations(getApplication())
                }
                if (pending.isEmpty()) return@launch
                val first = pending.first()
                withContext(Dispatchers.Main) {
                    EscalationNotifier.showNotificationAndStartRinger(
                        getApplication(),
                        first.contact_name ?: "Someone",
                        first.reason ?: "wants you to take over",
                    )
                }
                withContext(Dispatchers.IO) {
                    pending.forEach { item ->
                        (item.id ?: return@forEach).let { id ->
                            apiClient.ackEscalation(getApplication(), id)
                        }
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "checkEscalation failed", e)
            }
        }
    }

    companion object {
        private const val TAG = "VertexVM"
        private const val PREFS_NAME = "vertex_prefs"
        private const val KEY_HEY_VERTEX_ENABLED = "hey_vertex_enabled"
    }

    /** Stops the escalation ringer when user opens the app. */
    fun stopEscalationRinger() {
        EscalationNotifier.stopRinger()
    }

    private fun startNewRequest() {
        currentJob = viewModelScope.launch {
            val callbacks = object : VoiceSessionCallbacks {
                override fun onListening() {
                    _uiState.value = VertexUiState(
                        state = VertexState.LISTENING,
                        statusMessage = "Listening...",
                    )
                }
                override fun onTranscript(transcript: String) {
                    _uiState.value = _uiState.value.copy(
                        statusLog = _uiState.value.statusLog + "Transcribed: \"$transcript\"",
                    )
                }
                override fun onProcessing() {
                    _uiState.value = _uiState.value.copy(
                        state = VertexState.PROCESSING,
                        statusMessage = "Connecting...",
                    )
                }
                override fun onStatus(message: String) {
                    _uiState.value = _uiState.value.copy(
                        statusMessage = message,
                        statusLog = _uiState.value.statusLog + message
                    )
                }
                override fun onAudioSourceChanged(isBluetooth: Boolean) {
                    _uiState.value = _uiState.value.copy(isBluetoothActive = isBluetooth)
                }
                override fun onResult(newSessionId: String?, reply: String, latencyMs: Int, toolsUsed: List<String>, audioBase64: String?) {
                    sessionId = newSessionId
                    _uiState.value = _uiState.value.copy(
                        state = VertexState.SPEAKING,
                        statusMessage = "Speaking...",
                        reply = reply,
                        latencyMs = latencyMs,
                        toolsUsed = toolsUsed,
                        statusLog = _uiState.value.statusLog + "Done in ${latencyMs}ms",
                    )
                    // TTS is played by VertexVoiceRunner
                    _uiState.value = _uiState.value.copy(state = VertexState.IDLE, statusMessage = "")
                    restartHeyVertexIfEnabled()
                }
                override fun onError(message: String) {
                    _uiState.value = _uiState.value.copy(
                        state = VertexState.ERROR,
                        statusMessage = message,
                        error = message,
                    )
                    restartHeyVertexIfEnabled()
                }
            }
            sessionId = voiceRunner.runVoiceSession(sessionId, callbacks, playOpeningPhrase = false)
        }
    }

    /** Entry point for external triggers (e.g. long-press assistant, wake word). Runs the same voice pipeline and updates UI state. */
    fun runVoiceSessionFromExternalTrigger() {
        ttsEngine.stop()
        currentJob?.cancel()
        currentJob = null
        startNewRequest()
    }

    /** After a voice session ends, restart Hey Vertex listener so it can trigger again. */
    private fun restartHeyVertexIfEnabled() {
        if (!_heyVertexEnabled.value) return
        try {
            startWakeWordService()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to restart Hey Vertex", e)
        }
    }

    fun setHeyVertexEnabled(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_HEY_VERTEX_ENABLED, enabled).apply()
        _heyVertexEnabled.value = enabled
        if (enabled) {
            try {
                startWakeWordService()
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start Hey Vertex service", e)
                _heyVertexEnabled.value = false
                prefs.edit().putBoolean(KEY_HEY_VERTEX_ENABLED, false).apply()
            }
        } else {
            val intent = Intent(getApplication(), VertexWakeWordService::class.java).apply {
                action = VertexWakeWordService.ACTION_STOP
            }
            getApplication<Application>().stopService(intent)
        }
    }

    private fun startWakeWordService() {
        val intent = Intent(getApplication(), VertexWakeWordService::class.java).apply {
            action = VertexWakeWordService.ACTION_START
        }
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            getApplication<Application>().startForegroundService(intent)
        } else {
            getApplication<Application>().startService(intent)
        }
    }

    override fun onCleared() {
        super.onCleared()
        EscalationNotifier.stopRinger()
        ttsEngine.shutdown()
    }
}
