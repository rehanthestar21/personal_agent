package com.vertex.app.audio

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull

private const val TAG = "AudioSessionHelper"

/**
 * Routes audio to the Bluetooth headset for both mic and playback when in a voice session.
 * On Android 11+ uses setCommunicationDevice() to explicitly select the buds. On older
 * devices falls back to SCO (startBluetoothSco / setBluetoothScoOn).
 */
class AudioSessionHelper(private val context: Context) {

    private val audioManager: AudioManager
        get() = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    private var previousMode: Int = -1
    private var scoStarted: Boolean = false
    private var usedCommunicationDeviceApi: Boolean = false
    private var isCallModeActive: Boolean = false

    /**
     * Starts "Call Mode" by setting the communication mode and routing to Bluetooth.
     * Stays in this mode until endCallMode() is called.
     */
    suspend fun startCallMode() = withContext(Dispatchers.IO) {
        if (isCallModeActive) {
            // Re-verify routing even if active, sometimes BT disconnects/reconnects
            Log.d(TAG, "Call mode already active, re-verifying routing")
            routeToBluetooth()
            return@withContext
        }
        
        withContext(Dispatchers.Main) {
            previousMode = audioManager.mode
            // Use MODE_IN_COMMUNICATION to enable SCO/HFP
            audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
        }
        usedCommunicationDeviceApi = false
        scoStarted = false

        routeToBluetooth()
        isCallModeActive = true
    }

