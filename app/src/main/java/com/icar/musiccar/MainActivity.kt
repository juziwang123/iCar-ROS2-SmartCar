package com.icar.musiccar

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.MotionEvent
import android.view.View
import android.widget.ScrollView
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.google.android.material.button.MaterialButton
import com.google.android.material.materialswitch.MaterialSwitch
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/** UI for the commands that are explicitly advertised by car_app_bridge v3. */
class MainActivity : AppCompatActivity(), BridgeSession.Listener {
    private data class RuntimeRequest(val profile: String, val mapId: String?, val useYolo: Boolean?)
    private data class MapEntry(val id: String, val label: String)
    private data class VisionModel(val name: String, val labels: List<String>)
    private data class RouteCheckpointDraft(
        val id: String, val x: Double, val y: Double, val yaw: Double,
        val qrId: String, val model: String, val target: String, val required: Boolean
    )
    private enum class Module { DRIVE, MAP, MISSION, SETTINGS }
    private enum class MapTapMode { INITIAL_POSE, NAVIGATION_GOAL }

    private val mainHandler = Handler(Looper.getMainLooper())
    private lateinit var session: BridgeSession
    private var protocolReady = false
    private var capabilities = BridgeCapabilities()
    private var runtime = RuntimeSnapshot()
    private var speedRatio = 0.6
    private var leaseId: String? = null
    private var leaseRequested = false
    private var pendingMotion: Motion? = null
    private var activeMotion: Motion? = null
    private var effectiveEstop = false
    private var personSlowActive = false
    private var personEstopActive = false
    private var yoloFrame = YoloFrame()
    private var selectedTrackId: Int? = null
    private var followingTrackId: Int? = null
    private var nativeLidarFollowActive = false
    private var manualAvoidanceActive = false
    private var manualYoloEnabled = false
    private var pendingManualYolo: Boolean? = null
    private var currentMissionId: String? = null
    private var missionState = "IDLE"
    private var navigationState = "idle"
    private var pendingNavGoal = false
    private var initialPoseSubmitted = false
    private var mapTapMode = MapTapMode.INITIAL_POSE
    private var pendingMissionStart = false
    private var pendingRuntimeRequest: RuntimeRequest? = null
    private var runtimeCancellationRequested = false
    private var manualTakeoverPending = false
    private var manualPrerequisiteRequested = false
    private val mapIds = mutableListOf<String>()
    private val mapEntries = mutableListOf<MapEntry>()
    private var updatingMapSelector = false
    private val routeIds = mutableListOf<String>()
    private var mapSnapshot: MapSnapshot? = null
    private var robotPoint: MapPoint? = null
    private var checkpointPoints: List<MapPoint> = emptyList()
    private val visionModels = linkedMapOf<String, VisionModel>()
    private val routeDrafts = mutableListOf<RouteCheckpointDraft>()

    private lateinit var statusText: TextView
    private lateinit var runtimeDetailText: TextView
    private lateinit var lastCommandText: TextView
    private lateinit var speedText: TextView
    private lateinit var guardStatusText: TextView
    private lateinit var missionDetailText: TextView
    private lateinit var alertLevelText: TextView
    private lateinit var alertDetailText: TextView
    private lateinit var yoloStatusText: TextView
    private lateinit var yoloSafetyText: TextView
    private lateinit var yoloDetectionListText: TextView
    private lateinit var yoloOverlayView: YoloOverlayView
    private lateinit var cameraPreview: MjpegPreviewView
    private lateinit var cameraOverlayContainer: View
    private lateinit var mapSceneView: MapSceneView
    private lateinit var mapCoordinateText: TextView
    private lateinit var mapLocateModeButton: MaterialButton
    private lateinit var mapGoalModeButton: MaterialButton
    private lateinit var yoloMissionSwitch: MaterialSwitch
    private lateinit var hostInput: EditText
    private lateinit var portInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var mapNameInput: EditText
    private lateinit var mapIdInput: EditText
    private lateinit var mapSelector: Spinner
    private lateinit var routeIdInput: EditText
    private lateinit var checkpointIdInput: EditText
    private lateinit var checkpointXInput: EditText
    private lateinit var checkpointYInput: EditText
    private lateinit var checkpointYawInput: EditText
    private lateinit var checkpointQrInput: EditText
    private lateinit var checkpointModelSelector: Spinner
    private lateinit var checkpointTargetSelector: Spinner
    private lateinit var checkpointRequiredSwitch: MaterialSwitch
    private lateinit var routeDraftText: TextView
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
    private lateinit var videoPreviewButton: MaterialButton
    private lateinit var saveMapButton: MaterialButton
    private lateinit var mapRefreshButton: MaterialButton
    private lateinit var guardStartButton: MaterialButton
    private lateinit var guardResumeButton: MaterialButton
    private lateinit var guardStopButton: MaterialButton
    private lateinit var missionRefreshButton: MaterialButton
    private lateinit var missionRecoveryButton: MaterialButton
    private lateinit var routeAddCheckpointButton: MaterialButton
    private lateinit var routeRemoveCheckpointButton: MaterialButton
    private lateinit var routeSaveButton: MaterialButton
    private lateinit var routeLoadModelsButton: MaterialButton
    private lateinit var alertAcknowledgeButton: MaterialButton
    private lateinit var emergencyButton: MaterialButton
    private lateinit var clearEmergencyButton: MaterialButton
    private lateinit var avoidanceButton: MaterialButton
    private lateinit var manualYoloButton: MaterialButton
    private lateinit var stopButton: MaterialButton
    private lateinit var driveModuleButton: MaterialButton
    private lateinit var mapModuleButton: MaterialButton
    private lateinit var missionModuleButton: MaterialButton
    private lateinit var settingsModuleButton: MaterialButton
    private lateinit var connectionPanel: View
    private lateinit var mapPreviewPanel: View
    private lateinit var visionPanel: View
    private lateinit var alertPanel: View
    private lateinit var missionPanel: View
    private lateinit var navigationPanel: View
    private lateinit var drivePanel: View
    private lateinit var telemetryPanel: View
    private var selectedModule = Module.DRIVE
    private val motionButtons = mutableListOf<MaterialButton>()

