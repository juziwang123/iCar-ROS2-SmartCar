// 网络层 —— HTTP 客户端
// 对应 API: POST /api/cmd, POST /api/process/start, POST /api/process/stop

package com.icar.app.network

import com.google.gson.Gson
import com.icar.app.network.model.ApiResponse
import com.icar.app.network.model.CmdRequest
import com.icar.app.network.model.ProcessRequest
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

object ApiClient {
    private val client = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(3, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()
    private val jsonType = "application/json".toMediaType()

    var baseUrl: String = "http://192.168.1.1:5000"

    fun postCmd(cmd: CmdRequest): Result<ApiResponse> = runCatching {
        val body = gson.toJson(cmd).toRequestBody(jsonType)
        val request = Request.Builder()
            .url("$baseUrl/api/cmd")
            .post(body)
            .build()
        val response = client.newCall(request).execute()
        gson.fromJson(response.body?.string(), ApiResponse::class.java)
    }

    fun startProcess(function: String): Result<ApiResponse> = runCatching {
        val req = ProcessRequest(function)
        val body = gson.toJson(req).toRequestBody(jsonType)
        val request = Request.Builder()
            .url("$baseUrl/api/process/start")
            .post(body)
            .build()
        val response = client.newCall(request).execute()
        gson.fromJson(response.body?.string(), ApiResponse::class.java)
    }

    fun stopProcess(function: String): Result<ApiResponse> = runCatching {
        val req = ProcessRequest(function)
        val body = gson.toJson(req).toRequestBody(jsonType)
        val request = Request.Builder()
            .url("$baseUrl/api/process/stop")
            .post(body)
            .build()
        val response = client.newCall(request).execute()
        gson.fromJson(response.body?.string(), ApiResponse::class.java)
    }
}
