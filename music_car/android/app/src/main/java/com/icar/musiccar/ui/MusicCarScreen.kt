/**
 * 音乐小车 — 主页面（Android / Jetpack Compose）
 *
 * 功能：
 *   1. 编舞列表（预设 + AI 生成的）
 *   2. AI 编舞生成面板
 *   3. 播放控制 + 进度显示
 *   4. 实时状态监控（WebSocket）
 */

package com.icar.musiccar.ui

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.icar.musiccar.AppConstants
import com.icar.musiccar.data.DANCE_ROUTINES
import com.icar.musiccar.engine.BeatEngine
import com.icar.musiccar.engine.DanceEngine
import com.icar.musiccar.models.*
import com.icar.musiccar.network.AIChoreographer
import com.icar.musiccar.network.ApiClient
import com.icar.musiccar.network.CarState
import com.icar.musiccar.network.StateSocket
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MusicCarScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // ── 网络层 ────────────────────────────────
    val api = remember { ApiClient.getInstance() }
    val ws = remember { StateSocket() }
    val aiClient = remember { AIChoreographer() }

    // ── UI 状态 ───────────────────────────────
    var carIp by remember { mutableStateOf(AppConstants.DEFAULT_CAR_IP) }
    var carPort by remember { mutableStateOf(AppConstants.DEFAULT_CAR_PORT.toString()) }
    var showSettings by remember { mutableStateOf(false) }

    var routines by remember { mutableStateOf(DANCE_ROUTINES.toMutableList()) }
    var isPlaying by remember { mutableStateOf(false) }
    var progress by remember { mutableFloatStateOf(0f) }
    var currentName by remember { mutableStateOf("") }
    var currentMoveDesc by remember { mutableStateOf("") }
    var engineMode by remember { mutableStateOf("timeline") }

    // 小车连接状态
    var isConnected by remember { mutableStateOf(false) }
    var carModeLabel by remember { mutableStateOf("--") }
    var carSpeedLabel by remember { mutableStateOf("0.00 / 0.00") }

    // AI 编舞表单
    var aiSong by remember { mutableStateOf("") }
    var aiBpm by remember { mutableStateOf("120") }
    var aiDuration by remember { mutableStateOf("60") }
    var aiStyleIndex by remember { mutableIntStateOf(0) }
    var aiSpaceIndex by remember { mutableIntStateOf(1) }
    var aiExtra by remember { mutableStateOf("") }
    var aiGenerating by remember { mutableStateOf(false) }
    var aiResult by remember { mutableStateOf("") }
    var aiWarnings by remember { mutableStateOf(emptyList<String>()) }
    var showAIDialog by remember { mutableStateOf(false) }

    // ── 引擎 ──────────────────────────────────
    var danceEngine by remember { mutableStateOf<DanceEngine?>(null) }
    var beatEngine by remember { mutableStateOf<BeatEngine?>(null) }

    // ── 初始化 ──────────────────────────────
    fun connectToCar() {
        api.setServer(carIp, carPort.toIntOrNull() ?: 5000)
        aiClient.setServer(carIp, carPort.toIntOrNull() ?: 5000)
        ws.setServer(carIp, carPort.toIntOrNull() ?: 5000)

        ws.onState = { state ->
            carModeLabel = CTRL_MODE_NAMES[state.mode] ?: state.mode
            carSpeedLabel = "${String.format("%.2f", state.linear_x)} / ${String.format("%.2f", state.angular_z)}"
        }
        ws.onConnected = { isConnected = true }
        ws.onDisconnected = { isConnected = false }
        ws.onError = { /* 静默 */ }

        scope.launch {
            val pingOk = api.ping()
            if (pingOk) {
                ws.connect()
                Toast.makeText(context, "✅ 已连接到小车", Toast.LENGTH_SHORT).show()
            } else {
                isConnected = false
                Toast.makeText(context, "⚠️ 无法连接 $carIp:$carPort，请检查网络", Toast.LENGTH_SHORT).show()
            }
        }
    }

    LaunchedEffect(Unit) {
        connectToCar()
    }

    // ── 播放控制 ──────────────────────────────

    fun playRoutine(routine: DanceRoutine) {
        scope.launch {
            api.postCmd(CmdRequest(type = MoveTypes.MOVE, mode = "manual"))
            api.postCmd(CmdRequest(type = MoveTypes.STOP, active = false))

            currentName = routine.name
            progress = 0f
            currentMoveDesc = ""

            val engine = DanceEngine(routine, api)
            engine.onProgress = { elapsed, total ->
                progress = minOf(100f, (elapsed.toFloat() / total.toFloat()) * 100f)
            }
            engine.onMove = { move, index ->
                currentMoveDesc = "${MOVE_TYPE_ICONS[move.type]} ${move.type} #${index + 1}"
            }
            engine.onComplete = {
                isPlaying = false
                currentMoveDesc = "✅ 表演完成！"
            }
            engine.onError = { msg ->
                aiWarnings = aiWarnings + msg
            }

            danceEngine = engine
            engine.start()
            isPlaying = true
        }
    }

    fun stopDance() {
        danceEngine?.stop()
        beatEngine?.stop()
        isPlaying = false
        currentMoveDesc = ""
    }

    // ── AI 编舞 ────────────────────────────────

    fun generateAI() {
        if (aiSong.isBlank()) {
            Toast.makeText(context, "请输入歌曲名称", Toast.LENGTH_SHORT).show()
            return
        }

        scope.launch {
            aiGenerating = true
            aiResult = ""
            aiWarnings = emptyList()

            val req = ChoreographRequest(
                song = aiSong,
                bpm = aiBpm.toIntOrNull() ?: 120,
                durationMs = (aiDuration.toIntOrNull() ?: 60) * 1000L,
                style = STYLE_OPTIONS[aiStyleIndex],
                space = SPACE_OPTIONS[aiSpaceIndex],
                extraRequirements = aiExtra
            )

            val resp = aiClient.generate(req)
            aiGenerating = false

            if (resp.ok && resp.routine != null) {
                aiResult = "✅ 生成成功！${resp.routine.moves.size} 个动作"
                aiWarnings = resp.warnings ?: emptyList()
                routines = routines + resp.routine
                showAIDialog = true
            } else {
                aiResult = "❌ 生成失败: ${resp.error ?: "未知错误"}"
            }
        }
    }

    // ── AI 结果弹窗 ───────────────────────
    if (showAIDialog) {
        val lastRoutine = routines.lastOrNull()
        if (lastRoutine != null) {
            AlertDialog(
                onDismissRequest = { showAIDialog = false },
                title = { Text("AI 编舞完成") },
                text = {
                    Column {
                        Text("「${lastRoutine.name}」")
                        Text("${lastRoutine.moves.size} 个动作")
                        Text(lastRoutine.spaceRequired)
                    }
                },
                confirmButton = {
                    TextButton(onClick = {
                        showAIDialog = false
                        playRoutine(lastRoutine)
                    }) { Text("立即表演") }
                },
                dismissButton = {
                    TextButton(onClick = { showAIDialog = false }) { Text("稍后") }
                }
            )
        }
    }

    // ── 设置弹窗 ───────────────────────
    if (showSettings) {
        AlertDialog(
            onDismissRequest = { showSettings = false },
            title = { Text("⚙️ 小车连接设置") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedTextField(
                        value = carIp,
                        onValueChange = { carIp = it },
                        label = { Text("小车 IP 地址") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = carPort,
                        onValueChange = { carPort = it },
                        label = { Text("端口") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Text(
                        "手机需先连接小车发出的 WiFi 热点",
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    showSettings = false
                    ws.disconnect()
                    isConnected = false
                    connectToCar()
                }) { Text("保存并连接") }
            },
            dismissButton = {
                TextButton(onClick = { showSettings = false }) { Text("取消") }
            }
        )
    }

    // ── UI 构建 ────────────────────────────────

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("🎵 音乐小车", fontWeight = FontWeight.Bold) },
                actions = {
                    // 连接状态指示灯
                    Surface(
                        shape = MaterialTheme.shapes.small,
                        color = if (isConnected) Color(0xFF4CAF50) else Color(0xFFFF5722),
                        modifier = Modifier.padding(end = 4.dp)
                    ) {
                        Text(
                            text = if (isConnected) "● 已连接" else "● 未连接",
                            color = Color.White,
                            fontSize = 12.sp,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                    // 设置按钮
                    IconButton(onClick = { showSettings = true }) {
                        Icon(Icons.Default.Settings, contentDescription = "设置", tint = Color.White)
                    }
                }
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // ── 状态卡片 ──────────────────────
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceEvenly
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text("控制模式", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(carModeLabel, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                            }
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text("速度 (线/角)", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(carSpeedLabel, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                            }
                        }
                        Spacer(modifier = Modifier.height(8.dp))
                        // 重连按钮
                        OutlinedButton(
                            onClick = {
                                ws.disconnect()
                                isConnected = false
                                connectToCar()
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(6.dp))
                            Text("重新连接 $carIp", fontSize = 13.sp)
                        }
                    }
                }
            }

            // ── 播放进度 ──────────────────────
            if (isPlaying) {
                item {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            Text(currentName, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                            Text(currentMoveDesc, fontSize = 14.sp, color = MaterialTheme.colorScheme.primary)
                            Spacer(modifier = Modifier.height(8.dp))
                            LinearProgressIndicator(
                                progress = { progress / 100f },
                                modifier = Modifier.fillMaxWidth()
                            )
                            Text("${progress.toInt()}%", fontSize = 12.sp)
                        }
                    }
                    // 停止按钮
                    Button(
                        onClick = { stopDance() },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE53935))
                    ) {
                        Icon(Icons.Default.Stop, contentDescription = null)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("停止表演")
                    }
                }
            }

            // ── 编舞模式切换 ──────────────────
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    FilterChip(
                        selected = engineMode == "timeline",
                        onClick = { engineMode = "timeline" },
                        label = { Text("时间轴模式") }
                    )
                    FilterChip(
                        selected = engineMode == "beat",
                        onClick = { engineMode = "beat" },
                        label = { Text("节拍模式") }
                    )
                }
            }

            // ── 编舞列表 ──────────────────────
            items(routines) { routine ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    onClick = { playRoutine(routine) }
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(routine.name, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                            Text("BPM: ${routine.bpm} | ${routine.moves.size}个动作 | ${routine.duration / 1000}s",
                                fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(routine.spaceRequired, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Icon(Icons.Default.PlayArrow, contentDescription = "播放",
                            tint = MaterialTheme.colorScheme.primary)
                    }
                }
            }

            // ── AI 编舞面板 ────────────────────
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text("🤖 AI 编舞生成", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                        Spacer(modifier = Modifier.height(8.dp))

                        OutlinedTextField(
                            value = aiSong,
                            onValueChange = { aiSong = it },
                            label = { Text("歌曲名称 *") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true
                        )
                        Spacer(modifier = Modifier.height(8.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            OutlinedTextField(
                                value = aiBpm,
                                onValueChange = { aiBpm = it },
                                label = { Text("BPM") },
                                modifier = Modifier.weight(1f),
                                singleLine = true
                            )
                            OutlinedTextField(
                                value = aiDuration,
                                onValueChange = { aiDuration = it },
                                label = { Text("时长(秒)") },
                                modifier = Modifier.weight(1f),
                                singleLine = true
                            )
                        }
                        Spacer(modifier = Modifier.height(8.dp))

                        // 风格选择
                        Text("风格", fontSize = 12.sp)
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            STYLE_OPTIONS.forEachIndexed { index, style ->
                                FilterChip(
                                    selected = aiStyleIndex == index,
                                    onClick = { aiStyleIndex = index },
                                    label = { Text(style, fontSize = 11.sp) }
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(8.dp))

                        // 空间选择
                        Text("空间", fontSize = 12.sp)
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            SPACE_OPTIONS.forEachIndexed { index, space ->
                                FilterChip(
                                    selected = aiSpaceIndex == index,
                                    onClick = { aiSpaceIndex = index },
                                    label = { Text(space, fontSize = 11.sp) }
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(8.dp))

                        OutlinedTextField(
                            value = aiExtra,
                            onValueChange = { aiExtra = it },
                            label = { Text("额外要求（可选）") },
                            modifier = Modifier.fillMaxWidth(),
                            maxLines = 2
                        )

                        Spacer(modifier = Modifier.height(12.dp))

                        // 生成按钮
                        Button(
                            onClick = { generateAI() },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = !aiGenerating
                        ) {
                            if (aiGenerating) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(18.dp),
                                    strokeWidth = 2.dp,
                                    color = Color.White
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text("生成中...")
                            } else {
                                Text("✨ 生成编舞")
                            }
                        }

                        // 生成结果
                        if (aiResult.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(aiResult, fontSize = 14.sp,
                                color = if (aiResult.startsWith("✅")) Color(0xFF4CAF50) else Color(0xFFE53935))
                            aiWarnings.forEach { warn ->
                                Text("⚠️ $warn", fontSize = 12.sp, color = Color(0xFFFF9800))
                            }
                        }
                    }
                }
            }

            // 底部间距
            item { Spacer(modifier = Modifier.height(16.dp)) }
        }
    }
}
