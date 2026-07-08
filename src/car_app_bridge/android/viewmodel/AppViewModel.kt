// ViewModel —— 全局状态管理
// 所有 Fragment 共享同一个 ViewModel

package com.icar.app.viewmodel

import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import com.icar.app.network.ApiClient
import com.icar.app.network.StateWebSocket
import com.icar.app.network.model.CmdRequest
import com.icar.app.network.model.StateResponse
import kotlinx.coroutines.*

class AppViewModel : ViewModel() {
    // ── 实时状态 ────────────────────────
    private val _mode = MutableLiveData("manual")
    val mode: LiveData<String> = _mode

    private val _estop = MutableLiveData(false)
    val estop: LiveData<Boolean> = _estop

    private val _linearX = MutableLiveData(0.0)
    val linearX: LiveData<Double> = _linearX

    private val _angularZ = MutableLiveData(0.0)
    val angularZ: LiveData<Double> = _angularZ

    private val _runningNodes = MutableLiveData<List<String>>(emptyList())
    val runningNodes: LiveData<List<String>> = _runningNodes

    // ── WebSocket ────────────────────────
    private var ws: StateWebSocket? = null

    fun connectWebSocket() {
        ws = StateWebSocket(
            onState = { state ->
                _mode.postValue(state.mode)
                _estop.postValue(state.estop)
                _linearX.postValue(state.linearX)
                _angularZ.postValue(state.angularZ)
                _runningNodes.postValue(state.runningNodes)
            },
            onError = { /* 静默重连 */ }
        )
        ws?.connect()
    }

    override fun onCleared() {
        super.onCleared()
        ws?.disconnect()
    }

    // ── 控制操作 ──────────────────────────
    fun sendMove(linear: Double, angular: Double) {
        if (_estop.value == true) return
        val l = linear.coerceIn(-0.5, 0.5)
        val a = angular.coerceIn(-1.0, 1.0)
        viewModelScope.launch(Dispatchers.IO) {
            ApiClient.postCmd(CmdRequest("move", linear = l, angular = a))
        }
    }

    fun sendStop() {
        viewModelScope.launch(Dispatchers.IO) {
            ApiClient.postCmd(CmdRequest("stop"))
        }
    }

    fun sendMode(mode: String) {
        viewModelScope.launch(Dispatchers.IO) {
            ApiClient.postCmd(CmdRequest("mode", mode = mode))
        }
    }

    fun sendEstop(active: Boolean) {
        viewModelScope.launch(Dispatchers.IO) {
            ApiClient.postCmd(CmdRequest("estop", active = active))
        }
    }

    fun startProcess(function: String) {
        viewModelScope.launch(Dispatchers.IO) {
            ApiClient.startProcess(function)
        }
    }

    fun stopProcess(function: String) {
        viewModelScope.launch(Dispatchers.IO) {
            ApiClient.stopProcess(function)
        }
    }
}
