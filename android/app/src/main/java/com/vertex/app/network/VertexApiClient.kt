package com.vertex.app.network

import android.content.Context
import android.provider.Settings
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.vertex.app.BuildConfig
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.BufferedReader
import javax.inject.Inject
import javax.inject.Singleton

sealed class VoiceEvent {
    data class Status(val message: String) : VoiceEvent()
    data class Result(
        val reply: String,
        val toolsUsed: List<String>,
        val sessionId: String?,
        val latencyMs: Int,
        val audioBase64: String?,
    ) : VoiceEvent()
    data class Error(val message: String) : VoiceEvent()
}

@Singleton
class VertexApiClient @Inject constructor(
    private val api: VertexApi,
    private val httpClient: OkHttpClient,
) {
    private var accessToken: String? = null
    private var refreshToken: String? = null
    private val gson = Gson()

    suspend fun ensureAuthenticated(context: Context) {
        if (accessToken != null) return

        val deviceId = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ANDROID_ID,
        )

        val resp = api.registerDevice(DeviceRegisterRequest(deviceId))
        if (resp.isSuccessful) {
            val body = resp.body()!!
            accessToken = body.access_token
            refreshToken = body.refresh_token
        } else {
            throw RuntimeException("Auth failed: ${resp.code()}")
        }
    }

    fun sendVoiceStream(transcript: String, sessionId: String?): Flow<VoiceEvent> = flow {
        val json = gson.toJson(mapOf(
            "transcript" to transcript,
            "session_id" to sessionId,
        ))

        val request = Request.Builder()
            .url("${BuildConfig.DEFAULT_BACKEND_URL}api/v1/voice")
            .addHeader("Authorization", "Bearer $accessToken")
            .post(json.toRequestBody("application/json".toMediaType()))
            .build()

        val response = httpClient.newCall(request).execute()

        if (response.code == 401 && refreshToken != null) {
            val refreshResp = api.refreshTokens(RefreshRequest(refreshToken!!))
            if (refreshResp.isSuccessful) {
                val body = refreshResp.body()!!
                accessToken = body.access_token
                refreshToken = body.refresh_token
            }

            val retryRequest = request.newBuilder()
                .removeHeader("Authorization")
                .addHeader("Authorization", "Bearer $accessToken")
                .build()
            response.close()
            val retryResponse = httpClient.newCall(retryRequest).execute()
            emitEvents(retryResponse.body?.charStream()?.buffered())
            retryResponse.close()
            return@flow
        }

        if (!response.isSuccessful) {
            emit(VoiceEvent.Error("Request failed: ${response.code}"))
            response.close()
            return@flow
        }

        emitEvents(response.body?.charStream()?.buffered())
        response.close()
    }

    suspend fun getPendingEscalations(context: Context): List<EscalationItem> {
        ensureAuthenticated(context)
        val auth = "Bearer $accessToken" ?: return emptyList()
        val resp = api.getPendingEscalations(auth)
        if (!resp.isSuccessful) return emptyList()
        return resp.body()?.pending ?: emptyList()
    }

    suspend fun ackEscalation(context: Context, id: String): Boolean {
        ensureAuthenticated(context)
        val auth = "Bearer $accessToken" ?: return false
        val resp = api.ackEscalation(auth, AckEscalationBody(id))
        return resp.body()?.ok == true
    }

    suspend fun registerFcmToken(context: Context, fcmToken: String): Boolean {
        ensureAuthenticated(context)
        val auth = "Bearer $accessToken" ?: return false
        val resp = api.registerFcmToken(auth, FcmRegisterBody(fcmToken))
        return resp.isSuccessful && (resp.body()?.ok == true)
    }

    private suspend fun kotlinx.coroutines.flow.FlowCollector<VoiceEvent>.emitEvents(reader: BufferedReader?) {
        if (reader == null) {
            emit(VoiceEvent.Error("Empty response"))
            return
        }

        reader.useLines { lines ->
            for (line in lines) {
                if (line.isBlank()) continue
                try {
                    val obj = gson.fromJson(line, JsonObject::class.java)
                    when (obj.get("type")?.asString) {
                        "status" -> emit(VoiceEvent.Status(obj.get("message").asString))
                        "result" -> {
                            val toolsUsed = obj.getAsJsonArray("tools_used")
                                ?.map { it.asString } ?: emptyList()
                            emit(VoiceEvent.Result(
                                reply = obj.get("reply").asString,
                                toolsUsed = toolsUsed,
                                sessionId = obj.get("session_id")?.asString,
                                latencyMs = obj.get("latency_ms")?.asInt ?: 0,
                                audioBase64 = obj.get("audio_base64")?.asString,
                            ))
                        }
                    }
                } catch (e: Exception) {
                    // skip malformed lines
                }
            }
        }
    }
}
