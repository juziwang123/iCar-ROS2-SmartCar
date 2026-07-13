package com.icar.musiccar

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.MotionEvent
import android.view.View
import android.widget.EditText
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.google.android.material.button.MaterialButton
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.atomic.AtomicLong

/**
 * Android client for the protocol implemented by main/src/car_app_bridge.
 * Every command in this activity is part of that bridge's v3 capability set.
 */
class MainActivity : AppCompatActivity() {
    private data class Motion(val linearFactor: Double, val angularFactor: Double, val label: String)

    private val mainHandler = Handler(Looper.getMainLooper())
    private val requestIds = AtomicLong()
    private var client: TcpJsonLineClient? = null
    private var connected = false
    private var awaitingHello = true
    private var leaseId: String? = null
    private var leaseExpiresAt = 0L
    private var acquiringLease = false
    private var activeMotion: Motion? = null
    private var pendingMotion: Motion? = null
    private var heartbeatRunning = false
    private var runtimeProfile = "idle"
    private var runtimeReady = false
    private var currentMissionId: String? = null
    private var missionState = "idle"
    private var selectedTrackId: String? = null
    private var activeFollowTrackId: String? = null
    private var pendingNavigation = false
    private var pendingMissionStart = false
    private var maxLinear = 0.4
    private var maxAngular = 1.2
    private val commands = mutableSetOf<String>()
    private val mapIds = mutableListOf<String>()
    private val routeIds = mutableListOf<String>()

    private lateinit var statusText: TextView
    private lateinit var lastCommandText: TextView
    private lateinit var speedText: TextView
    private lateinit var guardStatusText: TextView
    private lateinit var missionDetailText: TextView
    private lateinit var alertLevelText: TextView
    private lateinit var alertDetailText: TextView
    private lateinit var hostInput: EditText
    private lateinit var portInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var mapIdInput: EditText
    private lateinit var routeIdInput: EditText
    private lateinit var navXInput: EditText
    private lateinit var navYInput: EditText
    private lateinit var navYawInput: EditText
    private lateinit var connectButton: MaterialButton
    private lateinit var mappingButton: MaterialButton
    private lateinit var navigationButton: MaterialButton
    private lateinit var navGoalButton: MaterialButton
    private lateinit var initialPoseButton: MaterialButton
    private lateinit var navCancelButton: MaterialButton
    private lateinit var trackingButton: MaterialButton
    private lateinit var saveMapButton: MaterialButton
    private lateinit var guardStartButton: MaterialButton
    private lateinit var guardResumeButton: MaterialButton
    private lateinit var guardStopButton: MaterialButton
    private lateinit var missionRefreshButton: MaterialButton
    private lateinit var missionRecoveryButton: MaterialButton
    private lateinit var alertAcknowledgeButton: MaterialButton
    private lateinit var stopButton: MaterialButton
    private val motionButtons = mutableListOf<MaterialButton>()

