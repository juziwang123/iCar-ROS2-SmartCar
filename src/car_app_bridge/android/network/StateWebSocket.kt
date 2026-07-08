// 网络层 —— WebSocket 客户端
// 接收 state 推送（每 200ms）

package com.icar.app.network

import com.google.gson.Gson
import com.icar.app.network.model.StateResponse
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit

class StateWebSocket(
    private val onState: (StateResponse) -> Unit,
    private val onError: (String) -> Unit
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()
    private var webSocket: WebSocket? = null

    fun connect() {
        val url = ApiClient.baseUrl.replace("http://", "ws://") + "/socket.io/?EIO=4&transport=websocket"
        val request = Request.Builder().url(url).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {}

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    // SocketIO 协议帧解析（简化版）
                    val json = text.trimStart('0', '4', '2', '[').trimEnd(']')
                    val msg = gson.fromJson(json, SocketIOMessage::class.java)
                    if (msg.first == "state" && msg.second != null) {
                        val state = gson.fromJson(gson.toJson(msg.second), StateResponse::class.java)
                        onState(state)
                    }
                } catch (_: Exception) {}
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                onError(t.message ?: "WebSocket disconnected")
            }
        })
    }

    fun disconnect() {
        webSocket?.close(1000, "app closed")
    }

    private data class SocketIOMessage(val first: String, val second: Any?)
}
