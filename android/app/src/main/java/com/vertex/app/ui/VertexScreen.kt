package com.vertex.app.ui

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.vertex.app.R
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.launch
import kotlin.math.cos
import kotlin.math.sin

private val BgCream = Color(0xFFF5F0E6)
private val SurfaceWhite = Color(0xFFFFFDF9)
private val TextDark = Color(0xFF1A1917)
private val TextMuted = Color(0xFF5A564E)
private val TextLight = Color(0xFF8A857A)
private val Sage = Color(0xFF6B7A5D)
private val SageMuted = Color(0x1A6B7A5D)
private val BorderLight = Color(0xFFD5CFC2)
private val ErrorRed = Color(0xFFC44D3A)
private val GainGreen = Color(0xFF3D8A52)

@Composable
fun VertexScreen(viewModel: VertexViewModel = hiltViewModel()) {
    val state by viewModel.uiState.collectAsState()
    val scrollState = rememberScrollState()

    var hasPermission by remember { mutableStateOf(false) }
    val permLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> hasPermission = granted }

    LaunchedEffect(Unit) {
        permLauncher.launch(Manifest.permission.RECORD_AUDIO)
    }

    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            viewModel.checkEscalation()
            awaitCancellation()
        }
    }

    LaunchedEffect(state.statusLog.size) {
        scrollState.animateScrollTo(scrollState.maxValue)
    }

    val infiniteTransition = rememberInfiniteTransition(label = "bg")

    val bgPhase by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 6.2832f,
        animationSpec = infiniteRepeatable(tween(25000, easing = LinearEasing), RepeatMode.Restart),
        label = "bgPhase",
    )

    val pulseScale by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = 1.06f,
        animationSpec = infiniteRepeatable(tween(800), RepeatMode.Reverse),
        label = "pulseScale",
    )

    val ringAlpha by infiniteTransition.animateFloat(
        initialValue = 0.05f,
        targetValue = 0.18f,
        animationSpec = infiniteRepeatable(tween(800), RepeatMode.Reverse),
        label = "ringAlpha",
    )

    val isActive = state.state == VertexState.LISTENING || state.state == VertexState.PROCESSING || state.state == VertexState.SPEAKING

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(BgCream)
            .drawBehind {
                val w = size.width
                val h = size.height

                val x1 = w * 0.3f + cos(bgPhase) * w * 0.25f
                val y1 = h * 0.2f + sin(bgPhase * 0.7f) * h * 0.1f
                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(Color(0x206B7A5D), Color(0x00F5F0E6)),
                        center = Offset(x1, y1),
                        radius = w * 0.5f,
                    ),
                    radius = w * 0.5f,
                    center = Offset(x1, y1),
                )

                val x2 = w * 0.7f + cos(bgPhase * 0.5f + 2f) * w * 0.2f
                val y2 = h * 0.65f + sin(bgPhase * 0.4f + 1f) * h * 0.08f
                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(Color(0x18D4C5A8), Color(0x00F5F0E6)),
                        center = Offset(x2, y2),
                        radius = w * 0.45f,
                    ),
                    radius = w * 0.45f,
                    center = Offset(x2, y2),
                )

                val x3 = w * 0.5f + sin(bgPhase * 0.3f + 4f) * w * 0.3f
                val y3 = h * 0.85f + cos(bgPhase * 0.6f) * h * 0.05f
                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(Color(0x106B7A5D), Color(0x00F5F0E6)),
                        center = Offset(x3, y3),
                        radius = w * 0.35f,
                    ),
                    radius = w * 0.35f,
                    center = Offset(x3, y3),
                )
            }
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .padding(horizontal = 28.dp)
                .verticalScroll(scrollState),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(modifier = Modifier.height(16.dp))

            Box(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.align(Alignment.Center),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        text = "Vertex",
                        color = TextDark,
                        fontSize = 44.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.sp,
                    )

                    Spacer(modifier = Modifier.height(2.dp))

                    Text(
                        text = "personal assistant",
                        color = TextMuted,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        letterSpacing = 4.sp,
                    )
                }

                Text(
                    text = "New",
                    color = Sage,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(top = 8.dp)
                        .background(SageMuted, RoundedCornerShape(10.dp))
                        .border(1.dp, Sage.copy(alpha = 0.3f), RoundedCornerShape(10.dp))
                        .clickable { viewModel.onNewChat() }
                        .padding(horizontal = 14.dp, vertical = 8.dp),
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = stringResource(R.string.hey_vertex_toggle),
                        color = TextDark,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        text = stringResource(R.string.hey_vertex_toggle_summary),
                        color = TextMuted,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Medium,
                    )
                }
                Switch(
                    checked = viewModel.heyVertexEnabled.collectAsState().value,
                    onCheckedChange = { viewModel.setHeyVertexEnabled(it) },
                    colors = SwitchDefaults.colors(
                        checkedThumbColor = Color.White,
                        checkedTrackColor = Sage,
                        uncheckedThumbColor = Color.White,
                        uncheckedTrackColor = BorderLight,
                    ),
                )
            }

            Spacer(modifier = Modifier.height(32.dp))

            Box(contentAlignment = Alignment.Center) {
                if (isActive) {
                    Box(
                        modifier = Modifier
                            .size(210.dp)
                            .clip(CircleShape)
                            .background(Sage.copy(alpha = ringAlpha * 0.3f))
                    )
                    Box(
                        modifier = Modifier
                            .size(180.dp)
                            .clip(CircleShape)
                            .background(Sage.copy(alpha = ringAlpha))
                    )
                }

                Box(
                    modifier = Modifier
                        .size(150.dp)
                        .scale(if (isActive) pulseScale else 1f)
                        .shadow(if (isActive) 24.dp else 10.dp, CircleShape, ambientColor = Sage, spotColor = Sage)
                        .clip(CircleShape)
                        .background(Sage)
                        .clickable(enabled = hasPermission) {
                            viewModel.onMicTap()
                        },
                    contentAlignment = Alignment.Center,
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            text = when (state.state) {
                                VertexState.IDLE -> "Tap"
                                VertexState.LISTENING -> "●"
                                VertexState.PROCESSING -> "···"
                                VertexState.SPEAKING -> "♪"
                                VertexState.ERROR -> "!"
                            },
                            color = Color.White,
                            fontSize = when (state.state) {
                                VertexState.LISTENING -> 48.sp
                                else -> 26.sp
                            },
                            fontWeight = FontWeight.SemiBold,
                            letterSpacing = if (state.state == VertexState.PROCESSING) 4.sp else 1.sp,
                        )
                        if (state.state == VertexState.IDLE) {
                            Text(
                                text = "to speak",
                                color = Color.White.copy(alpha = 0.8f),
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Medium,
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(28.dp))

            if (state.statusMessage.isNotEmpty()) {
                Text(
                    text = state.statusMessage,
                    color = if (state.state == VertexState.ERROR) ErrorRed else TextMuted,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                    textAlign = TextAlign.Center,
                )
            }

            if (state.statusLog.isNotEmpty()) {
                Spacer(modifier = Modifier.height(28.dp))

                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(SurfaceWhite.copy(alpha = 0.88f), shape = RoundedCornerShape(16.dp))
                        .border(1.dp, BorderLight, RoundedCornerShape(16.dp))
                        .padding(18.dp),
                ) {
                    state.statusLog.forEachIndexed { index, logLine ->
                        val isLatest = index == state.statusLog.lastIndex
                        Row(
                            modifier = Modifier.padding(vertical = 4.dp),
                            verticalAlignment = Alignment.Top,
                        ) {
                            Text(
                                text = "›",
                                color = if (isLatest) Sage else TextLight,
                                fontSize = 14.sp,
                                fontFamily = FontFamily.Monospace,
                                fontWeight = FontWeight.Bold,
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Text(
                                text = logLine,
                                color = if (isLatest) TextDark else TextMuted,
                                fontSize = 13.sp,
                                fontWeight = if (isLatest) FontWeight.Bold else FontWeight.Medium,
                                fontFamily = FontFamily.Monospace,
                                lineHeight = 20.sp,
                            )
                        }
                    }
                }
            }

            if (state.reply.isNotEmpty()) {
                Spacer(modifier = Modifier.height(24.dp))

                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(SurfaceWhite.copy(alpha = 0.92f), shape = RoundedCornerShape(16.dp))
                        .border(1.dp, BorderLight, RoundedCornerShape(16.dp))
                        .padding(22.dp),
                ) {
                    Text(
                        text = state.reply,
                        color = TextDark,
                        fontSize = 16.sp,
                        lineHeight = 26.sp,
                        fontWeight = FontWeight.Medium,
                    )
                }
            }

            if (state.latencyMs > 0 && state.state == VertexState.IDLE) {
                Spacer(modifier = Modifier.height(16.dp))
                Row(
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        modifier = Modifier
                            .size(6.dp)
                            .clip(CircleShape)
                            .background(if (state.latencyMs < 5000) GainGreen else TextLight)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = "${state.latencyMs}ms",
                        color = TextLight,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }

            if (state.toolsUsed.isNotEmpty() && state.state == VertexState.IDLE) {
                Spacer(modifier = Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.Center) {
                    state.toolsUsed.toSet().forEach { tool ->
                        val displayName = tool.split("__").firstOrNull() ?: tool
                        Text(
                            text = displayName,
                            color = Sage,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier
                                .background(SageMuted, RoundedCornerShape(8.dp))
                                .padding(horizontal = 10.dp, vertical = 4.dp),
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                    }
                }
            }

            Spacer(modifier = Modifier.height(48.dp))
        }
    }
}
