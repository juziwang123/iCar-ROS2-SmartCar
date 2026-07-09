/**
 * 音乐小车 — AI 编舞客户端（Android / Kotlin）
 *
 * 调用小车后端 /api/choreograph/* 接口，实现 AI 生成 + 微调编舞。
 *
 * 依赖: OkHttp + kotlinx.serialization
 */

package com.icar.musiccar.network

import com.icar.musiccar.AppConstants
import com.icar.musiccar.models.ChoreographRequest
import com.icar.musiccar.models.ChoreographResponse
import com.icar.musiccar.models.DanceRoutine
import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

class AIChoreographer {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private var baseUrl: String = "http://${AppConstants.DEFAULT_CAR_IP}:${AppConstants.DEFAULT_CAR_PORT}"
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(AppConstants.LLM_TIMEOUT, TimeUnit.MILLISECONDS)
        .readTimeout(AppConstants.LLM_TIMEOUT, TimeUnit.MILLISECONDS)
        .build()

    fun setServer(ip: String, port: Int) {
        baseUrl = "http://$ip:$port"
    }

    /** AI 生成编舞 */
    suspend fun generate(req: ChoreographRequest): ChoreographResponse {
        return post("/api/choreograph/generate", req)
    }

    /** AI 微调已有编舞 */
    suspend fun refine(routine: DanceRoutine, feedback: String): ChoreographResponse {
        val data = mapOf("routine" to routine, "feedback" to feedback)
        return post("/api/choreograph/refine", data)
    }

    /** 校验编舞合法性（不调 LLM） */
    suspend fun validate(routine: DanceRoutine): ChoreographResponse {
        return post("/api/choreograph/validate", routine)
    }

    /** 查看当前 System Prompt */
    suspend fun getPrompt(): PromptResponse {
        return kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            try {
                val request = Request.Builder()
                    .url("$baseUrl/api/choreograph/prompt")
                    .get()
                    .build()
                val response = client.newCall(request).execute()
                if (response.isSuccessful) {
                    val body = response.body?.string() ?: "{}"
                    json.decodeFromString<PromptResponse>(body)
                } else {
                    PromptResponse(ok = false)
                }
            } catch (_: Exception) {
                PromptResponse(ok = false)
            }
        }
    }

    // -- 内部方法 --

    private suspend fun post(path: String, data: Any): ChoreographResponse {
        val body = json.encodeToString(data).toRequestBody(jsonMediaType)
        val request = Request.Builder()
            .url("$baseUrl$path")
            .post(body)
            .build()

        return kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            try {
                val response = client.newCall(request).execute()
                if (response.isSuccessful) {
                    val bodyStr = response.body?.string() ?: "{}"
                    json.decodeFromString<ChoreographResponse>(bodyStr)
                } else {
                    ChoreographResponse(ok = false, error = "HTTP ${response.code}")
                }
            } catch (e: IOException) {
                ChoreographResponse(ok = false, error = "网络错误: ${e.message}")
            }
        }
    }
}

// -- Prompt 响应 --

data class PromptResponse(
    val ok: Boolean,
    val prompt: String? = null,
    val backend: String? = null
)
