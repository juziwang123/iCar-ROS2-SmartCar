/**
 * 网络层 — HTTP 客户端（Android / Kotlin）
 *
 * 对应鸿蒙端的 ApiClient.ets，严格复用 APP接口文档.md 的 HTTP 接口。
 *
 * 依赖: OkHttp + kotlinx.serialization
 *
 * 接口：
 *   POST /api/cmd              — 控制指令
 *   POST /api/process/start    — 启动功能节点
 *   POST /api/process/stop     — 停止功能节点
 *   GET  /api/state            — 获取状态（一次性快照）
 */

package com.icar.musiccar.network

import com.icar.musiccar.AppConstants
import com.icar.musiccar.models.CmdRequest
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

// ── 数据模型 ──────────────────────────────────────

@Serializable
data class ApiResponse(
    val ok: Boolean,
    val error: String? = null,
    val pid: Int? = null
)

@Serializable
data class CarState(
    val linear_x: Double,
    val angular_z: Double,
    val estop: Boolean,
    val mode: String,
    val running_nodes: List<String> = emptyList()
)

@Serializable
data class ProcessRequest(
    val function: String
)

// ── HTTP 客户端 ───────────────────────────────────

class ApiClient {
    companion object {
        @Volatile
        private var instance: ApiClient? = null

        fun getInstance(): ApiClient {
            return instance ?: synchronized(this) {
                instance ?: ApiClient().also { instance = it }
            }
        }
    }

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val client: OkHttpClient
    private var baseUrl: String = "http://${AppConstants.DEFAULT_CAR_IP}:${AppConstants.DEFAULT_CAR_PORT}"
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    init {
        client = OkHttpClient.Builder()
            .connectTimeout(AppConstants.HTTP_TIMEOUT, TimeUnit.MILLISECONDS)
            .readTimeout(AppConstants.HTTP_TIMEOUT, TimeUnit.MILLISECONDS)
            .build()
    }

    /** 设置小车地址 */
    fun setServer(ip: String, port: Int = 5000) {
        baseUrl = "http://$ip:$port"
    }

    // ── 公开接口 ────────────────────────────────

    /** 发送控制指令 */
    suspend fun postCmd(cmd: CmdRequest): ApiResponse {
        return post("/api/cmd", cmd)
    }

    /** 启动功能节点 */
    suspend fun startProcess(funcName: String): ApiResponse {
        return post("/api/process/start", ProcessRequest(funcName))
    }

    /** 停止功能节点 */
    suspend fun stopProcess(funcName: String): ApiResponse {
        return post("/api/process/stop", ProcessRequest(funcName))
    }

    /** 获取小车状态（一次性快照） */
    suspend fun getState(): CarState {
        val request = Request.Builder()
            .url("$baseUrl/api/state")
            .get()
            .build()

        return withIO {
            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                val body = response.body?.string() ?: throw IOException("空响应")
                json.decodeFromString<CarState>(body)
            } else {
                throw IOException("HTTP ${response.code}")
            }
        }
    }

    /** 测试连通性 */
    suspend fun ping(): Boolean {
        return try {
            getState()
            true
        } catch (_: Exception) {
            false
        }
    }

    // ── 内部方法 ────────────────────────────────

    private suspend fun post(path: String, data: Any): ApiResponse {
        val body = json.encodeToString(data).toRequestBody(jsonMediaType)
        val request = Request.Builder()
            .url("$baseUrl$path")
            .post(body)
            .build()

        return withIO {
            try {
                val response = client.newCall(request).execute()
                if (response.isSuccessful) {
                    val bodyStr = response.body?.string() ?: "{}"
                    json.decodeFromString<ApiResponse>(bodyStr)
                } else {
                    ApiResponse(ok = false, error = "HTTP ${response.code}")
                }
            } catch (e: IOException) {
                ApiResponse(ok = false, error = "网络错误: ${e.message}")
            }
        }
    }

    private suspend fun <T> withIO(block: () -> T): T {
        return kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            block()
        }
    }
}