    private val motionLoop = object : Runnable {
        override fun run() {
            val motion = activeMotion ?: return
            val lease = leaseId ?: return
            sendMove(motion, lease)
            mainHandler.postDelayed(this, MOTION_INTERVAL_MS)
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
        session = BridgeSession(this)
        bindViews()
        bindActions()
        render()
        // The car-side bridge may restart independently (for example after a
        // runtime deployment).  Reconnect on APP launch so controls do not
        // remain disabled merely because the user has to press Connect again.
        mainHandler.post { connect() }
    }

    override fun onDestroy() {
        stopMotion(true)
        session.close()
        mainHandler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    private fun bindViews() {
        statusText = findViewById(R.id.statusText)
        runtimeDetailText = findViewById(R.id.runtimeDetailText)
        lastCommandText = findViewById(R.id.lastCommandText)
        speedText = findViewById(R.id.speedText)
        guardStatusText = findViewById(R.id.guardStatusText)
        missionDetailText = findViewById(R.id.missionDetailText)
        alertLevelText = findViewById(R.id.alertLevelText)
        alertDetailText = findViewById(R.id.alertDetailText)
        yoloStatusText = findViewById(R.id.yoloStatusText)
        yoloSafetyText = findViewById(R.id.yoloSafetyText)
        yoloDetectionListText = findViewById(R.id.yoloDetectionListText)
        yoloOverlayView = findViewById(R.id.yoloOverlayView)
        cameraPreview = findViewById(R.id.cameraPreview)
        cameraOverlayContainer = findViewById(R.id.cameraOverlayContainer)
        mapSceneView = findViewById(R.id.mapSceneView)
        mapCoordinateText = findViewById(R.id.mapCoordinateText)
        mapLocateModeButton = findViewById(R.id.mapLocateModeButton)
        mapGoalModeButton = findViewById(R.id.mapGoalModeButton)
        yoloMissionSwitch = findViewById(R.id.yoloMissionSwitch)
        hostInput = findViewById(R.id.hostInput)
        portInput = findViewById(R.id.portInput)
        tokenInput = findViewById(R.id.tokenInput)
        mapNameInput = findViewById(R.id.mapNameInput)
        mapIdInput = findViewById(R.id.mapIdInput)
        mapSelector = findViewById(R.id.mapSelector)
        routeIdInput = findViewById(R.id.routeIdInput)
        checkpointIdInput = findViewById(R.id.checkpointIdInput)
        checkpointXInput = findViewById(R.id.checkpointXInput)
        checkpointYInput = findViewById(R.id.checkpointYInput)
        checkpointYawInput = findViewById(R.id.checkpointYawInput)
        checkpointQrInput = findViewById(R.id.checkpointQrInput)
        checkpointModelSelector = findViewById(R.id.checkpointModelSelector)
        checkpointTargetSelector = findViewById(R.id.checkpointTargetSelector)
        checkpointRequiredSwitch = findViewById(R.id.checkpointRequiredSwitch)
        routeDraftText = findViewById(R.id.routeDraftText)
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
        videoPreviewButton = findViewById(R.id.videoPreviewButton)
        saveMapButton = findViewById(R.id.saveMapButton)
        mapRefreshButton = findViewById(R.id.mapRefreshButton)
        guardStartButton = findViewById(R.id.guardStartButton)
        guardResumeButton = findViewById(R.id.guardResumeButton)
        guardStopButton = findViewById(R.id.guardStopButton)
        missionRefreshButton = findViewById(R.id.missionRefreshButton)
        missionRecoveryButton = findViewById(R.id.missionRecoveryButton)
        routeAddCheckpointButton = findViewById(R.id.routeAddCheckpointButton)
        routeRemoveCheckpointButton = findViewById(R.id.routeRemoveCheckpointButton)
        routeSaveButton = findViewById(R.id.routeSaveButton)
        routeLoadModelsButton = findViewById(R.id.routeLoadModelsButton)
        alertAcknowledgeButton = findViewById(R.id.alertAcknowledgeButton)
        emergencyButton = findViewById(R.id.emergencyButton)
        clearEmergencyButton = findViewById(R.id.clearEmergencyButton)
        avoidanceButton = findViewById(R.id.avoidanceButton)
        manualYoloButton = findViewById(R.id.manualYoloButton)
        stopButton = findViewById(R.id.stopButton)
        driveModuleButton = findViewById(R.id.driveModuleButton)
        mapModuleButton = findViewById(R.id.mapModuleButton)
        missionModuleButton = findViewById(R.id.missionModuleButton)
        settingsModuleButton = findViewById(R.id.settingsModuleButton)
        connectionPanel = findViewById(R.id.connectionPanel)
        mapPreviewPanel = findViewById(R.id.mapPreviewPanel)
        visionPanel = findViewById(R.id.visionPanel)
        alertPanel = findViewById(R.id.alertPanel)
        missionPanel = findViewById(R.id.missionPanel)
        navigationPanel = findViewById(R.id.navigationPanel)
        drivePanel = findViewById(R.id.drivePanel)
        telemetryPanel = findViewById(R.id.telemetryPanel)
        motionButtons += listOf(
            findViewById(R.id.forwardLeftButton), findViewById(R.id.forwardButton),
            findViewById(R.id.forwardRightButton), findViewById(R.id.backwardButton),
            findViewById(R.id.leftButton), findViewById(R.id.rightButton)
        )
    }

    private fun bindActions() {
        driveModuleButton.setOnClickListener { selectModule(Module.DRIVE) }
        mapModuleButton.setOnClickListener { selectModule(Module.MAP) }
        missionModuleButton.setOnClickListener { selectModule(Module.MISSION) }
        settingsModuleButton.setOnClickListener { selectModule(Module.SETTINGS) }
        connectButton.setOnClickListener { if (protocolReady) disconnect() else connect() }
        bindMotion(findViewById(R.id.forwardLeftButton), Motion(1.0, 0.65, "左前"))
        bindMotion(findViewById(R.id.forwardButton), Motion(1.0, 0.0, "前进"))
        bindMotion(findViewById(R.id.forwardRightButton), Motion(1.0, -0.65, "右前"))
        bindMotion(findViewById(R.id.backwardButton), Motion(-0.7, 0.0, "后退"))
        bindMotion(findViewById(R.id.leftButton), Motion(0.0, 1.0, "左转"))
        bindMotion(findViewById(R.id.rightButton), Motion(0.0, -1.0, "右转"))
        stopButton.setOnClickListener { stopMotion(true) }
        emergencyButton.setOnClickListener { stopMotion(true); sendSupported("estop", "active" to true) }
        clearEmergencyButton.setOnClickListener { sendSupported("estop", "active" to false) }
        avoidanceButton.setOnClickListener { sendSupported("manual_avoidance", "active" to !manualAvoidanceActive) }
        manualYoloButton.setOnClickListener { toggleManualYolo() }
        mappingButton.setOnClickListener { switchRuntime("mapping") }
        saveMapButton.setOnClickListener { saveMap() }
        mapRefreshButton.setOnClickListener { sendSupported("map_list") }
        navigationButton.setOnClickListener { switchToNavigation() }
        navGoalButton.setOnClickListener { sendNavigationGoal() }
        initialPoseButton.setOnClickListener { sendInitialPose() }
        navCancelButton.setOnClickListener { sendSupported("nav_cancel") }
        trackingButton.setOnClickListener { toggleFollow() }
        videoPreviewButton.setOnClickListener { toggleVideoPreview() }
        guardStartButton.setOnClickListener { startMission() }
        guardResumeButton.setOnClickListener { toggleMissionPause() }
        guardStopButton.setOnClickListener { cancelMission() }
        missionRefreshButton.setOnClickListener { refreshMissionRecords() }
        missionRecoveryButton.setOnClickListener { sendSupported("mission_recoveries") }
        routeAddCheckpointButton.setOnClickListener { addRouteCheckpoint() }
        routeRemoveCheckpointButton.setOnClickListener { removeLastRouteCheckpoint() }
        routeSaveButton.setOnClickListener { saveRouteDraft() }
        routeLoadModelsButton.setOnClickListener { requestVisionModels() }
        alertAcknowledgeButton.setOnClickListener { acknowledgeAlert() }
        mapLocateModeButton.setOnClickListener { selectMapTapMode(MapTapMode.INITIAL_POSE) }
        mapGoalModeButton.setOnClickListener { selectMapTapMode(MapTapMode.NAVIGATION_GOAL) }
        yoloOverlayView.onTrackSelected = { trackId ->
            selectedTrackId = trackId
            renderYolo()
            toast("已选择 YOLO track_id=$trackId")
        }
        mapSceneView.onMapPointSelected = { point ->
            navXInput.setText(String.format(Locale.US, "%.2f", point.x))
            navYInput.setText(String.format(Locale.US, "%.2f", point.y))
            checkpointXInput.setText(String.format(Locale.US, "%.2f", point.x))
            checkpointYInput.setText(String.format(Locale.US, "%.2f", point.y))
            when (mapTapMode) {
                MapTapMode.INITIAL_POSE -> {
                    mapCoordinateText.text = String.format(Locale.US,
                        "当前位置：x=%.2f，y=%.2f；正在提交初始定位", point.x, point.y)
                    sendInitialPose()
                }
                MapTapMode.NAVIGATION_GOAL -> {
                    mapCoordinateText.text = String.format(Locale.US,
                        "导航目标：x=%.2f，y=%.2f；正在发送导航", point.x, point.y)
                    if (!initialPoseSubmitted) {
                        toast("请先切到“设置当前位置”，在地图上点击小车实际位置完成定位")
                    } else sendNavigationGoal()
                }
            }
        }
        checkpointModelSelector.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                refreshCheckpointTargetSelector()
            }
        }
        mapSelector.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (!updatingMapSelector) mapEntries.getOrNull(position)?.let { entry ->
                    mapIdInput.setText(entry.id)
                    mapCoordinateText.text = "已选择地图：${entry.label}"
                }
            }
        }
        findViewById<SeekBar>(R.id.speedSlider).setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar, progress: Int, fromUser: Boolean) {
                speedRatio = progress.coerceIn(10, 100) / 100.0
                renderSpeed(progress.coerceIn(10, 100))
            }
            override fun onStartTrackingTouch(seekBar: SeekBar) = Unit
            override fun onStopTrackingTouch(seekBar: SeekBar) = Unit
        })
    }

    private fun bindMotion(button: MaterialButton, motion: Motion) {
        button.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> startMotion(motion)
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> stopMotion(true)
            }
            true
        }
    }

    private fun connect() {
        val host = hostInput.text.toString().trim()
        val port = portInput.text.toString().toIntOrNull()
        if (host.isBlank() || port == null || port !in 1..65535) {
            toast("请填写有效的小车 IP 和端口")
            return
        }
        resetConnectionState()
        statusText.text = "正在连接 $host:$port…"
        session.connect(host, port, tokenInput.text.toString().trim())
    }

    private fun disconnect() {
        stopMotion(true)
        session.close()
        resetConnectionState()
        lastCommandText.text = "连接已断开"
        render()
    }

    private fun resetConnectionState() {
        protocolReady = false
        capabilities = BridgeCapabilities()
        runtime = RuntimeSnapshot()
        leaseId = null
        leaseRequested = false
        pendingMotion = null
        activeMotion = null
        selectedTrackId = null
        followingTrackId = null
        effectiveEstop = false
        personSlowActive = false
        personEstopActive = false
        yoloFrame = YoloFrame()
        currentMissionId = null
        missionState = "IDLE"
        navigationState = "idle"
        pendingNavGoal = false
        pendingMissionStart = false
        pendingRuntimeRequest = null
        pendingManualYolo = null
        runtimeCancellationRequested = false
        manualTakeoverPending = false
        manualPrerequisiteRequested = false
        mapIds.clear()
        routeIds.clear()
    }

    override fun onTransportConnected() = ui { statusText.text = "TCP 已连接，等待 v3 握手…" }

    override fun onProtocolReady() = ui {
        protocolReady = true
        statusText.text = "桥接协议 v3 已连接，正在读取小车能力…"
        render()
    }

    override fun onCapabilities(capabilities: BridgeCapabilities) = ui {
        this.capabilities = capabilities
        lastCommandText.text = "已同步 ${capabilities.commands.size} 项车端能力"
        renderSpeed((speedRatio * 100).toInt())
        // Runtime status is transient on ROS, but a TCP reconnect can still
        // render an earlier STARTING event before the current state arrives.
        // Always query the authoritative snapshots after the v3 handshake.
        session.request("status")
        session.request("runtime_status")
        if (capabilities.supports("map_snapshot")) session.request("map_snapshot")
        if (capabilities.supports("vision_capabilities")) session.request("vision_capabilities")
        if (capabilities.supports("route_list")) session.request("route_list")
        render()
    }

    override fun onResponse(command: String, ok: Boolean, data: JSONObject, error: String, id: String?) = ui {
        if (!ok) {
            handleRejected(command, error.ifBlank { "未知错误" })
            return@ui
        }
        when (command) {
            "status" -> applyStatus(data)
            "runtime_status" -> applyRuntime(data)
            "runtime_switch" -> {
                pendingManualYolo?.let { manualYoloEnabled = it }
                pendingManualYolo = null
                lastCommandText.text = "运行态切换已受理，等待 runtime READY（generation ${data.optLong("generation")}）"
            }
            "map_list" -> updateMaps(data.optJSONArray("maps"))
            "map_snapshot" -> applyMap(data.optJSONObject("map"))
            "route_get" -> applyRoute(data.optJSONObject("route"))
            "route_list" -> updateIds(routeIds, data.optJSONArray("routes"), "route_id")
            "vision_capabilities" -> applyVisionCapabilities(data.optJSONObject("capabilities"))
            "route_save" -> {
                if (data.optBoolean("saved", false)) {
                    lastCommandText.text = "巡检路线已保存：${data.optString("route_id")} v${data.optInt("version", 1)}"
                    session.request("route_list")
                } else {
                    toast("路线校验失败：${data.optJSONObject("validation")?.toString() ?: "未知原因"}")
                }
            }
            "map_save" -> {
                val map = data.optJSONObject("map")
                val mapId = map?.optString("map_id").orEmpty()
                if (mapId.isNotBlank() && mapId !in mapIds) mapIds += mapId
                if (mapId.isNotBlank()) mapIdInput.setText(mapId)
                lastCommandText.text = "地图已保存：${map?.optString("name", mapId) ?: mapId}（$mapId）"
                session.request("map_list")
            }
            "teleop_acquire" -> acceptLease(data)
            "teleop_release" -> clearLease()
            "nav_goal" -> lastCommandText.text = "导航目标已提交，等待 navigation 事件"
            "nav_cancel" -> lastCommandText.text = "已请求取消直接导航，等待 navigation 终态"
            "initial_pose" -> {
                initialPoseSubmitted = true
                lastCommandText.text = "初始位姿已发送，等待雷达定位稳定后可选择导航目标"
                selectMapTapMode(MapTapMode.NAVIGATION_GOAL)
            }
            "follow_person" -> {
                followingTrackId = data.optInt("track_id", selectedTrackId ?: -1).takeIf { it >= 0 }
                nativeLidarFollowActive = false
                lastCommandText.text = "已锁定人物 track_id=$followingTrackId，跟随已启动"
            }
            "start_lidar_follow" -> {
                followingTrackId = null
                nativeLidarFollowActive = data.optBoolean("native_lidar_follow", true)
                lastCommandText.text = "原生雷达跟随已启动：将保持与前方最近目标的距离"
            }
            "stop_follow" -> {
                followingTrackId = null
                nativeLidarFollowActive = false
                lastCommandText.text = "已停止人物跟随"
            }
            "manual_avoidance" -> manualAvoidanceActive = data.optBoolean("active", false)
            "mission_start" -> {
                data.optString("mission_id").takeIf { it.isNotBlank() }?.let { currentMissionId = it }
                lastCommandText.text = "巡检已提交，等待 mission 事件"
            }
            "mission_checkins" -> showCheckins(data.optJSONArray("checkins"))
            "mission_inspections" -> showInspections(data.optJSONArray("inspections"))
            "mission_report" -> showMissionReport(data.optJSONObject("report") ?: data)
            "mission_recoveries" -> showRecoveries(data.optJSONArray("missions") ?: data.optJSONArray("recoveries"))
            "mission_pause", "mission_resume", "mission_cancel" -> lastCommandText.text = "$command 已受理，等待任务状态更新"
        }
        render()
    }

    override fun onEvent(channel: String, data: JSONObject) = ui {
        when (channel) {
            "runtime" -> applyRuntime(data)
            "status" -> applyStatus(data)
            "lidar" -> applyLidar(data)
            "vision" -> applyVision(data)
            "navigation" -> applyNavigation(data)
            "mission" -> applyMission(data)
            "inspection" -> applyInspection(data)
            "map" -> applyMap(data)
            "event" -> applyBusinessEvent(data)
            "control_lease" -> if (!data.optBoolean("active", true)) clearLease()
        }
        render()
    }

    override fun onDisconnected(error: Throwable?) = ui {
        resetConnectionState()
        statusText.text = "连接关闭：${error?.message ?: "小车已断开"}"
        render()
    }

    override fun onProtocolError(message: String) = ui {
        lastCommandText.text = message
        toast(message)
    }

    private fun handleRejected(command: String, error: String) {
        if (command == "teleop_acquire" || command == "move") clearLease()
        if (command == "runtime_switch") pendingManualYolo = null
        if (command == "runtime_switch" && error.contains("already active", true)) {
            lastCommandText.text = "车端报告运行态已存在，正在重新查询真实状态"
            session.request("runtime_status")
        } else {
            lastCommandText.text = "$command 被小车拒绝：$error"
            toast("小车拒绝：$error")
        }
        render()
    }

    private fun applyRuntime(data: JSONObject) {
        runtime = RuntimeSnapshot.from(data, runtime)
        if (runtime.ready && runtime.state == "READY") {
            if (runtime.activeProfile == "navigation" && pendingNavGoal) {
                pendingNavGoal = false
                submitNavigationGoal()
            }
            if (runtime.activeProfile == "mission" && pendingMissionStart) {
                pendingMissionStart = false
                submitMissionStart()
            }
        }
        if (runtime.state == "FAILED") {
            pendingNavGoal = false
            pendingMissionStart = false
            lastCommandText.text = "运行态启动失败：${runtime.message}"
        }
    }

    private fun applyStatus(data: JSONObject) {
        data.optJSONObject("runtime")?.let(::applyRuntime)
        effectiveEstop = data.optBoolean("effective_estop_active", data.optBoolean("estop_active", false))
        manualAvoidanceActive = data.optBoolean("manual_avoidance_active", manualAvoidanceActive)
        data.optJSONObject("lidar")?.let(::applyLidar)
        data.optJSONObject("vision_detection")?.let(::applyVision)
        data.optJSONObject("person_safety")?.let(::applyPersonSafety)
        data.optJSONObject("navigation")?.let(::applyNavigation)
        data.optJSONObject("mission")?.let(::applyMission)
        data.optJSONObject("inspection")?.let(::applyInspection)
        data.optJSONObject("map")?.let(::applyMap)
        data.optJSONObject("pose")?.let {
            robotPoint = MapPoint("小车", it.optDouble("x"), it.optDouble("y"))
            renderMap()
        }
        val follow = data.optInt("follow_target_id", -1)
        followingTrackId = follow.takeIf { it >= 0 }
    }

    private fun applyLidar(data: JSONObject) {
        val blocked = data.optBoolean("override_active", false) || data.optBoolean("warning_active", false)
        if (blocked) {
            alertLevelText.text = "雷达避障介入"
            alertDetailText.text = data.optString("warning_state", "安全链已限制车辆运动")
        } else if (alertLevelText.text == "雷达避障介入") {
            alertLevelText.text = getString(R.string.alert_normal)
            alertDetailText.text = getString(R.string.alert_waiting)
        }
    }

    private fun applyVision(data: JSONObject) {
        data.optJSONObject("capabilities")?.let(::applyVisionCapabilities)
        val payload = data.optJSONObject("detection") ?: data
        yoloFrame = YoloFrame.from(payload)
        val visibleTracks = yoloFrame.detections.mapNotNull(YoloDetection::trackId).toSet()
        selectedTrackId = selectedTrackId?.takeIf { it in visibleTracks }
        renderYolo()
    }

    private fun applyVisionCapabilities(data: JSONObject?) {
        if (data == null) return
        visionModels.clear()
        data.optJSONArray("models")?.objects()?.forEach { model ->
            val name = model.optString("name").trim()
            if (name.isBlank() || !model.optBoolean("loaded", true)) return@forEach
            val labels = model.optJSONArray("labels")?.stringSet()?.toList()?.sorted().orEmpty()
            visionModels[name] = VisionModel(name, labels)
        }
        refreshCheckpointModelSelector()
        lastCommandText.text = if (visionModels.isEmpty()) {
            "YOLO 模型类别尚不可用；请先在运行态启动需要的模型"
        } else "已读取 ${visionModels.size} 个 YOLO 模型的类别，可用于巡检任务"
    }

    private fun applyPersonSafety(data: JSONObject) {
        personSlowActive = data.optBoolean("slow_active", false)
        personEstopActive = data.optBoolean("estop_active", false)
        renderYolo()
    }

    private fun applyNavigation(data: JSONObject) {
        navigationState = data.optString("state", navigationState).lowercase()
        lastCommandText.text = "导航：$navigationState"
        if (!navigationIsActive()) {
            drainPendingRuntimeSwitch()
            continueManualTakeover()
        }
    }

    private fun applyMap(data: JSONObject?) {
        mapSnapshot = data?.let(MapSnapshot::from)
        renderMap()
    }

    private fun applyRoute(route: JSONObject?) {
        checkpointPoints = buildList {
            route?.optJSONArray("checkpoints")?.objects()?.forEach { checkpoint ->
                val pose = checkpoint.optJSONObject("pose") ?: return@forEach
                add(MapPoint(checkpoint.optString("checkpoint_id", "打卡点"), pose.optDouble("x"), pose.optDouble("y")))
            }
        }
        renderMap()
    }

    private fun applyMission(data: JSONObject) {
        data.optString("mission_id").takeIf { it.isNotBlank() }?.let { currentMissionId = it }
        missionState = data.optString("state", missionState).uppercase()
        val index = data.optInt("checkpoint_index", -1)
        val total = data.optInt("checkpoint_total", -1)
        val progress = data.optDouble("progress", -1.0)
        guardStatusText.text = "巡检：$missionState"
        missionDetailText.text = buildString {
            if (index >= 0 && total > 0) append("检查点 ${index + 1}/$total")
            if (progress >= 0) append(if (isEmpty()) "" else "｜").append("进度 ${(progress * 100).toInt()}%")
            data.optString("detail").takeIf { it.isNotBlank() }?.let { append(if (isEmpty()) "" else "｜").append(it) }
            if (isEmpty()) append("等待任务进度")
        }
        if (!missionIsActive()) drainPendingRuntimeSwitch()
        if (missionState == "PAUSED" || !missionIsActive()) continueManualTakeover()
    }

    private fun applyInspection(data: JSONObject) {
        val conclusion = data.optString("conclusion", "UNKNOWN")
        val pendingReview = data.optBoolean("needs_human_review", false) ||
            conclusion in setOf("UNKNOWN", "NEEDS_HUMAN_REVIEW")
        alertLevelText.text = if (pendingReview) "巡检结果待人工复核" else "巡检结果：$conclusion"
        alertDetailText.text = "${data.optString("checkpoint_id")} / ${data.optString("target")} / 置信度 ${data.optDouble("confidence", 0.0)}"
    }

    private fun applyBusinessEvent(data: JSONObject) {
        val event = data.optString("code", "任务事件")
        alertLevelText.text = event
        alertDetailText.text = data.optString("detail", data.toString())
    }

    private fun switchRuntime(profile: String, mapId: String? = null, useYolo: Boolean? = null) {
        if (!requireCommand("runtime_switch")) return
        if (runtime.isTransitioning) {
            toast("运行态正在切换，请等待当前 generation 完成")
            return
        }
        if (runtime.activeProfile == profile && runtime.ready && runtime.state == "READY" && useYolo == null) {
            lastCommandText.text = "$profile 已经 READY，无需重复切换"
            return
        }
        pendingRuntimeRequest = RuntimeRequest(profile, mapId, useYolo)
        runtimeCancellationRequested = false
        drainPendingRuntimeSwitch()
    }

    /** v3 requires APP-owned navigation and missions to finish before runtime_switch. */
    private fun drainPendingRuntimeSwitch() {
        val request = pendingRuntimeRequest ?: return
        if (missionIsActive()) {
            val missionId = currentMissionId ?: run {
                lastCommandText.text = "等待当前巡检任务 ID 后再切换运行态"
                return
            }
            if (!runtimeCancellationRequested) {
                runtimeCancellationRequested = true
                session.request("mission_cancel", "mission_id" to missionId)
                lastCommandText.text = "切换前正在取消巡检任务…"
            }
            return
        }
        if (navigationIsActive()) {
            if (!runtimeCancellationRequested) {
                runtimeCancellationRequested = true
                session.request("nav_cancel")
                lastCommandText.text = "切换前正在取消直接导航…"
            }
            return
        }
        pendingRuntimeRequest = null
        runtimeCancellationRequested = false
        val fields = mutableListOf<Pair<String, Any?>>("profile" to request.profile)
        request.mapId?.let { fields += "map_id" to it }
        request.useYolo?.let { fields += "use_yolo" to it }
        session.request("runtime_switch", *fields.toTypedArray())
        lastCommandText.text = "正在请求 ${request.profile} 运行态…"
    }

    private fun saveMap() {
        if (!requireCommand("map_save")) return
        if (runtime.activeProfile != "mapping" || !runtime.ready || runtime.state != "READY") {
            toast("请先进入建图态并等待 READY")
            return
        }
        val name = mapNameInput.text.toString().trim()
        if (name.isBlank()) { toast("请输入地图名称"); return }
        session.request("map_save", "name" to name)
        lastCommandText.text = "正在请求车端保存地图…"
    }

    private fun switchToNavigation() {
        val mapId = selectedMapId() ?: return toast("请先选择已保存地图 ID")
        initialPoseSubmitted = false
        selectMapTapMode(MapTapMode.INITIAL_POSE)
        mapCoordinateText.text = "步骤 1：导航正在启动；请立即在地图上点击小车当前实际位置完成定位"
        switchRuntime("navigation", mapId)
    }

    private fun selectMapTapMode(mode: MapTapMode) {
        mapTapMode = mode
        mapLocateModeButton.text = if (mode == MapTapMode.INITIAL_POSE) {
            "① 设置当前位置（当前）"
        } else "① 设置当前位置"
        mapGoalModeButton.text = if (mode == MapTapMode.NAVIGATION_GOAL) {
            "② 选择导航目标（当前）"
        } else "② 选择导航目标"
        if (mode == MapTapMode.INITIAL_POSE) {
            mapCoordinateText.text = "步骤 1：在地图上点击小车当前实际位置，将用雷达完成定位"
        } else {
            mapCoordinateText.text = "步骤 2：在地图上点击目标位置，小车将自动规划前往"
        }
    }

    private fun sendNavigationGoal() {
        if (!requireCommand("nav_goal")) return
        if (runtime.activeProfile != "navigation" || !runtime.ready) {
            val mapId = selectedMapId() ?: return toast("请先选择地图 ID")
            pendingNavGoal = true
            switchRuntime("navigation", mapId)
        } else submitNavigationGoal()
    }

    private fun submitNavigationGoal() {
        val x = navXInput.numberOrNull() ?: return toast("导航 x 无效")
        val y = navYInput.numberOrNull() ?: return toast("导航 y 无效")
        val yaw = navYawInput.numberOrNull() ?: return toast("导航 yaw 无效")
        session.request("nav_goal", "x" to x, "y" to y, "yaw" to yaw, "frame_id" to "map")
    }

    private fun sendInitialPose() {
        if (!requireCommand("initial_pose")) return
        // AMCL needs this pose *before* Nav2 can finish activation.  Requiring
        // READY here created a startup deadlock: planner waits for map->odom,
        // while AMCL waits for the APP's initial pose.
        if (runtime.activeProfile != "navigation" && runtime.requestedProfile != "navigation") {
            return toast("请先启动导航运行态，再设置初始位姿")
        }
        val mapId = selectedMapId() ?: return toast("请选择地图 ID")
        val x = navXInput.numberOrNull() ?: return toast("x 无效")
        val y = navYInput.numberOrNull() ?: return toast("y 无效")
        val yaw = navYawInput.numberOrNull() ?: return toast("yaw 无效")
        session.request("initial_pose", "map_id" to mapId, "x" to x, "y" to y, "yaw" to yaw)
    }

    private fun toggleFollow() {
        if (followingTrackId != null || nativeLidarFollowActive) {
            sendSupported("stop_follow")
            return
        }
        val trackId = selectedTrackId ?: return toast("请先点击 YOLO 画面中的人物框，选择要跟随的人")
        val selected = yoloFrame.detections.firstOrNull { it.trackId == trackId }
        if (selected?.isPerson != true) return toast("只能跟随识别为 person 的目标，请点击人物框")
        if (!requireCommand("follow_person")) return
        session.request("follow_person", "track_id" to trackId, "activate" to true)
        lastCommandText.text = "正在锁定人物 track_id=$trackId…"
    }

    private fun toggleVideoPreview() {
        if (cameraOverlayContainer.visibility == View.VISIBLE) {
            cameraPreview.stop()
            cameraOverlayContainer.visibility = View.GONE
            videoPreviewButton.text = "打开实时视频"
            return
        }
        val host = hostInput.text.toString().trim()
        if (host.isBlank()) return toast("请先在设置中填写小车 IP")
        cameraOverlayContainer.visibility = View.VISIBLE
        cameraPreview.start("http://$host:8080/stream.mjpg")
        videoPreviewButton.text = "关闭实时视频"
        ensureVideoYolo()
    }

    /** Video preview is only useful for person following when its detector is running. */
    private fun ensureVideoYolo() {
        if (manualYoloEnabled || pendingManualYolo == true || !protocolReady) return
        if (!requireCommand("runtime_switch")) return
        pendingManualYolo = true
        switchRuntime("vision", null, true)
        lastCommandText.text = "实时视频已打开，正在启动 YOLO 人物识别…"
    }

    private fun toggleManualYolo() {
        if (!requireCommand("runtime_switch")) return
        if (runtime.activeProfile == "mission") {
            toast("巡检运行态请使用“巡检运行态启用 YOLO”开关")
            return
        }
        val profile = "vision"
        val mapId: String? = null
        val enable = !manualYoloEnabled
        pendingManualYolo = enable
        switchRuntime(profile, mapId, enable)
        lastCommandText.text = if (enable) "正在启动手动 YOLO 识别…" else "正在停止手动 YOLO 识别…"
    }

    private fun startMission() {
        if (!requireCommand("mission_start")) return
        val mapId = selectedMapId()
        if (mapId == null) { showMissionStep("步骤 1/3：先在“地图导航”中选择已保存地图"); return }
        if (selectedRouteId() == null) { showMissionStep("步骤 2/3：选择该地图对应的巡检路线"); return }
        showMissionStep("步骤 3/3：正在启动巡检，稍后显示打卡进度")
        if (runtime.activeProfile != "mission" || !runtime.ready) {
            pendingMissionStart = true
            switchRuntime("mission", mapId, yoloMissionSwitch.isChecked)
        } else submitMissionStart()
    }

    private fun submitMissionStart() {
        val routeId = selectedRouteId() ?: return toast("请选择巡检路线 ID")
        session.request(
            "mission_start", "route_id" to routeId, "route_version" to 0,
            "start_checkpoint_index" to 0, "loop" to false
        )
    }

    private fun toggleMissionPause() {
        val missionId = currentMissionId ?: return toast("当前没有巡检任务")
        val command = if (missionState == "PAUSED") "mission_resume" else "mission_pause"
        sendSupported(command, "mission_id" to missionId)
    }

    private fun cancelMission() {
        val missionId = currentMissionId ?: return toast("当前没有巡检任务")
        sendSupported("mission_cancel", "mission_id" to missionId)
    }

    private fun refreshMissionRecords() {
        val missionId = currentMissionId ?: return toast("当前没有巡检任务")
        listOf("mission_checkins", "mission_inspections", "mission_report").forEach { command ->
            if (capabilities.supports(command)) session.request(command, "mission_id" to missionId)
        }
    }

    private fun startMotion(motion: Motion) {
        if (!requireCommand("teleop_acquire") || !requireCommand("move")) return
        if (effectiveEstop) return toast("有效急停仍在生效")
        pendingMotion = motion
        manualTakeoverPending = true
        if (missionIsActive() && missionState != "PAUSED") {
            val missionId = currentMissionId ?: return toast("等待当前巡检任务 ID")
            if (!manualPrerequisiteRequested) {
                manualPrerequisiteRequested = true
                session.request("mission_pause", "mission_id" to missionId)
                lastCommandText.text = "人工接管前正在暂停巡检…"
            }
            return
        }
        if (navigationIsActive()) {
            if (!manualPrerequisiteRequested) {
                manualPrerequisiteRequested = true
                session.request("nav_cancel")
                lastCommandText.text = "人工接管前正在取消直接导航…"
            }
            return
        }
        continueManualTakeover()
    }

    private fun continueManualTakeover() {
        val motion = pendingMotion ?: return
        if (!manualTakeoverPending) return
        if (missionIsActive() && missionState != "PAUSED") return
        if (navigationIsActive()) return
        manualPrerequisiteRequested = false
        if (leaseId != null) beginMotion(motion) else if (!leaseRequested) {
            leaseRequested = true
            session.request("teleop_acquire")
        }
    }

    private fun acceptLease(data: JSONObject) {
        leaseRequested = false
        manualTakeoverPending = false
        leaseId = data.optString("lease_id").takeIf { it.isNotBlank() }
        val motion = pendingMotion
        if (leaseId == null) return
        if (motion == null) {
            session.request("teleop_release", "lease_id" to leaseId)
        } else beginMotion(motion)
    }

    private fun beginMotion(motion: Motion) {
        activeMotion = motion
        pendingMotion = null
        mainHandler.removeCallbacks(motionLoop)
        motionLoop.run()
        lastCommandText.text = "手动控制：${motion.label}"
    }

    private fun sendMove(motion: Motion, lease: String) {
        val linear = capabilities.maxLinearSpeed * speedRatio * motion.linearFactor
        val angular = capabilities.maxAngularSpeed * speedRatio * motion.angularFactor
        session.request("move", "lease_id" to lease, "linear" to linear, "angular" to angular)
    }

    private fun stopMotion(release: Boolean) {
        mainHandler.removeCallbacks(motionLoop)
        pendingMotion = null
        activeMotion = null
        manualTakeoverPending = false
        manualPrerequisiteRequested = false
        val lease = leaseId
        if (lease != null && protocolReady) {
            session.request("move", "lease_id" to lease, "linear" to 0.0, "angular" to 0.0)
            if (release) session.request("teleop_release", "lease_id" to lease)
        }
        if (release) clearLease()
    }

    private fun clearLease() {
        leaseId = null
        leaseRequested = false
        mainHandler.removeCallbacks(motionLoop)
    }

    private fun navigationIsActive() = navigationState in setOf(
        "goal_published", "goal_sent", "accepted", "cancel_requested"
    )

    private fun missionIsActive() = missionState.lowercase() in setOf(
        "goal_requested", "accepted", "preparing", "localizing", "navigating",
        "arrival_confirming", "checking_in", "recording", "recovering", "capturing",
        "inspecting", "pausing", "paused", "resuming", "waiting_operator", "estopped"
    )

    private fun showCheckins(items: JSONArray?) {
        missionDetailText.text = "打卡记录：${items?.length() ?: 0} 条"
    }

    private fun showInspections(items: JSONArray?) {
        val pending = items.objects().count {
            it.optBoolean("needs_human_review", false) || it.optString("conclusion") in setOf("UNKNOWN", "NEEDS_HUMAN_REVIEW")
        }
        missionDetailText.text = "巡检记录：${items?.length() ?: 0} 条｜待复核 $pending 条"
    }

    private fun showMissionReport(report: JSONObject) {
        val summary = report.optJSONObject("summary") ?: JSONObject()
        missionDetailText.text = "报告：打卡 ${summary.optInt("checkin_successes")}/${summary.optInt("checkin_attempts")}｜巡检 ${summary.optInt("inspection_count")}"
    }

    private fun showRecoveries(items: JSONArray?) {
        lastCommandText.text = "可恢复的中断任务：${items?.length() ?: 0} 个"
    }

    private fun acknowledgeAlert() {
        alertLevelText.text = getString(R.string.alert_normal)
        alertDetailText.text = getString(R.string.alert_waiting)
    }

    private fun requireCommand(command: String): Boolean {
        if (!protocolReady) { toast("请先连接小车"); return false }
        if (!capabilities.supports(command)) {
            toast("当前小车未声明 $command 能力")
            return false
        }
        return true
    }

    private fun sendSupported(command: String, vararg fields: Pair<String, Any?>) {
        if (requireCommand(command)) session.request(command, *fields)
    }

    private fun selectedMapId() = mapIdInput.text.toString().trim().ifBlank { mapIds.firstOrNull().orEmpty() }.ifBlank { null }
    private fun selectedRouteId() = routeIdInput.text.toString().trim().ifBlank { routeIds.firstOrNull().orEmpty() }.ifBlank { null }

    private fun updateIds(target: MutableList<String>, array: JSONArray?, key: String) {
        target.clear()
        array.objects().map { it.optString(key) }.filter(String::isNotBlank).forEach(target::add)
        if (key == "map_id" && mapIdInput.text.isNullOrBlank() && target.isNotEmpty()) mapIdInput.setText(target.first())
        if (key == "route_id" && routeIdInput.text.isNullOrBlank() && target.isNotEmpty()) routeIdInput.setText(target.first())
    }

    private fun render() {
        renderModule()
        connectButton.text = getString(if (protocolReady) R.string.disconnect else R.string.connect)
        if (protocolReady) statusText.text = "已连接｜${runtime.activeProfile} / ${runtime.state}"
        val mappingProgress = when {
            runtime.activeProfile != "mapping" && runtime.requestedProfile != "mapping" -> ""
            runtime.state == "STARTING" -> "\n正在启动 SLAM、雷达与地图保存服务…"
            runtime.activeProfile == "mapping" && runtime.ready -> "\n建图运行中：请手动行驶采集环境；完成后输入地图名称并保存。桥接协议不传输地图图片。"
            runtime.state == "FAILED" -> "\n建图栈启动失败，请查看车端错误。"
            else -> "\n等待建图运行态就绪…"
        }
        runtimeDetailText.text = "目标：${runtime.requestedProfile}｜generation ${runtime.generation}｜${if (runtime.ready) "READY" else "未就绪"}" +
            runtime.message.takeIf { it.isNotBlank() }?.let { "\n$it" }.orEmpty() + mappingProgress
        val available = protocolReady && capabilities.commands.isNotEmpty()
        mappingButton.isEnabled = available && capabilities.supports("runtime_switch") && !runtime.isTransitioning
        navigationButton.isEnabled = mappingButton.isEnabled
        mapRefreshButton.isEnabled = available && capabilities.supports("map_list")
        saveMapButton.isEnabled = available && capabilities.supports("map_save") && runtime.activeProfile == "mapping" && runtime.ready
        navGoalButton.isEnabled = available && capabilities.supports("nav_goal")
        initialPoseButton.isEnabled = available && capabilities.supports("initial_pose") &&
            (runtime.activeProfile == "navigation" || runtime.requestedProfile == "navigation")
        navCancelButton.isEnabled = available && capabilities.supports("nav_cancel")
        trackingButton.isEnabled = available && if (followingTrackId == null && !nativeLidarFollowActive) {
            capabilities.supports("follow_person") && selectedTrackId != null
        } else capabilities.supports("stop_follow")
        trackingButton.text = getString(
            if (followingTrackId == null && !nativeLidarFollowActive) R.string.tracking else R.string.tracking_stop
        )
        videoPreviewButton.isEnabled = hostInput.text.isNotBlank()
        yoloMissionSwitch.isEnabled = available && capabilities.supports("runtime_switch") &&
            runtime.activeProfile != "mission" && runtime.requestedProfile != "mission"
        guardStartButton.isEnabled = available && capabilities.supports("mission_start")
        guardResumeButton.isEnabled = available && (capabilities.supports("mission_pause") || capabilities.supports("mission_resume"))
        guardStopButton.isEnabled = available && capabilities.supports("mission_cancel")
        missionRefreshButton.isEnabled = available && currentMissionId != null
        missionRecoveryButton.isEnabled = available && capabilities.supports("mission_recoveries")
        emergencyButton.isEnabled = available && capabilities.supports("estop")
        clearEmergencyButton.isEnabled = emergencyButton.isEnabled
        avoidanceButton.isEnabled = available && capabilities.supports("manual_avoidance")
        avoidanceButton.text = if (manualAvoidanceActive) "关闭手动避障" else "开启手动避障（10cm）"
        manualYoloButton.isEnabled = available && capabilities.supports("runtime_switch") && !runtime.isTransitioning
        manualYoloButton.text = if (manualYoloEnabled) "关闭手动 YOLO 识别" else "开启手动 YOLO 识别"
        stopButton.isEnabled = available && capabilities.supports("move")
        motionButtons.forEach { it.isEnabled = available && capabilities.supports("teleop_acquire") && capabilities.supports("move") && !effectiveEstop }
        renderYolo()
    }

    private fun renderYolo() {
        yoloOverlayView.showFrame(yoloFrame, selectedTrackId)
        yoloStatusText.text = when {
            yoloFrame.error != null -> "YOLO 不可用：${yoloFrame.error}"
            yoloFrame.stampSeconds == null -> "等待 vision 遥测"
            else -> "模型 ${yoloFrame.model ?: "未知"}｜${yoloFrame.detections.size} 个目标｜" +
                "${yoloFrame.imageWidth}×${yoloFrame.imageHeight}｜${yoloFrame.frameId.ifBlank { "无 frame_id" }}"
        }
        yoloSafetyText.text = when {
            personEstopActive -> "人员安全：近距急停已触发"
            effectiveEstop -> "人员安全：车辆有效急停中"
            personSlowActive -> "人员安全：人员接近，安全减速中"
            else -> "人员安全：未触发减速/急停"
        }
        yoloSafetyText.setTextColor(
            getColor(if (personEstopActive || effectiveEstop) R.color.danger else R.color.primary)
        )
        yoloDetectionListText.text = if (yoloFrame.detections.isEmpty()) {
            "当前帧未检测到目标"
        } else buildString {
            yoloFrame.detections.take(MAX_RENDERED_DETECTIONS).forEachIndexed { index, detection ->
                if (index > 0) append('\n')
                val chosen = if (detection.trackId == selectedTrackId) "● " else "○ "
                val track = detection.trackId?.let { "track_id=$it" } ?: "无 track_id"
                val distance = detection.distanceMeters?.let { "｜%.2f m".format(it) }.orEmpty()
                append(chosen).append(detection.label).append("｜").append(track)
                    .append("｜").append((detection.confidence * 100).toInt()).append("%").append(distance)
            }
            if (yoloFrame.detections.size > MAX_RENDERED_DETECTIONS) {
                append("\n…另有 ${yoloFrame.detections.size - MAX_RENDERED_DETECTIONS} 个目标")
            }
        }
    }

    private fun requestVisionModels() {
        if (!requireCommand("vision_capabilities")) return
        session.request("vision_capabilities")
    }

    private fun refreshCheckpointModelSelector() {
        val models = visionModels.keys.sorted()
        checkpointModelSelector.adapter = ArrayAdapter(
            this, android.R.layout.simple_spinner_dropdown_item, models.ifEmpty { listOf("请先读取模型类别") }
        )
        refreshCheckpointTargetSelector()
    }

    private fun refreshCheckpointTargetSelector() {
        val model = checkpointModelSelector.selectedItem?.toString().orEmpty()
        val labels = visionModels[model]?.labels.orEmpty()
        checkpointTargetSelector.adapter = ArrayAdapter(
            this, android.R.layout.simple_spinner_dropdown_item, labels.ifEmpty { listOf("请先选择有效类别") }
        )
    }

    private fun addRouteCheckpoint() {
        val mapId = selectedMapId() ?: return toast("请先选择已保存地图")
        val id = checkpointIdInput.text.toString().trim().ifBlank {
            "CP-%02d".format(Locale.US, routeDrafts.size + 1)
        }
        val x = checkpointXInput.numberOrNull() ?: return toast("巡检点 x 无效")
        val y = checkpointYInput.numberOrNull() ?: return toast("巡检点 y 无效")
        val yaw = checkpointYawInput.numberOrNull() ?: return toast("巡检点 yaw 无效")
        val model = checkpointModelSelector.selectedItem?.toString().orEmpty()
        val target = checkpointTargetSelector.selectedItem?.toString().orEmpty()
        if (model !in visionModels || target !in visionModels[model]!!.labels) {
            return toast("请先读取 YOLO 模型类别，并选择有效模型与目标类别")
        }
        if (routeDrafts.any { it.id == id }) return toast("巡检点 ID 不能重复")
        val qrId = checkpointQrInput.text.toString().trim().ifBlank { "ICAR:$mapId:$id:v1" }
        routeDrafts += RouteCheckpointDraft(id, x, y, yaw, qrId, model, target, checkpointRequiredSwitch.isChecked)
        checkpointIdInput.setText("CP-%02d".format(Locale.US, routeDrafts.size + 1))
        checkpointQrInput.text?.clear()
        renderRouteDraft()
        toast("已加入巡检点 $id")
    }

    private fun removeLastRouteCheckpoint() {
        if (routeDrafts.isEmpty()) return toast("当前路线没有巡检点")
        routeDrafts.removeLast()
        renderRouteDraft()
    }

    private fun renderRouteDraft() {
        routeDraftText.text = if (routeDrafts.isEmpty()) {
            "尚未添加巡检点：在地图上点位后，选择二维码、模型与目标类别。"
        } else routeDrafts.joinToString("\n") { draft ->
            "${draft.id}｜${draft.target} (${draft.model})｜二维码 ${draft.qrId}"
        }
        checkpointPoints = routeDrafts.map { MapPoint(it.id, it.x, it.y) }
        renderMap()
    }

    private fun saveRouteDraft() {
        if (!requireCommand("route_save")) return
        val routeId = selectedRouteId() ?: return toast("请输入巡检路线 ID")
        val mapId = selectedMapId() ?: return toast("请选择已保存地图")
        if (routeDrafts.isEmpty()) return toast("请至少添加一个巡检点")
        val checkpoints = JSONArray()
        routeDrafts.forEachIndexed { index, draft ->
            val task = JSONObject()
                .put("task_id", "${draft.id}-visual")
                .put("type", "visual_presence")
                .put("target", draft.target)
                .put("required", draft.required)
                .put("capture_count", 3)
                .put("local_model", draft.model)
                .put("use_vlm_fallback", false)
                .put("confidence_threshold", 0.60)
            checkpoints.put(JSONObject()
                .put("checkpoint_id", draft.id)
                .put("sequence", index + 1)
                .put("name", draft.id)
                .put("type", "checkin")
                .put("pose", JSONObject().put("frame_id", "map").put("x", draft.x).put("y", draft.y).put("yaw", draft.yaw))
                .put("arrival", JSONObject().put("position_tolerance_m", 0.30).put("yaw_tolerance_rad", 0.35).put("dwell_sec", 1.0).put("max_pose_covariance", 0.25))
                .put("checkin", JSONObject().put("method", "visual_marker").put("marker_type", "qr").put("expected_marker_id", draft.qrId).put("timeout_sec", 12.0).put("retries", 1).put("confirmation_frames", 2))
                .put("tasks", JSONArray().put(task))
                .put("failure_policy", JSONObject().put("navigation", "retry_then_wait_operator").put("checkin", "retry_then_wait_operator").put("required_task", if (draft.required) "wait_operator" else "continue")))
        }
        val route = JSONObject()
            .put("schema_version", 1).put("route_id", routeId).put("map_id", mapId)
            .put("name", routeId).put("version", 1).put("loop", false).put("checkpoints", checkpoints)
        session.request("route_save", "route" to route, "replace" to true)
        lastCommandText.text = "正在保存巡检路线 $routeId…"
    }

    private fun updateMaps(array: JSONArray?) {
        val previouslySelected = mapIdInput.text.toString().trim()
        mapEntries.clear()
        array.objects().forEach { map ->
            val id = map.optString("map_id").trim()
            if (id.isBlank()) return@forEach
            val name = map.optString("name").trim().ifBlank { id }
            val created = map.optString("created_at").take(19).replace('T', ' ')
            mapEntries += MapEntry(id, "$name${if (created.isBlank()) "" else "｜$created"}")
        }
        mapIds.clear()
        mapIds += mapEntries.map(MapEntry::id)
        updatingMapSelector = true
        mapSelector.adapter = ArrayAdapter(
            this, android.R.layout.simple_spinner_dropdown_item, mapEntries.map(MapEntry::label)
        )
        val index = mapEntries.indexOfFirst { it.id == previouslySelected }.takeIf { it >= 0 } ?: 0
        if (mapEntries.isNotEmpty()) {
            mapSelector.setSelection(index)
            mapIdInput.setText(mapEntries[index].id)
        }
        updatingMapSelector = false
    }

    private fun showMissionStep(message: String) {
        missionDetailText.text = message
        toast(message)
    }

    private fun renderMap() = mapSceneView.show(mapSnapshot, robotPoint, checkpointPoints)

    private fun renderSpeed(percent: Int) {
        speedText.text = String.format(
            Locale.getDefault(), "速度 %d%%｜上限 %.2f m/s、%.2f rad/s",
            percent, capabilities.maxLinearSpeed * speedRatio, capabilities.maxAngularSpeed * speedRatio
        )
    }

    private fun selectModule(module: Module) {
        selectedModule = module
        stopMotion(true)
        renderModule()
        findViewById<ScrollView>(R.id.main).smoothScrollTo(0, 0)
    }

    private fun renderModule() {
        val isDrive = selectedModule == Module.DRIVE
        val isMap = selectedModule == Module.MAP
        val isMission = selectedModule == Module.MISSION
        val isSettings = selectedModule == Module.SETTINGS
        connectionPanel.visibility = if (isSettings) View.VISIBLE else View.GONE
        mapPreviewPanel.visibility = if (isMap) View.VISIBLE else View.GONE
        navigationPanel.visibility = if (isMap) View.VISIBLE else View.GONE
        visionPanel.visibility = if (isDrive || isMission) View.VISIBLE else View.GONE
        alertPanel.visibility = if (isDrive) View.VISIBLE else View.GONE
        missionPanel.visibility = if (isMission) View.VISIBLE else View.GONE
        drivePanel.visibility = if (isDrive) View.VISIBLE else View.GONE
        telemetryPanel.visibility = if (isDrive || isSettings) View.VISIBLE else View.GONE
        driveModuleButton.isChecked = isDrive
        mapModuleButton.isChecked = isMap
        missionModuleButton.isChecked = isMission
        settingsModuleButton.isChecked = isSettings
    }

    private fun ui(block: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) block() else runOnUiThread(block)
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    private fun EditText.numberOrNull() = text.toString().trim().toDoubleOrNull()?.takeIf(Double::isFinite)

    private companion object {
        const val MOTION_INTERVAL_MS = 300L
        const val MAX_RENDERED_DETECTIONS = 8
    }
}