    private val heartbeat = object : Runnable {
        override fun run() {
            val heldLease = leaseId
            if (!connected || heldLease == null || activeMotion == null) {
                heartbeatRunning = false
                return
            }
            sendRequest("teleop_heartbeat", "lease_id" to heldLease)
            sendMove(activeMotion!!)
            mainHandler.postDelayed(this, HEARTBEAT_MS)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.activity_main)
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.main)) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        bindViews()
        bindActions()
        updateUi()
    }

    override fun onDestroy() {
        stopMotion(releaseLease = true)
        client?.close()
        mainHandler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    private fun bindViews() {
        statusText = findViewById(R.id.statusText)
        lastCommandText = findViewById(R.id.lastCommandText)
        speedText = findViewById(R.id.speedText)
        guardStatusText = findViewById(R.id.guardStatusText)
        missionDetailText = findViewById(R.id.missionDetailText)
        alertLevelText = findViewById(R.id.alertLevelText)
        alertDetailText = findViewById(R.id.alertDetailText)
        hostInput = findViewById(R.id.hostInput)
        portInput = findViewById(R.id.portInput)
        tokenInput = findViewById(R.id.tokenInput)
        mapIdInput = findViewById(R.id.mapIdInput)
        routeIdInput = findViewById(R.id.routeIdInput)
        navXInput = findViewById(R.id.navXInput)
        navYInput = findViewById(R.id.navYInput)
        navYawInput = findViewById(R.id.navYawInput)
        connectButton = findViewById(R.id.connectButton)
        mappingButton = findViewById(R.id.mappingButton)
        navigationButton = findViewById(R.id.navigationButton)
        navGoalButton = findViewById(R.id.navGoalButton)
        initialPoseButton = findViewById(R.id.initialPoseButton)
        navCancelButton = findViewById(R.id.navCancelButton)
        trackingButton = findViewById(R.id.trackingButton)
        saveMapButton = findViewById(R.id.saveMapButton)
        guardStartButton = findViewById(R.id.guardStartButton)
        guardResumeButton = findViewById(R.id.guardResumeButton)
        guardStopButton = findViewById(R.id.guardStopButton)
        missionRefreshButton = findViewById(R.id.missionRefreshButton)
        missionRecoveryButton = findViewById(R.id.missionRecoveryButton)
        alertAcknowledgeButton = findViewById(R.id.alertAcknowledgeButton)
        stopButton = findViewById(R.id.stopButton)
        motionButtons += listOf(
            findViewById(R.id.forwardLeftButton), findViewById(R.id.forwardButton),
            findViewById(R.id.forwardRightButton), findViewById(R.id.backwardButton),
            findViewById(R.id.leftButton), findViewById(R.id.rightButton)
        )
    }

    private fun bindActions() {
        connectButton.setOnClickListener { if (connected) disconnect() else connect() }
        bindMotionButton(findViewById(R.id.forwardLeftButton), Motion(1.0, 0.65, "左前行驶"))
        bindMotionButton(findViewById(R.id.forwardButton), Motion(1.0, 0.0, "前进"))
        bindMotionButton(findViewById(R.id.forwardRightButton), Motion(1.0, -0.65, "右前行驶"))
        bindMotionButton(findViewById(R.id.backwardButton), Motion(-0.7, 0.0, "后退"))
        bindMotionButton(findViewById(R.id.leftButton), Motion(0.0, 1.0, "左转"))
        bindMotionButton(findViewById(R.id.rightButton), Motion(0.0, -1.0, "右转"))
        stopButton.setOnClickListener { stopMotion(releaseLease = true) }
        findViewById<MaterialButton>(R.id.emergencyButton).setOnClickListener {
            stopMotion(releaseLease = true); sendRequest("estop", "active" to true)
        }
        findViewById<MaterialButton>(R.id.clearEmergencyButton).setOnClickListener {
            sendRequest("estop", "active" to false)
        }
        mappingButton.setOnClickListener { requestRuntime("mapping") }
        saveMapButton.setOnClickListener { saveMap() }
        navigationButton.setOnClickListener { requestNavigation() }
        navGoalButton.setOnClickListener { sendNavigationGoal() }
        initialPoseButton.setOnClickListener { sendInitialPose() }
        navCancelButton.setOnClickListener { if (requireCommand("nav_cancel")) sendRequest("nav_cancel") }
        trackingButton.setOnClickListener { toggleFollow() }
        guardStartButton.setOnClickListener { startMission() }
        guardResumeButton.setOnClickListener { toggleMissionPause() }
        guardStopButton.setOnClickListener { cancelMission() }
        missionRefreshButton.setOnClickListener { refreshMissionRecords() }
        missionRecoveryButton.setOnClickListener { requestMissionRecoveries() }
        alertAcknowledgeButton.setOnClickListener { acknowledgeAlert() }
        findViewById<SeekBar>(R.id.speedSlider).setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar, progress: Int, fromUser: Boolean) {
                val ratio = (progress.coerceAtLeast(10) / 100.0)
                maxLinear = 0.65 * ratio
                maxAngular = 2.0 * ratio
                speedText.text = "速度 $progress%（线速度 %.2f m/s）".format(maxLinear)
            }
            override fun onStartTrackingTouch(seekBar: SeekBar) = Unit
            override fun onStopTrackingTouch(seekBar: SeekBar) = Unit
        })
    }

    private fun bindMotionButton(button: MaterialButton, motion: Motion) {
        button.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> startMotion(motion)
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> stopMotion(releaseLease = false)
            }
            true
        }
    }

    private fun connect() {
        val host = hostInput.text.toString().trim()
        val port = portInput.text.toString().toIntOrNull()
        if (host.isEmpty() || port == null || port !in 1..65535) {
            toast("请填写有效的小车 IP 和端口")
            return
        }
        disconnect(silent = true)
        awaitingHello = true
        statusText.text = "正在连接 $host:$port…"
        client = TcpJsonLineClient(
            onConnected = { runOnUiThread { statusText.text = "传输层已连接，等待桥接协议握手…" } },
            onMessage = { line -> runOnUiThread { handleMessage(line) } },
            onClosed = { error -> runOnUiThread { handleClosed(error) } }
        ).also { it.connect(host, port) }
        updateUi()
    }

    private fun disconnect(silent: Boolean = false) {
        stopMotion(releaseLease = true)
        client?.close()
        client = null
        connected = false
        commands.clear()
        if (!silent) lastCommandText.text = "控制通道已断开"
        updateUi()
    }

    private fun handleClosed(error: Throwable?) {
        if (!connected && client == null) return
        connected = false
        leaseId = null
        activeMotion = null
        statusText.text = if (error == null) "连接已关闭" else "连接已关闭：${error.message ?: error.javaClass.simpleName}"
        updateUi()
    }

    private fun handleMessage(line: String) {
        val message = try { JSONObject(line) } catch (_: Exception) { return }
        when (message.optString("type")) {
            "hello" -> handleHello(message)
            "response" -> handleResponse(message)
            "event" -> handleEvent(message)
        }
    }

    private fun handleHello(hello: JSONObject) {
        if (hello.optInt("protocol_version", -1) != 3) {
            statusText.text = "不支持的小车桥接协议版本"
            client?.close(); return
        }
        if (hello.optBoolean("authentication_required", false)) {
            val token = tokenInput.text.toString().trim()
            if (token.isEmpty()) { toast("小车要求控制令牌"); return }
            sendRequest("auth", "token" to token)
        } else finishHandshake()
    }

    private fun finishHandshake() {
        if (!awaitingHello) return
        awaitingHello = false
        connected = true
        statusText.text = "已连接 main 桥接协议 v3"
        sendRequest("capabilities")
        sendRequest("subscribe", "channels" to JSONArray(listOf("status", "lidar", "vision", "navigation", "mission", "inspection", "event", "control_lease", "runtime")))
        sendRequest("status")
        sendRequest("runtime_status")
        sendRequest("map_list")
        sendRequest("route_list")
        updateUi()
    }

    private fun handleResponse(response: JSONObject) {
        val command = response.optString("cmd")
        if (!response.optBoolean("ok", false)) {
            val error = response.optString("error", "未知错误")
            if (command == "teleop_acquire" || (command == "move" && error.contains("lease", true))) clearLease()
            lastCommandText.text = "$command 被小车拒绝：$error"
            toast("小车拒绝指令：$error")
            updateUi()
            return
        }
        val data = response.optJSONObject("data") ?: JSONObject()
        when (command) {
            "auth" -> finishHandshake()
            "capabilities" -> {
                val array = data.optJSONArray("commands")
                commands.clear()
                for (index in 0 until (array?.length() ?: 0)) commands += array!!.optString(index)
                lastCommandText.text = "桥接能力已同步：${commands.size} 项"
            }
            "status" -> applyStatus(data)
            "runtime_status", "runtime_switch" -> applyRuntime(data)
            "map_list" -> {
                replaceIds(mapIds, data.optJSONArray("maps"), "map_id", "id", "name")
                if (mapIdInput.text.isNullOrBlank() && mapIds.isNotEmpty()) mapIdInput.setText(mapIds.first())
            }
            "route_list" -> {
                replaceIds(routeIds, data.optJSONArray("routes"), "route_id", "id", "name")
                if (routeIdInput.text.isNullOrBlank() && routeIds.isNotEmpty()) routeIdInput.setText(routeIds.first())
            }
            "map_save" -> { data.optString("map_id").takeIf { it.isNotBlank() }?.let { if (it !in mapIds) mapIds += it }; lastCommandText.text = "地图已保存" }
            "teleop_acquire" -> {
                leaseId = data.optString("lease_id").takeIf { it.isNotBlank() }
                leaseExpiresAt = SystemClock.elapsedRealtime() + data.optLong("expires_in_sec", 3) * 1000L
                acquiringLease = false
                pendingMotion?.let { beginMotionWithLease(it) }
                pendingMotion = null
            }
            "teleop_release" -> clearLease()
            "nav_goal" -> lastCommandText.text = "导航目标已发送，等待 navigation 事件"
            "nav_cancel" -> lastCommandText.text = "已请求取消导航目标"
            "initial_pose" -> lastCommandText.text = "初始位姿已发布给 AMCL"
            "follow_person" -> { activeFollowTrackId = data.optString("track_id").ifBlank { selectedTrackId }; lastCommandText.text = "已启动人员跟随" }
            "stop_follow" -> { activeFollowTrackId = null; lastCommandText.text = "已停止人员跟随" }
            "mission_start" -> { currentMissionId = data.optString("mission_id").ifBlank { currentMissionId }; lastCommandText.text = "巡检任务已启动" }
            "mission_pause", "mission_resume", "mission_cancel" -> lastCommandText.text = "$command 已执行"
            "mission_checkins" -> showCheckins(data.optJSONArray("checkins"))
            "mission_inspections" -> showInspections(data.optJSONArray("inspections"))
            "mission_report" -> showMissionReport(data.optJSONObject("report"))
            "mission_recoveries" -> showMissionRecoveries(data.optJSONArray("missions"))
            "estop" -> lastCommandText.text = if (data.optBoolean("active", false)) "急停已开启" else "急停已解除"
        }
        updateUi()
    }

    private fun handleEvent(event: JSONObject) {
        val channel = event.optString("channel")
        val data = event.optJSONObject("data") ?: return
        when (channel) {
            "status" -> applyStatus(data)
            "runtime" -> applyRuntime(data)
            "lidar" -> applyLidar(data)
            "vision" -> applyVision(data)
            "mission" -> applyMission(data)
            "inspection" -> applyInspection(data)
            "event" -> applyAlert(data)
            "navigation" -> lastCommandText.text = "导航：${data.optString("state", data.optString("status", "运行中"))}"
            "control_lease" -> if (data.optBoolean("expired", false)) clearLease()
        }
        updateUi()
    }

    private fun applyStatus(data: JSONObject) {
        data.optJSONObject("runtime")?.let { applyRuntime(it) }
        data.optJSONObject("mission")?.let { applyMission(it) }
        data.optJSONObject("lidar")?.let { applyLidar(it) }
    }

    private fun applyRuntime(data: JSONObject) {
        runtimeProfile = data.optString("profile", runtimeProfile)
        val state = data.optString("state", data.optString("status", ""))
        runtimeReady = data.optBoolean("ready", state.equals("READY", true) || state.equals("ready", true))
        if (runtimeReady && pendingNavigation) { pendingNavigation = false; requestNavigation() }
        if (runtimeReady && pendingMissionStart) { pendingMissionStart = false; startMission() }
        statusText.text = "已连接｜运行态：$runtimeProfile ${if (runtimeReady) "就绪" else state}"
    }

    private fun applyLidar(data: JSONObject) {
        val blocked = data.optBoolean("blocked", data.optBoolean("override_active", false))
        if (blocked) {
            alertLevelText.text = "安全保护"
            alertDetailText.text = "激光雷达安全层正在限速或急停（由小车端 safety mux 决定）"
        }
    }

    private fun applyVision(data: JSONObject) {
        val tracks = data.optJSONArray("tracks") ?: data.optJSONArray("persons")
        for (i in 0 until (tracks?.length() ?: 0)) {
            val track = tracks!!.optJSONObject(i) ?: continue
            val id = track.optString("track_id", track.optString("id"))
            if (id.isNotBlank()) { selectedTrackId = id; return }
        }
    }

    private fun applyMission(data: JSONObject) {
        currentMissionId = data.optString("mission_id", currentMissionId ?: "").ifBlank { currentMissionId }
        missionState = data.optString("state", data.optString("status", missionState))
        guardStatusText.text = "巡检：$missionState${currentMissionId?.let { "（$it）" } ?: ""}"
        val checkpoint = data.optString("checkpoint_id", data.optString("current_checkpoint_id", ""))
        val next = data.optString("next_checkpoint_id", "")
        val index = data.optInt("current_checkpoint_index", -1)
        val total = data.optInt("checkpoint_count", data.optInt("total_checkpoints", -1))
        val progress = when {
            index >= 0 && total > 0 -> "第 ${index + 1}/$total 站"
            checkpoint.isNotBlank() -> "当前站：$checkpoint"
            else -> "P1 → P2 → P3"
        }
        val detail = data.optString("detail", data.optString("message", ""))
        missionDetailText.text = listOf(progress, checkpoint.takeIf { it.isNotBlank() }?.let { "当前 $it" }, next.takeIf { it.isNotBlank() }?.let { "下一站 $it" }, detail.takeIf { it.isNotBlank() }).filterNotNull().joinToString("｜")
    }

    private fun applyInspection(data: JSONObject) {
        val checkpoint = data.optString("checkpoint_id", "检查点")
        val conclusion = data.optString("conclusion", "UNKNOWN")
        val needsReview = data.optBoolean("needs_human_review", false) || conclusion == "UNKNOWN" || conclusion == "NEEDS_HUMAN_REVIEW"
        missionDetailText.text = if (needsReview) "$checkpoint 巡检结论：$conclusion（待人工处理）" else "$checkpoint 巡检结论：$conclusion"
        if (needsReview) {
            alertLevelText.text = "待人工处理"
            alertDetailText.text = data.optString("detail", "$checkpoint 的巡检结果需要复核")
        }
    }

    private fun applyAlert(data: JSONObject) {
        val level = data.optString("level", data.optString("severity", "信息"))
        alertLevelText.text = level
        alertDetailText.text = data.optString("message", data.optString("detail", data.toString()))
    }

    private fun startMotion(motion: Motion) {
        if (!connected || "move" !in commands || "teleop_acquire" !in commands) { toast("当前桥接未提供手动控制能力"); return }
        if (leaseId == null || SystemClock.elapsedRealtime() >= leaseExpiresAt) {
            pendingMotion = motion
            if (!acquiringLease) { acquiringLease = true; sendRequest("teleop_acquire") }
            return
        }
        beginMotionWithLease(motion)
    }

    private fun beginMotionWithLease(motion: Motion) {
        activeMotion = motion
        sendMove(motion)
        if (!heartbeatRunning) { heartbeatRunning = true; mainHandler.postDelayed(heartbeat, HEARTBEAT_MS) }
        lastCommandText.text = "手动控制：${motion.label}（按住持续，松手停止）"
    }

    private fun sendMove(motion: Motion) {
        val heldLease = leaseId ?: return
        sendRequest("move", "linear" to motion.linearFactor * maxLinear, "angular" to motion.angularFactor * maxAngular, "lease_id" to heldLease)
    }

    private fun stopMotion(releaseLease: Boolean) {
        val heldLease = leaseId
        activeMotion = null
        pendingMotion = null
        mainHandler.removeCallbacks(heartbeat)
        heartbeatRunning = false
        if (heldLease != null && connected) {
            sendRequest("move", "linear" to 0.0, "angular" to 0.0, "lease_id" to heldLease)
            if (releaseLease) sendRequest("teleop_release", "lease_id" to heldLease)
        }
        if (releaseLease) clearLease()
        lastCommandText.text = "停止"
        updateUi()
    }

    private fun clearLease() { leaseId = null; leaseExpiresAt = 0L; acquiringLease = false }

    private fun requestRuntime(profile: String, mapId: String? = null) {
        if (!requireCommand("runtime_switch")) return
        val fields = mutableListOf<Pair<String, Any?>>("profile" to profile)
        mapId?.let { fields += "map_id" to it }
        sendRequest("runtime_switch", *fields.toTypedArray())
        lastCommandText.text = "请求切换到 $profile，等待 runtime 就绪事件"
    }

    private fun saveMap() {
        if (!requireCommand("map_save")) return
        if (runtimeProfile != "mapping" || !runtimeReady) { requestRuntime("mapping"); toast("已请求进入建图态，待小车就绪后再保存"); return }
        val name = "app_map_" + SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        sendRequest("map_save", "name" to name)
        lastCommandText.text = "正在保存地图：$name"
    }

    private fun requestNavigation() {
        if (!requireCommand("runtime_switch")) return
        val mapId = selectedMapId() ?: run { sendRequest("map_list"); toast("请先选择或等待加载地图 ID"); return }
        if (runtimeProfile != "navigation" || !runtimeReady) { pendingNavigation = false; requestRuntime("navigation", mapId); return }
        lastCommandText.text = "导航态已就绪，请填写坐标后发送导航目标"
    }

    private fun sendNavigationGoal() {
        if (!requireCommand("nav_goal")) return
        if (runtimeProfile != "navigation" || !runtimeReady) { pendingNavigation = true; requestNavigation(); toast("先进入导航态，运行态就绪后可发送目标"); return }
        val x = navXInput.text.toString().toDoubleOrNull()
        val y = navYInput.text.toString().toDoubleOrNull()
        val yaw = navYawInput.text.toString().toDoubleOrNull()
        if (x == null || y == null || yaw == null) { toast("请输入有效的 x、y、yaw 数值"); return }
        sendRequest("nav_goal", "x" to x, "y" to y, "yaw" to yaw)
    }

    private fun sendInitialPose() {
        if (!requireCommand("initial_pose")) return
        val mapId = selectedMapId() ?: run { toast("请先选择或等待加载地图 ID"); return }
        val x = navXInput.text.toString().toDoubleOrNull()
        val y = navYInput.text.toString().toDoubleOrNull()
        val yaw = navYawInput.text.toString().toDoubleOrNull()
        if (x == null || y == null || yaw == null) { toast("请输入有效的 x、y、yaw 数值"); return }
        sendRequest("initial_pose", "map_id" to mapId, "x" to x, "y" to y, "yaw" to yaw)
    }

    private fun toggleFollow() {
        if (activeFollowTrackId != null) { if (requireCommand("stop_follow")) sendRequest("stop_follow"); return }
        if (!requireCommand("follow_person")) return
        val trackId = selectedTrackId
        if (trackId.isNullOrBlank()) { toast("尚未从 vision 遥测收到可跟随的 track_id"); return }
        sendRequest("follow_person", "track_id" to trackId)
    }

    private fun startMission() {
        if (!requireCommand("mission_start")) return
        val mapId = selectedMapId()
        val routeId = selectedRouteId()
        if (routeId == null || mapId == null) { sendRequest("route_list"); sendRequest("map_list"); toast("请先选择或等待加载路线和地图 ID"); return }
        if (runtimeProfile != "mission" || !runtimeReady) { pendingMissionStart = true; requestRuntime("mission", mapId); return }
        sendRequest("mission_start", "route_id" to routeId, "route_version" to 0, "start_checkpoint_index" to 0, "loop" to false)
    }

    private fun toggleMissionPause() {
        val id = currentMissionId
        if (id.isNullOrBlank()) { toast("当前没有巡检任务"); return }
        val command = if (missionState.equals("paused", true)) "mission_resume" else "mission_pause"
        if (requireCommand(command)) sendRequest(command, "mission_id" to id)
    }

    private fun cancelMission() {
        val id = currentMissionId
        if (id.isNullOrBlank()) { toast("当前没有巡检任务"); return }
        if (requireCommand("mission_cancel")) sendRequest("mission_cancel", "mission_id" to id)
    }

    private fun refreshMissionRecords() {
        val id = currentMissionId
        if (id.isNullOrBlank()) { toast("当前没有可查询的巡检任务"); return }
        if ("mission_checkins" in commands) sendRequest("mission_checkins", "mission_id" to id)
        if ("mission_inspections" in commands) sendRequest("mission_inspections", "mission_id" to id)
        if ("mission_report" in commands) sendRequest("mission_report", "mission_id" to id)
    }

    private fun requestMissionRecoveries() {
        if (requireCommand("mission_recoveries")) sendRequest("mission_recoveries")
    }

    private fun showCheckins(checkins: JSONArray?) {
        val count = checkins?.length() ?: 0
        val latest = checkins?.optJSONObject(count - 1)
        val checkpoint = latest?.optString("checkpoint_id", "") ?: ""
        val result = latest?.optString("result", latest.optString("state", "")) ?: ""
        missionDetailText.text = if (count == 0) "尚无持久化打卡记录" else "打卡记录 $count 条｜最近：$checkpoint $result"
    }

    private fun showInspections(inspections: JSONArray?) {
        val count = inspections?.length() ?: 0
        val latest = inspections?.optJSONObject(count - 1)
        val conclusion = latest?.optString("conclusion", "UNKNOWN") ?: "UNKNOWN"
        val review = latest?.optBoolean("needs_human_review", false) == true || conclusion == "UNKNOWN" || conclusion == "NEEDS_HUMAN_REVIEW"
        if (count > 0) missionDetailText.text = "巡检结果 $count 条｜最近：$conclusion${if (review) "（待人工处理）" else ""}"
    }

    private fun showMissionReport(report: JSONObject?) {
        if (report == null) return
        val summary = report.optJSONObject("summary") ?: JSONObject()
        val checkins = summary.optInt("checkin_successes", 0)
        val attempts = summary.optInt("checkin_attempts", 0)
        val inspections = summary.optInt("inspection_count", 0)
        val reviews = summary.optInt("needs_human_review_count", 0)
        missionDetailText.text = "本轮报告：打卡 $checkins/$attempts｜巡检 $inspections｜待复核 $reviews"
    }

    private fun showMissionRecoveries(missions: JSONArray?) {
        val first = missions?.optJSONObject(0)
        missionDetailText.text = if (first == null) "没有等待人工处理的中断任务" else {
            val id = first.optString("mission_id", "任务")
            val retry = first.optInt("retry_current_checkpoint_index", -1)
            val next = first.optInt("continue_next_checkpoint_index", -1)
            "$id 等待人工处理｜可重试第 ${retry + 1} 站或从第 ${next + 1} 站新建任务"
        }
    }

    private fun acknowledgeAlert() {
        // main has no separate alert-ack command; resume a paused mission when one exists.
        if (!currentMissionId.isNullOrBlank() && missionState.equals("paused", true)) toggleMissionPause()
        else toast("main 协议没有独立的告警确认命令；告警由巡检事件流上报")
    }

    private fun requireCommand(command: String): Boolean {
        if (!connected) { toast("请先连接小车"); return false }
        if (command !in commands) { toast("当前小车 main 桥接未提供：$command"); return false }
        return true
    }

    private fun selectedMapId(): String? = mapIdInput.text.toString().trim().ifBlank { mapIds.firstOrNull() }

    private fun selectedRouteId(): String? = routeIdInput.text.toString().trim().ifBlank { routeIds.firstOrNull() }

    private fun sendRequest(command: String, vararg fields: Pair<String, Any?>) {
        val payload = JSONObject().put("id", "android-${requestIds.incrementAndGet()}").put("cmd", command)
        fields.forEach { (key, value) -> payload.put(key, value) }
        if (client?.send(payload.toString()) != true) lastCommandText.text = "发送失败：$command"
    }

    private fun replaceIds(target: MutableList<String>, items: JSONArray?, vararg keys: String) {
        target.clear()
        for (i in 0 until (items?.length() ?: 0)) {
            val item = items!!.optJSONObject(i) ?: continue
            val id = keys.asSequence().map { item.optString(it) }.firstOrNull { it.isNotBlank() }
            if (id != null) target += id
        }
    }

    private fun updateUi() {
        connectButton.text = if (connected) getString(R.string.disconnect) else getString(R.string.connect)
        val manual = connected && "move" in commands && "teleop_acquire" in commands
        motionButtons.forEach { it.isEnabled = manual }
        stopButton.isEnabled = connected
        mappingButton.isEnabled = connected && "runtime_switch" in commands
        navigationButton.isEnabled = connected && "runtime_switch" in commands
        navGoalButton.isEnabled = connected && "nav_goal" in commands
        initialPoseButton.isEnabled = connected && "initial_pose" in commands
        navCancelButton.isEnabled = connected && "nav_cancel" in commands
        saveMapButton.isEnabled = connected && "map_save" in commands
        trackingButton.isEnabled = connected && ("follow_person" in commands || "stop_follow" in commands)
        guardStartButton.isEnabled = connected && "mission_start" in commands
        guardResumeButton.isEnabled = connected && ("mission_pause" in commands || "mission_resume" in commands)
        guardStopButton.isEnabled = connected && "mission_cancel" in commands
        missionRefreshButton.isEnabled = connected && "mission_report" in commands
        missionRecoveryButton.isEnabled = connected && "mission_recoveries" in commands
        trackingButton.text = if (activeFollowTrackId == null) getString(R.string.tracking) else getString(R.string.tracking_stop)
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_SHORT).show()

    private companion object { const val HEARTBEAT_MS = 400L }
}