    private suspend fun routeToBluetooth() = withContext(Dispatchers.IO) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val devices = audioManager.availableCommunicationDevices
            val bluetooth = devices.firstOrNull { info ->
                info.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO ||
                info.type == AudioDeviceInfo.TYPE_BLE_HEADSET
            }
            if (bluetooth != null) {
                // Force SCO/HFP profile by starting SCO if not already on
                @Suppress("DEPRECATION")
                if (!audioManager.isBluetoothScoOn) {
                    Log.d(TAG, "Starting Bluetooth SCO link...")
                    withContext(Dispatchers.Main) {
                        audioManager.startBluetoothSco()
                    }
                    scoStarted = true
                    val connected = waitForScoConnected(1500)
                    Log.d(TAG, "Bluetooth SCO link connected: $connected")
                }

                withContext(Dispatchers.Main) {
                    val ok = audioManager.setCommunicationDevice(bluetooth)
                    usedCommunicationDeviceApi = ok
                    if (ok) {
                        Log.d(TAG, "Persistent Call Mode: Set communication device to Bluetooth (${bluetooth.productName})")
                        // Force speakerphone OFF to ensure mic/audio goes to BT
                        audioManager.isSpeakerphoneOn = false
                    }
                }
            } else {
                Log.w(TAG, "No Bluetooth communication device found")
            }
        } else {
            @Suppress("DEPRECATION")
            if (!audioManager.isBluetoothScoOn) {
                withContext(Dispatchers.Main) {
                    audioManager.startBluetoothSco()
                }
                scoStarted = true
                waitForScoConnected(1500)
                withContext(Dispatchers.Main) {
                    audioManager.isSpeakerphoneOn = false
                }
            }
        }
    }

    /**
     * Ends "Call Mode" and restores the previous audio state.
     */
    fun endCallMode() {
        if (!isCallModeActive) return
        restoreMode()
        isCallModeActive = false
        Log.d(TAG, "Persistent Call Mode: Ended")
    }

    /**
     * Set communication mode and route to Bluetooth headset when one is connected.
     * On API 31+ explicitly selects the Bluetooth device so the buds' mic is used.
     */
    fun setCommunicationMode() {
        previousMode = audioManager.mode
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
        usedCommunicationDeviceApi = false

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val devices = audioManager.availableCommunicationDevices
            val bluetooth = devices.firstOrNull { info ->
                info.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO ||
                info.type == AudioDeviceInfo.TYPE_BLE_HEADSET
            }
            if (bluetooth != null) {
                val ok = audioManager.setCommunicationDevice(bluetooth)
                usedCommunicationDeviceApi = ok
            }
            return
        }
        @Suppress("DEPRECATION")
        run {
            if (!audioManager.isBluetoothScoOn) {
                audioManager.startBluetoothSco()
                scoStarted = true
            }
        }
    }

    /**
     * Wait for Bluetooth SCO to be connected (API < 31 only). No-op on API 31+.
     */
    @Suppress("DEPRECATION")
    suspend fun waitForScoConnected(timeoutMs: Long = 3000): Boolean = withContext(Dispatchers.IO) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) return@withContext true
        if (audioManager.isBluetoothScoOn) return@withContext true
        val channel = Channel<Boolean>(Channel.CONFLATED)
        var receiver: BroadcastReceiver? = null
        try {
            receiver = object : BroadcastReceiver() {
                override fun onReceive(ctx: Context?, intent: Intent?) {
                    if (intent?.action != AudioManager.ACTION_SCO_AUDIO_STATE_UPDATED) return
                    val state = intent.getIntExtra(AudioManager.EXTRA_SCO_AUDIO_STATE, -1)
                    if (state == AudioManager.SCO_AUDIO_STATE_CONNECTED) {
                        try {
                            audioManager.setBluetoothScoOn(true)
                        } catch (_: Exception) { }
                        channel.trySend(true)
                    }
                }
            }
            val filter = IntentFilter(AudioManager.ACTION_SCO_AUDIO_STATE_UPDATED)
            withContext(Dispatchers.Main) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    context.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED)
                } else {
                    context.registerReceiver(receiver, filter)
                }
            }
            withTimeoutOrNull(timeoutMs) { channel.receive() } ?: false
        } finally {
            receiver?.let {
                try {
                    withContext(Dispatchers.Main) {
                        context.unregisterReceiver(it)
                    }
                } catch (_: Exception) { }
            }
        }
    }

    fun restoreMode() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && usedCommunicationDeviceApi) {
            try {
                audioManager.clearCommunicationDevice()
            } catch (_: Exception) { }
            usedCommunicationDeviceApi = false
        }
        @Suppress("DEPRECATION")
        fun restoreSco() {
            try {
                audioManager.setBluetoothScoOn(false)
            } catch (_: Exception) { }
            if (scoStarted) {
                try {
                    audioManager.stopBluetoothSco()
                } catch (_: Exception) { }
                scoStarted = false
            }
        }
        restoreSco()
        if (previousMode >= 0) {
            audioManager.mode = previousMode
            previousMode = -1
        }
    }

    fun isBluetoothActive(): Boolean {
        @Suppress("DEPRECATION")
        return audioManager.isBluetoothScoOn || audioManager.isBluetoothA2dpOn
    }

    /**
     * Re-applies Bluetooth as the communication device. Call this before each STT listen
     * in a continuous session so the mic stays on the earbuds after TTS or other audio
     * has finished (Android can revert to the phone mic otherwise).
     */
    suspend fun ensureBluetoothRouting() = withContext(Dispatchers.Main) {
        if (!isCallModeActive) return@withContext
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val devices = audioManager.availableCommunicationDevices
            val bluetooth = devices.firstOrNull { info ->
                info.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO ||
                info.type == AudioDeviceInfo.TYPE_BLE_HEADSET
            }
            if (bluetooth != null) {
                val ok = audioManager.setCommunicationDevice(bluetooth)
                if (ok) {
                    Log.d(TAG, "Re-applied communication device to Bluetooth (${bluetooth.productName})")
                    audioManager.isSpeakerphoneOn = false
                }
            }
        } else {
            @Suppress("DEPRECATION")
            run {
                audioManager.isSpeakerphoneOn = false
                if (!audioManager.isBluetoothScoOn && audioManager.isBluetoothA2dpOn) {
                    audioManager.startBluetoothSco()
                }
            }
        }
    }
}
