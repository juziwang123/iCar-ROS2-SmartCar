/**
 * 网络层 — WebSocket 状态推送客户端（Android / Kotlin）
 *
 * 对应鸿蒙端的 StateSocket.ets，
 * 连接 Flask-SocketIO 服务，接收每 200ms 的状态推送。
 *
 * 协议：SocketIO v4（EIO=4, transport=websocket）
 *
 * 依赖: OkHttp WebSocket
 */

package com.icar.musiccar.network

import android.os.Handler
import android.os.Looper
import android.util.Log
import com.icar.musiccar.AppConstants
import okhttp3.*
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class StateSocket {
    companion object {
        private const val TAG = "StateSocket"
    }

    private var ws: WebSocket? = null
    private val client: OkHttpClient
    private var baseUrl: String = "ws://${AppConstants.DEFAULT_CAR_IP}:${AppConstants.DEFAULT_CAR_PORT}"
    private val handler = Handler(Looper.getMainLooper())
    private var reconnectTimer: Runnable? = null
    private var reconnectDelay: Long = 1000     // 初始重连延迟
    private val maxReconnectDelay: Long = 30000 // 最大重连延迟
    private var shouldReconnect: Boolean = false

    /** 状态回调 */
    var onState: ((CarState) -> Unit)? = null
    /** 连接成功回调 */
    var onConnected: (() -> Unit)? = null
    /** 错误回调 */
    var onError: ((String) -> Unit)? = null
    /** 断开回调 */
    var onDisconnected: (() -> Unit)? = null

    init {
        client = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.MILLISECONDS) // 无读取超时
            .build()
    }

    fun setServer(ip: String, port: Int = 5000) {
        baseUrl = "ws://$ip:$port"
    }

    /** 连接 WebSocket */
    fun connect() {
        shouldReconnect = true
        cancelReconnect()

        val url = "$baseUrl/socket.io/?EIO=4&transport=websocket"
        val request = Request.Builder().url(url).build()

        ws = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.d(TAG, "WebSocket 已连接")
                reconnectDelay = 1000 // 重置重连延迟
                handler.post { onConnected?.invoke() }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleMessage(text)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "WebSocket 错误: ${t.message}")
                handler.post { onError?.invoke("WebSocket error: ${t.message}") }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket 已关闭")
                handler.post { onDisconnected?.invoke() }
                if (shouldReconnect) {
                    scheduleReconnect()
                }
            }
        })
    }

    /** 断开连接 */
    fun disconnect() {
        shouldReconnect = false
        cancelReconnect()
        ws?.close(1000, "客户端主动断开")
        ws = null
    }

    /** 发送指令（备用通道，通过 WebSocket 发 cmd 事件） */
    fun sendCmd(cmd: Any) {
        ws?.let { webSocket ->
            // SocketIO 协议: 42["event", data]
            val payload = "42${JSONArray(listOf("cmd", cmd)).toString()}"
            webSocket.send(payload)
        }
    }

    // ── 内部 ──────────────────────────────────

    private fun handleMessage(text: String) {
        try {
            if (text.contains("\"state\"")) {
                // 移除 SocketIO 帧头: 42["state",
                val start = text.indexOf("[{")
                val end = text.lastIndexOf("}]")
                if (start >= 0 && end > start) {
                    val inner = text.substring(start + 1, end + 1)
                    val arr = JSONArray(inner)
                    if (arr.length() >= 2 && arr.getString(0) == "state") {
                        val stateObj = arr.getJSONObject(1)
                        val state = CarState(
                            linear_x = stateObj.getDouble("linear_x"),
                            angular_z = stateObj.getDouble("angular_z"),
                            estop = stateObj.getBoolean("estop"),
                            mode = stateObj.getString("mode"),
                            running_nodes = stateObj.optJSONArray("running_nodes")?.let { nodes ->
                                (0 until nodes.length()).map { nodes.getString(it) }
                            } ?: emptyList()
                        )
                        handler.post { onState?.invoke(state) }
                    }
                }
            }
        } catch (_: Exception) {
            // 静默忽略解析错误
        }
    }

    private fun scheduleReconnect() {
        cancelReconnect()
        reconnectTimer = Runnable {
            Log.i(TAG, "重连中... (延迟 ${reconnectDelay}ms)")
            connect()
            // 指数退避
            reconnectDelay = minOf(reconnectDelay * 2, maxReconnectDelay)
        }
        handler.postDelayed(reconnectTimer!!, reconnectDelay)
    }

    private fun cancelReconnect() {
        reconnectTimer?.let { handler.removeCallbacks(it) }
        reconnectTimer = null
    }
}
