// Android APP 网络数据模型
// 严格对应 docs/APP接口文档.md

package com.icar.app.network.model

import com.google.gson.annotations.SerializedName

// ── 请求 ──────────────────────────────────────────
data class CmdRequest(
    val type: String,                        // move / stop / mode / estop
    val linear: Double? = null,              // move 时必填
    val angular: Double? = null,             // move 时必填
    val mode: String? = null,                // mode 时必填: manual/nav/vision/follow
    val active: Boolean? = null              // estop 时必填
)

data class ProcessRequest(
    val function: String                     // mapping / nav_bringup / avoidance 等
)

// ── 响应 ──────────────────────────────────────────
data class ApiResponse(
    val ok: Boolean,
    val error: String? = null,
    val pid: Int? = null
)

data class StateResponse(
    val mode: String,
    val estop: Boolean,
    @SerializedName("linear_x") val linearX: Double,
    @SerializedName("angular_z") val angularZ: Double,
    @SerializedName("running_nodes") val runningNodes: List<String>
)
