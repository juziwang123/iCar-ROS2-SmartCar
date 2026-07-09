/**
 * 音乐小车 — 主页面（iOS / SwiftUI）
 *
 * 功能：
 *   1. 编舞列表（预设 + AI 生成的）
 *   2. AI 编舞生成面板
 *   3. 播放控制 + 进度显示
 *   4. 实时状态监控（WebSocket）
 */

import SwiftUI

struct MusicCarView: View {
    // ── 网络层 ────────────────────────────────
    @StateObject private var api = ApiClient.shared
    private let ws = StateSocket()
    private let aiClient = AIChoreographer()
    
    // ── UI 状态 ───────────────────────────────
    @State private var carIp: String = AppConstants.defaultCarIP
    @State private var carPort: String = "\(AppConstants.defaultCarPort)"
    @State private var showSettings: Bool = false
    @State private var showToast: Bool = false
    @State private var toastMessage: String = ""

    @State private var routines: [DanceRoutine] = DANCE_ROUTINES
    @State private var isPlaying: Bool = false
    @State private var progress: Double = 0
    @State private var currentName: String = ""
    @State private var currentMoveDesc: String = ""
    @State private var engineMode: String = "timeline"
    
    // 小车连接状态
    @State private var isConnected: Bool = false
    @State private var carModeLabel: String = "--"
    @State private var carSpeedLabel: String = "0.00 / 0.00"
    
    // AI 编舞表单
    @State private var aiSong: String = ""
    @State private var aiBpm: String = "120"
    @State private var aiDuration: String = "60"
    @State private var aiStyleIndex: Int = 0
    @State private var aiSpaceIndex: Int = 1
    @State private var aiExtra: String = ""
    @State private var aiGenerating: Bool = false
    @State private var aiResult: String = ""
    @State private var aiWarnings: [String] = []
    @State private var showAIDialog: Bool = false
    @State private var generatedRoutine: DanceRoutine? = nil
    
    // ── 引擎 ──────────────────────────────────
    @State private var danceEngine: DanceEngine? = nil
    @State private var beatEngine: BeatEngine? = nil
    
