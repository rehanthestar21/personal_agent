package com.vertex.app

import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import com.vertex.app.ui.VertexScreen
import com.vertex.app.ui.VertexViewModel
import com.vertex.app.voice.VoiceCommandActivity
import dagger.hilt.android.AndroidEntryPoint

private val VertexLightScheme = lightColorScheme(
    primary = Color(0xFF6B7A5D),
    secondary = Color(0xFF6B7A5D),
    background = Color(0xFFF5F0E6),
    surface = Color(0xFFFFFDF9),
    onBackground = Color(0xFF1A1917),
    onSurface = Color(0xFF1A1917),
    onPrimary = Color(0xFFF5F0E6),
    error = Color(0xFFC44D3A),
    outline = Color(0xFFD5CFC2),
)

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    private val viewModel: VertexViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (intent?.getBooleanExtra(VoiceCommandActivity.EXTRA_START_VOICE_SESSION, false) == true) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
                setShowWhenLocked(true)
                setTurnScreenOn(true)
            }
        }
        enableEdgeToEdge()
        setContent {
            MaterialTheme(colorScheme = VertexLightScheme) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    VertexScreen()
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (intent?.getBooleanExtra(VoiceCommandActivity.EXTRA_START_VOICE_SESSION, false) == true) {
            intent?.removeExtra(VoiceCommandActivity.EXTRA_START_VOICE_SESSION)
            viewModel.runVoiceSessionFromExternalTrigger()
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
    }
}
