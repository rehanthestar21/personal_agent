package com.vertex.app.network

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST

data class EscalationItem(
    val id: String?,
    val contact_name: String?,
    val reason: String?,
    val timestamp: Double?,
)

data class PendingEscalationsResponse(val pending: List<EscalationItem> = emptyList())

data class AckEscalationBody(val id: String)

data class VoiceRequest(
    val transcript: String,
    val session_id: String? = null,
)

data class VoiceResponse(
    val reply: String,
    val tools_used: List<String> = emptyList(),
    val session_id: String? = null,
    val latency_ms: Int = 0,
    val audio_base64: String? = null,
)

data class DeviceRegisterRequest(val device_id: String)
data class RefreshRequest(val refresh_token: String)

data class TokenResponse(
    val access_token: String,
    val refresh_token: String,
    val token_type: String,
)

interface VertexApi {

    @POST("/api/v1/voice")
    suspend fun voice(
        @Header("Authorization") auth: String,
        @Body body: VoiceRequest,
    ): Response<VoiceResponse>

    @POST("/api/v1/auth/device")
    suspend fun registerDevice(
        @Body body: DeviceRegisterRequest,
    ): Response<TokenResponse>

    @POST("/api/v1/auth/refresh")
    suspend fun refreshTokens(
        @Body body: RefreshRequest,
    ): Response<TokenResponse>

    @GET("/api/v1/escalation/pending")
    suspend fun getPendingEscalations(
        @Header("Authorization") auth: String,
    ): Response<PendingEscalationsResponse>

    @POST("/api/v1/escalation/ack")
    suspend fun ackEscalation(
        @Header("Authorization") auth: String,
        @Body body: AckEscalationBody,
    ): Response<AckEscalationResponse>

    @POST("/api/v1/fcm/register")
    suspend fun registerFcmToken(
        @Header("Authorization") auth: String,
        @Body body: FcmRegisterBody,
    ): Response<FcmRegisterResponse>
}

data class AckEscalationResponse(val ok: Boolean, val error: String? = null)
data class FcmRegisterBody(val token: String)
data class FcmRegisterResponse(val ok: Boolean, val error: String? = null)