    var body: some View {
        NavigationView {
            List {
                // ── 状态卡片 ──────────────────────
                Section {
                    HStack {
                        Spacer()
                        VStack {
                            Text("控制模式")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text(carModeLabel)
                                .font(.headline)
                        }
                        Spacer()
                        Divider()
                        Spacer()
                        VStack {
                            Text("速度 (线/角)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text(carSpeedLabel)
                                .font(.headline)
                        }
                        Spacer()
                    }
                    .padding(.vertical, 8)
                    
                    HStack {
                        Circle()
                            .fill(isConnected ? Color.green : Color.red)
                            .frame(width: 10, height: 10)
                        Text(isConnected ? "已连接 \(carIp)" : "未连接")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    
                    Button {
                        ws.disconnect()
                        isConnected = false
                        connectToCar()
                    } label: {
                        Label("重新连接", systemImage: "arrow.clockwise")
                    }
                }
                
                // ── 播放进度 ──────────────────────
                if isPlaying {
                    Section("正在播放") {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(currentName)
                                .font(.headline)
                            Text(currentMoveDesc)
                                .font(.subheadline)
                                .foregroundColor(.blue)
                            ProgressView(value: progress, total: 100)
                            Text("\(Int(progress))%")
                                .font(.caption)
                        }
                        
                        Button(role: .destructive) {
                            stopDance()
                        } label: {
                            Label("停止表演", systemImage: "stop.fill")
                        }
                    }
                }
                
                // ── 编舞模式切换 ──────────────────
                Section("编舞模式") {
                    Picker("模式", selection: $engineMode) {
                        Text("时间轴模式").tag("timeline")
                        Text("节拍模式").tag("beat")
                    }
                    .pickerStyle(.segmented)
                }
                
                // ── 编舞列表 ──────────────────────
                Section("编舞列表") {
                    ForEach(routines) { routine in
                        Button {
                            playRoutine(routine)
                        } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(routine.name)
                                        .font(.headline)
                                        .foregroundColor(.primary)
                                    Text("BPM: \(routine.bpm) | \(routine.moves.count)个动作 | \(routine.duration / 1000)s")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    Text(routine.spaceRequired)
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                }
                                Spacer()
                                Image(systemName: "play.circle.fill")
                                    .font(.title2)
                                    .foregroundColor(.blue)
                            }
                        }
                    }
                }
                
                // ── AI 编舞面板 ────────────────────
                Section("🤖 AI 编舞生成") {
                    TextField("歌曲名称 *", text: $aiSong)
                    
                    HStack {
                        TextField("BPM", text: $aiBpm)
                            .keyboardType(.numberPad)
                        TextField("时长(秒)", text: $aiDuration)
                            .keyboardType(.numberPad)
                    }
                    
                    // 风格选择
                    VStack(alignment: .leading) {
                        Text("风格").font(.caption).foregroundColor(.secondary)
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(Array(STYLE_OPTIONS.enumerated()), id: \.offset) { index, style in
                                    Button {
                                        aiStyleIndex = index
                                    } label: {
                                        Text(style)
                                            .font(.caption)
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 6)
                                            .background(aiStyleIndex == index ? Color.blue : Color(.systemGray5))
                                            .foregroundColor(aiStyleIndex == index ? .white : .primary)
                                            .cornerRadius(16)
                                    }
                                }
                            }
                        }
                    }
                    
                    // 空间选择
                    VStack(alignment: .leading) {
                        Text("空间").font(.caption).foregroundColor(.secondary)
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(Array(SPACE_OPTIONS.enumerated()), id: \.offset) { index, space in
                                    Button {
                                        aiSpaceIndex = index
                                    } label: {
                                        Text(space)
                                            .font(.caption)
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 6)
                                            .background(aiSpaceIndex == index ? Color.blue : Color(.systemGray5))
                                            .foregroundColor(aiSpaceIndex == index ? .white : .primary)
                                            .cornerRadius(16)
                                    }
                                }
                            }
                        }
                    }
                    
                    TextField("额外要求（可选）", text: $aiExtra)
                    
                    // 生成按钮
                    Button {
                        generateAI()
                    } label: {
                        HStack {
                            if aiGenerating {
                                ProgressView()
                                    .scaleEffect(0.8)
                                Text("生成中...")
                            } else {
                                Text("✨ 生成编舞")
                            }
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(aiGenerating)
                    
                    // 生成结果
                    if !aiResult.isEmpty {
                        Text(aiResult)
                            .font(.subheadline)
                            .foregroundColor(aiResult.hasPrefix("✅") ? .green : .red)
                        
                        ForEach(aiWarnings, id: \.self) { warning in
                            Text("⚠️ \(warning)")
                                .font(.caption)
                                .foregroundColor(.orange)
                        }
                    }
                }
            }
            .navigationTitle("🎵 音乐小车")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button { showSettings = true } label: {
                        Image(systemName: "gearshape.fill")
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    HStack(spacing: 4) {
                        Circle()
                            .fill(isConnected ? Color.green : Color.red)
                            .frame(width: 8, height: 8)
                        Text(isConnected ? "在线" : "离线")
                            .font(.caption)
                    }
                }
            }
        }
        .onAppear {
            setupCallbacks()
            connectToCar()
        }
        .onDisappear {
            stopDance()
            ws.disconnect()
        }
        .sheet(isPresented: $showSettings) {
            NavigationView {
                Form {
                    Section("小车连接设置") {
                        TextField("IP 地址", text: $carIp)
                            .keyboardType(.decimalPad)
                        TextField("端口", text: $carPort)
                            .keyboardType(.numberPad)
                        Text("手机需先连接小车发出的 WiFi 热点")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                .navigationTitle("⚙️ 设置")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("保存并连接") {
                            showSettings = false
                            ws.disconnect()
                            isConnected = false
                            connectToCar()
                        }
                    }
                    ToolbarItem(placement: .cancellationAction) {
                        Button("取消") { showSettings = false }
                    }
                }
            }
        }
        .alert("AI 编舞完成", isPresented: $showAIDialog) {
            Button("立即表演") {
                if let routine = generatedRoutine {
                    playRoutine(routine)
                }
            }
            Button("稍后", role: .cancel) {}
        } message: {
            if let routine = generatedRoutine {
                Text("「\(routine.name)」\n\(routine.moves.count) 个动作\n\(routine.spaceRequired)")
            }
        }
    }
    
    // ── 回调设置 ──────────────────────────────
    
    private func setupCallbacks() {
        ws.onState = { state in
            carModeLabel = CTRL_MODE_NAMES[state.mode] ?? state.mode
            carSpeedLabel = String(format: "%.2f / %.2f", state.linear_x, state.angular_z)
        }
        ws.onConnected = { isConnected = true }
        ws.onDisconnected = { isConnected = false }
        ws.onError = { _ in }
    }
    
    private func connectToCar() {
        let port = Int(carPort) ?? 5000
        api.setServer(ip: carIp, port: port)
        aiClient.setServer(ip: carIp, port: port)
        ws.setServer(ip: carIp, port: port)
        setupCallbacks()
        
        Task {
            let pingOk = await api.ping()
            if pingOk {
                ws.connect()
            }
        }
    }
    
    // ── 播放控制 ──────────────────────────────
    
    private func playRoutine(_ routine: DanceRoutine) {
        Task {
            try? await api.postCmd(CmdRequest(type: MoveType.move, mode: CtrlMode.manual.rawValue))
            try? await api.postCmd(CmdRequest(type: MoveType.stop, active: false))
            
            currentName = routine.name
            progress = 0
            currentMoveDesc = ""
            
            let engine = DanceEngine(routine: routine, api: api)
            engine.onProgress = { elapsed, total in
                progress = min(100, Double(elapsed) / Double(total) * 100)
            }
            engine.onMove = { move, index in
                currentMoveDesc = "\(MOVE_TYPE_ICONS[move.type] ?? "") \(move.type) #\(index + 1)"
            }
            engine.onComplete = {
                isPlaying = false
                currentMoveDesc = "✅ 表演完成！"
            }
            engine.onError = { msg in
                aiWarnings.append(msg)
            }
            
            danceEngine = engine
            await engine.start()
            isPlaying = true
        }
    }
    
    private func stopDance() {
        danceEngine?.stop()
        beatEngine?.stop()
        isPlaying = false
        currentMoveDesc = ""
    }
    
    // ── AI 编舞 ────────────────────────────────
    
    private func generateAI() {
        guard !aiSong.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        
        Task {
            aiGenerating = true
            aiResult = ""
            aiWarnings = []
            
            let req = ChoreographRequest(
                song: aiSong,
                bpm: Int(aiBpm) ?? 120,
                durationMs: Int64(Int(aiDuration) ?? 60) * 1000,
                style: STYLE_OPTIONS[aiStyleIndex],
                space: SPACE_OPTIONS[aiSpaceIndex],
                extraRequirements: aiExtra.isEmpty ? nil : aiExtra
            )
            
            let resp = await aiClient.generate(req)
            aiGenerating = false
            
            if resp.ok, let routine = resp.routine {
                aiResult = "✅ 生成成功！\(routine.moves.count) 个动作"
                aiWarnings = resp.warnings ?? []
                routines.append(routine)
                generatedRoutine = routine
                showAIDialog = true
            } else {
                aiResult = "❌ 生成失败: \(resp.error ?? "未知错误")"
            }
        }
    }
}

#Preview {
    MusicCarView()
}
